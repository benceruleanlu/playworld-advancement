#!/usr/bin/env python3
"""LingBot-World v2 (causal-fast) runner: upstream closed-loop harness with LingBot swapped in for SANA-WM.

Same argv as run_agent.py. `pwa gen EXP --runner lingbot_world2 ...` (14B) or
`--runner lingbot_world2_1p3b` (1.3B, for cheap iteration).

Default: a persistent session (session.py). The harness calls generate() once per
chunk; when the call is the next chunk of the same task (`<task>_chunk_<NN>`) the
session continues, so LingBot's KV cache (its only memory) spans the whole
closed-loop rollout. Chunk 01, another task or a `<task>_full` (dataset mode) call
resets it. Dataset mode is reset plus one long step.

Stateless A/B baseline: `--lingbot-stateless` (stripped before run_agent parses
argv) or LINGBOT_SESSION=0: every call is a fresh upstream rollout from image_path.

Turn calibration (off by default): `--lingbot-turn-cal` or LINGBOT_TURN_CAL=1 sets the
arrow-key rates so one dataset token turns 22.5 deg (yaw) / 20 deg (pitch); see poses.calibrate.

Caption prompt (off by default): `--lingbot-caption-prompt` or LINGBOT_PROMPT_MODE=auto conditions
the model on the task's scene caption instead of the agent goal ("wait and observe" for Insight);
see adapters/common/prompts.py. The agent player still gets the goal.

Re-anchoring (off by default, session mode only): `--lingbot-reanchor` or LINGBOT_REANCHOR=1.
When the commanded camera track of a GC task returns to the start pose, the input image is
given to the model again at that latent; see session.ReturnDetector.

Player hint (off by default): `--lingbot-player-hint` or LINGBOT_PLAYER_HINT=1 tells the
closed-loop player how far one action turns the camera and where the commanded camera
is relative to the start; see player_hint.py. The world model's inputs do not change.

Return stop (off by default): `--lingbot-return-stop` or LINGBOT_RETURN_STOP=1 ends a closed-loop
rollout (WAIT for LINGBOT_RETURN_STOP_HOLD chunks, then END) once the commanded camera has left
and come back to the start, on goals that end with a return; see return_stop.py.

Env:
  LINGBOT_ROOT      checkout of Robbyant/lingbot-world-v2 (default /opt/lingbot)
  LINGBOT_WEIGHTS   dir holding lingbot-world-v2-{14b,1.3b}-causal-fast (default /weights/lingbot)
  LINGBOT_VARIANT   14b (default) | 1.3b
  LINGBOT_T5_CPU    1 keeps the 11 GB text encoder off the GPU (default: 1 for 14b, 0 for 1.3b)
  LINGBOT_YAW_RAD / LINGBOT_PITCH_RAD   per-frame camera rotation for arrow keys (poses.py)
  LINGBOT_TURN_CAL  1 = same as --lingbot-turn-cal (overrides the two rates above)
  LINGBOT_UNIT_YAW_DEG / LINGBOT_UNIT_PITCH_DEG / LINGBOT_CHUNK_UNITS   turn-cal angles (22.5 / 20 / 2)
  LINGBOT_PROMPT_MODE  goal (default) | caption | auto (= --lingbot-caption-prompt)
  LINGBOT_REANCHOR  1 = same as --lingbot-reanchor
  LINGBOT_REANCHOR_TASKS  regex matched at the start of the call name (default GC)
  LINGBOT_REANCHOR_DEG / LINGBOT_REANCHOR_TRANS   return tolerance: degrees / key units (6 / 2)
  LINGBOT_PLAYER_HINT  1 = same as --lingbot-player-hint
  LINGBOT_RETURN_STOP  1 = same as --lingbot-return-stop
  LINGBOT_RETURN_STOP_HOLD / LINGBOT_RETURN_STOP_FRAC   WAIT chunks before END (2) / share of the goal's angle
                    or steps that counts as having left (0.75)
  LINGBOT_SESSION   0 = stateless (same as --lingbot-stateless)
  LINGBOT_STREAM_DECODE  0 = re-decode all latents each step instead of streaming the VAE cache

Start-up (fast_start.py): `[lingbot] timing <part> <s>s` lines for each load component and for the
reset and first step of every rollout, always on. Opt-in, all off by default:
  --lingbot-fast-t5    (LINGBOT_FAST_T5=1)   prompt-embedding cache on the weights volume; T5 loads
                       only on a cache miss. Cache dir: LINGBOT_T5_CACHE_DIR (default $LINGBOT_WEIGHTS/t5_cache)
  --lingbot-fast-load  (LINGBOT_FAST_LOAD=1) parallel read-ahead of the checkpoint files during the
                       load (LINGBOT_READ_AHEAD_THREADS, default 8); T5 built on meta + mmap state dict
  --lingbot-fast-y     (LINGBOT_FAST_Y=1)    session mode: stream-encode `y` as the rollout advances
  --lingbot-fast       (LINGBOT_FAST=1)      all three
  --lingbot-t5-gpu     T5 on the GPU (same as LINGBOT_T5_CPU=0; changes embeddings at bf16 rounding level)

In-process use (pwa gen-arms): main(argv) can be called several times in one process. Each call re-reads
the flags and env, resets poses' turn rates, the flag counters and prompts' current task, and imports a
fresh upstream run_agent (so no patch stacks); only the loaded pipe (_PIPES, keyed by checkpoint, T5
placement and KV window) is shared, and each call's engine builds its own session.
The fast-start flags are per call too: --lingbot-fast-y / --lingbot-fast-t5's disk cache follow each call's
flags, while the load-time parts (read-ahead, meta T5, lazy T5) only apply to the call that loads the pipe;
the loader patches are undone after that load, so they never stack.

Flag counters (flag_stats.py): after each task one greppable line, e.g.
  [lingbot] flags task=GC033 turn_cal=1 caption=used reanchor=on reanchor_events=2 player_hint=on player_hints=30
and a `[lingbot] flags total ...` line at the end; also "lingbot_flags" in <task>_result.json.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.common import agent_api, prompts  # noqa: E402
from adapters.common.upstream import import_run_agent  # noqa: E402
from adapters.lingbot_world2 import fast_start as FS  # noqa: E402
from adapters.lingbot_world2 import flag_stats  # noqa: E402
from adapters.lingbot_world2 import player_hint as H  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import return_stop as RS  # noqa: E402
from adapters.lingbot_world2 import session as S  # noqa: E402

_FLAG_ARGS = ("--lingbot-stateless", "--lingbot-turn-cal", "--lingbot-caption-prompt",
              "--lingbot-reanchor", "--lingbot-player-hint", "--lingbot-return-stop")


def configure(argv: list[str], environ=os.environ) -> tuple[dict, list[str]]:
    """The --lingbot-* flags (or their env vars) in argv, and argv without them. Read once per main() call,
    so a process that runs several arms (pwa gen-arms) sees each arm's own flags."""
    mode = "auto" if "--lingbot-caption-prompt" in argv else environ.get("LINGBOT_PROMPT_MODE", "goal")
    if mode not in prompts.MODES:
        raise SystemExit(f"LINGBOT_PROMPT_MODE must be one of {prompts.MODES}, got {mode!r}")
    flags = {
        "stateless": "--lingbot-stateless" in argv or environ.get("LINGBOT_SESSION", "1") == "0",
        "turn_cal": "--lingbot-turn-cal" in argv or environ.get("LINGBOT_TURN_CAL", "0") == "1",
        "prompt_mode": mode,
        "reanchor": "--lingbot-reanchor" in argv or environ.get("LINGBOT_REANCHOR", "0") == "1",
        "player_hint": "--lingbot-player-hint" in argv or environ.get("LINGBOT_PLAYER_HINT", "0") == "1",
        "return_stop": "--lingbot-return-stop" in argv or environ.get("LINGBOT_RETURN_STOP", "0") == "1",
        "fast": FS.parse_flags(argv, environ),
    }
    return flags, FS.strip_flags([a for a in argv if a not in _FLAG_ARGS])


# Set by main() from configure(); the engine reads them at call time.
STATELESS = TURN_CAL = REANCHOR = PLAYER_HINT = RETURN_STOP = False
PROMPT_MODE = "goal"
FAST = FS.FastFlags()
STATS = flag_stats.FlagStats(False, "goal", False, False)

MAX_AREA = 480 * 832  # the released checkpoints' reference resolution
LOCAL_ATTN, SINK = 18, 6  # README settings for causal-fast
DEFAULT_PROMPT = "A photo-realistic scene with rich details."
_PIPES: dict = {}  # loaded wan.WanI2VCausal by checkpoint and window


def load_pipe(environ=os.environ):
    """(config, pipe, weights dir, t5_cpu) for the checkpoint the env selects, loading the pipe on first use in
    this process with the current fast-start flags (FAST). Shared by every engine in the process (pwa gen-arms)
    and called ahead of time by warm_app.py's @modal.enter."""
    root = environ.get("LINGBOT_ROOT", "/opt/lingbot")
    weights = Path(environ.get("LINGBOT_WEIGHTS", "/weights/lingbot"))
    variant = environ.get("LINGBOT_VARIANT", "14b").lower()
    if variant not in ("14b", "1.3b"):
        raise SystemExit(f"LINGBOT_VARIANT must be 14b or 1.3b, got {variant!r}")
    ckpt = weights / f"lingbot-world-v2-{variant}-causal-fast"
    # The 1.3B release ships DiT shards only; T5, VAE and tokenizer come from the 14B dir.
    assets = weights / "lingbot-world-v2-14b-causal-fast" if variant == "1.3b" else None
    for p in (Path(root) / "wan", ckpt, *( [assets] if assets else [])):
        if not p.exists():
            raise SystemExit(f"[lingbot] missing {p}; set LINGBOT_ROOT / LINGBOT_WEIGHTS or run prefetch_lingbot.py")
    t5_cpu = environ.get("LINGBOT_T5_CPU", "1" if variant == "14b" else "0") == "1" and not FAST.t5_gpu

    t0 = time.time()
    if root not in sys.path:
        sys.path.insert(0, root)
    import wan  # noqa: PLC0415
    import wan.image2video as i2v  # noqa: PLC0415
    from wan.configs import WAN_CONFIGS  # noqa: PLC0415
    FS.log("load.import_wan", time.time() - t0)

    cfg = WAN_CONFIGS["i2v-1.3B" if variant == "1.3b" else "i2v-A14B"]
    key = (root, str(ckpt), str(assets), t5_cpu, LOCAL_ATTN, SINK)
    if key not in _PIPES:  # one load per process: pwa gen-arms runs several arms on the same pipe
        print(f"[lingbot] fast start: {FAST.describe()}", flush=True)
        with FS.patched_loaders(i2v, lazy_t5=FAST.t5_cache, fast_load=FAST.fast_load) as timer:
            if FAST.fast_load:
                FS.read_ahead(FS.checkpoint_files(cfg, ckpt, assets, include_t5=not FAST.t5_cache),
                              threads=int(environ.get("LINGBOT_READ_AHEAD_THREADS", "8")))
            t0 = time.time()
            _PIPES[key] = wan.WanI2VCausal(
                config=cfg, checkpoint_dir=str(ckpt), device_id=0, rank=0, t5_cpu=t5_cpu,
                local_attn_size=LOCAL_ATTN, sink_size=SINK, infer_mode="causal_fast",
                assets_dir=str(assets) if assets else None)
            timer.rest(time.time() - t0)
        print(f"[lingbot] loaded {variant} from {ckpt} in {time.time() - t0:.0f}s (t5_cpu={t5_cpu})", flush=True)
    else:
        print(f"[lingbot] reusing {variant} loaded earlier in this process (t5_cpu={t5_cpu}); "
              f"fast start {FAST.describe()} (load-time parts apply only to the first load)", flush=True)
    return cfg, _PIPES[key], weights, t5_cpu


class LingBotWorld2Engine:
    """Drop-in for run_agent.SanaWMEngine."""

    def __init__(self, args):
        self.args = args
        self.cfg, self.pipe, weights, t5_cpu = load_pipe()
        self.t5_cache = self._t5_cache(weights, t5_cpu) if FAST.t5_cache else None
        self.session = None
        if not STATELESS:
            self.session = S.LingBotSession(self.pipe, MAX_AREA, self.cfg.sample_shift,
                                            horizon_frames=int(getattr(args, "max_total_frames", 961) or 961),
                                            stream_encode=FAST.fast_y, t5_cache=self.t5_cache)
        self._last_chunk = None
        print(f"[lingbot] mode: {'stateless' if STATELESS else 'session'}"
              + ("" if STATELESS else f" (stream_decode={self.session.stream_decode})")
              + (f", turn-cal {P.UNIT_YAW_DEG}/{P.UNIT_PITCH_DEG} deg per token" if TURN_CAL else "")
              + ("" if PROMPT_MODE == "goal" else f", prompt mode {PROMPT_MODE}")
              + ((", re-anchor ignored (stateless)" if STATELESS else ", re-anchor on") if REANCHOR else "")
              + (", player hint on" if PLAYER_HINT else "")
              + (", return stop on" if RETURN_STOP else ""),
              flush=True)

    def _t5_cache(self, weights, t5_cpu):
        """--lingbot-fast-t5: disk cache keyed by prompt + everything that decides T5's output bits."""
        import torch  # noqa: PLC0415
        enc = self.pipe.text_encoder
        ident = FS.t5_identity(
            enc.checkpoint_path, enc.tokenizer_path, enc.text_len, enc.dtype,
            device_kind="cpu" if t5_cpu else "cuda",
            device_name=FS.cpu_model() if t5_cpu else torch.cuda.get_device_name(self.pipe.device),
            torch_version=torch.__version__, num_threads=torch.get_num_threads() if t5_cpu else None)
        root = Path(os.environ.get("LINGBOT_T5_CACHE_DIR", str(weights / "t5_cache")))
        print(f"[lingbot] t5 cache: {root} identity {ident}", flush=True)
        return FS.EmbeddingCache(root, ident)

    def _calibrate(self, name, n_keys):
        """--lingbot-turn-cal: arrow-key rates from dataset token angles (poses.calibrate)."""
        if TURN_CAL:
            P.calibrate(S.parse_chunk_name(name) is None, n_keys,
                        int(getattr(self.args, "action_frame_unit", 20) or 20))

    def generate(self, image_path, prompt, action, output_dir, name, num_frames, intrinsics_path=None):
        if PROMPT_MODE != "goal":
            goal, prompt = prompt, prompts.model_prompt(prompt, name, PROMPT_MODE)
            STATS.caption(prompt != goal)
            if (S.parse_chunk_name(name) or (name, 1))[1] == 1:  # once per rollout
                print(f"[lingbot] {name}: prompt mode {PROMPT_MODE}, "
                      f"{'caption' if prompt != goal else 'goal (no caption found)'}: {prompt[:120]!r}", flush=True)
        if self.session is None:
            return self._generate_stateless(image_path, prompt, action, output_dir, name, num_frames)
        return self._generate_session(image_path, prompt, action, output_dir, name, num_frames)

    def _generate_session(self, image_path, prompt, action, output_dir, name, num_frames):
        """Continue (or reset and start) the persistent session; write <output_dir>/<name>.mp4.
        Frame counts follow session.frames_returned (33 -> 29 first, 33 after)."""
        import imageio  # noqa: PLC0415
        import torch  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        parsed = S.parse_chunk_name(name)
        cont = self.session.started and S.is_continuation(self._last_chunk, parsed)
        self._last_chunk = None  # stays None if this call fails, so the next one resets
        n = S.chunks_for(num_frames)
        keys = S.fit_keys(P.parse_action(action), S.keys_needed(n, first=not cont))
        self._calibrate(name, len(keys))
        t0 = time.time()
        torch.cuda.reset_peak_memory_stats()
        if not cont:
            horizon = max(int(num_frames), int(getattr(self.args, "max_total_frames", 961) or 961))
            reanchor = REANCHOR and S.reanchor_task(name)
            self.session.reset(Image.open(image_path).convert("RGB"), prompt or DEFAULT_PROMPT,
                               int(self.args.seed), horizon_frames=horizon,
                               reanchor=reanchor)
            if reanchor:
                STATS.armed()
        start = self.session.chunk_id
        anchored = self.session.reanchor_events
        frames = self.session.step(keys)
        STATS.reanchored(self.session.reanchor_events - anchored)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"{name}.mp4"
        imageio.mimsave(str(out), list(frames), fps=int(self.args.fps))
        self._last_chunk = parsed
        dt = time.time() - t0
        print(f"[lingbot] {name}: {'continue' if cont else 'reset'} latent chunks {start}->{self.session.chunk_id} "
              f"{len(frames)} frames {frames.shape[2]}x{frames.shape[1]} in {dt:.1f}s ({len(frames) / dt:.1f} fps), "
              f"peak VRAM {torch.cuda.max_memory_allocated() / 2**30:.1f} GiB", flush=True)
        return out

    def _generate_stateless(self, image_path, prompt, action, output_dir, name, num_frames):
        """Write <output_dir>/<name>.mp4 continuing from image_path under `action`.

        `action` is run_agent's SANA-style string: comma-separated "<key>-<frames>"
        (w/s/a/d move, i/k/j/l look up/down/left/right, none = wait). The harness
        intrinsics are ignored: LingBot expects its own 480p calibration.
        The clip may be a few frames longer than num_frames (see poses.frame_count).
        """
        import imageio  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        output_dir = Path(output_dir)
        action_dir = output_dir / f"{name}_action"
        action_dir.mkdir(parents=True, exist_ok=True)
        self._calibrate(name, P.frame_count(int(num_frames)) - 1)
        c2ws = P.build_poses(action, int(num_frames))
        np.save(action_dir / "poses.npy", c2ws)
        np.save(action_dir / "intrinsics.npy", P.intrinsics(len(c2ws)))

        S.encode_prompt(self.pipe, prompt or DEFAULT_PROMPT, self.t5_cache)  # fills pipe._t5_cache as upstream would
        t0 = time.time()
        torch.cuda.reset_peak_memory_stats()
        video = self.pipe.generate(
            prompt or DEFAULT_PROMPT, Image.open(image_path).convert("RGB"), action_path=str(action_dir),
            chunk_size=P.LATENT_CHUNK, max_area=MAX_AREA, frame_num=len(c2ws),
            shift=self.cfg.sample_shift, seed=int(self.args.seed), offload_model=False)
        frames = ((video.clamp(-1, 1) + 1) * 127.5).round().to(torch.uint8).permute(1, 2, 3, 0).cpu().numpy()
        del video
        out = output_dir / f"{name}.mp4"
        imageio.mimsave(str(out), list(frames), fps=int(self.args.fps))
        dt = time.time() - t0
        print(f"[lingbot] {name}: stateless {len(frames)} frames {frames.shape[2]}x{frames.shape[1]} in {dt:.1f}s "
              f"({len(frames) / dt:.1f} fps), peak VRAM {torch.cuda.max_memory_allocated() / 2**30:.1f} GiB", flush=True)
        return out


def main(argv: list[str] | None = None) -> int:
    """One run_agent invocation. argv is run_agent's (argv[0] is the script). Every call re-reads the flags,
    resets the turn rates and imports a fresh run_agent, so patches and counters never carry over; only the
    loaded pipe (_PIPES) is shared between calls in one process."""
    global STATELESS, TURN_CAL, PROMPT_MODE, REANCHOR, PLAYER_HINT, RETURN_STOP, STATS, FAST
    flags, sys.argv = configure(list(sys.argv if argv is None else argv))
    STATELESS, TURN_CAL, PROMPT_MODE = flags["stateless"], flags["turn_cal"], flags["prompt_mode"]
    REANCHOR, PLAYER_HINT, FAST = flags["reanchor"], flags["player_hint"], flags["fast"]
    RETURN_STOP = flags["return_stop"]
    STATS = flag_stats.FlagStats(TURN_CAL, PROMPT_MODE, REANCHOR, PLAYER_HINT, RETURN_STOP)
    P.reset()
    prompts.reset()
    run_agent = import_run_agent(fresh=True)
    run_agent.SanaWMEngine = LingBotWorld2Engine
    prompts.install(run_agent)
    STATS.install(run_agent)
    print(f"[adapter] agent provider: {agent_api.patch(run_agent)}", flush=True)
    if PLAYER_HINT:
        run_agent.decide_action = H.wrap(run_agent.decide_action, run_agent.to_sana_key,
                                         session=not STATELESS, turn_cal=TURN_CAL, on_hint=STATS.hint)
        print("[lingbot] player hint: on", flush=True)
    if RETURN_STOP:  # outermost: a stopped step never reaches the player (or the hint)
        run_agent.decide_action = RS.wrap(run_agent.decide_action, run_agent.to_sana_key, session=not STATELESS,
                                          turn_cal=TURN_CAL, on_event=STATS.return_stop_event)
        print("[lingbot] return stop: on", flush=True)
    rc = run_agent.main()
    print(STATS.total_line(), flush=True)
    return rc or 0


if __name__ == "__main__":
    raise SystemExit(main())
