#!/usr/bin/env python3
"""Stub runner with run_agent.py's argv: writes ffmpeg testsrc mp4s. FAKE_FAIL="ID ..." simulates failures."""
import argparse
import json
import os
import subprocess
from pathlib import Path

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
a, _ = ap.parse_known_args()
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
                    f"testsrc=duration={a.seconds}:size=640x360:rate=16", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    (d / f"{tid}_result.json").write_text(json.dumps({"task_id": tid, "success": True, "action_source": a.action_source}))
    print(f"[{tid}] DONE -> {mp4}")
