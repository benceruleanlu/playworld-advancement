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

GC completion hint (off by default): `--lingbot-gc-completion-hint` or
LINGBOT_GC_COMPLETION_HINT=1 reminds the player to finish the requested path once, then
END on visual completion. Counts hints and END replies; never forces an action.

IF horizon (off by default): `--lingbot-if-horizon` or LINGBOT_IF_HORIZON=1 ends a closed-loop IF
rollout after a chunk budget sized from the length of its dataset action; see if_horizon.py.

IF camera hint (off by default): `--lingbot-if-camera-hint` or LINGBOT_IF_CAMERA_HINT=1 reminds
third-person IF players that keys command the camera, not the subject; see if_camera.py.

Player history endpoints (off by default): `--lingbot-player-history-endpoints` or
LINGBOT_PLAYER_HISTORY_ENDPOINTS=1 keeps only the first and last sampled frame of each older chunk in
the player's input (the latest chunk keeps all eight); see player_history.py.

Insight director (off by default): `--lingbot-insight-director` or LINGBOT_INSIGHT_DIRECTOR=1 conditions
the model on the scene caption plus a fixed activity-continuation cue on insight tasks only (implies the
caption on those tasks, even without --lingbot-caption-prompt); see prompts.directed_insight.

IF repeat check (off by default): `--lingbot-if-repeat-check` or LINGBOT_IF_REPEAT_CHECK=1: after four
identical IF actions, the player is asked to recheck visible goal progress; see if_repeat.py.

IF slow translation (off by default, session only): `--lingbot-if-slow-translation` or
LINGBOT_IF_SLOW_TRANSLATION=1 halves IF per-frame camera translation before normalisation (and in the
player hint's replay); rejected with --lingbot-stateless.

decide_action wrappers, innermost first: player hint, IF repeat check, IF camera hint, GC completion hint,
return stop, IF horizon. The goal the player reads is therefore goal + GC completion | (IF camera, then
IF repeat) + player hint; return stop and IF horizon answer without asking the player, so their WAIT/END
replies never reach the hints or their counters.

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
  LINGBOT_GC_COMPLETION_HINT  1 = same as --lingbot-gc-completion-hint
  LINGBOT_IF_HORIZON  1 = same as --lingbot-if-horizon
  LINGBOT_IF_HORIZON_MULT / LINGBOT_IF_HORIZON_MIN   budget = MULT x the dataset action's frames (2), at least MIN chunks (6)
  LINGBOT_IF_CAMERA_HINT  1 = same as --lingbot-if-camera-hint
  LINGBOT_PLAYER_HISTORY_ENDPOINTS  1 = same as --lingbot-player-history-endpoints
  LINGBOT_INSIGHT_DIRECTOR  1 = same as --lingbot-insight-director
  LINGBOT_IF_REPEAT_CHECK  1 = same as --lingbot-if-repeat-check
  LINGBOT_IF_SLOW_TRANSLATION  1 = same as --lingbot-if-slow-translation
  LINGBOT_SESSION   0 = stateless (same as --lingbot-stateless)
  LINGBOT_STREAM_DECODE  0 = re-decode all latents each step instead of streaming the VAE cache

Stall watchdog (watchdog.py), per generate() call: `--lingbot-stall-dump N` (LINGBOT_STALL_DUMP_S, default
300, 0 = off) dumps every thread's stack to stderr once a call has run N s, and every N s after;
`--lingbot-stall-abort N` (LINGBOT_STALL_ABORT_S, default 0 = off) dumps, prints `[lingbot] stall:` and
exits the process with 124 after N s. The process is this runner: under pwa gen-arms that is the whole
shard, so an abort drops every remaining arm and family of the shard.

Start-up (fast_start.py): `[lingbot] timing <part> <s>s` lines for each load component and for the
reset and first step of every rollout, always on. Opt-in, all off by default:
  --lingbot-fast-t5    (LINGBOT_FAST_T5=1)   prompt-embedding cache on the weights volume; T5 loads
                       only on a cache miss. Cache dir: LINGBOT_T5_CACHE_DIR (default $LINGBOT_WEIGHTS/t5_cache)
  --lingbot-fast-load  (LINGBOT_FAST_LOAD=1) parallel read-ahead of the checkpoint files during the
                       load (LINGBOT_READ_AHEAD_THREADS, default 8); T5 built on meta + mmap state dict
  --lingbot-fast-y     (LINGBOT_FAST_Y=1)    session mode: stream-encode `y` as the rollout advances
  --lingbot-fast       (LINGBOT_FAST=1)      all three plus --lingbot-fast-dit
  --lingbot-t5-gpu     T5 on the GPU (same as LINGBOT_T5_CPU=0; changes embeddings at bf16 rounding level)
  --lingbot-fast-dit   (LINGBOT_FAST_DIT=1)  DiT built on meta, tensors copied to the GPU and cast there
                       (LINGBOT_DIT_LOAD_THREADS shards at a time, default 4); bit-identical weights on 14B
                       (checksum and sample verify on an H100); any error falls back to the upstream loader
  --lingbot-cpu-threads[=N]  (LINGBOT_CPU_THREADS=N|auto)  torch CPU threads (auto: usable CPUs); may change
                       CPU T5 bits, so not in --lingbot-fast. A `[lingbot] cpu {...}` line is always printed.
                       In-memory prompt embeddings are dropped when the count differs from the previous call's.
  --lingbot-dit-checksum  (LINGBOT_DIT_CHECKSUM=1)  log a DiT parameter checksum after the load (and, with
                       fast-dit, compare sampled tensors with a CPU cast)

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
Player counters (adapters/common/agent_api.py, every runner): `[agent] player task=... decisions= calls= empty=
retries= errors= fallbacks=` per task, `[agent] player total ...` at the end, "player" in <task>_result.json.
The --player-* args (completion budget, reasoning effort, empty-reply retries) are read there too.
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
from adapters.lingbot_world2 import gc_director as D  # noqa: E402
from adapters.lingbot_world2 import gc_completion as C  # noqa: E402
from adapters.lingbot_world2 import if_camera as IC  # noqa: E402
from adapters.lingbot_world2 import if_horizon as IH  # noqa: E402
from adapters.lingbot_world2 import if_repeat as IR  # noqa: E402
from adapters.lingbot_world2 import player_hint as H  # noqa: E402
from adapters.lingbot_world2 import player_history as PH  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import return_stop as RS  # noqa: E402
from adapters.lingbot_world2 import session as S  # noqa: E402
from adapters.lingbot_world2 import watchdog as W  # noqa: E402

_FLAG_ARGS = ("--lingbot-stateless", "--lingbot-turn-cal", "--lingbot-caption-prompt",
              "--lingbot-reanchor", "--lingbot-player-hint", "--lingbot-return-stop",
              "--lingbot-gc-completion-hint", "--lingbot-if-horizon", "--lingbot-if-camera-hint",
              "--lingbot-player-history-endpoints", "--lingbot-insight-director", "--lingbot-if-repeat-check",
              "--lingbot-if-slow-translation", "--lingbot-gc-chunk-director")


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
        "gc_completion": "--lingbot-gc-completion-hint" in argv or environ.get("LINGBOT_GC_COMPLETION_HINT", "0") == "1",
        "if_horizon": "--lingbot-if-horizon" in argv or environ.get("LINGBOT_IF_HORIZON", "0") == "1",
        "if_camera": "--lingbot-if-camera-hint" in argv or environ.get("LINGBOT_IF_CAMERA_HINT", "0") == "1",
        "history_endpoints": "--lingbot-player-history-endpoints" in argv
                             or environ.get("LINGBOT_PLAYER_HISTORY_ENDPOINTS", "0") == "1",
        "insight_director": "--lingbot-insight-director" in argv
                            or environ.get("LINGBOT_INSIGHT_DIRECTOR", "0") == "1",
        "if_repeat": "--lingbot-if-repeat-check" in argv or environ.get("LINGBOT_IF_REPEAT_CHECK", "0") == "1",
        "if_slow": "--lingbot-if-slow-translation" in argv
                   or environ.get("LINGBOT_IF_SLOW_TRANSLATION", "0") == "1",
        "gc_director": "--lingbot-gc-chunk-director" in argv or environ.get("LINGBOT_GC_CHUNK_DIRECTOR", "0") == "1",
        "fast": FS.parse_flags(argv, environ),
    }
    if flags["gc_director"] and (mode == "goal" or flags["stateless"]):
        raise SystemExit("--lingbot-gc-chunk-director requires caption prompting and session mode")
    flags["stall"], argv = W.parse(argv, environ)
    if flags["if_slow"] and flags["stateless"]:
        raise SystemExit("--lingbot-if-slow-translation requires session mode (stateless normalizes away scale)")
    flags["player"], argv = agent_api.configure(argv, environ)
    return flags, FS.strip_flags([a for a in argv if a not in _FLAG_ARGS])


# Set by main() from configure(); the engine reads them at call time.
GC_DIRECTOR = False  # --lingbot-gc-chunk-director / LINGBOT_GC_CHUNK_DIRECTOR=1, off by default
STATELESS = TURN_CAL = REANCHOR = PLAYER_HINT = RETURN_STOP = GC_COMPLETION = IF_HORIZON = False
PROMPT_MODE = "goal"
FAST = FS.FastFlags()
CPU_THREADS = None  # FS.thread_tag of this call's --lingbot-cpu-threads (None = torch's default)
STALL = W.Limits()
STATS = flag_stats.FlagStats(False, "goal", False, False)

MAX_AREA = 480 * 832  # the released checkpoints' reference resolution
LOCAL_ATTN, SINK = 18, 6  # README settings for causal-fast
DEFAULT_PROMPT = "A photo-realistic scene with rich details."
_PIPES: dict = {}  # loaded wan.WanI2VCausal by checkpoint and window


def _print_cpu():
    """Always-on diagnostic: what decides torch's CPU thread count in this container."""
    try:
        print(f"[lingbot] cpu {FS.cpu_report()}", flush=True)
    except ImportError:  # no torch (tests)
        pass


def _cuda0():
    import torch  # noqa: PLC0415
    return torch.device("cuda", 0) if torch.cuda.is_available() else None


def _check_dit(model):
    """--lingbot-dit-checksum: parameter checksum, plus a sample compared with a CPU cast (fast-dit only)."""
    t0 = time.time()
    digest, n = FS.dit_checksum(model)
    print(f"[lingbot] dit checksum {digest} ({n} tensors, {time.time() - t0:.1f}s)", flush=True)
    info = getattr(model, "_lingbot_fast_dit", None)
    if info:
        same, checked = FS.verify_dit_sample(model, info["shards"], info["dtype"])
        print(f"[lingbot] dit verify {same}/{checked} sampled tensors bit-identical to the CPU cast "
              f"({'ok' if same == checked else 'MISMATCH'})", flush=True)


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
        _print_cpu()
        dit_dev = _cuda0() if FAST.fast_dit else None
        with FS.patched_loaders(i2v, lazy_t5=FAST.t5_cache, fast_load=FAST.fast_load, fast_dit_device=dit_dev,
                                dit_threads=int(environ.get("LINGBOT_DIT_LOAD_THREADS", "4"))) as timer:
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
        if FAST.dit_checksum:
            _check_dit(_PIPES[key].model)
    else:
        print(f"[lingbot] reusing {variant} loaded earlier in this process (t5_cpu={t5_cpu}); "
              f"fast start {FAST.describe()} (load-time parts apply only to the first load)", flush=True)
    return cfg, _PIPES[key], weights, t5_cpu


class LingBotWorld2Engine:
    """Drop-in for run_agent.SanaWMEngine."""

    def __init__(self, args):
        self.args = args
        self.cfg, self.pipe, weights, t5_cpu = load_pipe()
        # upstream's in-memory embeddings are keyed by prompt only: drop them when the CPU T5 thread count changed
        FS.partition_t5_memory(self.pipe, CPU_THREADS if t5_cpu else "gpu")
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
              + (", return stop on" if RETURN_STOP else "")
              + (", GC completion hint on" if GC_COMPLETION else "")
              + (", gc-chunk-director on" if GC_DIRECTOR else "")
              + (", IF horizon on" if IF_HORIZON else "")
              + (", IF camera hint on" if STATS.if_camera else "")
              + (", player history endpoints on" if STATS.history_endpoints else "")
              + (", insight director on" if STATS.insight_director else "")
              + (", IF repeat check on" if STATS.if_repeat else "")
              + (", IF slow translation on (gain 0.5)" if STATS.if_slow else "")
              + f", stall watchdog {STALL.describe()}",
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
        original_prompt = prompt
        if PROMPT_MODE != "goal":
            goal, prompt = prompt, prompts.model_prompt(prompt, name, PROMPT_MODE)
            STATS.caption(prompt != goal)
            if (S.parse_chunk_name(name) or (name, 1))[1] == 1:  # once per rollout
                print(f"[lingbot] {name}: prompt mode {PROMPT_MODE}, "
                      f"{'caption' if prompt != goal else 'goal (no caption found)'}: {prompt[:120]!r}", flush=True)
        if STATS.insight_director:  # insight tasks: caption + fixed cue (adds the caption even in goal mode)
            directed = prompts.directed_insight(prompt, name)
            STATS.director_prompt(directed != prompt)
            if directed != prompt and (S.parse_chunk_name(name) or (name, 1))[1] == 1:  # once per rollout
                print(f"[lingbot] {name}: insight director: {directed[:120]!r}", flush=True)
            prompt = directed
        if GC_DIRECTOR and prompt != original_prompt:
            directed = D.compose(prompt, name, action)
            STATS.gc_director_chunks += directed != prompt
            prompt = directed
        with W.watch(name, STALL):
            if self.session is None:
                return self._generate_stateless(image_path, prompt, action, output_dir, name, num_frames)
            return self._generate_session(image_path, prompt, action, output_dir, name, num_frames)

    def _configure_if_motion(self, name, keys):
        slow = STATS.if_slow and str(name).startswith("IF")
        self.session.track.translation_gain = 0.5 if slow else 1.0
        if slow:
            STATS.if_scaled(sum(bool(set(k.lower().split("+")) & {"w", "s", "a", "d"}) for k in keys))

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
        self._configure_if_motion(name, keys)
        if cont and GC_DIRECTOR and name.startswith("GC"):
            STATS.gc_director_updates += self.session.update_prompt(prompt or DEFAULT_PROMPT)
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
    global STATELESS, TURN_CAL, PROMPT_MODE, REANCHOR, PLAYER_HINT, RETURN_STOP, GC_COMPLETION, STATS, FAST
    global CPU_THREADS, STALL, IF_HORIZON, GC_DIRECTOR
    flags, sys.argv = configure(list(sys.argv if argv is None else argv))
    STATELESS, TURN_CAL, PROMPT_MODE = flags["stateless"], flags["turn_cal"], flags["prompt_mode"]
    REANCHOR, PLAYER_HINT, FAST = flags["reanchor"], flags["player_hint"], flags["fast"]
    RETURN_STOP, GC_COMPLETION, STALL = flags["return_stop"], flags["gc_completion"], flags["stall"]
    IF_HORIZON = flags["if_horizon"]
    # before the engine: the T5 cache identity records the count, and the engine partitions pipe._t5_cache by it
    GC_DIRECTOR = flags["gc_director"]
    CPU_THREADS = FS.thread_tag(FS.apply_cpu_threads(FAST.cpu_threads))
    STATS = flag_stats.FlagStats(TURN_CAL, PROMPT_MODE, REANCHOR, PLAYER_HINT, RETURN_STOP, gc_completion=GC_COMPLETION,
                                 if_horizon=IF_HORIZON, if_camera=flags["if_camera"],
                                 history_endpoints=flags["history_endpoints"],
                                 insight_director=flags["insight_director"], if_repeat=flags["if_repeat"],
                                 if_slow=flags["if_slow"], gc_director=GC_DIRECTOR)
    if flags["insight_director"]:
        print("[lingbot] insight director: on (fixed scene activity cue)", flush=True)
    if flags["if_slow"]:
        print("[lingbot] IF slow translation: on (gain=0.5, session only)", flush=True)
    P.reset()
    prompts.reset()
    run_agent = import_run_agent(fresh=True)
    run_agent.SanaWMEngine = LingBotWorld2Engine
    prompts.install(run_agent)
    STATS.install(run_agent)
    print(f"[adapter] agent provider: {agent_api.patch(run_agent, flags['player'])}", flush=True)
    if flags["history_endpoints"]:
        PH.install(run_agent, STATS.history_removed)
        print("[lingbot] player history endpoints: on", flush=True)
    # decide_action wrappers, innermost first (see the module docstring): each prompt hint appends to the goal
    # the inner ones see, so the player reads goal + [GC completion | IF camera + IF repeat] + player hint.
    # Player hint is innermost: the pose summary always ends the goal text.
    if PLAYER_HINT:
        run_agent.decide_action = H.wrap(run_agent.decide_action, run_agent.to_sana_key, session=not STATELESS,
                                         turn_cal=TURN_CAL, on_hint=STATS.hint, if_slow=flags["if_slow"])
        print("[lingbot] player hint: on", flush=True)
    if flags["if_repeat"]:  # conditional IF reminder, after the fixed IF camera reminder
        run_agent.decide_action = IR.wrap(run_agent.decide_action, STATS.if_repeat_hint)
        print("[lingbot] IF repeat check: on", flush=True)
    if flags["if_camera"]:
        run_agent.decide_action = IC.wrap(run_agent.decide_action, STATS.if_camera_hint)
        print("[lingbot] IF camera hint: on", flush=True)
    if GC_COMPLETION:  # GC only, so it never shares a goal with the two IF reminders
        run_agent.decide_action = C.wrap(run_agent.decide_action, STATS.completion_hint, STATS.completion_end)
        print("[lingbot] GC completion hint: on", flush=True)
    if RETURN_STOP:  # outside the hints: a stopped step never reaches the player (or the hints' counters)
        run_agent.decide_action = RS.wrap(run_agent.decide_action, run_agent.to_sana_key, session=not STATELESS,
                                          turn_cal=TURN_CAL, on_event=STATS.return_stop_event)
        print("[lingbot] return stop: on", flush=True)
    if IF_HORIZON:  # outermost, IF only: its END is not counted by any hint; the player is told the budget
        run_agent.decide_action = IH.wrap(run_agent.decide_action, run_agent.parse_segments,
                                          on_event=STATS.if_horizon_event)
        print("[lingbot] IF horizon: on", flush=True)
    rc = run_agent.main()
    agent_api.finish(run_agent)
    print(STATS.total_line(), flush=True)
    return rc or 0


if __name__ == "__main__":
    raise SystemExit(main())
