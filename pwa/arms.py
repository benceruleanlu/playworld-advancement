"""pwa gen-arms: several arms (runner arg strings) on one task list, back to back in one process.

    pwa gen-arms EXP --arms " | --lingbot-turn-cal --lingbot-player-hint" --tasks GC005 --runner lingbot_world2_1p3b

Arm i (1-based) is an ordinary experiment named EXP-a<i>: its own runs/EXP-a<i>/ with meta.json, gen.log and
videos, written by the same pwa/gen.py code as `pwa gen`. The difference is how the runner runs: instead of
one child process per family, pwa calls the runner's `main(argv)` in this process, so a runner that keeps
its model in a module-level cache (adapters/lingbot_world2/run.py) loads it once for all arms and families.

Each call gets its own argv, environment (restored afterwards), working directory and captured output;
the runner is responsible for resetting its own module state per call (lingbot_world2/run.py re-reads its
flags, resets turn rates and counters and imports a fresh upstream run_agent).
"""
from __future__ import annotations

import contextlib
import copy
import gc
import hashlib
import importlib
import importlib.util
import io
import os
import shlex
import sys
import traceback
from pathlib import Path

from . import gen
from .core import ROOT, SANA_RUNNER, PwaError, exp_dir, log

SEP = "|"
MAX_ARMS = 8


def parse_arms(text: str) -> list[list[str]]:
    """'|'-separated runner arg strings -> one argv list per arm. An empty segment is a baseline arm
    (no extra args), so " | --lingbot-turn-cal" is baseline vs turn-cal."""
    if not (text or "").strip():
        raise PwaError("--arms is empty; give '|'-separated runner arg strings, e.g. ' | --lingbot-turn-cal'")
    arms = []
    for seg in text.split(SEP):
        try:
            arms.append(shlex.split(seg))
        except ValueError as e:
            raise PwaError(f"cannot parse arm {seg.strip()!r}: {e}") from e
    if len(arms) > MAX_ARMS:
        raise PwaError(f"{len(arms)} arms; at most {MAX_ARMS} per container")
    return arms


def arm_names(exp: str, n: int) -> list[str]:
    return [f"{exp}-a{i}" for i in range(1, n + 1)]


def arm_label(arm: list[str], shared: list[str] | None = None) -> str:
    """Every arg the arm ran with: the args shared by all arms (`--` / workflow `extra`), then its own.
    "base" only when both are empty, so a label never hides a flag the run used."""
    return " ".join([*(shared or []), *arm]) or "base"


def load_main(runner: Path):
    """The runner's in-process entry point main(argv) -> int. adapters/<name>/run.py is imported as
    adapters.<name>.run, so later calls share its module (and model cache); other paths load once per
    process under a name derived from the path."""
    if runner == SANA_RUNNER.resolve():
        raise PwaError("gen-arms needs a runner with main(argv); the upstream SANA runner has none")
    # importing a script without a __main__ guard would run it; refuse before importing anything
    if '__name__ == "__main__"' not in runner.read_text():
        raise PwaError(f"runner {runner} has no __main__ guard and main(argv); gen-arms needs an in-process "
                       f"runner (lingbot_world2, lingbot_world2_1p3b)")
    try:
        rel = runner.relative_to((ROOT / "adapters").resolve())
    except ValueError:
        rel = None
    if rel is not None and len(rel.parts) == 2 and rel.name == "run.py":
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        mod = importlib.import_module(f"adapters.{rel.parts[0]}.run")
    else:
        name = "_pwa_runner_" + hashlib.sha1(str(runner).encode()).hexdigest()[:12]
        mod = sys.modules.get(name)
        if mod is None:
            spec = importlib.util.spec_from_file_location(name, runner)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
    fn = getattr(mod, "main", None)
    if not callable(fn):
        raise PwaError(f"runner {runner} has no main(argv); gen-arms needs an in-process runner "
                       f"(lingbot_world2, lingbot_world2_1p3b)")
    return fn


class _Lines(io.TextIOBase):
    """File-like stdout/stderr that hands complete lines to on_line (what gen.py reads from a child's pipe)."""

    def __init__(self, on_line):
        # on_line echoes to stderr; it must reach the real one, not this object
        self.on_line, self.buf, self.real = on_line, "", (sys.stdout, sys.stderr)

    @property
    def encoding(self):
        return "utf-8"

    def writable(self):
        return True

    def _emit(self, line):
        cur = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = self.real
        try:
            self.on_line(line)
        finally:
            sys.stdout, sys.stderr = cur

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._emit(line + "\n")
        return len(s)

    def finish(self):
        if self.buf:
            self._emit(self.buf + "\n")
            self.buf = ""


def _free_gpu_cache():
    gc.collect()
    torch = sys.modules.get("torch")
    if torch is not None and getattr(torch, "cuda", None) is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def inproc_launch(main_fn):
    """A gen.gen launch() that calls main_fn(argv) in this process instead of spawning the runner.
    Output written through sys.stdout / sys.stderr reaches gen.log; output a child process of the runner
    writes straight to file descriptor 1 or 2 (e.g. ffmpeg) does not."""
    def launch(cmd: list[str], env: dict, on_line) -> int:
        argv = list(cmd[2:])  # drop [python, -u]; argv[0] is the runner script, as in a child process
        saved_env, saved_argv, saved_cwd = dict(os.environ), sys.argv, os.getcwd()
        sink = _Lines(on_line)
        try:
            os.environ.update(env)
            os.chdir(ROOT)
            sys.argv = list(argv)
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                try:
                    rc = main_fn(argv)
                except SystemExit as e:
                    if e.code is None or isinstance(e.code, int):
                        rc = e.code or 0
                    else:
                        print(e.code)
                        rc = 1
                except Exception:  # noqa: BLE001 - a crashed arm is recorded like a crashed child
                    traceback.print_exc()
                    rc = 1
        finally:
            sink.finish()
            sys.argv = saved_argv
            os.chdir(saved_cwd)
            os.environ.clear()
            os.environ.update(saved_env)
            _free_gpu_cache()
        return int(rc or 0)
    return launch


def gen_arms(a, sel: list[dict]) -> dict:
    arms = parse_arms(a.arms)
    names = arm_names(a.exp, len(arms))
    if not a.resume:
        taken = [n for n in names if exp_dir(n).exists()]
        if taken:
            raise PwaError(f"{', '.join(taken)} already exist(s). Pick a new experiment name, or pass --resume.")
    main_fn = load_main(gen.resolve_runner(a.runner))
    launch = inproc_launch(main_fn)
    summaries = []
    for i, (name, arm) in enumerate(zip(names, arms), 1):
        b = copy.copy(a)
        b.exp, b.extra = name, [*(a.extra or []), *arm]
        label = arm_label(arm, a.extra)
        b.notes = " ".join(x for x in (a.notes, f"[arm {i}/{len(arms)} of {a.exp}: {label}]") if x)
        log(f"[pwa] arm {i}/{len(arms)} {name}: {label}")
        s = gen.gen(b, sel, launch=launch,
                    meta_extra={"arm_group": a.exp, "arm": i, "num_arms": len(arms), "arm_args": arm})
        summaries.append({**s, "arm": i, "arm_args": arm})
    return {"exp": a.exp, "arms": summaries,
            "failed": any(s["failed"] or s["runner_errors"] for s in summaries)}


def listing(exp: str, text: str, shared: str = "") -> list[str]:
    """One "NAME I/N LABEL" line per arm (python -m pwa.arms EXP ARMS [SHARED]; read by .github/workflows/arms.yml).
    SHARED is the runner arg string every arm gets first (the workflow's `extra`), so labels match gen_arms."""
    arms = parse_arms(text)
    try:
        common = shlex.split(shared or "")
    except ValueError as e:
        raise PwaError(f"cannot parse shared args {shared!r}: {e}") from e
    return [f"{name} {i}/{len(arms)} {arm_label(arm, common)}"
            for i, (name, arm) in enumerate(zip(arm_names(exp, len(arms)), arms), 1)]


if __name__ == "__main__":
    try:
        print("\n".join(listing(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")))
    except PwaError as e:
        log(f"pwa: {e}")
        raise SystemExit(2) from None
