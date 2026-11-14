"""What LingBot's self-attention KV cache can still see (numpy only; step 0 of the memory study).

LingBot-World v2 causal-fast runs with local_attn_size=18, sink_size=6 (run.py).
Upstream CausalWanSelfAttention (wan/modules/model_fast.py @ 1895d300) keeps the
first `sink` latents forever and rolls the rest, so while chunk c is generated the
queries see: the sink latents, plus the latest `local - sink` latents, which
include the chunk itself. Everything in between is evicted. This module mirrors
that rule and asks, for every chunk, whether the camera is looking at something
it saw before (a revisit) and whether those latents are still in the cache.

    python -m adapters.lingbot_world2.cache_model --split dev --family outsight
    python -m adapters.lingbot_world2.cache_model --split dev --local-attn 36 --sink 6 --json

The CLI replays each task's dataset action (upstream build_full_sana_action, the
same string `--action-source dataset` generates) and needs data/<family>/data.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

CHUNK = 4                 # latents per causal chunk
LOCAL_ATTN, SINK = 18, 6  # run.py defaults
ANGLE_DEG = 20.0          # forward vectors within this angle count as the same view
DIST = 16.0               # and camera centres within this distance (poses.py units: 1 per frame of 'w')
RECENT_CHUNKS = 1         # matches inside the previous chunk are continuity, not a revisit


def visible(chunk: int, local_attn: int = LOCAL_ATTN, sink: int = SINK, chunk_len: int = CHUNK) -> list[int]:
    """Global latent indices before `chunk` that its queries attend to."""
    start = chunk * chunk_len
    end = start + chunk_len  # cache after the chunk's own keys are written
    if local_attn < 0 or end <= local_attn:
        return list(range(start))
    rolled = range(max(sink, end - (local_attn - sink)), start)
    return list(range(min(sink, start))) + list(rolled)


def forward(c2w: np.ndarray) -> np.ndarray:
    """Camera viewing direction (OpenCV: +z forward) in world coordinates."""
    f = np.asarray(c2w)[..., :3, 2]
    return f / np.linalg.norm(f, axis=-1, keepdims=True)


def view_angles(cur: np.ndarray, past: np.ndarray) -> np.ndarray:
    """[len(cur), len(past)] degrees between viewing directions."""
    d = np.clip(forward(cur) @ forward(past).T, -1.0, 1.0)
    return np.degrees(np.arccos(d))


def chunk_report(latent_c2ws: np.ndarray, local_attn: int = LOCAL_ATTN, sink: int = SINK,
                 angle: float = ANGLE_DEG, dist: float = DIST, chunk_len: int = CHUNK) -> list[dict]:
    """One row per chunk after the first.

    best_all / best_vis: median over the chunk's latents of the angle to the
    nearest matching past latent (all history vs what the cache still holds);
    None when nothing within `dist` exists. revisit: some latent of the chunk
    matches history older than the previous chunk. evicted: a revisit whose
    matching latents are all gone from the cache."""
    lat = np.asarray(latent_c2ws, dtype=np.float64)
    n_chunks = len(lat) // chunk_len
    rows = []
    for c in range(1, n_chunks):
        cur = lat[c * chunk_len:(c + 1) * chunk_len]
        old_end = max(0, (c - RECENT_CHUNKS) * chunk_len)
        vis = set(visible(c, local_attn, sink, chunk_len))
        ang = view_angles(cur, lat[:c * chunk_len])
        near = np.linalg.norm(cur[:, None, :3, 3] - lat[None, :c * chunk_len, :3, 3], axis=-1) <= dist
        ang = np.where(near, ang, np.inf)
        match = ang <= angle
        old = match[:, :old_end]
        vis_mask = np.zeros(c * chunk_len, dtype=bool)
        vis_mask[list(vis)] = True
        revisit = bool(old.any())
        old_vis = old & vis_mask[None, :old_end]

        def med(a):
            m = a.min(axis=1)
            m = m[np.isfinite(m)]
            return round(float(np.median(m)), 1) if len(m) else None

        rows.append({
            "chunk": c,
            "latents": [c * chunk_len, (c + 1) * chunk_len],
            "best_all": med(ang),
            "best_vis": med(np.where(vis_mask[None], ang, np.inf)),
            "revisit": revisit,
            "evicted": revisit and not bool(old_vis.any()),
            "matched_latents": sorted({int(j) for j in np.nonzero(old.any(axis=0))[0]}),
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    rev = [r for r in rows if r["revisit"]]
    ev = [r for r in rev if r["evicted"]]
    return {"chunks": len(rows) + 1, "revisit_chunks": len(rev), "evicted_revisit_chunks": len(ev),
            "first_evicted_chunk": ev[0]["chunk"] if ev else None}


def latents_from_frames(c2ws: np.ndarray) -> np.ndarray:
    """Per-pixel-frame poses -> one pose per latent (frame 0, then every 4th), whole chunks only."""
    lat = np.asarray(c2ws)[::4]
    return lat[: len(lat) // CHUNK * CHUNK]


# ------------------------------------------------------------------- CLI

def _task_latents(task: dict, args):
    """Latent poses the default persistent runner generates for the task's dataset action: the same chunk
    count and fitted keys as run.py _generate_session (reset plus one long step), not the stateless rounding."""
    from adapters.common.upstream import import_run_agent  # noqa: PLC0415
    from adapters.lingbot_world2 import poses as P  # noqa: PLC0415
    from adapters.lingbot_world2 import session as S  # noqa: PLC0415
    ra = import_run_agent()
    action, _ = ra.build_full_sana_action(task, args.action_frame_unit, args.tail_frames, args.max_total_frames)
    n = sum(int(s.rpartition("-")[2]) for s in action.split(",") if s) + 1
    keys = S.fit_keys(P.parse_action(action), S.keys_needed(S.chunks_for(n), first=True))
    if args.turn_cal:
        P.calibrate(True, len(keys), args.action_frame_unit)
    track = S.PoseTrack()
    track.advance(keys)
    return np.stack(track.latents), action


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--split", default="dev")
    ap.add_argument("--family", action="append")
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--local-attn", type=int, default=LOCAL_ATTN)
    ap.add_argument("--sink", type=int, default=SINK)
    ap.add_argument("--angle", type=float, default=ANGLE_DEG)
    ap.add_argument("--dist", type=float, default=DIST)
    ap.add_argument("--turn-cal", action="store_true", help="as run.py --lingbot-turn-cal")
    ap.add_argument("--action-frame-unit", type=int, default=20)
    ap.add_argument("--tail-frames", type=int, default=50)
    ap.add_argument("--max-total-frames", type=int, default=961)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    from pwa import core  # noqa: PLC0415
    out = []
    for t in core.select(args.split, args.family, args.tasks):
        rec = dict(core.records(t["family"])[t["task_id"]])
        lat, action = _task_latents(rec, args)
        rows = chunk_report(lat, args.local_attn, args.sink, args.angle, args.dist)
        out.append({"family": t["family"], "task_id": t["task_id"], "action": action,
                    **summarize(rows), "rows": rows})
    if args.json:
        json.dump(out, sys.stdout, indent=1)
        print()
        return 0
    print(f"window local_attn={args.local_attn} sink={args.sink}; revisit = view within {args.angle} deg "
          f"and {args.dist} units of history older than one chunk")
    print(f"{'family':9} {'task':8} {'chunks':>6} {'revisit':>7} {'evicted':>7}  first_evicted")
    for r in out:
        print(f"{r['family']:9} {r['task_id']:8} {r['chunks']:6d} {r['revisit_chunks']:7d} "
              f"{r['evicted_revisit_chunks']:7d}  {r['first_evicted_chunk'] if r['first_evicted_chunk'] is not None else '-'}")
    hit = [r for r in out if r["evicted_revisit_chunks"]]
    print(f"\n{len(hit)}/{len(out)} tasks revisit a view whose latents were already evicted")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
