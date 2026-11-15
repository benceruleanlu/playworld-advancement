#!/usr/bin/env python3
"""SANA-WM streaming runner: one chunk-causal SANA-WM session per task instead of a restart per chunk.

    pwa gen EXP --runner sana_stream --action-source agent -- --chunk-frames 25 --num-chunks 40

An option only: nothing selects this runner by default, and SANA-WM work is stopped (AGENTS.md, Adapters).
It carries no inference-time method; it is the SANA-WM counterpart of the LingBot persistent session.

Upstream's SANA-WM player calls the bidirectional model (60 steps) once per chunk on the previous chunk's
last frame, so the model's own context (stage-1 KV cache and sink token, refiner KV window, causal VAE
cache) is dropped at every agent decision. This runner keeps one streaming generation (4-step distilled
stage 1 + chunk-causal refiner + causal VAE) alive per task and feeds it the action for each 24-frame block
just before that block is sampled:

  * camera tensors for the whole horizon are allocated once; before each block they are overwritten in place
    with the trajectory implied by every action so far (poses are relative to frame 0 and sliced per chunk
    at sample time, so earlier blocks are unaffected), which makes the commanded camera pose absolute;
  * the session continues only if the image the harness passes in is the frame emitted last; a new task, or
    a wrapper that hands in another frame, starts a new session from that image.

Measured on one Modal H100 at NVlabs/Sana 9f714116 (the wm/ scripts are byte-identical at the 27303b8 this
repo pins): about 2.3 s per 1.5 s block once warm, against over a minute per chunk for the upstream player.
In a 6-task blind review per family it scored level with upstream SANA-WM (no gain from the session alone).

Same argv as run_agent.py. One closed-loop decision is exactly one 24-frame block, whatever --chunk-frames
says, so use `--chunk-frames 25 --num-chunks 40` (40 blocks = 60 s).

Env:
  SANA_KEYMAP=head|legacy   head (default): current Sana DSL, a/d yaw and j/l strafe, so the harness keys
                            (j/l = turn, a/d = strafe, written for the first Sana-WM release) are swapped
  SANA_ROT_DEG=0.9375       degrees per frame while turning (0.9375 * 24 = 22.5 per block, one dataset
                            action token); Sana's default is 0.6
  SANA_TRANS=0.025          translation per frame
  SANA_CACHED_BLOCKS=2      stage-1 KV window in blocks; -1 keeps every past block
  SANA_STREAM_FRAMES=961    session horizon in frames
  SANA_COMPILE=0            torch.compile the refiner (about 3 min warmup, faster steady state)

Image notes (not applied anywhere by this file): flash-attn is optional, the refiner then needs
SANA_WM_REFINER_SELF_ATTN_KERNEL=sdpa (set here when flash_attn is not importable); the Gemma tokenizer
needed protobuf >= 7.36.1 in the image this was run on.
"""
from __future__ import annotations

import argparse
import os
import queue
import re
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.common import agent_api  # noqa: E402
from adapters.common.upstream import import_run_agent  # noqa: E402

run_agent = import_run_agent()
BLOCK = 24                      # pixel frames per refiner block (3 latent frames x 8)
SWAP = {"a": "j", "d": "l", "j": "a", "l": "d"}


def parse_action(action: str) -> list[tuple[str, int]]:
    """'<key>-<frames>' segments joined by commas, as run_agent builds them."""
    out = []
    for seg in (action or "").split(","):
        m = re.fullmatch(r"\s*([a-z]+)-(\d+)\s*", seg)
        if m:
            out.append((m.group(1), int(m.group(2))))
    return out


def to_model_keys(key: str) -> str:
    """Harness key (j/l = turn, a/d = strafe) -> Sana DSL key."""
    if key == "none" or os.environ.get("SANA_KEYMAP", "head") == "legacy":
        return key
    return "".join(SWAP.get(c, c) for c in key)


def per_frame_keys(action: str) -> list[str]:
    keys = []
    for key, n in parse_action(action):
        keys += [key] * n
    return keys


def blocks_from_action(action: str, single_call_frames: int | None = None) -> list[list[str]]:
    """Split an action string into 24-frame blocks of per-frame keys (padded with 'none')."""
    keys = per_frame_keys(action)
    if single_call_frames is not None and len(parse_action(action)) == 1:
        keys = keys[:1] * BLOCK  # closed loop: one decision = exactly one block
    while len(keys) % BLOCK:
        keys.append("none")
    return [keys[i:i + BLOCK] for i in range(0, len(keys), BLOCK)]


def keys_to_dsl(frame_keys: list[str]) -> str:
    out, i = [], 0
    while i < len(frame_keys):
        j = i
        while j < len(frame_keys) and frame_keys[j] == frame_keys[i]:
            j += 1
        out.append(f"{to_model_keys(frame_keys[i])}-{j - i}")
        i = j
    return ",".join(out)


class _Stop(Exception):
    pass


class Session:
    def __init__(self):
        self.q_in: queue.Queue = queue.Queue()
        self.q_out: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.frame_keys: list[str] = []
        self.last_frame: np.ndarray | None = None
        self.blocks_done = 0
        self.n_blocks = 0
        self.intr = None


class SanaStreamEngine:
    def __init__(self, args):
        import torch
        self.args = args
        self.torch = torch
        sana_root = Path(args.sana_root or os.environ.get("SANA_ROOT") or run_agent.DEFAULT_SANA_ROOT).resolve()
        if str(sana_root) not in sys.path:
            sys.path.insert(0, str(sana_root))
        import pyrallis
        from inference_video_scripts.wm import inference_sana_wm as wm
        from inference_video_scripts.wm import inference_sana_wm_streaming as st
        from inference_video_scripts.wm import streaming_pipeline as sp
        self.wm, self.st, self.sp = wm, st, sp
        env = os.environ.get
        self.rot = float(env("SANA_ROT_DEG", "0.9375"))
        self.trans = float(env("SANA_TRANS", str(wm.DEFAULT_TRANSLATION_SPEED)))
        self.cached_blocks = int(env("SANA_CACHED_BLOCKS", "2"))
        self.horizon = int(env("SANA_STREAM_FRAMES", "961"))
        self.horizon = (self.horizon - 1) // BLOCK * BLOCK + 1
        st._apply_fast_defaults()
        ns = argparse.Namespace(streaming_root=st.DEFAULT_STREAMING_ROOT, config=None, model_path=None,
                                causal_vae_path=None, refiner_root=None, refiner_gemma_root=None)
        config_path, model_path, causal_vae_path, refiner_root, gemma_root = st._resolve_streaming_paths(ns)
        config = pyrallis.parse(config_class=wm.InferenceConfig, config_path=str(config_path), args=[])
        config.vae.vae_type = "LTX2VAE_diffusers_causal"
        config.vae.vae_pretrained = str(causal_vae_path)
        refiner = wm.RefinerSettings(root=str(refiner_root), gemma_root=str(gemma_root), sink_size=1, seed=42,
                                     block_size=3, kv_max_frames=st.DEFAULT_REFINER_KV_MAX_FRAMES)
        self.pipeline = wm.SanaWMPipeline(config=config, model_path=str(model_path),
                                          device=torch.device("cuda"), refiner=refiner, logger=wm.get_root_logger())
        if env("SANA_COMPILE", "0") == "1":
            self.pipeline.refiner.transformer = torch.compile(
                self.pipeline.refiner.transformer, mode="max-autotune-no-cudagraphs", dynamic=True)
        # Upstream moves the VAE encoder to the CPU after the first frame is encoded (fine for one clip).
        # We open many sessions; a 1280x704 CPU encode takes minutes and looked like a hang. Keep it on GPU.
        self.pipeline._offload_vae_encoder_for_streaming = lambda: None
        self.steps = [int(t) for t in st.DEFAULT_DENOISING_STEP_LIST.split(",")]
        sp.run_streaming_inference = self._driver          # generate_streaming imports it at call time
        # Remember the sampler generate_streaming builds: it owns the camera tensors we rewrite per block.
        self._last_solver = [None]
        solver_cls, last = wm.SelfForcingFlowEulerCamCtrl, self._last_solver
        orig_init = solver_cls.__init__

        def init_and_remember(obj, *a, **kw):
            orig_init(obj, *a, **kw)
            last[0] = obj

        solver_cls.__init__ = init_and_remember
        self._tls = threading.local()
        self.sess: Session | None = None
        print(f"[sana_stream] ready: rot={self.rot} deg/frame ({self.rot * BLOCK:.1f}/block) "
              f"cached_blocks={self.cached_blocks} horizon={self.horizon} keymap={env('SANA_KEYMAP', 'head')}", flush=True)

    # ---- runs inside the session thread, called by pipeline.generate_streaming ------------
    def _driver(self, *, stage1_chunk_iter, n_stage1_chunks, z_init, refiner_runner, vae_streaming_decoder,
                pixel_h, pixel_w, config, logger=None):
        torch = self.torch
        sess: Session = self._tls.sess
        extra = self._last_solver[0]._extra_model_kwargs   # same thread built it just before calling us
        sink, block = int(config.sink_size), int(config.block_size)
        n_ref = max(int(z_init.shape[2]) - sink, 0) // block
        ends = tuple(int(v) for v in (config.stage1_chunk_ends or
                                      [sink + (i + 1) * block for i in range(n_stage1_chunks)]))
        latents = torch.empty_like(z_init)
        latents[:, :, :sink] = z_init[:, :, :sink]
        refined = torch.empty_like(z_init)
        refined[:, :, :sink] = z_init[:, :, :sink]
        vae_streaming_decoder.reset()
        stage_i, t0 = 0, time.perf_counter()
        sess.n_blocks = n_ref
        sess.q_out.put(("ready", n_ref))
        with torch.inference_mode():
            for k in range(n_ref):
                cam = sess.q_in.get()
                if cam is None:
                    raise _Stop()
                for name, key in (("camera_conditions", "raymap"), ("chunk_plucker", "chunk_plucker")):
                    dst = extra[name]
                    dst.copy_(cam[key].unsqueeze(0).to(dst.device, dtype=dst.dtype).expand_as(dst))
                b0, b1 = sink + k * block, sink + (k + 1) * block
                while stage_i < len(ends) and (stage_i == 0 or ends[stage_i - 1] < b1):
                    _, view, s, e = next(stage1_chunk_iter)
                    latents[:, :, s:e].copy_(view)
                    stage_i += 1
                out = refiner_runner.refine_block(block_idx=k, clean_block=latents[:, :, b0:b1], block_start=b0,
                                                  block_end=b1, sink_seed_frames=latents[:, :, :sink] if k == 0 else None)
                refined[:, :, b0:b1].copy_(out)
                pix = vae_streaming_decoder.decode_chunk(refined[:, :, :b1] if k == 0 else refined[:, :, b0:b1])
                arr = (pix.float() * 127.5 + 127.5).clamp(0, 255).to(torch.uint8)
                arr = arr.permute(0, 2, 3, 4, 1).contiguous().cpu().numpy()[0]
                if k == 0:
                    arr = arr[1:]
                sess.q_out.put(("frames", arr))
        wall = time.perf_counter() - t0
        return types.SimpleNamespace(
            output_path=None, n_pixel_frames=n_ref * BLOCK, n_refiner_blocks=n_ref, n_decode_chunks=n_ref,
            output_mode="cpu", wall_seconds=wall, first_chunk_seconds=None, first_chunk_frames=None,
            steady_state_seconds=None, steady_state_frames_per_second=None, steady_state_realtime_factor=None,
            frames_per_second=0.0, realtime_factor=0.0, stage1_cuda_seconds=None, refiner_cuda_seconds=None,
            decode_cuda_seconds=None, sample_frames_path=None, sampled_frame_count=0, sampled_frame_indices=None)

    # ---- session management (harness thread) ----------------------------------------------
    def _camera(self, sess: Session):
        wm = self.wm
        keys = sess.frame_keys + ["none"] * max(0, self.horizon - 1 - len(sess.frame_keys))
        c2w = wm.action_string_to_c2w(keys_to_dsl(keys), translation_speed=self.trans, rotation_speed_deg=self.rot)
        c2w = np.asarray(c2w)[:self.horizon]
        return wm.prepare_camera(c2w, sess.intr[:c2w.shape[0]], target_size=(wm.TARGET_HEIGHT, wm.TARGET_WIDTH),
                                 vae_stride=self.pipeline.config.vae.vae_stride)

    def _stop(self):
        sess, self.sess = self.sess, None
        if sess and sess.thread and sess.thread.is_alive():
            sess.q_in.put(None)
            sess.thread.join(timeout=120)

    def _start(self, image_path: str, prompt: str, intrinsics_path: str | None) -> Session:
        from PIL import Image
        wm = self.wm
        self._stop()
        sess = Session()
        encoder = getattr(self.pipeline.vae, "encoder", None)
        if encoder is not None:
            encoder.to(self.pipeline.device)
        image = Image.open(image_path).convert("RGB")
        cropped, src_size, resized_size, crop_offset = wm.resize_and_center_crop(image)
        if intrinsics_path:
            intr_src = wm.load_intrinsics(Path(intrinsics_path), 1)
        else:
            f = float(max(image.size))
            intr_src = np.array([[f, f, image.size[0] / 2.0, image.size[1] / 2.0]], dtype=np.float32)
        intr_src = np.repeat(np.asarray(intr_src, dtype=np.float32)[:1], self.horizon, axis=0)
        sess.intr = wm.transform_intrinsics_for_crop(intr_src, src_size, resized_size, crop_offset)
        sess.last_frame = np.asarray(cropped.convert("RGB"))
        c2w0 = np.repeat(np.eye(4, dtype=np.float32)[None], self.horizon, axis=0)
        params = wm.GenerationParams(num_frames=self.horizon, fps=self.args.fps, cfg_scale=1.0, flow_shift=8.0,
                                     seed=self.args.seed, negative_prompt="", sampling_algo="self_forcing",
                                     num_cached_blocks=self.cached_blocks, sink_token=True,
                                     num_frame_per_block=3, denoising_step_list=self.steps)

        def work():
            self._tls.sess = sess
            try:
                self.pipeline.generate_streaming(cropped, prompt or "A realistic scene.", c2w0, sess.intr, params,
                                                 output_path="/tmp/unused.mp4", output_mode="cpu")
                sess.q_out.put(("done", None))
            except _Stop:
                sess.q_out.put(("stopped", None))
            except BaseException as exc:  # surfaced on the harness thread
                import traceback
                traceback.print_exc()
                sess.q_out.put(("error", exc))

        sess.thread = threading.Thread(target=work, daemon=True)
        sess.thread.start()
        kind, val = sess.q_out.get(timeout=900)
        if kind != "ready":
            raise RuntimeError(f"SANA streaming session failed to start: {kind} {val}")
        self.sess = sess
        return sess

    def _continues(self, image_path: str) -> bool:
        from PIL import Image
        sess = self.sess
        if sess is None or sess.last_frame is None or not sess.thread.is_alive() or sess.blocks_done >= sess.n_blocks:
            return False
        cur = np.asarray(Image.open(image_path).convert("RGB"))
        if cur.shape != sess.last_frame.shape:
            return False
        return float(np.abs(cur.astype(np.int16) - sess.last_frame.astype(np.int16)).mean()) < 5.0

    def generate(self, image_path, prompt, action, output_dir, name, num_frames, intrinsics_path=None):
        output_dir = Path(output_dir)
        t0 = time.time()
        import faulthandler
        faulthandler.dump_traceback_later(240, exit=False)   # a stuck chunk prints every thread's stack
        try:
            return self._generate(image_path, prompt, action, output_dir, name, num_frames, intrinsics_path, t0)
        finally:
            faulthandler.cancel_dump_traceback_later()

    def _generate(self, image_path, prompt, action, output_dir, name, num_frames, intrinsics_path, t0):
        fresh = name.endswith("_chunk_01") or name.endswith("_full") or not self._continues(image_path)
        sess = self._start(image_path, prompt, intrinsics_path) if fresh else self.sess
        frames = [sess.last_frame]
        blocks = blocks_from_action(action, single_call_frames=num_frames)
        blocks = blocks[:max(0, sess.n_blocks - sess.blocks_done)]
        for keys in blocks:
            sess.frame_keys += keys
            sess.q_in.put(self._camera(sess))
            kind, val = sess.q_out.get(timeout=900)
            if kind != "frames":
                self.sess = None
                raise RuntimeError(f"SANA streaming session ended early: {kind} {val}")
            frames.extend(list(val))
            sess.blocks_done += 1
        sess.last_frame = frames[-1]
        print(f"    [sana_stream] {name}: {'new session' if fresh else 'continue'} blocks={len(blocks)} "
              f"t={sess.blocks_done * BLOCK / 16:.1f}s gen={time.time() - t0:.1f}s", flush=True)
        import imageio
        out = output_dir / f"{name}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        imageio.mimsave(str(out), frames, fps=self.args.fps, quality=9, macro_block_size=1)
        return out


if __name__ == "__main__":
    import importlib.util
    if importlib.util.find_spec("flash_attn") is None:
        os.environ.setdefault("SANA_WM_REFINER_SELF_ATTN_KERNEL", "sdpa")
    player_cfg, sys.argv = agent_api.configure(sys.argv)  # --player-* runner args (agent_api docstring)
    run_agent.SanaWMEngine = SanaStreamEngine
    print(f"[adapter] agent provider: {agent_api.patch(run_agent, player_cfg)}", flush=True)
    rc = run_agent.main()
    agent_api.finish(run_agent)
    raise SystemExit(rc)
