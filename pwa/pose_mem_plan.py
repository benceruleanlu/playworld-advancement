"""Dry run of --lingbot-pose-memory selection on a task's commanded camera track (no GPU, no torch).

    python -m pwa.pose_mem_plan GC031 OE048 [--chunked] [--no-turn-cal] [--summary] [--json]
                                [--lingbot-pose-mem-time sink ...] [--lingbot-sink-size 10 --lingbot-local-attn 22]

Builds the same key sequence the runner gets (dataset mode: upstream build_full_sana_action, one `<task>_full` step
including the still tail; --chunked: the scripted player's `<task>_chunk_NN` calls), drives the real PoseTrack, and
replays PoseMemory.decide / PoseMemory.record chunk by chunk with the session's bookkeeping (_pose_mem_before /
_pose_mem_after). Turn calibration is on by default, as in the pose-memory arms. Prints per latent chunk the commanded
pose, the decision, the stored chunk, the pose difference and the RoPE time, then one summary line per task.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from adapters.lingbot_world2 import pose_memory as PM  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import session as S  # noqa: E402
from adapters.lingbot_world2 import yaw_gain as YG  # noqa: E402

CHUNK = PM.CHUNK


def find_task(task_id: str, data_dir: Path) -> dict:
    for f in sorted(Path(data_dir).glob("*/data.json")):
        for t in json.loads(f.read_text()):
            if t.get("task_id") == task_id:
                return t
    raise SystemExit(f"task {task_id} not found under {data_dir}/*/data.json")


def calls(task: dict, chunked: bool, chunk_frames: int = 33, frame_unit: int = 20, tail: int = 50,
          max_total: int = 961, num_chunks: int = 30) -> list[tuple[str, str, int]]:
    """(call name, action string, num_frames) the harness would send the engine."""
    from adapters.common.upstream import import_run_agent  # noqa: PLC0415
    ra = import_run_agent()
    tid = task["task_id"]
    if not chunked:
        action, log = ra.build_full_sana_action(task, frame_unit, tail, max_total)
        return [(f"{tid}_full", action, sum(r["frames"] for r in log) + 1)]
    from adapters.lingbot_world2 import scripted_player as SP  # noqa: PLC0415
    args = SimpleNamespace(chunk_frames=chunk_frames, action_frame_unit=frame_unit, tail_frames=tail)
    steps = SP.plan(task, args, ra.parse_segments, ra.VALID_ACTIONS)
    cap = min(num_chunks, max(1, (max_total - 1) // max(1, chunk_frames - 1)))
    return [(f"{tid}_chunk_{i + 1:02d}", f"{ra.to_sana_key(a)}-{chunk_frames}", chunk_frames)
            for i, a in enumerate(steps[:cap])]


def plan_task(task: dict, cfg: PM.PoseMemoryConfig, chunked: bool = False, turn_cal: bool = True,
              sink: int = 6, local: int = 18, chunk_frames: int = 33,
              yaw_gain: tuple[float, float] | None = None) -> tuple[list[dict], dict]:
    """Per-chunk rows and the summary of one rollout. The poses module's rotation rates are put back afterwards."""
    saved = (P.YAW, P.PITCH)
    P.reset()
    try:
        return _plan(task, cfg, chunked, turn_cal, sink, local, chunk_frames, yaw_gain)
    finally:
        P.YAW, P.PITCH = saved


def _plan(task, cfg, chunked, turn_cal, sink, local, chunk_frames, yaw_gain=None):
    track, pm, installed, chunk_id = S.PoseTrack(), None, (), 0
    track.yaw_gain = yaw_gain
    rows, applies = [], None
    for name, action, num_frames in calls(task, chunked, chunk_frames):
        cont = chunk_id > 0
        n = S.chunks_for(num_frames)
        keys = S.fit_keys(P.parse_action(action), S.keys_needed(n, first=not cont))
        if turn_cal:  # run.LingBotWorld2Engine._calibrate
            P.calibrate(S.parse_chunk_name(name) is None, len(keys), 20)
        if applies is None:
            applies = cfg.applies(name)
            pm = PM.PoseMemory(cfg, sink, local, name=name) if applies else None
        track.advance(keys)
        src = track.model_latents if cfg.track == "model" else track.latents
        for c in range(n):
            cid, lat = chunk_id, src[c * CHUNK:(c + 1) * CHUNK]
            v = PM.view_of(PM.centre(lat))
            row = {"call": name, "chunk": cid, "yaw": v[0], "pitch": v[1], "pos": float(np.linalg.norm(v[2:])),
                   "kind": "off", "memory": [], "rope": [], "notes": [], "installed_during": False}
            if pm is not None:
                d = pm.decide(lat, cid, installed)
                row["kind"] = d.kind
                if d.plan is not None:
                    row["window"], row["matched"] = d.plan.window, d.plan.matched
                    row["yaw"] = float(d.plan.target[0]) if cfg.rule != "legacy" else row["yaw"]
                if d.kind == "restore":
                    installed, pm.current = (), []
                elif d.kind in ("install", "retime"):
                    installed, pm.current = d.ids, list(d.matches)
                    row["memory"] = [m.entry.cid for m in d.matches]
                    row["diff"] = [(round(m.dyaw, 1), round(m.dpitch, 1), round(m.dpos, 1), round(m.overlap, 2))
                                   for m in d.matches]
                    row["rope"] = list(d.ropes)
                    row["notes"] = [m.note for m in d.matches if m.note]
                row["installed"] = [i for i, _ in installed]
                row["installed_during"] = bool(installed)
                pm.record(cid, lat)
            rows.append(row)
            chunk_id += 1
    mem = [r for r in rows if r["installed_during"]]
    summary = {"task": task["task_id"], "mode": "chunked" if chunked else "dataset", "chunks": len(rows),
               "applies": bool(applies),
               "retrievals": sum(r["kind"] == "install" for r in rows),
               "retimes": sum(r["kind"] == "retime" for r in rows),
               "restores": sum(r["kind"] == "restore" for r in rows),
               "memories": sorted({c for r in rows if r["kind"] == "install" for c in r["memory"]}),
               "opening_only": sum(r["kind"] == "install" and bool(r["memory"]) and all(
                   c * CHUNK < sink for c in r["memory"]) for r in rows),
               "chunks_with_memory": len(mem),
               "first": mem[0]["chunk"] if mem else None, "last": mem[-1]["chunk"] if mem else None}
    return rows, summary


def summary_line(s: dict) -> str:
    return (f"{s['task']} {s['mode']}: chunks={s['chunks']} retrievals={s['retrievals']} retimes={s['retimes']} "
            f"restores={s['restores']} memories={','.join(map(str, s['memories'])) or '-'} "
            f"opening_only={s['opening_only']} chunks_with_memory={s['chunks_with_memory']} "
            f"first={s['first'] if s['first'] is not None else '-'} last={s['last'] if s['last'] is not None else '-'}"
            + ("" if s["applies"] else " (task not matched by --lingbot-pose-mem-tasks)"))


def row_line(r: dict) -> str:
    head = f"  c{r['chunk']:02d} yaw {r['yaw']:7.1f} pitch {r['pitch']:5.1f} pos {r['pos']:5.1f}"
    if r["kind"] in ("install", "retime"):
        what = " ".join(f"<- {c} (dyaw {d[0]}, dpitch {d[1]}, dpos {d[2]}, o={d[3]})"
                        for c, d in zip(r["memory"], r["diff"])) if r["kind"] == "install" else \
            f"keeps {','.join(map(str, r['memory']))}"
        win = f" window o={r['window']:.2f}" if "window" in r else ""
        notes = f" [{'; '.join(r['notes'])}]" if r["notes"] else ""
        return f"{head} | {r['kind']} {what}{win} rope {','.join(map(str, r['rope']))}{notes}"
    tail = f" installed {','.join(map(str, r['installed']))}" if r.get("installed") else ""
    win = f" window o={r['window']:.2f} matched {r['matched']}" if "window" in r and r["kind"] != "warmup" else ""
    return f"{head} | {r['kind']}{win}{tail}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pwa.pose_mem_plan", description=__doc__.split("\n")[0])
    ap.add_argument("tasks", nargs="+")
    ap.add_argument("--chunked", action="store_true", help="scripted-player chunk calls instead of one dataset step")
    ap.add_argument("--chunk-frames", type=int, default=33)
    ap.add_argument("--no-turn-cal", action="store_true", help="default rotation rates (no --lingbot-turn-cal)")
    ap.add_argument("--lingbot-sink-size", type=int, default=6)
    ap.add_argument("--lingbot-local-attn", type=int, default=18)
    ap.add_argument("--data", type=Path, default=REPO / "data")
    ap.add_argument("--summary", action="store_true", help="summary lines only")
    ap.add_argument("--json", action="store_true")
    args, rest = ap.parse_known_args(argv)
    cfg, left = PM.parse([PM.FLAG, *rest], environ={})
    yg, left = YG.parse(left, environ={})
    if left:
        ap.error(f"unknown arguments: {' '.join(left)}")
    PM.check_window(cfg, args.lingbot_local_attn, args.lingbot_sink_size)
    out = []
    for tid in args.tasks:
        rows, s = plan_task(find_task(tid, args.data), cfg, args.chunked, not args.no_turn_cal,
                            args.lingbot_sink_size, args.lingbot_local_attn, args.chunk_frames, yg.pair())
        out.append({"summary": s, "rows": rows})
        if args.json:
            continue
        if not args.summary:
            print(f"{tid} ({cfg.describe()})")
            for r in rows:
                print(row_line(r))
        print(summary_line(s))
    if args.json:
        print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
