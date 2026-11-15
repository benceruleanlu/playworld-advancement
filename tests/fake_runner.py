#!/usr/bin/env python3
"""Stub runner with run_agent.py's argv: writes ffmpeg testsrc mp4s. FAKE_FAIL="ID ..." simulates failures.
FAKE_PLAYER=1 prints, per task, an empty player reply, a retry, an upstream fallback and the agent_api counter
line, and a counter total at the end (what a closed-loop run with a flaky player logs).

main(argv) is the in-process entry point `pwa gen-arms` calls; _model() stands in for a model load that a
real runner caches per process, and every call prints `[fake] model loads=N` so tests can count loads."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_MODEL = None
LOADS = 0


def _model():
    global _MODEL, LOADS
    if _MODEL is None:
        LOADS += 1
        _MODEL = object()
    return _MODEL


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping-json", required=True)
    ap.add_argument("--images-dir")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--tasks", nargs="+")
    ap.add_argument("--action-source")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--no-skip-done", dest="skip_done", action="store_false")
    ap.add_argument("--seconds", type=float, default=float(os.environ.get("FAKE_SECONDS", "2")))
    a, rest = ap.parse_known_args(argv[1:])
    _model()
    print(f"[fake] model loads={LOADS} args={' '.join(rest)}")
    wanted = set(a.tasks or [])
    tasks = [t["task_id"] for t in json.load(open(a.mapping_json)) if not wanted or t["task_id"] in wanted]
    if a.num_shards > 1:
        tasks = [t for i, t in enumerate(tasks) if i % a.num_shards == a.shard]
    fail = set(os.environ.get("FAKE_FAIL", "").split())
    out = Path(a.output_dir)
    for tid in tasks:
        d = out / tid
        mp4 = d / f"{tid}.mp4"
        if a.skip_done and mp4.exists():
            print(f"skip {tid}")
            continue
        d.mkdir(parents=True, exist_ok=True)
        if tid in fail:
            print(f"[{tid}] fatal: simulated")
            (d / f"{tid}_result.json").write_text(json.dumps({"task_id": tid, "success": False, "error": "simulated"}))
            continue
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc=duration={a.seconds}:size=640x360:rate=16", "-pix_fmt", "yuv420p", str(mp4)],
                       check=True)
        (d / f"{tid}_result.json").write_text(json.dumps({"task_id": tid, "success": True,
                                                         "action_source": a.action_source}))
        if os.environ.get("FAKE_PLAYER") == "1":
            print("    [agent] empty reply (finish_reason=length, completion_tokens=4096, reasoning_tokens=4096) "
                  "-> retry 1 (max_completion_tokens=4096)")
            print("    [agent] fallback=RIGHT")
            print(f"[agent] player task={tid} decisions=3 calls=4 empty=1 retries=1 errors=0 fallbacks=1")
        print(f"[{tid}] DONE -> {mp4}")
    if os.environ.get("FAKE_PLAYER") == "1":
        n = len(tasks)
        print(f"[agent] player total tasks={n} decisions={3 * n} calls={4 * n} empty={n} retries={n} errors=0 "
              f"fallbacks={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
