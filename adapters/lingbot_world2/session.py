"""Persistent LingBot-World v2 causal-fast session: the KV cache survives across agent steps.

`LingBotSession.reset(image, prompt, seed)` starts a rollout; each `step(keys)`
generates the next 4-latent chunks under per-pixel-frame keys and returns only
the new frames. The DiT self-attention KV cache (LingBot's only memory), the
cross-attention cache, the noise generator, the absolute camera track and the
VAE decoder's causal cache all live across steps, so a closed-loop rollout is
the same computation as one long upstream rollout, chunked at agent decisions.

The sampling loop re-implements upstream `WanI2VCausal._generate_causal_fast`
(Robbyant/lingbot-world-v2 @ 1895d300, wan/image2video.py, CC BY-NC-SA 4.0)
split into reset/step; it imports the upstream modules at runtime and copies
no files. Differences from upstream, all deliberate:
  * noise is drawn per chunk from the seeded generator instead of all up front
    (same distribution, different sample for a given seed);
  * camera translations use a fixed scale (see normalise_translation), because
    upstream divides by the max norm of the whole sequence, which a closed
    loop does not know in advance;
  * the image conditioning `y` is encoded once for a fixed horizon (it is the
    input image followed by zeros, so it does not depend on the actions);
  * opt-in streamed `y` (stream_encode=True, --lingbot-fast-y, off by default): `y` is encoded
    only as far as the rollout has got, keeping the VAE encoder's causal cache across steps,
    instead of for the whole horizon at reset (same encoder calls on the same inputs);
  * opt-in re-anchoring (reset(reanchor=True), off by default): when the commanded
    camera track returns to the start pose, that latent of `y` is set to the input
    image again (ReturnDetector, _anchor_y);
  * opt-in noisy KV writes (kv_noise=KVNoise, --lingbot-kv-noise, off by default): the
    KV-write forward of a generated chunk sees add_noise(x0, eps, t_kv) at t_kv instead of
    x0 at t=0, eps from its own generator (kv_noise.py); chunks with an image latent stay clean.
  * opt-in early-step self-guidance (stg=stg.SkipGuidance, --lingbot-stg, off by default):
    one extra forward with chosen blocks' self-attention skipped on the first denoising
    step(s) of each chunk, combined with the full prediction before the x0 conversion.
  * opt-in sink key scaling (sink_scale=SinkScaleConfig, --lingbot-sink-key-scale, off by
    default): the cached keys of the attention-sink tokens are scaled on a chunk's denoising
    forwards and copied back before its KV write (_sink_scaled, sink_scale.py).
  * opt-in pose-indexed memory (pose_mem=PoseMemoryConfig, --lingbot-pose-memory, off by default):
    before a chunk whose commanded view an evicted, earlier-left chunk covers better than the rolling window does
    (PoseMemory.decide, also replayed by `python -m pwa.pose_mem_plan`), that chunk's stored x0 is recomputed by
    one clean forward into the sink slots after the anchor latents; the original sink is copied back when nothing
    matches, and on an exception (_pose_mem_before, _mem_recompute, pose_memory.py).
  * opt-in split sink key scaling (split_sink=SplitSinkConfig, --lingbot-split-sink, off by default):
    once the sink latents are written, a camera-rotation-compensated foreground mask splits sink tokens into
    foreground (fg_scale) and static background (bg_scale) during active chunks' denoising forwards, restoring
    the pristine sink keys before each clean KV write (_split_sink_scaled, split_sink.py).

Everything above the LingBotSession class is numpy-only and unit-tested
(tests/test_lingbot_session.py); torch is imported lazily.
"""
from __future__ import annotations

import contextlib
import math
import os
import re
import time

import numpy as np

from adapters.lingbot_world2 import fast_start as FS
from adapters.lingbot_world2 import pose_memory as PM
from adapters.lingbot_world2 import poses as P
from adapters.lingbot_world2 import sink_scale as SK
from adapters.lingbot_world2 import split_sink as SS
from adapters.lingbot_world2 import watchdog as W

CHUNK = P.LATENT_CHUNK          # latent frames per causal chunk
FRAMES_PER_CHUNK = 4 * CHUNK    # pixel frames per chunk after the first latent
ROPE_LATENTS = 1024             # WanModelFast rope_params(1024, ...) table length
# One latent step of straight single-key motion: 4 pixel frames x unit translation.
TRANS_SCALE = 4.0
TIMESTEPS_INDEX = (0, 250, 500, 750)  # WanI2VCausal.generate() default

_CHUNK_RE = re.compile(r"^(?P<task>.+)_chunk_(?P<idx>\d+)$")


# ---------------------------------------------------------------- pure logic

def chunks_for(num_frames: int) -> int:
    """Latent chunks to generate for a harness request of num_frames (33 -> 2)."""
    return max(1, int(math.floor((int(num_frames) - 1) / FRAMES_PER_CHUNK + 0.5)))


def to_uint8_host(x):
    """Decoded VAE output slice -> uint8 frames on the host, the same ops in the same order as the
    full-video post-processing this replaces: .float().clamp(-1, 1), then ((x + 1) * 127.5).round()
    cast to uint8, then .cpu(). All elementwise, so converting slice by slice gives identical frames."""
    import torch  # noqa: PLC0415
    return ((x.float().clamp(-1, 1) + 1) * 127.5).round().to(torch.uint8).cpu()


def decode_slices(decoder, x, feat_cache, skip: int = 0):
    """Run the causal VAE decoder one latent at a time over x [1, C, L, h, w] (latent 0 of a rollout gives
    1 frame, every later latent 4), as WanVAE_.decode does, and return uint8 host frames [1, 3, F, H, W]
    with the first `skip` frames dropped. Each slice is converted and moved off the device as soon as it is
    decoded, so no full-length video tensor is built on the device. A progress mark per latent."""
    import torch  # noqa: PLC0415
    outs, seen = [], 0
    for i in range(x.shape[2]):
        out = decoder(x[:, :, i:i + 1], feat_cache=feat_cache, feat_idx=[0])
        n = out.shape[2]
        if seen + n > skip:
            with torch.autocast("cuda", enabled=False):
                outs.append(to_uint8_host(out[:, :, max(0, skip - seen):]))
        seen += n
        del out
        W.progress()
    return torch.cat(outs, 2)


def keys_needed(n_chunks: int, first: bool) -> int:
    """Pixel-frame deltas consumed by a step: 16n-4 on the first step (latent 0
    is the input frame itself), 16n on a continuation."""
    return FRAMES_PER_CHUNK * n_chunks - (4 if first else 0)


def frames_returned(n_chunks: int, first: bool) -> int:
    """Frames a step returns. First: 16n-3, starting with the input frame.
    Continuation: the previous last frame then 16n new ones; the harness drops
    the first frame of every chunk after the first, so stitching leaves no gap."""
    return keys_needed(n_chunks, first) + 1


def fit_keys(keys: list[str], n: int) -> list[str]:
    """First n keys, padded by repeating the last key ('none' if empty)."""
    keys = list(keys[:n])
    return keys + [keys[-1] if keys else "none"] * (n - len(keys))


def parse_chunk_name(name: str):
    """'GC005_chunk_03' -> ('GC005', 3); anything else (e.g. 'GC005_full') -> None."""
    m = _CHUNK_RE.match(name or "")
    return (m["task"], int(m["idx"])) if m else None


def is_continuation(prev, parsed) -> bool:
    """True when `parsed` is the chunk right after `prev` of the same task."""
    return bool(prev and parsed and parsed[1] > 1 and prev == (parsed[0], parsed[1] - 1))


def se3_inverse(T: np.ndarray) -> np.ndarray:
    R, t = T[..., :3, :3], T[..., :3, 3:]
    out = np.zeros_like(T)
    out[..., :3, :3] = np.swapaxes(R, -1, -2)
    out[..., :3, 3:] = -np.swapaxes(R, -1, -2) @ t
    out[..., 3, 3] = 1.0
    return out


def relative_latent_poses(latent_c2ws: np.ndarray, prev: np.ndarray | None = None) -> np.ndarray:
    """Frame-to-frame relative poses, as upstream compute_relative_poses(framewise=True)
    but without normalisation: rel[i] = inv(c2w[i-1]) @ c2w[i]; the first latent of
    the rollout (prev is None) is the identity, otherwise it is relative to prev."""
    lat = np.asarray(latent_c2ws, dtype=np.float64)
    if prev is None:
        full = lat
        head = [np.eye(4)]
    else:
        full = np.concatenate([np.asarray(prev, dtype=np.float64)[None], lat])
        head = []
    rel = se3_inverse(full[:-1]) @ full[1:]
    return np.concatenate([np.stack(head), rel]) if head else rel


def normalise_translation(rel: np.ndarray, scale: float = TRANS_SCALE) -> np.ndarray:
    """Fixed-scale stand-in for upstream's divide-by-max-norm.

    Upstream scales translations so the largest per-latent step of the whole
    sequence has norm 1. In closed loop the future is unknown, so we divide by
    TRANS_SCALE = 4 (one latent of straight single-key motion with poses.py's unit
    per-pixel-frame step) and clip norms above 1 (e.g. 'w+d' diagonals), which keeps
    every input inside the range upstream produces. For any sequence whose fastest
    latent is straight single-key motion this equals upstream exactly."""
    out = np.array(rel, dtype=np.float64, copy=True)
    t = out[:, :3, 3] / scale
    n = np.linalg.norm(t, axis=-1, keepdims=True)
    out[:, :3, 3] = np.where(n > 1.0, t / np.maximum(n, 1e-12), t)
    return out


def is_pure_turn(keys) -> bool:
    """True when every key is the same single rotation key (j/l/i/k): --lingbot-gc-ease-turns eases only these."""
    return bool(keys) and len(set(keys)) == 1 and keys[0] in ("j", "l", "i", "k")


class PoseTrack:
    """Absolute camera track across steps. advance(keys) -> normalised relative
    poses for the new latent frames (one per 4 pixel frames).

    yaw_gain (left, right), --lingbot-yaw-gain, off (None) by default: the relative poses returned
    (what the model gets) and `model_latents` turn j / l by the gain, while `latents` (what ReturnDetector
    reads) follow the intended track without it, kept separately in `intended_last`. Off, both tracks are one."""

    def __init__(self, translation_gain: float = 1.0, yaw_gain: tuple[float, float] | None = None):
        self.translation_gain = translation_gain
        self.yaw_gain = yaw_gain     # set per call by run.py with --lingbot-yaw-gain
        self.last = np.eye(4)        # absolute pose of the latest pixel frame (model track)
        self.intended_last = np.eye(4)  # same, intended track (no yaw gain)
        self.prev_latent = None      # absolute pose of the latest latent frame (model track)
        self.latents = None          # intended absolute poses of the last advance()'s latents (one per rel)
        self.model_latents = None    # model-track absolute poses of the last advance()'s latents (one per rel)

    def advance(self, keys: list[str], ease_turns: bool = False) -> np.ndarray:
        first = self.prev_latent is None
        if (len(keys) + (4 if first else 0)) % FRAMES_PER_CHUNK:
            raise ValueError(f"{len(keys)} keys do not fill whole chunks (first={first})")
        # Raised-cosine speed: half speed at edges, 1.5x mid-chunk; sum preserves total angle.
        scales = (1 - 0.5 * np.cos(2 * np.pi * (np.arange(len(keys)) + 0.5) / len(keys))
                  if ease_turns and is_pure_turn(keys) else None)
        gain = self.yaw_gain
        cur, want = self.last, (self.intended_last if gain else None)
        lat = [cur] if first else []  # latent 0 is pixel frame 0
        ilat = [want] if first else []
        for i, k in enumerate(keys, 1):
            s = 1.0 if scales is None else float(scales[i - 1])
            if gain:
                want = want @ P.key_delta(k, self.translation_gain, s)
                cur = cur @ P.key_delta(k, self.translation_gain, s, yaw_gain=gain)
            else:
                cur = cur @ P.key_delta(k, self.translation_gain, s)
            if i % 4 == 0:
                lat.append(cur)
                ilat.append(want)
        model_lats = np.stack(lat)
        rel = relative_latent_poses(model_lats, self.prev_latent)
        self.last, self.prev_latent, self.model_latents = cur, lat[-1], model_lats
        self.intended_last, self.latents = (want, np.stack(ilat)) if gain else (cur, model_lats)
        return normalise_translation(rel)


def pose_offset(c2w: np.ndarray) -> tuple[float, float]:
    """(rotation in degrees, translation norm in key units) of an absolute pose from the start pose."""
    cos = (np.trace(c2w[:3, :3]) - 1.0) / 2.0
    return math.degrees(math.acos(min(1.0, max(-1.0, cos)))), float(np.linalg.norm(c2w[:3, 3]))


class ReturnDetector:
    """Finds the latents where the commanded camera track comes back to the start pose
    (--lingbot-reanchor). A return counts only after the track has left: at least
    leave_deg of rotation or leave_trans key units of translation away. Each visit
    (a run of latents within tol_deg and tol_trans of the start) yields one index, the
    latent closest to the start, so a camera resting at the start is anchored once."""

    def __init__(self, tol_deg: float | None = None, tol_trans: float | None = None,
                 leave_deg: float = 20.0, leave_trans: float = 8.0):
        self.tol_deg = float(os.environ.get("LINGBOT_REANCHOR_DEG", "6")) if tol_deg is None else tol_deg
        self.tol_trans = float(os.environ.get("LINGBOT_REANCHOR_TRANS", "2")) if tol_trans is None else tol_trans
        self.leave_deg, self.leave_trans = leave_deg, leave_trans
        self.away = False

    def update(self, latent_c2ws: np.ndarray) -> list[int]:
        """Indices into latent_c2ws (one step's absolute latent poses) to re-anchor."""
        out, run = [], []
        for i, c2w in enumerate(latent_c2ws):
            deg, trans = pose_offset(c2w)
            if self.away and deg <= self.tol_deg and trans <= self.tol_trans:
                run.append((deg + trans, i))
                continue
            if run:
                out.append(min(run)[1])
                run, self.away = [], False
            if deg >= self.leave_deg or trans >= self.leave_trans:
                self.away = True
        if run:
            out.append(min(run)[1])
            self.away = False
        return out


def reanchor_task(name: str) -> bool:
    """True when --lingbot-reanchor applies to this call name. Default: GC tasks only.
    The Out-of-sight rubric scores a returned view that equals the first frame as a
    reset (level 1), so those tasks are excluded unless LINGBOT_REANCHOR_TASKS says so."""
    return re.match(os.environ.get("LINGBOT_REANCHOR_TASKS", "GC"), name or "") is not None


def horizon_latents(horizon_frames: int) -> int:
    """Latents to pre-encode `y` for: enough for horizon_frames, chunk-aligned, plus
    one chunk of slack, capped by the RoPE table."""
    lat = (max(int(horizon_frames), 1) - 1) // 4 + 1
    lat = math.ceil(lat / CHUNK) * CHUNK + CHUNK
    return min(lat, ROPE_LATENTS)


# ------------------------------------------------------------- torch session

def encode_prompt(pipe, prompt: str, disk=None):
    """T5 context for `prompt`, filling upstream's pipe._t5_cache (same key and device-resident
    value as upstream), through the optional disk cache (fast_start.EmbeddingCache). Prints one
    timing line. Returns the context."""
    import torch  # noqa: PLC0415

    def compute(p):
        if not pipe.t5_cpu:
            pipe.text_encoder.model.to(pipe.device)
            return pipe.text_encoder([p], pipe.device)
        return [t.to(pipe.device) for t in pipe.text_encoder([p], torch.device("cpu"))]

    # A start line, so a stall here shows in the log as a start with no timing line after it.
    print(f"[lingbot] reset: text encode start (t5={'gpu' if not pipe.t5_cpu else 'cpu'}, "
          f"torch threads={torch.get_num_threads()}, disk cache={'on' if disk is not None else 'off'})", flush=True)
    t0 = time.time()
    ctx, source = FS.resolve_context(prompt, pipe._t5_cache, compute, disk,
                                     to_device=lambda c: [t.to(pipe.device) for t in c])
    torch.cuda.synchronize()
    FS.log("reset.text_encode", time.time() - t0,
           f"(source={source}, t5={'gpu' if not pipe.t5_cpu else 'cpu'}"
           + (f", disk hits={disk.hits} misses={disk.misses}" if disk is not None else "") + ")")
    return ctx


class LingBotSession:
    """Stateful wrapper around a loaded wan.WanI2VCausal (causal_fast)."""

    def __init__(self, pipe, max_area: int, shift: float, horizon_frames: int = 961,
                 stream_decode: bool | None = None, stream_encode: bool = False, t5_cache=None, weight_mod=None,
                 cond_sched=None, kv_noise=None, stg=None, sink_scale=None, pose_mem=None, split_sink=None):
        self.pipe = pipe
        self.max_area = max_area
        self.shift = shift
        self.horizon_frames = horizon_frames
        if stream_decode is None:
            stream_decode = os.environ.get("LINGBOT_STREAM_DECODE", "1") != "0"
        self.stream_decode = stream_decode
        self.stream_encode = bool(stream_encode)  # --lingbot-fast-y
        self.t5_cache = t5_cache                  # fast_start.EmbeddingCache or None
        self._timing = False                      # timing lines for the first step after reset
        self.chunk_id = 0
        self.started = False
        self.reanchor_events = 0  # _anchor_y calls over the session's life (flag_stats reads deltas)
        # --lingbot-weight-mod: steps with any modulated latent chunk, and modulated latent chunks (flag_stats reads deltas)
        self.weight_mod, self.weight_mod_steps, self.weight_mod_chunks, self.third_person = weight_mod, 0, 0, False
        self.cond_sched, self.cond_sched_chunks, self.cond_sched_calls = cond_sched, 0, 0
        self.kv_noise, self.kv_noise_chunks = kv_noise, 0  # --lingbot-kv-noise (flag_stats reads deltas)
        # --lingbot-stg: an stg.SkipGuidance; latent chunks with a guided step, and extra skip forwards (deltas)
        self.stg, self.stg_chunks, self.stg_calls = stg, 0, 0
        # --lingbot-sink-key-scale: config (None = off), whether this rollout's task matched, chunks scaled
        self.sink_scale, self.sink_scale_on, self.sink_scaled_chunks = sink_scale, False, 0
        # --lingbot-pose-memory: config (None = off), whether this rollout's task matched (set by the engine after
        # reset), and counters over the session's life (flag_stats reads deltas; pm_peak_bytes is per rollout)
        self.pose_mem, self.pose_mem_on = pose_mem, False
        self.pose_mem_name = ""   # call name of the rollout (set by the engine with the flag; picks `auto`)
        self.pm_stored = self.pm_installs = self.pm_restores = self.pm_latents = self.pm_forwards = 0
        self.pm_chunks = self.pm_evicted = self.pm_retimes = 0
        # --lingbot-split-sink: config (None = off), whether this rollout's task matched, counters (deltas)
        self.split_sink, self.split_sink_on = split_sink, False
        self.split_sink_chunks = self.split_sink_fg_tokens = 0
        self._free()

    def _free(self):
        self.noise_mean = None
        self.kv = self.cross = self.y = None
        self._feat_map = None
        self._enc_feat_map = None
        self._all_lat = []
        self._last_frame = None
        self._anchor = None
        self._anchored = set()  # latents re-anchored to the input image (kv_noise keeps their chunk clean)
        self.detector = None
        self.pmem = None          # --lingbot-pose-memory bank, cleared on every reset
        self._pm_snapshot = None  # host copy of the original sink slots [anchor, anchor + latents) of every block
        self._pm_installed = ()   # (chunk id, rope latent) pairs whose recomputed K/V sit in those slots
        self.pm_peak_bytes = 0
        self._ss_latents = []     # --lingbot-split-sink host x0 slices for the opening sink latents
        self._ss_poses = []       # --lingbot-split-sink host c2w poses for the opening sink latents
        self._ss_scales = None    # built per-token sink scale vector [1, n_tokens, 1, 1] for this rollout

    # -- reset -------------------------------------------------------------
    def reset(self, image, prompt: str, seed: int, horizon_frames: int | None = None,
              reanchor: bool = False, third_person: bool = False,
              noise_mean: bool = False):
        import torch  # noqa: PLC0415
        import torchvision.transforms.functional as TF  # noqa: PLC0415
        from wan.utils.cam_utils import get_Ks_transformed  # noqa: PLC0415

        pipe = self.pipe
        dev = pipe.device
        t_reset = time.time()
        self._free()
        if noise_mean:
            from .noise_mean import CoupledMean  # noqa: PLC0415
            self.noise_mean = CoupledMean()
        torch.cuda.empty_cache()

        img = TF.to_tensor(image).sub_(0.5).div_(0.5).to(dev)
        h, w = img.shape[1:]
        ar = h / w
        vs, ps = pipe.vae_stride, pipe.patch_size
        self.lat_h = round(np.sqrt(self.max_area * ar) // vs[1] // ps[1] * ps[1])
        self.lat_w = round(np.sqrt(self.max_area / ar) // vs[2] // ps[2] * ps[2])
        self.h, self.w = self.lat_h * vs[1], self.lat_w * vs[2]
        self.max_seq_len = CHUNK * self.lat_h * self.lat_w // (ps[1] * ps[2])  # sp_size 1
        self.frame_seqlen = self.lat_h * self.lat_w // 4

        pipe.scheduler.set_timesteps(pipe.num_train_timesteps, shift=self.shift)
        self.timesteps = pipe.scheduler.timesteps[list(TIMESTEPS_INDEX)]
        self.context = encode_prompt(pipe, prompt, self.t5_cache)
        self.prompt = prompt

        Ks = torch.tensor([P.INTRINSICS_480P], dtype=torch.float32)
        Ks = get_Ks_transformed(Ks, height_org=480, width_org=832, height_resize=self.h,
                                width_resize=self.w, height_final=self.h, width_final=self.w)
        self.Ks = Ks[0].view(1, 4).to(dev)

        self._img = torch.nn.functional.interpolate(
            img[None].cpu(), size=(self.h, self.w), mode="bicubic").transpose(0, 1)  # [3,1,h,w]
        if self.stream_encode:
            from wan.modules.vae2_1 import count_conv3d  # noqa: PLC0415
            self._enc_feat_map = [None] * count_conv3d(pipe.vae.model.encoder)  # y grows in step()
        else:
            print("[lingbot] reset: y encode start", flush=True)
            t0 = time.time()
            self._encode_y(horizon_latents(horizon_frames or self.horizon_frames))
            torch.cuda.synchronize()
            FS.log("reset.y_encode", time.time() - t0, f"({self.y.shape[1]} latents, full horizon)")

        cfg = pipe.model.config
        head_dim = cfg.dim // cfg.num_heads
        if pipe.local_attn_size > -1:
            self.kv_size = self.frame_seqlen * pipe.local_attn_size
        else:
            self.kv_size = self.frame_seqlen * ROPE_LATENTS
        self.kv = pipe._initialize_self_kv_cache(
            num_layers=cfg.num_layers, shape=[1, self.kv_size, cfg.num_heads, head_dim],
            dtype=pipe.pipe_dtype, device=dev)
        self.cross = pipe._initialize_crossattn_cache(
            num_layers=cfg.num_layers, shape=[1, 512, cfg.num_heads, head_dim],
            dtype=pipe.pipe_dtype, device=dev)
        self.cross_init = False

        self.gen = torch.Generator(device=dev)
        self.gen.manual_seed(int(seed))
        self.track = PoseTrack()
        self.detector = ReturnDetector() if reanchor else None
        self.third_person = bool(third_person)
        if self.weight_mod is not None:
            self.weight_mod.reset()
        if self.cond_sched is not None:
            self.cond_sched.reset()
        if self.kv_noise is not None:
            self.kv_noise.reset(pipe.scheduler, seed, dev)
        if self.stream_decode:
            from wan.modules.vae2_1 import count_conv3d  # noqa: PLC0415
            self._feat_map = [None] * count_conv3d(pipe.vae.model.decoder)
        self.chunk_id = 0
        self.started = True
        self._timing = True
        torch.cuda.synchronize()
        FS.log("reset.total", time.time() - t_reset)

    def _ensure_y(self, end_lat: int):
        """Make `y` cover latents [0, end_lat)."""
        if self.stream_encode:
            self._extend_y(end_lat)
        elif end_lat > self.y.shape[1]:
            self._encode_y(min(ROPE_LATENTS, end_lat + 8 * CHUNK))

    def _extend_y(self, n_lat: int):
        """--lingbot-fast-y: append latents to `y` up to n_lat. Mirrors WanVAE_.encode (vae2_1.py):
        the encoder runs on the image frame, then on 4-frame chunks (here all zeros), with its causal
        feature cache, which this session keeps across calls instead of clearing it. conv1 (kernel 1
        in time) and the latent scaling are pointwise in time, so they run per extension."""
        import torch  # noqa: PLC0415
        have = 0 if self.y is None else self.y.shape[1]
        if n_lat <= have:
            return
        vae, dev = self.pipe.vae, self.pipe.device
        m = vae.model
        mean, inv_std = vae.scale
        t0 = time.time()
        with torch.no_grad(), torch.cuda.amp.autocast(dtype=vae.dtype):
            outs = []
            for i in range(have, n_lat):
                x = (self._img if i == 0 else torch.zeros(3, 4, self.h, self.w)).to(dev).unsqueeze(0)
                outs.append(m.encoder(x, feat_cache=self._enc_feat_map, feat_idx=[0]))
            mu, _ = m.conv1(torch.cat(outs, 2)).chunk(2, dim=1)
            mu = (mu - mean.view(1, m.z_dim, 1, 1, 1)) * inv_std.view(1, m.z_dim, 1, 1, 1)
        lat = mu.float().squeeze(0)
        msk = torch.zeros(4, n_lat - have, self.lat_h, self.lat_w, device=dev)
        if have == 0:
            msk[:, 0] = 1
        new = torch.concat([msk, lat])
        self.y = new if self.y is None else torch.cat([self.y, new], dim=1)
        if self._timing:
            torch.cuda.synchronize()
            FS.log("step0.y_encode", time.time() - t0, f"(streamed, latents {have}->{n_lat})")

    def _encode_y(self, n_lat: int):
        """y = [mask (4ch), VAE(image then zeros)] for n_lat latents. The encoder is
        causal, so a longer horizon only appends latents; the prefix is unchanged."""
        import torch  # noqa: PLC0415
        dev = self.pipe.device
        F = (n_lat - 1) * 4 + 1
        t0 = time.time()
        with torch.no_grad():
            video = torch.concat([self._img, torch.zeros(3, F - 1, self.h, self.w)], dim=1).to(dev)
            y = self.pipe.vae.encode([video])[0]
            del video
        # upstream builds the mask per pixel frame and folds it 4:1; the result is
        # all ones for latent 0 and zeros elsewhere.
        msk = torch.zeros(4, n_lat, self.lat_h, self.lat_w, device=dev)
        msk[:, 0] = 1
        self.y = torch.concat([msk, y])
        print(f"[lingbot] session: encoded y for {n_lat} latents ({F} frames) in {time.time() - t0:.1f}s",
              flush=True)

    def _anchor_y(self, g: int):
        """Re-anchor: mark latent g of `y` as given and set it to the input image.

        Upstream gives the model the input image only at latent 0 (mask 1, VAE latent of
        the image). Here latent g gets the same signal: mask 1 on its four pixel frames and
        the latent of a still clip of the image (the second latent of [image x 5], which
        is what a 4-frame latent of an unchanging view looks like to the causal VAE)."""
        import torch  # noqa: PLC0415
        if self._anchor is None:
            with torch.no_grad():
                still = self._img.repeat(1, 5, 1, 1).to(self.pipe.device)
                self._anchor = self.pipe.vae.encode([still])[0][:, -1]
        self.y[:4, g] = 1
        self.y[4:, g] = self._anchor.to(self.y.dtype)
        self.reanchor_events += 1
        self._anchored.add(g)
        print(f"[lingbot] session: re-anchored latent {g} (frame {4 * g}) to the input image", flush=True)

    def _plucker(self, rel: np.ndarray):
        """[1, 384, f, lat_h, lat_w] camera embedding for f relative poses (float32 math
        outside autocast, cast to param dtype, as upstream)."""
        import torch  # noqa: PLC0415
        from einops import rearrange  # noqa: PLC0415
        from wan.utils.cam_utils import get_plucker_embeddings  # noqa: PLC0415
        f = len(rel)
        c2ws = torch.from_numpy(np.asarray(rel, dtype=np.float32)).to(self.pipe.device)
        emb = get_plucker_embeddings(c2ws, self.Ks.repeat(f, 1), self.h, self.w)
        emb = rearrange(emb, "f (h c1) (w c2) c -> (f h w) (c c1 c2)",
                        c1=self.h // self.lat_h, c2=self.w // self.lat_w)[None]
        emb = rearrange(emb, "b (f h w) c -> b c f h w", f=f, h=self.lat_h, w=self.lat_w)
        return emb.to(self.pipe.param_dtype)

    # -- step --------------------------------------------------------------
    def _couple_noise(self, noise, stage):
        return noise if self.noise_mean is None else self.noise_mean.apply(noise, stage)

    def update_prompt(self, prompt: str) -> bool:
        """Refresh text cross-attention only; preserve visual KV, camera and decoder state."""
        if not self.started:
            raise RuntimeError("reset the session before updating its prompt")
        if prompt == self.prompt:
            return False
        context = encode_prompt(self.pipe, prompt, self.t5_cache)
        self.context, self.prompt = context, prompt
        self.cross_init = False  # upstream overwrites text K/V on the next first-call forward
        return True

    def step(self, keys: list[str], ease_turns: bool = False):
        """Generate len(keys) pixel frames (whole chunks) and return uint8 [F, H, W, 3]:
        first step 16n-3 frames from the input frame, later steps the previous last
        frame plus 16n new ones."""
        import torch  # noqa: PLC0415
        if not self.started:
            raise RuntimeError("LingBotSession.step() before reset()")
        pipe = self.pipe
        first = self.chunk_id == 0
        rel = self.track.advance(keys, ease_turns=ease_turns)
        n_chunks = len(rel) // CHUNK
        end_lat = (self.chunk_id + n_chunks) * CHUNK
        if end_lat > ROPE_LATENTS:
            raise RuntimeError(f"rollout would reach {end_lat} latents; the RoPE table has {ROPE_LATENTS}")
        timing, t_mark = self._timing, time.time()

        def mark(part, extra=""):
            nonlocal t_mark
            if timing:
                torch.cuda.synchronize()
                now = time.time()
                FS.log(part, now - t_mark, extra)
                t_mark = now

        self._ensure_y(end_lat)  # logs its own timing line when streamed
        self._timing = False
        if timing:
            torch.cuda.synchronize()
            t_mark = time.time()
        if self.detector is not None:
            for i in self.detector.update(self.track.latents):
                self._anchor_y(self.chunk_id * CHUNK + i)

        new, modulated = [], False
        pm = self._pose_memory()  # None unless --lingbot-pose-memory is on for this rollout
        with (self.weight_mod or contextlib.nullcontext()), (self.cond_sched or contextlib.nullcontext()), \
                contextlib.ExitStack() as sink, torch.amp.autocast("cuda", dtype=pipe.param_dtype), torch.no_grad(), \
                (self._pose_mem_guard() if pm is not None else contextlib.nullcontext()):
            for c in range(n_chunks):
                cid, chunk_hit, stg_hit = self.chunk_id, False, False
                rel_c = rel[c * CHUNK:(c + 1) * CHUNK]
                if pm is not None:  # before weight_mod.step; _mem_recompute sets the stored chunk's own scales
                    self._pose_mem_before(cid, self.track.latents[c * CHUNK:(c + 1) * CHUNK])
                if self.weight_mod is not None and self.weight_mod.step(rel_c, third_person=self.third_person):
                    modulated = True
                    self.weight_mod_chunks += 1
                with torch.autocast("cuda", enabled=False):
                    emb = self._plucker(rel_c)
                latent = torch.randn(16, CHUNK, self.lat_h, self.lat_w, dtype=torch.float32,
                                     generator=self.gen, device=pipe.device)
                latent = self._couple_noise(latent, 0)
                kwargs = {
                    "context": [self.context[0]],
                    "seq_len": self.max_seq_len,
                    "y": [self.y[:, cid * CHUNK:(cid + 1) * CHUNK]],
                    "dit_cond_dict": {"c2ws_plucker_emb": emb.chunk(1, dim=0)},
                    "kv_cache": self.kv,
                    "crossattn_cache": self.cross,
                    "current_start": cid * CHUNK * self.frame_seqlen,
                    "max_attention_size": self.kv_size,
                    "frame_seqlen": self.frame_seqlen,
                }
                ts = self.timesteps
                for i in range(len(ts)):
                    if i == 0:  # --lingbot-sink-key-scale / --lingbot-split-sink: no-op unless it acts on this chunk
                        sink.enter_context(self._sink_scaled(cid))
                        if self.split_sink is not None and self.split_sink_on:
                            sink.enter_context(self._split_sink_scaled(cid))
                    if self.weight_mod is not None:
                        self.weight_mod.denoise_step(i, len(ts))
                    if self.cond_sched is not None and self.cond_sched.set_step(rel_c, i, third_person=self.third_person):
                        self.cond_sched_calls += 1
                        chunk_hit = True
                    t = torch.stack([ts[i]]).to(pipe.device)
                    pred_skip = None
                    if self.stg is not None and self.stg.guided(i):
                        # before the full pass, which then rewrites this chunk's KV slot and sees main's caches
                        with self.stg.skipped():
                            pred_skip = pipe.model(x=[latent], t=t, cross_attn_first_call=not self.cross_init,
                                                   **kwargs)[0]
                        self.stg_calls += 1
                        stg_hit = True
                    pred = pipe.model(x=[latent], t=t, cross_attn_first_call=not self.cross_init, **kwargs)[0]
                    self.cross_init = True
                    if pred_skip is not None:
                        pred = self.stg.combine(pred, pred_skip)
                    if c == 0 and i == 0:
                        mark("step0.first_forward", "(first DiT call after reset: includes any warm-up)")
                    x0 = pipe._convert_flow_pred_to_x0(flow_pred=pred, xt=latent, timestep=ts[i],
                                                       scheduler=pipe.scheduler)
                    if i < len(ts) - 1:
                        noise = torch.randn(x0.shape, generator=self.gen, device=x0.device, dtype=x0.dtype)
                        noise = self._couple_noise(noise, i + 1)
                        latent = pipe.scheduler.add_noise(x0, noise, ts[i + 1])
                sink.close()  # sink keys restored before the clean KV write
                new.append(x0)
                if self.weight_mod is not None:
                    self.weight_mod.end_chunk()  # the clean KV write uses the chunk's base scale
                if self.cond_sched is not None:
                    self.cond_sched.reset()
                if chunk_hit:
                    self.cond_sched_chunks += 1
                self.stg_chunks += stg_hit
                # weight_mod.end_chunk() and cond_sched.reset() ran above, so either KV write below uses
                # cond scales 1.0 and the chunk's base weight-mod scale.
                if (self.kv_noise is not None and cid > 0
                        and cid * CHUNK >= int(getattr(pipe, "sink_size", 0) or 0)
                        and not self._anchored.intersection(range(cid * CHUNK, (cid + 1) * CHUNK))):
                    # --lingbot-kv-noise: write keys/values of a lightly re-noised x0 at t_kv. Chunks that
                    # overlap the attention sink stay clean: sink slots are never evicted, so a noised
                    # write there would stay in every later chunk's context.
                    x_kv, t_kv = self.kv_noise.kv_input(x0, pipe.scheduler)
                    self.kv_noise_chunks += 1
                    pipe.model(x=[x_kv], t=torch.stack([t_kv]).to(pipe.device), cross_attn_first_call=False, **kwargs)
                else:
                    # write clean keys/values for this chunk into the KV cache
                    t0 = torch.stack([ts[-1] * 0.0]).to(pipe.device)
                    pipe.model(x=[x0], t=t0, cross_attn_first_call=False, **kwargs)
                if pm is not None:
                    self._pose_mem_after(cid, self.track.latents[c * CHUNK:(c + 1) * CHUNK], x0, rel_c)
                if self.split_sink is not None and self.split_sink_on:
                    sink_n = int(getattr(pipe, "sink_size", 0) or 0)
                    if len(self._ss_poses) < sink_n:
                        self._split_sink_record(x0, c, sink_n)
                self.chunk_id += 1
                W.progress()  # stall watchdog: a long (dataset-mode) step is not a stall while chunks advance
            lat = torch.cat(new, dim=1)
            del new, latent, x0, pred, kwargs, emb  # denoise temporaries; KV cache, y and track stay
            mark("step0.denoise_rest", f"({n_chunks} chunks x {len(self.timesteps)} steps + KV writes, minus first call)")
            video = self._decode(lat)  # uint8 [3, F, H, W] on the host
            mark("step0.decode", f"({lat.shape[1]} latents, {video.shape[1]} frames, "
                 f"peak VRAM {torch.cuda.max_memory_allocated() / 2**30:.1f} GiB)" if timing else "")
        if modulated:
            self.weight_mod_steps += 1

        frames = video.permute(1, 2, 3, 0).cpu().numpy()
        del video
        mark("step0.to_host")
        if not first:
            frames = np.concatenate([self._last_frame[None], frames])
        self._last_frame = frames[-1].copy()
        return frames

    def _sink_scaled(self, cid: int):
        """--lingbot-sink-key-scale: scale the sink keys of every block for this chunk's denoising forwards, then
        copy the saved originals back (also on an exception). nullcontext when off or not active for cid."""
        sink = int(getattr(self.pipe, "sink_size", 0) or 0)
        if not (self.sink_scale_on and SK.active(self.sink_scale, cid, CHUNK, sink)):
            return contextlib.nullcontext()
        return self._sink_scale_ctx(SK.sink_tokens(sink, self.frame_seqlen))

    @contextlib.contextmanager
    def _sink_scale_ctx(self, n_tokens: int):
        saved = []
        try:
            SK.scale_keys(self.kv, n_tokens, self.sink_scale.scale, saved)
            self.sink_scaled_chunks += 1
            yield
        finally:
            SK.restore_keys(self.kv, n_tokens, saved)

    def _split_sink_record(self, x0, chunk_idx: int, sink: int):
        have = len(self._ss_poses)
        take = min(CHUNK, sink - have)
        if take <= 0:
            return
        lat = x0.detach() if hasattr(x0, "detach") else x0
        if hasattr(lat, "float"):
            lat = lat.float()
        if hasattr(lat, "cpu"):
            lat = lat.cpu()
        if hasattr(lat, "numpy"):
            lat = lat.numpy()
        lat_np = np.array(np.asarray(lat, dtype=np.float32)[:, :take], dtype=np.float32, copy=True)
        c2ws = np.asarray(self.track.model_latents[chunk_idx * CHUNK:chunk_idx * CHUNK + take], dtype=np.float64)
        self._ss_latents.append(lat_np)
        self._ss_poses.extend(np.array(c2ws[i], dtype=np.float64, copy=True) for i in range(len(c2ws)))

    def _split_sink_scaled(self, cid: int):
        """--lingbot-split-sink: spatially scale foreground/background sink keys on denoising forwards of cid,
        then copy the saved originals back (also on an exception). nullcontext when off or not active for cid."""
        sink = int(getattr(self.pipe, "sink_size", 0) or 0)
        if not (self.split_sink is not None and self.split_sink_on
                and SS.active(self.split_sink, cid, CHUNK, sink) and len(self._ss_poses) >= sink):
            return contextlib.nullcontext()
        if self._ss_scales is None:
            self._build_split_sink_scales(sink)
        return self._split_sink_ctx()

    def _build_split_sink_scales(self, sink: int):
        import torch  # noqa: PLC0415
        full_lat = np.concatenate(self._ss_latents, axis=1)[:, :sink]
        full_c2w = np.stack(self._ss_poses[:sink], axis=0)
        scales_1d, fg_tokens = SS.compute_sink_scales(full_lat, full_c2w, self.split_sink)
        n_tokens = SS.sink_tokens(sink, self.frame_seqlen)
        if len(scales_1d) != n_tokens:
            raise RuntimeError(f"split-sink scale length {len(scales_1d)} != sink_tokens {n_tokens}")
        arr = scales_1d.reshape(1, n_tokens, 1, 1)
        ref_k = self.kv[0]["k"] if self.kv else None
        if ref_k is not None and not isinstance(ref_k, np.ndarray) and hasattr(torch, "as_tensor"):
            self._ss_scales = torch.as_tensor(arr, device=ref_k.device, dtype=ref_k.dtype)
        elif isinstance(ref_k, np.ndarray):
            self._ss_scales = arr.astype(ref_k.dtype, copy=False)
        else:
            self._ss_scales = arr
        self.split_sink_fg_tokens += int(fg_tokens)
        print(f"[lingbot] split-sink: built spatial mask at chunk {self.chunk_id} "
              f"(fg_tokens={fg_tokens}/{n_tokens}, fg={self.split_sink.fg_scale:g}, "
              f"bg={self.split_sink.bg_scale:g}, frac={self.split_sink.fg_frac:g})", flush=True)
        # once-per-rollout mask dump: latent 0's DiT patches, '#' = foreground (fg_scale), '.' = background,
        # so a smoke can check from gen.log that the mask lands on the moving subject
        ph, pw = full_lat.shape[2] // 2, full_lat.shape[3] // 2
        if fg_tokens and ph * pw == self.frame_seqlen:
            grid = np.asarray(scales_1d[:ph * pw]).reshape(ph, pw) < self.split_sink.bg_scale
            for r, row in enumerate(grid):
                print(f"[lingbot] split-sink mask {r:02d} " + "".join("#" if v else "." for v in row), flush=True)

    @contextlib.contextmanager
    def _split_sink_ctx(self):
        n_tokens = int(self._ss_scales.shape[1])
        saved = []
        try:
            SS.scale_keys_vector(self.kv, self._ss_scales, saved)
            self.split_sink_chunks += 1
            yield
        finally:
            SS.restore_keys(self.kv, n_tokens, saved)

    # -- pose-indexed memory (--lingbot-pose-memory) -------------------------
    def _pose_memory(self):
        """This rollout's bank (built on first use after reset), or None when the flag is off or the task
        did not match."""
        if self.pose_mem is None or not self.pose_mem_on:
            return None
        if self.pmem is None:
            self.pmem = PM.PoseMemory(self.pose_mem, int(getattr(self.pipe, "sink_size", 0) or 0),
                                      int(self.pipe.local_attn_size), name=self.pose_mem_name)
        return self.pmem

    def _pm_span(self):
        """Cache token range [lo, hi) the memory may overwrite: sink latents [anchor, anchor + latents)."""
        fs, cfg = self.frame_seqlen, self.pose_mem
        return cfg.anchor * fs, (cfg.anchor + cfg.latents) * fs

    def _pm_restore(self):
        """Copy the original sink slots back into every block (an exact copy) and mark nothing installed."""
        lo, hi = self._pm_span()
        for blk, (k, v) in zip(self.kv, self._pm_snapshot):
            blk["k"][:, lo:hi] = k
            blk["v"][:, lo:hi] = v
        self._pm_installed = ()
        if self.pmem is not None:
            self.pmem.current = []

    @contextlib.contextmanager
    def _pose_mem_guard(self):
        """On an exception during a step, put the original sink back, so the cache holds no partial recompute
        or retrieved memory."""
        try:
            yield
        except BaseException:
            if self._pm_snapshot is not None and self._pm_installed != ():
                self._pm_restore()
            raise

    def _pose_mem_before(self, cid: int, latent_c2ws):
        """Select memory for chunk cid from its commanded latent poses (PoseMemory.decide) and install it in the
        sink slots, re-time it, or put the original sink back when nothing matches (fallback start)."""
        pm, cfg = self.pmem, self.pose_mem
        d = pm.decide(latent_c2ws, cid, self._pm_installed)
        if d.kind == "restore":
            self._pm_restore()
            self.pm_restores += 1
            print(f"[lingbot] pose-mem: chunk {cid} restore start sink (no match)", flush=True)
            return
        if d.kind not in ("install", "retime"):
            return
        import torch  # noqa: PLC0415
        t0 = time.time()
        lo, hi = self._pm_span()
        if self._pm_snapshot is None:  # these slots are final once cid * CHUNK >= sink
            self._pm_snapshot = [(blk["k"][:, lo:hi].to("cpu", copy=True), blk["v"][:, lo:hi].to("cpu", copy=True))
                                 for blk in self.kv]
        if len(d.matches) < cfg.chunks and self._pm_installed != ():  # unused slots hold the original sink
            self._pm_restore()
        self._pm_installed = None  # mid-install: the guard restores if a recompute raises
        for s, r, m in zip(d.slots, d.ropes, d.matches):
            self._mem_recompute(m.entry, s, r)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        self._pm_installed = d.ids
        pm.current = list(d.matches)
        if d.kind == "install":
            self.pm_installs += 1
            self.pm_latents += CHUNK * len(d.matches)
        else:
            self.pm_retimes += 1
        dt = time.time() - t0
        for s, r, m in zip(d.slots, d.ropes, d.matches):
            if d.kind == "retime":
                print(f"[lingbot] pose-mem: chunk {cid} keeps chunk {m.entry.cid} re-timed slots {s}-{s + CHUNK - 1} "
                      f"rope={cfg.time}:{r} {dt:.2f}s", flush=True)
                continue
            print(f"[lingbot] pose-mem: chunk {cid} <- chunk {m.entry.cid} (dyaw {m.dyaw:.1f} deg, dpitch "
                  f"{m.dpitch:.1f} deg, dpos {m.dpos:.1f}, o={m.overlap:.2f}"
                  + (f", window o={m.window:.2f}" if cfg.rule != "legacy" else "")
                  + f") slots {s}-{s + CHUNK - 1} rope={cfg.time}:{r} {dt:.2f}s"
                  + (f" [{m.note}]" if m.note else ""), flush=True)

    def _mem_recompute(self, entry, slot: int, rope_lat: int):
        """One clean t=0 forward of a stored chunk that writes its K/V into sink slots [slot, slot + CHUNK) of every
        block. Each block gets a dict whose k/v are views of the live cache from latent 0 to slot + CHUNK and whose
        end indices are its own copies, so the forward takes upstream's no-eviction branch, writes only those
        slots, attends the anchor latents (and memory in lower slots) plus itself, and never reads or writes the
        live global/local end indices. Its RoPE time is rope_lat (current_start). With --lingbot-weight-mod the
        forward runs at chunk j's own base scales (as its clean KV write did), then the current ones come back."""
        fs = self.frame_seqlen
        views = []
        for blk in self.kv:
            g, loc = blk["global_end_index"].clone(), blk["local_end_index"].clone()
            g.fill_(rope_lat * fs)
            loc.fill_(slot * fs)
            views.append({"k": blk["k"][:, :(slot + CHUNK) * fs], "v": blk["v"][:, :(slot + CHUNK) * fs],
                          "global_end_index": g, "local_end_index": loc})
        wm = self.weight_mod
        saved = (wm.cam_scale, wm.text_scale, wm._regime, wm._base_cam) if wm is not None else None
        if wm is not None:  # chunk j's base scales, as its own clean KV write had them (end_chunk)
            wm.step(entry.rel, third_person=self.third_person)
        try:
            self._mem_forward(entry, views, rope_lat, slot)
        finally:
            if saved is not None:
                wm.cam_scale, wm.text_scale, wm._regime, wm._base_cam = saved
        self.cross_init = True  # after update_prompt the call above wrote the new text K/V, as a first forward would
        self.pm_forwards += 1

    def _mem_forward(self, entry, views, rope_lat: int, slot: int):
        import torch  # noqa: PLC0415
        fs, pipe, j = self.frame_seqlen, self.pipe, entry.cid
        with torch.autocast("cuda", enabled=False):
            emb = self._plucker(entry.rel)
        pipe.model(x=[entry.x0.to(pipe.device)], t=torch.stack([self.timesteps[-1] * 0.0]).to(pipe.device),
                   cross_attn_first_call=not self.cross_init, context=[self.context[0]], seq_len=self.max_seq_len,
                   y=[self.y[:, j * CHUNK:(j + 1) * CHUNK]], dit_cond_dict={"c2ws_plucker_emb": emb.chunk(1, dim=0)},
                   kv_cache=views, crossattn_cache=self.cross, current_start=rope_lat * fs,
                   max_attention_size=(slot + CHUNK) * fs, frame_seqlen=fs)

    def _pose_mem_after(self, cid: int, latent_c2ws, x0, rel_c):
        """Store the chunk just written (x0 on the host) and mark stored views the camera has now left."""
        pm = self.pmem
        if self._pm_installed:
            self.pm_chunks += 1
        host = x0.to("cpu", copy=True)
        self.pm_evicted += pm.record(cid, latent_c2ws, host, np.array(rel_c), int(host.numel() * host.element_size()))
        self.pm_stored += 1
        snap = sum(int(k.numel() * k.element_size() + v.numel() * v.element_size())
                   for k, v in (self._pm_snapshot or ()))
        self.pm_peak_bytes = max(self.pm_peak_bytes, pm.nbytes + snap)

    def _decode(self, lat):
        """New latents -> new pixel frames, uint8 [3, F, H, W] on the host (to_uint8_host per decoded
        latent, see decode_slices). Neither path builds a full-length video tensor on the device: a
        dataset-mode task is one step of up to 280 latents (1117 frames, an fp32 copy of 4.82 GiB)."""
        import torch  # noqa: PLC0415
        torch.cuda.empty_cache()  # hand the cached blocks the denoise loop no longer needs to the decoder
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()  # step0.decode reports the decode's own peak
        vae = self.pipe.vae
        m = vae.model
        mean, inv_std = vae.scale
        if self.stream_decode:
            # Streaming: mirrors Wan2_1_VAE.decode / WanVAE_.decode (vae2_1.py) but keeps the decoder's
            # causal feature cache (_feat_map) across steps instead of clearing it each call.
            zs, feat, skip = lat, self._feat_map, 0
        else:
            # Re-decode every latent so far with a fresh cache (what WanVAE_.decode does after
            # clear_cache()) and keep only the new frames.
            from wan.modules.vae2_1 import count_conv3d  # noqa: PLC0415
            self._all_lat.append(lat)
            zs, feat = torch.cat(self._all_lat, dim=1), [None] * count_conv3d(m.decoder)
            n_new = 4 * lat.shape[1] - (3 if len(self._all_lat) == 1 else 0)
            skip = 4 * zs.shape[1] - 3 - n_new
        with torch.cuda.amp.autocast(dtype=vae.dtype):
            z = zs.unsqueeze(0)
            z = z / inv_std.view(1, m.z_dim, 1, 1, 1) + mean.view(1, m.z_dim, 1, 1, 1)
            x = m.conv2(z)  # kernel 1 in time: no cache needed
            out = decode_slices(m.decoder, x, feat, skip)
        return out.squeeze(0)
