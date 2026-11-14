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
    input image followed by zeros, so it does not depend on the actions).

Everything above the LingBotSession class is numpy-only and unit-tested
(tests/test_lingbot_session.py); torch is imported lazily.
"""
from __future__ import annotations

import math
import os
import re
import time

import numpy as np

from adapters.lingbot_world2 import poses as P

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


class PoseTrack:
    """Absolute camera track across steps. advance(keys) -> normalised relative
    poses for the new latent frames (one per 4 pixel frames)."""

    def __init__(self):
        self.last = np.eye(4)        # absolute pose of the latest pixel frame
        self.prev_latent = None      # absolute pose of the latest latent frame

    def advance(self, keys: list[str]) -> np.ndarray:
        first = self.prev_latent is None
        if (len(keys) + (4 if first else 0)) % FRAMES_PER_CHUNK:
            raise ValueError(f"{len(keys)} keys do not fill whole chunks (first={first})")
        cur = self.last
        lat = [cur] if first else []  # latent 0 is pixel frame 0
        for i, k in enumerate(keys, 1):
            cur = cur @ P.key_delta(k)
            if i % 4 == 0:
                lat.append(cur)
        rel = relative_latent_poses(np.stack(lat), self.prev_latent)
        self.last, self.prev_latent = cur, lat[-1]
        return normalise_translation(rel)


def horizon_latents(horizon_frames: int) -> int:
    """Latents to pre-encode `y` for: enough for horizon_frames, chunk-aligned, plus
    one chunk of slack, capped by the RoPE table."""
    lat = (max(int(horizon_frames), 1) - 1) // 4 + 1
    lat = math.ceil(lat / CHUNK) * CHUNK + CHUNK
    return min(lat, ROPE_LATENTS)


# ------------------------------------------------------------- torch session

class LingBotSession:
    """Stateful wrapper around a loaded wan.WanI2VCausal (causal_fast)."""

    def __init__(self, pipe, max_area: int, shift: float, horizon_frames: int = 961,
                 stream_decode: bool | None = None):
        self.pipe = pipe
        self.max_area = max_area
        self.shift = shift
        self.horizon_frames = horizon_frames
        if stream_decode is None:
            stream_decode = os.environ.get("LINGBOT_STREAM_DECODE", "1") != "0"
        self.stream_decode = stream_decode
        self.chunk_id = 0
        self.started = False
        self._free()

    def _free(self):
        self.kv = self.cross = self.y = None
        self._feat_map = None
        self._all_lat = []
        self._last_frame = None

    # -- reset -------------------------------------------------------------
    def reset(self, image, prompt: str, seed: int, horizon_frames: int | None = None):
        import torch  # noqa: PLC0415
        import torchvision.transforms.functional as TF  # noqa: PLC0415
        from wan.utils.cam_utils import get_Ks_transformed  # noqa: PLC0415

        pipe = self.pipe
        dev = pipe.device
        self._free()
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
        self.context = self._text_context(prompt)

        Ks = torch.tensor([P.INTRINSICS_480P], dtype=torch.float32)
        Ks = get_Ks_transformed(Ks, height_org=480, width_org=832, height_resize=self.h,
                                width_resize=self.w, height_final=self.h, width_final=self.w)
        self.Ks = Ks[0].view(1, 4).to(dev)

        self._img = torch.nn.functional.interpolate(
            img[None].cpu(), size=(self.h, self.w), mode="bicubic").transpose(0, 1)  # [3,1,h,w]
        self._encode_y(horizon_latents(horizon_frames or self.horizon_frames))

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
        if self.stream_decode:
            from wan.modules.vae2_1 import count_conv3d  # noqa: PLC0415
            self._feat_map = [None] * count_conv3d(pipe.vae.model.decoder)
        self.chunk_id = 0
        self.started = True

    def _text_context(self, prompt: str):
        """Same T5 path and cache as upstream (pipe._t5_cache keyed by sha256)."""
        import hashlib  # noqa: PLC0415

        import torch  # noqa: PLC0415
        pipe = self.pipe
        key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if key not in pipe._t5_cache:
            if not pipe.t5_cpu:
                pipe.text_encoder.model.to(pipe.device)
                ctx = pipe.text_encoder([prompt], pipe.device)
            else:
                ctx = [t.to(pipe.device) for t in pipe.text_encoder([prompt], torch.device("cpu"))]
            pipe._t5_cache[key] = ctx
        return pipe._t5_cache[key]

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
    def step(self, keys: list[str]):
        """Generate len(keys) pixel frames (whole chunks) and return uint8 [F, H, W, 3]:
        first step 16n-3 frames from the input frame, later steps the previous last
        frame plus 16n new ones."""
        import torch  # noqa: PLC0415
        if not self.started:
            raise RuntimeError("LingBotSession.step() before reset()")
        pipe = self.pipe
        first = self.chunk_id == 0
        rel = self.track.advance(keys)
        n_chunks = len(rel) // CHUNK
        end_lat = (self.chunk_id + n_chunks) * CHUNK
        if end_lat > ROPE_LATENTS:
            raise RuntimeError(f"rollout would reach {end_lat} latents; the RoPE table has {ROPE_LATENTS}")
        if end_lat > self.y.shape[1]:
            self._encode_y(min(ROPE_LATENTS, end_lat + 8 * CHUNK))

        new = []
        with torch.amp.autocast("cuda", dtype=pipe.param_dtype), torch.no_grad():
            for c in range(n_chunks):
                cid = self.chunk_id
                with torch.autocast("cuda", enabled=False):
                    emb = self._plucker(rel[c * CHUNK:(c + 1) * CHUNK])
                latent = torch.randn(16, CHUNK, self.lat_h, self.lat_w, dtype=torch.float32,
                                     generator=self.gen, device=pipe.device)
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
                    t = torch.stack([ts[i]]).to(pipe.device)
                    pred = pipe.model(x=[latent], t=t, cross_attn_first_call=not self.cross_init, **kwargs)[0]
                    self.cross_init = True
                    x0 = pipe._convert_flow_pred_to_x0(flow_pred=pred, xt=latent, timestep=ts[i],
                                                       scheduler=pipe.scheduler)
                    if i < len(ts) - 1:
                        noise = torch.randn(x0.shape, generator=self.gen, device=x0.device, dtype=x0.dtype)
                        latent = pipe.scheduler.add_noise(x0, noise, ts[i + 1])
                new.append(x0)
                # write clean keys/values for this chunk into the KV cache
                t0 = torch.stack([ts[-1] * 0.0]).to(pipe.device)
                pipe.model(x=[x0], t=t0, cross_attn_first_call=False, **kwargs)
                self.chunk_id += 1
            lat = torch.cat(new, dim=1)
            video = self._decode(lat)

        frames = ((video.clamp(-1, 1) + 1) * 127.5).round().to(torch.uint8).permute(1, 2, 3, 0).cpu().numpy()
        del video
        if not first:
            frames = np.concatenate([self._last_frame[None], frames])
        self._last_frame = frames[-1].copy()
        return frames

    def _decode(self, lat):
        """New latents -> new pixel frames [3, F, H, W] in [-1, 1]."""
        import torch  # noqa: PLC0415
        vae = self.pipe.vae
        if not self.stream_decode:
            self._all_lat.append(lat)
            full = vae.decode([torch.cat(self._all_lat, dim=1)])[0]
            n_new = 4 * lat.shape[1] - (3 if len(self._all_lat) == 1 else 0)
            return full[:, -n_new:]
        # Streaming: mirrors Wan2_1_VAE.decode / WanVAE_.decode (vae2_1.py) but keeps
        # the decoder's causal feature cache (_feat_map) across steps instead of
        # clearing it at the start and end of each call.
        m = vae.model
        mean, inv_std = vae.scale
        with torch.cuda.amp.autocast(dtype=vae.dtype):
            z = lat.unsqueeze(0)
            z = z / inv_std.view(1, m.z_dim, 1, 1, 1) + mean.view(1, m.z_dim, 1, 1, 1)
            x = m.conv2(z)  # kernel 1 in time: no cache needed
            outs = []
            for i in range(x.shape[2]):
                outs.append(m.decoder(x[:, :, i:i + 1], feat_cache=self._feat_map, feat_idx=[0]))
            out = torch.cat(outs, 2)
        return out.float().clamp_(-1, 1).squeeze(0)
