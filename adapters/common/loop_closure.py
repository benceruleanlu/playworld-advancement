"""Frame-level loop closure around any engine's generate() (opt-in, model-agnostic; numpy + imageio).

`LOOP_CLOSE=1` wraps the engine a runner installs as run_agent.SanaWMEngine. The wrapper follows the
commanded camera path of a closed-loop rollout from the action strings the harness sends. When a chunk
brings the commanded pose back to the start pose, the wrapper

  1. asks the same engine for a second chunk that starts on the task's first image and moves the opposite
     way (`<inverse key>-<frames>`), reverses it in time, so it is a clip that arrives exactly on the first
     image while moving in the commanded direction;
  2. cross-fades the chunk the model just generated into that clip over the whole chunk, and returns the
     blend. The last frame of the returned chunk is the first image (up to codec noise), and the harness
     continues from it.

Nothing inside the model is touched, so it composes with any engine that implements generate(). It differs
from LingBot re-anchoring (session.ReturnDetector, which feeds the first image back as conditioning and lets
the model render the return): this one is a blend of two generated clips and always lands on the start view.

When it fires:
  * call names matching LOOP_CLOSE_TASKS (regex, default `GC`): the Out-of-sight rubric scores a reset to
    the opening frame as level 1, so it stays off there unless asked for;
  * closed-loop calls only (`<task>_chunk_NN`, one `<key>-<frames>` segment); a dataset-mode `<task>_full`
    call passes through untouched;
  * the commanded pose is back at the start after having left it, and at least two pose-changing chunks
    have been generated since the start. Pose is counted in frames per key. Turns and pitches that cancel
    close the loop; translations close it only when every one of them was made at the starting heading
    (a rectangle walk with the camera facing one way), unless LOOP_CLOSE_DEG_PER_FRAME gives the yaw rate,
    in which case translations are integrated along the heading and a full 360 degree turn also closes;
  * a rollout that translates while turned, with no yaw rate given, is marked `pose unknown` for the rest of
    the task and never closes (no guess).

Cost: one extra generate() call per closure. In a stateful engine that call starts from another image, so
the engine's own context is restarted there.

Evidence: none on its own. On SANA-WM it was only run together with a replay memory, with a scripted
player and unofficial reviewers; there the arrival on a long walk (GC005) read as an abrupt snap. Treat it
as untested under the adoption rule.

Log lines: `[loop-close] <task>: closed via <action>` and one `[loop-close] total ...` from finish();
per-task records go to <task>/loop_close.json.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

INVERSE = {"j": "l", "l": "j", "i": "k", "k": "i", "w": "s", "s": "w", "a": "d", "d": "a"}
YAW = {"j": -1.0, "l": 1.0}         # harness keys: j/l turn left/right, i/k pitch up/down, w/s/a/d translate
PITCH = {"i": 1.0, "k": -1.0}
EPS = 1e-6


def parse_action(action: str) -> list[tuple[str, int]]:
    out = []
    for seg in (action or "").split(","):
        m = re.fullmatch(r"\s*([a-z]+)-(\d+)\s*", seg)
        if m:
            out.append((m.group(1), int(m.group(2))))
    return out


def read_frames(path) -> list[np.ndarray]:
    import imageio
    return [np.asarray(f)[..., :3] for f in imageio.mimread(str(path), memtest=False)]


def write_frames(frames, path, fps: int) -> Path:
    import imageio
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(str(path), [np.asarray(f, dtype=np.uint8) for f in frames], fps=fps, macro_block_size=1)
    return path


def crossfade(a: list, b: list) -> list:
    """Linear blend from sequence a (weight 1 at the first frame) to sequence b (weight 1 at the last)."""
    n = min(len(a), len(b))
    out = []
    for t in range(n):
        w = t / max(n - 1, 1)
        out.append((a[t].astype(np.float32) * (1 - w) + b[t].astype(np.float32) * w).round().astype(np.uint8))
    return out


@dataclass
class Pose:
    """Commanded camera pose in frames held per key, relative to the start of the task."""
    deg_per_frame: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    pos: np.ndarray = field(default_factory=lambda: np.zeros(2))
    moved: int = 0           # pose-changing chunks since the start (or since the last closure)
    unknown: bool = False    # translated while turned and no yaw rate was given

    def step(self, key: str, frames: int) -> None:
        if key in YAW:
            self.yaw += YAW[key] * frames
        elif key in PITCH:
            self.pitch += PITCH[key] * frames
        elif key in INVERSE:
            if self.deg_per_frame > 0:
                ang = np.deg2rad(self.yaw * self.deg_per_frame)
            else:
                if abs(self.yaw) > EPS:
                    self.unknown = True
                ang = 0.0
            fwd, right = np.array([np.sin(ang), np.cos(ang)]), np.array([np.cos(ang), -np.sin(ang)])
            self.pos = self.pos + frames * {"w": fwd, "s": -fwd, "d": right, "a": -right}[key]
        else:
            return
        self.moved += 1

    def at_start(self) -> bool:
        if self.unknown or np.abs(self.pos).max() > 1e-3 or abs(self.pitch) > EPS:
            return False
        if abs(self.yaw) < EPS:
            return True
        turned = abs(self.yaw * self.deg_per_frame)
        return self.deg_per_frame > 0 and turned > 1.0 and min(turned % 360.0, 360.0 - turned % 360.0) < 1e-3


class LoopClosureEngine:
    def __init__(self, base, args=None, tasks: str | None = None, deg_per_frame: float | None = None):
        self.base, self.args = base, args
        self.fps = int(getattr(args, "fps", 16) or 16)
        self.tasks = re.compile(tasks if tasks is not None else os.environ.get("LOOP_CLOSE_TASKS", "GC"))
        self.deg = float(deg_per_frame if deg_per_frame is not None
                         else os.environ.get("LOOP_CLOSE_DEG_PER_FRAME", "0") or 0)
        self.task_id, self.pose, self.origin, self.records = None, Pose(self.deg), None, []
        self.closures = self.calls = 0

    def __getattr__(self, name):  # everything else is the wrapped engine's
        return getattr(self.base, name)

    def generate(self, image_path, prompt, action, output_dir, name, num_frames, intrinsics_path=None):
        output_dir = Path(output_dir)
        mp4 = self.base.generate(image_path, prompt, action, output_dir, name, num_frames,
                                 intrinsics_path=intrinsics_path)
        m = re.fullmatch(r"(.+)_chunk_(\d+)", name)
        segs = parse_action(action)
        if not m or len(segs) != 1 or not self.tasks.search(name):
            return mp4
        task_id, key, n = m.group(1), segs[0][0], segs[0][1]
        if task_id != self.task_id or int(m.group(2)) == 1:
            self.task_id, self.pose, self.origin, self.records = task_id, Pose(self.deg), str(image_path), []
        self.calls += 1
        self.pose.step(key, n)
        if key not in INVERSE or self.pose.moved < 2 or not self.pose.at_start():
            return mp4
        frames = read_frames(mp4)
        anchor_mp4 = self.base.generate(self.origin, prompt, f"{INVERSE[key]}-{n}", output_dir, f"{name}_anchor",
                                        num_frames, intrinsics_path=intrinsics_path)
        anchor = read_frames(anchor_mp4)[::-1]
        if len(anchor) < len(frames) or anchor[0].shape != frames[0].shape:
            print(f"  [loop-close] {task_id}: anchor clip does not match the chunk "
                  f"({len(anchor)} vs {len(frames)} frames), left as generated", flush=True)
            return mp4
        out = write_frames(crossfade(frames, anchor[-len(frames):]), output_dir / f"{name}.mp4", self.fps)
        self.closures += 1
        self.records.append({"chunk": int(m.group(2)), "action": action})
        self.pose = Pose(self.deg)
        print(f"  [loop-close] {task_id}: closed via {action} at chunk {int(m.group(2))}", flush=True)
        try:
            task_dir = output_dir.parent.parent if output_dir.name.startswith("chunk_") else output_dir
            (task_dir / "loop_close.json").write_text(json.dumps(self.records, indent=1))
        except OSError:
            pass
        return out


_engines: list[LoopClosureEngine] = []


def enabled(environ=os.environ) -> bool:
    return environ.get("LOOP_CLOSE", "0") == "1"


def install(run_agent_module, environ=os.environ) -> bool:
    """Wrap the engine currently installed as run_agent.SanaWMEngine when LOOP_CLOSE=1. Call after the
    runner has installed its own engine."""
    if not enabled(environ):
        return False
    base_cls = run_agent_module.SanaWMEngine

    def factory(args):
        eng = LoopClosureEngine(base_cls(args), args)
        _engines.append(eng)
        return eng

    run_agent_module.SanaWMEngine = factory
    return True


def finish() -> None:
    for eng in _engines:
        print(f"[loop-close] total closures={eng.closures} tracked_chunks={eng.calls}", flush=True)
