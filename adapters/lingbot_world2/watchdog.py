"""Stall watchdog for one engine call (reset + step of a chunk, or a stateless rollout).

Twice, one 14B shard of three sat in the first chunk's reset for 13-24 minutes with no output after the
harness's `chunk 1/N` line, while the same reset takes 77-97 s on the other shards. Nothing in the log
said which sub-step was stuck (CPU T5 encode is the suspect). Limits come from runner args, which reach
the Modal container, or from env vars, which reach only local runs:

- `--lingbot-stall-dump N` / LINGBOT_STALL_DUMP_S (default 300; 0 = off): if one call runs longer than
  N s, every thread's Python stack is written to the process's real stderr (faulthandler runs in a C
  thread, so it fires even while the main thread is inside a torch op), and again every N s until the
  call returns.
- `--lingbot-stall-abort N` / LINGBOT_STALL_ABORT_S (default 0 = off): if one call runs longer than N s,
  print a `[lingbot] stall:` line, dump the stacks and end the process with exit code 124, so a stuck
  shard fails and frees its GPU. The process is the runner, which holds one task family of the shard
  under `pwa gen` and every remaining arm and family of the shard under `pwa gen-arms`; those tasks get
  no mp4 and `pwa gen` reports them missing.
"""
from __future__ import annotations

import faulthandler
import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

ABORT_EXIT_CODE = 124
DUMP_ARG, ABORT_ARG = "--lingbot-stall-dump", "--lingbot-stall-abort"
DUMP_ENV, ABORT_ENV = "LINGBOT_STALL_DUMP_S", "LINGBOT_STALL_ABORT_S"
DEFAULT_DUMP_S = 300.0


@dataclass(frozen=True)
class Limits:
    dump_s: float = DEFAULT_DUMP_S  # 0 = off
    abort_s: float = 0.0            # 0 = off

    def describe(self) -> str:
        return (f"dump {self.dump_s:.0f}s" if self.dump_s else "dump off") + \
            (f", abort {self.abort_s:.0f}s (exit {ABORT_EXIT_CODE})" if self.abort_s else ", abort off")


def _seconds(name: str, raw: str) -> float:
    try:
        v = float(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be a number of seconds, got {raw!r}") from exc
    if not v >= 0 or v == float("inf"):
        raise SystemExit(f"{name} must be a finite number >= 0, got {raw!r}")
    return v


def parse(argv: list[str], environ) -> tuple[Limits, list[str]]:
    """Limits from `--lingbot-stall-dump N` / `--lingbot-stall-abort N` (or `=N`) in argv, else the env vars,
    else the defaults; and argv without those args. The last occurrence of an arg wins."""
    vals = {DUMP_ARG: None, ABORT_ARG: None}
    rest, i = [], 0
    while i < len(argv):
        a = argv[i]
        key = next((k for k in vals if a == k or a.startswith(k + "=")), None)
        if key is None:
            rest.append(a)
            i += 1
            continue
        if a == key:
            if i + 1 >= len(argv):
                raise SystemExit(f"{key} needs a number of seconds")
            vals[key], i = argv[i + 1], i + 2
        else:
            vals[key], i = a[len(key) + 1:], i + 1

    def pick(arg, env, default):
        if vals[arg] is not None:
            return _seconds(arg, vals[arg])
        raw = environ.get(env, "")
        return default if raw.strip() == "" else _seconds(env, raw)

    return Limits(pick(DUMP_ARG, DUMP_ENV, DEFAULT_DUMP_S), pick(ABORT_ARG, ABORT_ENV, 0.0)), rest


def _say(msg: str, file) -> None:
    """Print to the current stderr (gen.log in a `pwa gen` child) and to the real one if it differs
    (`pwa gen-arms` redirects sys.stderr into a buffer that an os._exit would lose)."""
    for f in dict.fromkeys(x for x in (sys.stderr, file) if x is not None):
        try:
            print(msg, file=f, flush=True)
        except Exception:  # noqa: BLE001 - logging must never break the call it guards
            pass


def _abort(label: str, abort_s: float, file, exit_fn) -> None:
    _say(f"[lingbot] stall: {label} still running after {abort_s:.0f}s; dumping stacks and exiting "
         f"with {ABORT_EXIT_CODE} ({ABORT_ARG})", file)
    faulthandler.dump_traceback(file=file, all_threads=True)
    file.flush()
    try:
        sys.stdout.flush()
    except Exception:  # noqa: BLE001
        pass
    exit_fn(ABORT_EXIT_CODE)


@contextmanager
def watch(label: str, limits: Limits, file=None, exit_fn=os._exit):
    """Guard one engine call. `file` must have a real file descriptor (faulthandler writes to it directly);
    default sys.__stderr__. `exit_fn` is injectable for tests."""
    file = sys.__stderr__ if file is None else file
    dump_s, abort_s = limits.dump_s, limits.abort_s
    timer = None
    if dump_s > 0:
        faulthandler.dump_traceback_later(dump_s, repeat=True, file=file)
    if abort_s > 0:
        timer = threading.Timer(abort_s, _abort, args=(label, abort_s, file, exit_fn))
        timer.daemon = True
        timer.start()
    t0 = time.time()
    try:
        yield
    finally:
        if dump_s > 0:
            faulthandler.cancel_dump_traceback_later()
        if timer is not None:
            timer.cancel()
        dt = time.time() - t0
        if dump_s > 0 and dt > dump_s:
            _say(f"[lingbot] stall: {label} returned after {dt:.0f}s (over {DUMP_ARG} {dump_s:.0f})", file)
