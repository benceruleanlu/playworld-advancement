"""Controlled camera-response measurements for LingBot (numpy only; the GPU side is workspace.turn_trial).

The yaw-gain and backlash flags rest on rotation measured in one or two published clips. This asks the
model directly, with fixed scripts, the same seed and full-resolution frames:

  gain        when the poses command a turn of X degrees, how far does the rendered view rotate?
  direction   is that the same turning left and right?
  hysteresis  after turning out, does the same commanded angle back return the view?
  closure     does the start view come back: what heading error is left, and is it the same content?

A script is a list of segments: ("l", degrees) turns right, ("j", degrees) turns left, ("none", frames)
waits. Turns run at `rate_deg` per frame; the default is the task prompts' own rate, 22.5 degrees per
20-frame dataset token ("→*4" means 90 degrees), which is what --lingbot-turn-cal commands.

Rotation is read with measured_turn.chunk_turn (phase correlation between consecutive frames, centre half
of the image, LingBot's intrinsics). It is an image-motion estimate: a narrower rendered field of view than
the intrinsics say would scale every angle, but not the comparisons between directions or the closure error
at zero. Closure compares two frames directly and is only trusted inside about 20 degrees, where the views
still overlap; `match` says whether they do.
"""
from __future__ import annotations

import math

import numpy as np

from adapters.lingbot_world2 import measured_turn as MT
from adapters.lingbot_world2 import poses as P
from adapters.lingbot_world2 import session as S
from adapters.lingbot_world2.yaw_servo import RIGID_MIN, rigid_share  # noqa: F401 - used on trial clips

TOKEN_FRAMES = 20
TOKEN_YAW_DEG = 22.5
RATE_DEG = TOKEN_YAW_DEG / TOKEN_FRAMES   # 1.125 degrees per frame
SIGN = {"l": 1.0, "j": -1.0}              # right positive, as measured_turn and player_hint
GOOD_MATCH = 0.06                         # phase-correlation peak above which two frames show the same view


def build(segments, rate_deg: float = RATE_DEG) -> tuple[list[str], list[dict], int]:
    """(keys, spans, n_chunks) for a fresh rollout.

    keys: one key per generated frame, padded with waits to whole latent chunks (16n - 4 keys).
    spans: per segment {"key", "first", "last", "commanded"}; frames[first..last] are the frames the segment
    produced plus the one before it, so their consecutive pairs are exactly the segment's motion (frame 0 is
    the input image). `commanded` is in degrees, right positive, 0 for a wait."""
    if rate_deg <= 0:
        raise ValueError(f"rate_deg must be positive, got {rate_deg}")
    keys, spans = [], []
    for key, amount in segments:
        if key in SIGN:
            n = max(1, round(float(amount) / rate_deg))
            commanded = SIGN[key] * n * rate_deg
        elif key == "none":
            n, commanded = int(amount), 0.0
        else:
            raise ValueError(f"segment key must be 'l' (right), 'j' (left) or 'none', got {key!r}")
        if n <= 0:
            raise ValueError(f"empty segment {(key, amount)!r}")
        spans.append({"key": key, "first": len(keys), "last": len(keys) + n, "commanded": commanded})
        keys += [key] * n
    n_chunks = max(1, math.ceil((len(keys) + 4) / S.FRAMES_PER_CHUNK))
    keys += ["none"] * (S.keys_needed(n_chunks, first=True) - len(keys))
    return keys, spans, n_chunks


def measure(frames, spans) -> list[dict]:
    """Per segment: commanded and rendered yaw (degrees, right positive), their ratio, vertical drift and the
    mean correlation peak (under measured_turn.MIN_PEAK the estimate is not trusted)."""
    out = []
    for s in spans:
        yaw, pitch, peak = MT.chunk_turn(frames[s["first"]:s["last"] + 1])
        gain = yaw / s["commanded"] if s["commanded"] else None
        out.append({"key": s["key"], "frames": s["last"] - s["first"], "commanded": round(s["commanded"], 2),
                    "rendered": round(yaw, 2), "gain": None if gain is None else round(gain, 3),
                    "pitch": round(pitch, 2), "peak": round(peak, 3), "trusted": bool(peak >= MT.MIN_PEAK)})
    return out


def _prep(frame) -> tuple[np.ndarray, float, float, float, float]:
    """Centre half of a grey frame at about 416 px wide, with chunk_turn's focal lengths and off-axis factors."""
    g = np.asarray(frame, dtype=np.float32)
    g = g.mean(axis=2) if g.ndim == 3 else g
    g = g[::max(1, round(g.shape[1] / 416)), ::max(1, round(g.shape[1] / 416))]
    h, w = g.shape
    scale = w / (2.0 * P.INTRINSICS_480P[2])
    fx, fy = P.INTRINSICS_480P[0] * scale, P.INTRINSICS_480P[1] * scale
    kx, ky = 1 + (w / 4) ** 2 / (3 * fx * fx), 1 + (h / 4) ** 2 / (3 * fy * fy)
    return g[h // 4:h - h // 4, w // 4:w - w // 4], fx, fy, kx, ky


def closure(frames, i: int = 0, j: int = -1) -> dict:
    """How frame j sits relative to frame i: heading and tilt offset in degrees (right and up positive, 0 when
    the view is back), and `match`, the correlation peak (near 0 when the two frames show different content)."""
    a, fx, fy, kx, ky = _prep(frames[i])
    b = _prep(frames[j])[0]
    dx, dy, peak = MT.shift(a, b)
    return {"yaw": round(-math.degrees(math.atan(dx / fx)) / kx, 2),
            "pitch": round(math.degrees(math.atan(dy / fy)) / ky, 2),
            "match": round(peak, 3), "ncc": round(_ncc(a, b, dx, dy), 3), "same_view": bool(peak >= GOOD_MATCH)}


def _ncc(a: np.ndarray, b: np.ndarray, dx: float, dy: float) -> float:
    """Zero-mean normalised correlation of the part of a and b that overlaps once b's content shift (dx, dy)
    is undone: near 1 for the same view, near 0 for unrelated content. 0 when under a tenth overlaps."""
    sx, sy = int(round(dx)), int(round(dy))
    h, w = a.shape
    if abs(sx) >= w or abs(sy) >= h:
        return 0.0
    pa = a[max(0, -sy):h - max(0, sy), max(0, -sx):w - max(0, sx)]
    pb = b[max(0, sy):h - max(0, -sy), max(0, sx):w - max(0, -sx)]
    if pa.size < 0.1 * a.size:
        return 0.0
    pa, pb = pa - pa.mean(), pb - pb.mean()
    den = float(np.sqrt((pa * pa).sum() * (pb * pb).sum()))
    return float((pa * pb).sum() / den) if den > 0 else 0.0


def best_return(frames, after: int, ref: int = 0) -> dict:
    """The frame at or after `after` that best matches frame `ref`: where the start view reappears, if it does."""
    a = _prep(frames[ref])[0]
    best = {"frame": None, "match": 0.0}
    for k in range(max(after, ref + 1), len(frames)):
        peak = MT.shift(a, _prep(frames[k])[0])[2]
        if peak > best["match"]:
            best = {"frame": k, "match": round(peak, 3)}
    best["same_view"] = bool(best["match"] >= GOOD_MATCH)
    return best


def summarize(frames, spans) -> dict:
    """One trial's readout: per-segment turns, net rendered heading at the end, closure against frame 0 at the
    end of the last turn, and the best later match with frame 0."""
    segs = measure(frames, spans)
    turns = [s for s in spans if s["commanded"]]
    end = turns[-1]["last"] if turns else len(frames) - 1
    commanded_net = sum(s["commanded"] for s in spans)
    rendered_net = sum(m["rendered"] for m in segs)
    first_turn_end = turns[0]["last"] if turns else 0
    return {"segments": segs, "commanded_net": round(commanded_net, 2), "rendered_net": round(rendered_net, 2),
            "closure": closure(frames, 0, end), "best_return": best_return(frames, first_turn_end),
            "frames": int(len(frames)), "trusted": all(m["trusted"] for m in segs if m["commanded"])}


def gains_from(trials: list[dict]) -> dict:
    """Mean rendered/commanded ratio per direction and phase over trusted turn segments.
    phase: 'out' = the first turn of a trial, 'back' = any later turn (after a reversal)."""
    acc: dict = {}
    for t in trials:
        seen_turn = False
        for m in t["segments"]:
            if not m["commanded"]:
                continue
            phase = "back" if seen_turn else "out"
            seen_turn = True
            if m["trusted"] and m["gain"] is not None:
                acc.setdefault((m["key"], phase), []).append(m["gain"])
    return {f"{'right' if k == 'l' else 'left'}_{phase}": {"mean": round(float(np.mean(v)), 3),
                                                             "sd": round(float(np.std(v)), 3), "n": len(v)}
            for (k, phase), v in sorted(acc.items())}


# ----------------------------------------------------------------- report

def load_trials(paths) -> list[dict]:
    """Trial readouts from .jsonl files (one JSON object per line); a repeated id keeps its last entry."""
    import json  # noqa: PLC0415
    seen: dict = {}
    for path in paths:
        with open(path) as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    seen[row.get("id") or len(seen)] = row
    return list(seen.values())


def _turns(row: dict) -> list[dict]:
    return [m for m in row["segments"] if m["commanded"]]


def arm_of(row: dict) -> str:
    """Which method produced a trial: 'open' (gain 1, no feedback), 'servo', or its tag (e.g. 'fixed-L0.8')."""
    tag = row.get("tag") or "base"
    if "servo" in row:
        return "servo" if row["servo"].get("adapt", True) else "open"
    return "open" if tag in ("base", "onestep") else tag


def end_error(row: dict) -> float:
    """Degrees between where the script should end and where the rendered view ended (from summed frame motion)."""
    return abs(row["rendered_net"] - row["commanded_net"])


def gain_table(rows: list[dict]) -> str:
    """Markdown: per scene, rendered / commanded for left and right, on the first turn and after a reversal."""
    by: dict = {}
    for r in rows:
        if arm_of(r) != "open" or not r.get("trusted", True):
            continue
        for i, m in enumerate(_turns(r)):
            by.setdefault(r["task"], {}).setdefault(("L" if m["key"] == "j" else "R", "first" if i == 0 else "later"), []).append(m["gain"])
    out = ["| Scene | Left, first turn | Left, later | Right, first turn | Right, later | Left over right |", "|---|---|---|---|---|---|"]
    mean = lambda v: sum(v) / len(v) if v else float("nan")  # noqa: E731
    fmt = lambda v: f"{mean(v):.2f}" if v else "-"            # noqa: E731
    for task in sorted(by):
        g = by[task]
        left, right = g.get(("L", "first"), []) + g.get(("L", "later"), []), g.get(("R", "first"), []) + g.get(("R", "later"), [])
        ratio = f"{mean(left) / mean(right):.2f}" if left and right else "-"
        out.append(f"| {task} | {fmt(g.get(('L', 'first'), []))} | {fmt(g.get(('L', 'later'), []))} | "
                   f"{fmt(g.get(('R', 'first'), []))} | {fmt(g.get(('R', 'later'), []))} | {ratio} |")
    return "\n".join(out)


def arm_table(rows: list[dict], names=("L90-R90", "R90-L90")) -> str:
    """Markdown: per scene and script, the end heading error of each arm, with the mean per arm."""
    arms = sorted({arm_of(r) for r in rows}, key=lambda a: (a != "open", a))
    cell: dict = {}
    for r in rows:
        if r["name"] in names:
            cell[(r["task"], r["name"], arm_of(r))] = r
    out = ["| Scene | Script | " + " | ".join(arms) + " |", "|---|---|" + "---|" * len(arms)]
    sums = {a: [] for a in arms}
    for task, name in sorted({(t, n) for t, n, _ in cell}):
        vals = []
        for a in arms:
            r = cell.get((task, name, a))
            if r is None:
                vals.append("-")
            else:
                vals.append(f"{end_error(r):.1f}" + ("" if r.get("trusted", True) else " (untrusted)"))
                if all((task, name, b) in cell for b in arms):
                    sums[a].append(end_error(r))
        out.append(f"| {task} | {name} | " + " | ".join(vals) + " |")
    n = len(next(iter(sums.values()))) if sums else 0
    out.append(f"| **mean over the {n} rows every arm ran** | | "
               + " | ".join(f"**{sum(v) / len(v):.1f}**" if v else "-" for v in sums.values()) + " |")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    trials = load_trials(sys.argv[1:])
    print(f"{len(trials)} trials\n\nRendered / commanded yaw, open loop:\n\n{gain_table(trials)}\n\n"
          f"Heading error at the end of the script, degrees:\n\n{arm_table(trials)}")
