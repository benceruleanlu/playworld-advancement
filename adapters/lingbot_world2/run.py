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

GC chunk director (off by default, session + caption only): `--lingbot-gc-chunk-director` or
LINGBOT_GC_CHUNK_DIRECTOR=1 appends one sentence for the chunk's own single-key camera command to the
GC caption and refreshes only the text cross-attention on continuation (session.update_prompt); requires
caption prompting, rejected with --lingbot-stateless. See gc_director.py.

GC ease turns (off by default, session only): `--lingbot-gc-ease-turns` or LINGBOT_GC_EASE_TURNS=1
reshapes per-frame yaw/pitch of a GC chunk that turns on one axis (one key of j/l/i/k) with a raised
cosine (0.5x at the edges, 1.5x mid-chunk, mean 1), so the chunk ends at the same commanded pose;
rejected with --lingbot-stateless. See session.is_pure_turn and PoseTrack.advance.

IF subject director (off by default): `--lingbot-if-subject-director` or LINGBOT_IF_SUBJECT_DIRECTOR=1
conditions third-person IF tasks on "Subject action: goal / Scene: caption / fixed cue" instead of the
caption prompt; requires caption prompting (--lingbot-caption-prompt or LINGBOT_PROMPT_MODE=auto|caption).
Its counter if_subject_prompts counts generate() calls (about 30 per closed-loop rollout), not T5 encodes
(one per session reset). See if_subject.py.

Scripted player (off by default, closed loop only): `--lingbot-scripted-player` or LINGBOT_SCRIPTED_PLAYER=1
answers every closed-loop decision from the task's dataset action, cut into chunks (upstream parse_segments;
poses.CHUNK_UNITS rotation tokens or (chunk_frames - 1) / action_frame_unit translation tokens per chunk, rounded
on each axis's running total), then WAIT for the dataset-mode tail and END; the LLM is never called. Angles match
the dataset only with --lingbot-turn-cal. Outermost decide_action wrapper, so the player-side wrappers and player
history endpoints are not reached. For A/B of model-side flags only, not final numbers. Needs --action-source
agent or refined. See scripted_player.py.

Conditioning schedule (off by default, session only): `--lingbot-cond-schedule` or LINGBOT_COND_SCHEDULE=1
scales DiT camera FiLM and cross-attention output on early denoising steps of stationary and third-person
chunks, restoring (1, 1) on late steps and the t=0 KV write (--lingbot-cond-early/cam/3p/text; cond_schedule.py).
Refused together with --lingbot-weight-mod: both wrap the same layers.

Noisy KV writes (off by default, session only): `--lingbot-kv-noise` or LINGBOT_KV_NOISE=1 writes each
generated chunk into the KV cache from add_noise(x0, eps, t_kv) at t_kv (--lingbot-kv-noise-t, default 25,
snapped to the scheduler table) instead of x0 at t=0; eps has its own generator, so denoising and the
returned frames of the current chunk are unchanged. Chunks with an image latent stay clean. See kv_noise.py.

Weight modulation (off by default): `--lingbot-weight-mod` or LINGBOT_WEIGHT_MOD=1 multiplies the outputs of
every DiT block's cam_scale_layer / cam_shift_layer (camera FiLM) and cross_attn.o (text cross-attention) by a
scale picked per latent chunk: LINGBOT_CAM_WEIGHT_STATIC (0.0) on still chunks (every relative latent pose within
1e-5 of identity), LINGBOT_CAM_WEIGHT_3P (0.85) on moving chunks of third-person tasks (task JSON "perspective"),
LINGBOT_CAM_WEIGHT_MOVE (1.0) on other moving chunks; text LINGBOT_TEXT_WEIGHT_SCALE (1.0) on still and third-person
chunks, LINGBOT_TEXT_WEIGHT_MOVE (1.0) on first-person moving ones, LINGBOT_TEXT_WEIGHT_STATIC (default: the text
scale) on still chunks only. Session mode also takes a late-step camera schedule: LINGBOT_CAM_LATE_STEPS (0 = off)
last denoising steps of a still / third-person chunk use LINGBOT_CAM_WEIGHT_STATIC_LATE / LINGBOT_CAM_WEIGHT_3P_LATE
(default: the base scales); the clean KV-write pass always uses the base scale. Cam scale 0 is out of distribution for
these weights (always trained with Plucker input), not a "base" no-camera DiT. Acts in dataset mode (the per-chunk
choice runs inside the one long step); stateless classifies the whole rollout once. See weight_mod.py.

Attention window (off by default): `--lingbot-sink-size N` / `--lingbot-local-attn N` (LINGBOT_SINK_SIZE /
LINGBOT_LOCAL_ATTN_SIZE, defaults 6 / 18, the README causal-fast settings). Set on the loaded pipe and its modules
at every main() call (read at forward time), so pwa gen-arms reuses one pipe. Requires local >= sink + 4 (one
latent chunk) unless local is -1 (full attention, then sink must be 0).

IF identity cue (off by default): `--lingbot-if-identity-cue` or LINGBOT_IF_IDENTITY_CUE=1 appends a fixed sentence
group about keeping each subject's identity (if_identity.CUE) to the model prompt of third-person IF tasks that have
an image_caption; requires LINGBOT_PROMPT_MODE=auto (--lingbot-caption-prompt), so the IF goal is in the prompt.
Its counter if_identity_prompts counts prompts that are encoded with the cue: one per session reset (chunk 01 or
`<task>_full`), every call on the stateless path. See if_identity.py.

Measured turn (off by default, player-side): `--lingbot-measured-turn` or LINGBOT_MEASURED_TURN=1 measures the
rotation each finished turn/tilt chunk shows in the video (phase correlation, measured_turn.py), logs it next to the
command and, on GC tasks only (LINGBOT_MEASURED_TURN_TELL, a regex, default GC), adds one sentence with both totals
to the player's goal. No effect with --action-source dataset (decide_action is never called there).

Model prompt composition, in order: caption prompt (prompts.model_prompt), insight director (insight
tasks), GC chunk director (GC chunks; appends to the caption), IF subject director (third-person IF;
replaces the prompt with its structured form), IF identity cue (third-person IF; appends to whatever the
prompt is by then, so it survives the subject director). Only the two IF ones can touch the same task.

decide_action wrappers, innermost first: player hint, measured turn, IF repeat check, IF camera hint, GC completion hint,
return stop, IF horizon, scripted player. The goal the player reads is therefore goal + GC completion | (IF camera, then
IF repeat) + measured turn + player hint; return stop and IF horizon answer without asking the player, so their WAIT/END
replies never reach the hints or their counters.
The scripted player answers every decision itself, so with it on none of the others is reached.

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
  LINGBOT_GC_CHUNK_DIRECTOR  1 = same as --lingbot-gc-chunk-director
  LINGBOT_GC_EASE_TURNS  1 = same as --lingbot-gc-ease-turns
  LINGBOT_IF_SUBJECT_DIRECTOR  1 = same as --lingbot-if-subject-director
  LINGBOT_SCRIPTED_PLAYER  1 = same as --lingbot-scripted-player
  LINGBOT_SCRIPTED_TAIL  WAIT chunks after the script (default ceil(--tail-frames / (--chunk-frames - 1)) = 2)
  LINGBOT_MEASURED_TURN  1 = same as --lingbot-measured-turn; LINGBOT_MEASURED_TURN_TELL  task-id regex told (GC)
  LINGBOT_IF_IDENTITY_CUE  1 = same as --lingbot-if-identity-cue
  LINGBOT_WEIGHT_MOD  1 = same as --lingbot-weight-mod (scale knobs above)
  LINGBOT_SINK_SIZE / LINGBOT_LOCAL_ATTN_SIZE   attention window (6 / 18)
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
fresh upstream run_agent (so no patch stacks); only the loaded pipe (_PIPES, keyed by checkpoint and T5
placement) is shared; each call's engine sets its own KV window on it, detaches an earlier arm's weight-mod
wrappers, and builds its own session.
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
import contextlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.common import agent_api, prompts  # noqa: E402
from adapters.common.upstream import import_run_agent  # noqa: E402
from adapters.lingbot_world2 import cond_schedule as CS  # noqa: E402
from adapters.lingbot_world2 import fast_start as FS  # noqa: E402
from adapters.lingbot_world2 import flag_stats  # noqa: E402
from adapters.lingbot_world2 import gc_director as D  # noqa: E402
from adapters.lingbot_world2 import gc_completion as C  # noqa: E402
from adapters.lingbot_world2 import if_camera as IC  # noqa: E402
from adapters.lingbot_world2 import if_horizon as IH  # noqa: E402
from adapters.lingbot_world2 import if_identity as IFI  # noqa: E402
from adapters.lingbot_world2 import if_repeat as IR  # noqa: E402
from adapters.lingbot_world2 import kv_noise as KVN  # noqa: E402
from adapters.lingbot_world2 import measured_turn as MT  # noqa: E402
from adapters.lingbot_world2 import if_subject as IFS  # noqa: E402
from adapters.lingbot_world2 import player_hint as H  # noqa: E402
from adapters.lingbot_world2 import player_history as PH  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import return_stop as RS  # noqa: E402
from adapters.lingbot_world2 import scripted_player as SP  # noqa: E402
from adapters.lingbot_world2 import session as S  # noqa: E402
from adapters.lingbot_world2 import watchdog as W  # noqa: E402
from adapters.lingbot_world2 import weight_mod as WM  # noqa: E402

_FLAG_ARGS = ("--lingbot-stateless", "--lingbot-turn-cal", "--lingbot-caption-prompt",
              "--lingbot-reanchor", "--lingbot-player-hint", "--lingbot-return-stop",
              "--lingbot-gc-completion-hint", "--lingbot-if-horizon", "--lingbot-if-camera-hint",
              "--lingbot-player-history-endpoints", "--lingbot-insight-director", "--lingbot-if-repeat-check",
              "--lingbot-if-slow-translation", "--lingbot-gc-chunk-director", "--lingbot-gc-ease-turns",
              "--lingbot-if-subject-director", "--lingbot-weight-mod", "--lingbot-if-identity-cue",
              "--lingbot-measured-turn", "--lingbot-scripted-player")


def _take_value(argv: list[str], name: str) -> tuple[str | None, list[str]]:
    """`--name V` / `--name=V` out of argv: the last value given, and argv without the flag."""
    out, rest, i = None, [], 0
    while i < len(argv):
        a = argv[i]
        if a == name:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise SystemExit(f"{name} needs an integer value")
            out, i = argv[i + 1], i + 2
        elif a.startswith(name + "="):
            out, i = a.split("=", 1)[1], i + 1
        else:
            rest.append(a)
            i += 1
    return out, rest


def _window(argv: list[str], environ) -> tuple[dict, list[str]]:
    """Attention window sizes: --lingbot-local-attn / --lingbot-sink-size (env LINGBOT_LOCAL_ATTN_SIZE /
    LINGBOT_SINK_SIZE). Defaults are the README causal-fast settings (18 local, 6 sink). Checked here, before
    any load: upstream's eviction needs local >= sink + one latent chunk, and ignores sink with full attention."""
    local_v, argv = _take_value(argv, "--lingbot-local-attn")
    sink_v, argv = _take_value(argv, "--lingbot-sink-size")
    local_v = environ.get("LINGBOT_LOCAL_ATTN_SIZE") if local_v is None else local_v
    sink_v = environ.get("LINGBOT_SINK_SIZE") if sink_v is None else sink_v
    try:
        local = LOCAL_ATTN_DEFAULT if local_v in (None, "") else int(local_v)
        sink = SINK_DEFAULT if sink_v in (None, "") else int(sink_v)
    except ValueError:
        raise SystemExit(f"window sizes must be integers, got local={local_v!r} sink={sink_v!r}") from None
    if sink < 0 or local == 0 or local < -1:
        raise SystemExit(f"window sizes must be sink >= 0 and local >= 1 (or -1 for full), got local={local} sink={sink}")
    if local == -1 and sink > 0:
        raise SystemExit(f"--lingbot-sink-size {sink} has no effect with full attention (local -1); use sink 0")
    if local != -1 and local < sink + P.LATENT_CHUNK:
        raise SystemExit(f"--lingbot-local-attn {local} must be >= sink ({sink}) + {P.LATENT_CHUNK} (one latent chunk)")
    return {"local_attn": local, "sink": sink}, argv


def set_window(pipe, local_attn: int, sink: int) -> int:
    """Set the KV window on a loaded pipe and every module that carries one (all read at forward time; the
    session sizes its cache from pipe.local_attn_size at reset). Returns how many modules were set."""
    pipe.local_attn_size, pipe.sink_size = local_attn, sink
    n = 0
    model = getattr(pipe, "model", None)
    for m in (model.modules() if hasattr(model, "modules") else ()):
        if hasattr(m, "local_attn_size") and hasattr(m, "sink_size"):
            m.local_attn_size, m.sink_size = local_attn, sink
            n += 1
    if not n and (local_attn, sink) != (LOCAL_ATTN_DEFAULT, SINK_DEFAULT):
        raise SystemExit("[lingbot] window: no module exposes local_attn_size / sink_size; upstream layout changed")
    return n


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
        "gc_ease_turns": "--lingbot-gc-ease-turns" in argv or environ.get("LINGBOT_GC_EASE_TURNS", "0") == "1",
        "if_subject": "--lingbot-if-subject-director" in argv or environ.get("LINGBOT_IF_SUBJECT_DIRECTOR", "0") == "1",
        "scripted": "--lingbot-scripted-player" in argv or environ.get("LINGBOT_SCRIPTED_PLAYER", "0") == "1",
        "if_identity": "--lingbot-if-identity-cue" in argv or environ.get("LINGBOT_IF_IDENTITY_CUE", "0") == "1",
        "measured_turn": "--lingbot-measured-turn" in argv or environ.get("LINGBOT_MEASURED_TURN", "0") == "1",
        "weight_mod": "--lingbot-weight-mod" in argv or environ.get("LINGBOT_WEIGHT_MOD", "0") == "1",
        "fast": FS.parse_flags(argv, environ),
    }
    if flags["scripted"]:
        SP.check_action_source(argv)
        SP.validate(environ)
    if flags["gc_director"] and (mode == "goal" or flags["stateless"]):
        raise SystemExit("--lingbot-gc-chunk-director requires caption prompting and session mode")
    if flags["gc_ease_turns"] and flags["stateless"]:
        raise SystemExit("--lingbot-gc-ease-turns requires session mode")
    if flags["if_subject"] and mode == "goal":
        raise SystemExit("--lingbot-if-subject-director requires caption prompting")
    if flags["if_identity"] and mode != "auto":
        raise SystemExit("--lingbot-if-identity-cue requires auto caption prompting (scene plus IF goal)")
    flags["stall"], argv = W.parse(argv, environ)
    flags["cond_sched"], argv = CS.parse(argv, environ)
    if flags["cond_sched"].enabled and flags["weight_mod"]:
        raise SystemExit("--lingbot-cond-schedule and --lingbot-weight-mod both wrap the DiT conditioning layers; use one")
    flags["kv_noise"], argv = KVN.parse(argv, environ)
    window, argv = _window(argv, environ)
    flags.update(window)
    if flags["if_slow"] and flags["stateless"]:
        raise SystemExit("--lingbot-if-slow-translation requires session mode (stateless normalizes away scale)")
    flags["player"], argv = agent_api.configure(argv, environ)
    return flags, FS.strip_flags([a for a in argv if a not in _FLAG_ARGS])


# Set by main() from configure(); the engine reads them at call time.
GC_DIRECTOR = False  # --lingbot-gc-chunk-director / LINGBOT_GC_CHUNK_DIRECTOR=1 (requires caption + session)
GC_EASE_TURNS = False  # --lingbot-gc-ease-turns / LINGBOT_GC_EASE_TURNS=1; session-only, off by default
IF_SUBJECT = False  # --lingbot-if-subject-director / LINGBOT_IF_SUBJECT_DIRECTOR=1, off by default
WEIGHT_MOD = False  # --lingbot-weight-mod / LINGBOT_WEIGHT_MOD=1, off by default
IF_IDENTITY = False  # --lingbot-if-identity-cue / LINGBOT_IF_IDENTITY_CUE=1, off by default
STATELESS = TURN_CAL = REANCHOR = PLAYER_HINT = RETURN_STOP = GC_COMPLETION = IF_HORIZON = False
PROMPT_MODE = "goal"
FAST = FS.FastFlags()
CPU_THREADS = None  # FS.thread_tag of this call's --lingbot-cpu-threads (None = torch's default)
STALL = W.Limits()
COND_SCHED = CS.ScheduleConfig()
KV_NOISE = KVN.KVNoiseConfig()  # --lingbot-kv-noise / LINGBOT_KV_NOISE=1, session only, off by default
STATS = flag_stats.FlagStats(False, "goal", False, False)

MAX_AREA = 480 * 832  # the released checkpoints' reference resolution
LOCAL_ATTN_DEFAULT, SINK_DEFAULT = 18, 6  # README settings for causal-fast (the pipe is loaded with these)
LOCAL_ATTN, SINK = LOCAL_ATTN_DEFAULT, SINK_DEFAULT  # this call's window (--lingbot-local-attn / --lingbot-sink-size)
DEFAULT_PROMPT = "A photo-realistic scene with rich details."
_PIPES: dict = {}  # loaded wan.WanI2VCausal by checkpoint and T5 placement (the window is set per call)


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
    key = (root, str(ckpt), str(assets), t5_cpu)
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
                local_attn_size=LOCAL_ATTN_DEFAULT, sink_size=SINK_DEFAULT, infer_mode="causal_fast",
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

    weight_mod = None  # --lingbot-weight-mod: a WeightModulator, set in __init__

    def __init__(self, args):
        self.args = args
        self.cfg, self.pipe, weights, t5_cpu = load_pipe()
        # upstream's in-memory embeddings are keyed by prompt only: drop them when the CPU T5 thread count changed
        FS.partition_t5_memory(self.pipe, CPU_THREADS if t5_cpu else "gpu")
        set_window(self.pipe, LOCAL_ATTN, SINK)  # every call: an earlier arm in this process may have changed it
        self.t5_cache = self._t5_cache(weights, t5_cpu) if FAST.t5_cache else None
        CS.detach_model(getattr(self.pipe, "model", None))
        WM.detach_model(getattr(self.pipe, "model", None))  # an earlier arm's modulator in this process
        sched = (CS.CondScheduler(self.pipe.model, COND_SCHED)
                 if COND_SCHED.enabled and not STATELESS and hasattr(self.pipe, "model") else None)
        self.weight_mod = WM.WeightModulator(self.pipe.model) if WEIGHT_MOD and hasattr(self.pipe, "model") else None
        if self.weight_mod is not None:
            STATS.weight_mod_late = "" if STATELESS else self.weight_mod.late_schedule()  # stateless: schedule inert
        self.session = None
        if not STATELESS:
            self.session = S.LingBotSession(self.pipe, MAX_AREA, self.cfg.sample_shift,
                                            horizon_frames=int(getattr(args, "max_total_frames", 961) or 961),
                                            stream_encode=FAST.fast_y, t5_cache=self.t5_cache,
                                            weight_mod=self.weight_mod,
                                            **({"cond_sched": sched} if sched is not None else {}),
                                            **({"kv_noise": KVN.KVNoise(KV_NOISE)} if KV_NOISE.enabled else {}))
        self._last_chunk = None
        print(f"[lingbot] mode: {'stateless' if STATELESS else 'session'}"
              + ("" if STATELESS else f" (stream_decode={self.session.stream_decode})")
              + (f", turn-cal {P.UNIT_YAW_DEG}/{P.UNIT_PITCH_DEG} deg per token" if TURN_CAL else "")
              + ("" if PROMPT_MODE == "goal" else f", prompt mode {PROMPT_MODE}")
              + ((", re-anchor ignored (stateless)" if STATELESS else ", re-anchor on") if REANCHOR else "")
              + ("" if (LOCAL_ATTN, SINK) == (LOCAL_ATTN_DEFAULT, SINK_DEFAULT)
                 else f", window local_attn={LOCAL_ATTN} sink={SINK}")
              + ((", cond-schedule ignored (stateless)" if STATELESS else f", {COND_SCHED.describe()}")
                 if COND_SCHED.enabled else "")
              + ((", kv-noise ignored (stateless)" if STATELESS else f", {KV_NOISE.describe()}")
                 if KV_NOISE.enabled else "")
              + (f", weight-mod on ({self.weight_mod.describe()})" if self.weight_mod is not None
                 else ", weight-mod on (no DiT found)" if WEIGHT_MOD else "")
              + (", player hint on" if PLAYER_HINT else "")
              + (", return stop on" if RETURN_STOP else "")
              + (", GC completion hint on" if GC_COMPLETION else "")
              + (", IF horizon on" if IF_HORIZON else "")
              + (", IF camera hint on" if STATS.if_camera else "")
              + (", player history endpoints on" if STATS.history_endpoints else "")
              + (", insight director on" if STATS.insight_director else "")
              + (", IF repeat check on" if STATS.if_repeat else "")
              + (", IF slow translation on (gain 0.5)" if STATS.if_slow else "")
              + (", GC chunk director on" if GC_DIRECTOR else "")
              + (", GC ease turns on" if GC_EASE_TURNS else "")
              + (", IF subject director on" if IF_SUBJECT else "")
              + (", IF identity cue on" if IF_IDENTITY else "")
              + (", measured turn on" if STATS.measured_turn else "")
              + (f", scripted player on ({SP.units():g} tokens per chunk"
                 + ("" if TURN_CAL else ", angles uncalibrated: turn-cal off") + ")" if STATS.scripted else "")
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
        if IF_SUBJECT:
            directed = IFS.compose(prompts._current.get("task"), original_prompt, name)
            if directed is not None:
                prompt = directed
                STATS.subject_prompt()
                if (S.parse_chunk_name(name) or (name, 1))[1] == 1:
                    print(f"[lingbot] {name}: IF subject director: {prompt!r}", flush=True)
        if IF_IDENTITY:  # last: appends to the prompt the model gets, whichever composer built it
            directed = IFI.compose(prompts._current.get("task"), prompt, name)
            if directed is not None:
                prompt = directed
                first = (S.parse_chunk_name(name) or (name, 1))[1] == 1
                if self.session is None or first:  # counts encodes: session encodes at reset only
                    STATS.if_identity_prompts += 1
                if first:
                    print(f"[lingbot] {name}: IF identity cue: {prompt!r}", flush=True)
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
            # only with the flag, so the no-flag reset call stays main's
            mod = {"third_person": WM.is_third_person(prompts._current.get("task"), name)} if self.weight_mod else {}
            self.session.reset(Image.open(image_path).convert("RGB"), prompt or DEFAULT_PROMPT,
                               int(self.args.seed), horizon_frames=horizon,
                               reanchor=reanchor, **mod)
            self.session.third_person = CS.is_third_person(prompts._current.get("task"), name)
            if reanchor:
                STATS.armed()
        self._configure_if_motion(name, keys)
        if cont and GC_DIRECTOR and name.startswith("GC"):
            STATS.gc_director_updates += self.session.update_prompt(prompt or DEFAULT_PROMPT)
        start = self.session.chunk_id
        anchored = self.session.reanchor_events
        modded = (self.session.weight_mod_steps, self.session.weight_mod_chunks) if self.weight_mod is not None else None
        cs_chunks = getattr(self.session, "cond_sched_chunks", 0)
        cs_calls = getattr(self.session, "cond_sched_calls", 0)
        kvn_chunks = getattr(self.session, "kv_noise_chunks", 0)
        ease = bool(GC_EASE_TURNS and parsed and parsed[0].startswith("GC") and S.is_pure_turn(keys))
        frames = self.session.step(keys, ease_turns=True) if ease else self.session.step(keys)
        STATS.gc_eased_turns += ease
        STATS.reanchored(self.session.reanchor_events - anchored)
        STATS.cond_scheduled(getattr(self.session, "cond_sched_chunks", 0) - cs_chunks,
                             getattr(self.session, "cond_sched_calls", 0) - cs_calls)
        if KV_NOISE.enabled:
            STATS.kv_noised(getattr(self.session, "kv_noise_chunks", 0) - kvn_chunks)
        if self.weight_mod is not None:
            STATS.modulated(self.session.weight_mod_steps - modded[0], self.session.weight_mod_chunks - modded[1])
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
        with (self.weight_mod or contextlib.nullcontext()):
            # stateless: one classification for the whole rollout (still only if every latent pose is identity)
            if self.weight_mod is not None and self.weight_mod.step(
                    S.normalise_translation(S.relative_latent_poses(c2ws[::4])),
                    third_person=WM.is_third_person(prompts._current.get("task"), name)):
                STATS.modulated(1, 1)
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
    global CPU_THREADS, STALL, IF_HORIZON, GC_DIRECTOR, GC_EASE_TURNS, IF_SUBJECT, WEIGHT_MOD, LOCAL_ATTN, SINK
    global IF_IDENTITY, COND_SCHED, KV_NOISE
    flags, sys.argv = configure(list(sys.argv if argv is None else argv))
    LOCAL_ATTN, SINK = flags["local_attn"], flags["sink"]
    window = (LOCAL_ATTN, SINK) != (LOCAL_ATTN_DEFAULT, SINK_DEFAULT)
    if window:
        print(f"[lingbot] window: local_attn={LOCAL_ATTN} sink={SINK}", flush=True)
    STATELESS, TURN_CAL, PROMPT_MODE = flags["stateless"], flags["turn_cal"], flags["prompt_mode"]
    REANCHOR, PLAYER_HINT, FAST = flags["reanchor"], flags["player_hint"], flags["fast"]
    RETURN_STOP, GC_COMPLETION, STALL = flags["return_stop"], flags["gc_completion"], flags["stall"]
    IF_HORIZON, GC_DIRECTOR, GC_EASE_TURNS = flags["if_horizon"], flags["gc_director"], flags["gc_ease_turns"]
    IF_SUBJECT, WEIGHT_MOD, IF_IDENTITY = flags["if_subject"], flags["weight_mod"], flags["if_identity"]
    COND_SCHED = flags["cond_sched"]
    cs_mode = "off" if not COND_SCHED.enabled else ("skip" if STATELESS else "on")
    KV_NOISE = flags["kv_noise"]
    kvn_mode = "off" if not KV_NOISE.enabled else ("skip" if STATELESS else "on")
    # before the engine: the T5 cache identity records the count, and the engine partitions pipe._t5_cache by it
    CPU_THREADS = FS.thread_tag(FS.apply_cpu_threads(FAST.cpu_threads))
    STATS = flag_stats.FlagStats(TURN_CAL, PROMPT_MODE, REANCHOR, PLAYER_HINT, RETURN_STOP, gc_completion=GC_COMPLETION,
                                 if_horizon=IF_HORIZON, if_camera=flags["if_camera"],
                                 history_endpoints=flags["history_endpoints"],
                                 insight_director=flags["insight_director"], if_repeat=flags["if_repeat"],
                                 if_slow=flags["if_slow"], gc_director=GC_DIRECTOR,
                                 gc_ease_turns=GC_EASE_TURNS, if_subject=IF_SUBJECT, weight_mod=WEIGHT_MOD, if_identity=IF_IDENTITY,
                                 measured_turn=flags["measured_turn"], cond_sched=cs_mode,
                                 kv_noise=kvn_mode, kv_noise_t=KV_NOISE.t,
                                 window=f"{LOCAL_ATTN}:{SINK}" if window else "", scripted=flags["scripted"])
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
    if flags["measured_turn"]:  # its sentence sits just before the player hint's pose summary
        run_agent.decide_action = MT.wrap(run_agent.decide_action, run_agent.to_sana_key, session=not STATELESS,
                                          turn_cal=TURN_CAL, on_event=STATS.measured_turn_event,
                                          tell_tasks=os.environ.get("LINGBOT_MEASURED_TURN_TELL", "GC"))
        print("[lingbot] measured turn: on", flush=True)
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
    if flags["scripted"]:  # outermost: answers every decision, so no wrapper inside it and no LLM is reached
        run_agent.decide_action = SP.wrap(run_agent.decide_action, run_agent.parse_segments,
                                          run_agent.VALID_ACTIONS, on_event=STATS.scripted_event)
        inert = [n for n, on in (("player hint", PLAYER_HINT), ("IF repeat check", flags["if_repeat"]),
                                 ("IF camera hint", flags["if_camera"]), ("GC completion hint", GC_COMPLETION),
                                 ("return stop", RETURN_STOP), ("IF horizon", IF_HORIZON),
                                 ("player history endpoints", flags["history_endpoints"]),
                                 ("measured turn", flags["measured_turn"])) if on]
        print(f"[lingbot] scripted player: on ({SP.units():g} rotation tokens per chunk, then WAIT tail and END; "
              f"LLM player not called)" + (f"; not reached: {', '.join(inert)}" if inert else ""), flush=True)
    rc = run_agent.main()
    agent_api.finish(run_agent)
    print(STATS.total_line(), flush=True)
    return rc or 0


if __name__ == "__main__":
    raise SystemExit(main())
