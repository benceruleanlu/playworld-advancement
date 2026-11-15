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


# ------------------------------------------------------------------ servo

GAIN_RANGE = (0.5, 2.0)   # the same limits as --lingbot-yaw-gain


class Servo:
    """Self-correcting yaw: follow a scripted heading using the rotation the video actually showed.

    The script gives a target heading for every frame. Before each latent chunk the servo plans that chunk's
    keys and a (left, right) pose gain; after the chunk it is told how far the frames really turned. It keeps
    one estimate per direction of rendered / commanded (`est`), divides it out of the next command, and adds
    back a share `k` of the heading error so far. When the script is waiting and the heading is off by more
    than `tol` degrees it spends some of the wait on a trim turn. Pure Python: the kernel supplies the
    measurements (workspace.servo_trial); tests drive it with a simulated camera.

    Open loop is the same class with adapt=False: it replays the script at gain 1, in the same chunks."""

    def __init__(self, segments, rate_deg: float = RATE_DEG, prior: tuple[float, float] = (1.0, 1.0),
                 adapt: bool = True, k: float = 1.0, beta: float = 0.6, tol: float = 2.0, trim: bool = True,
                 min_frames: int = 4):
        self.keys, self.spans, self.n_chunks = build(segments, rate_deg)
        self.rate, self.adapt, self.k, self.beta, self.tol, self.trim = rate_deg, adapt, k, beta, tol, trim
        self.min_frames = min_frames
        self.est = {"j": float(prior[0]), "l": float(prior[1])}   # rendered / commanded, per direction
        self.target = [0.0]                                        # scripted heading after each frame
        for key in self.keys:
            self.target.append(self.target[-1] + SIGN.get(key, 0.0) * rate_deg)
        self.frame = 0            # frames generated so far
        self.heading = 0.0        # rendered heading so far (degrees, right positive)
        self.log: list[dict] = []
        self._plan = None

    @property
    def done(self) -> bool:
        return self.frame >= len(self.keys)

    def error(self) -> float:
        """Scripted heading minus rendered heading, now (positive: the view should be further right)."""
        return self.target[self.frame] - self.heading

    def next_chunk(self) -> tuple[list[str], tuple[float, float]]:
        """(keys, (left gain, right gain)) for the next latent chunk: 12 frames on the first, 16 after."""
        n = S.keys_needed(1, first=self.frame == 0)
        script = self.keys[self.frame:self.frame + n]
        want = {"j": 0.0, "l": 0.0}                    # degrees of rendered turn wanted in this chunk, per direction
        for key in script:
            if key in SIGN:
                want[key] += self.rate
        keys = list(script)
        err = self.error() if self.adapt else 0.0
        if self.adapt and abs(err) > 1e-9:
            turning = [k for k in ("j", "l") if want[k] > 0]
            if turning:
                # fold the correction into the direction that reduces it, if the chunk turns that way; else the other
                helps = "l" if err > 0 else "j"
                if helps in turning:
                    want[helps] += self.k * abs(err)
                else:
                    other = turning[0]
                    want[other] = max(0.0, want[other] - self.k * abs(err))
            elif self.trim and abs(err) > self.tol:
                helps = "l" if err > 0 else "j"
                per_frame = self.rate * self.est[helps]                       # rendered degrees per frame at gain 1
                n_t = min(n, max(self.min_frames, math.ceil(abs(err) / max(per_frame, 1e-6))))
                keys = [helps] * n_t + ["none"] * (n - n_t)
                want[helps] = self.k * abs(err)
        gain = {}
        for k in ("j", "l"):
            frames = keys.count(k)
            g = want[k] / (frames * self.rate * self.est[k]) if frames and self.adapt else 1.0
            gain[k] = min(GAIN_RANGE[1], max(GAIN_RANGE[0], g))
        self._plan = {"chunk": len(self.log), "first": self.frame, "keys": keys, "gain": (gain["j"], gain["l"]),
                      "target_before": self.target[self.frame], "heading_before": self.heading, "error_before": err,
                      "est_before": dict(self.est)}
        return keys, (gain["j"], gain["l"])

    def observe(self, rendered: dict, trusted: dict | None = None) -> dict:
        """Tell the servo what the chunk it planned showed: rendered = {"j": degrees, "l": degrees, "none": degrees}
        (signed, right positive) summed over that key's frames. Updates the heading and the per-direction estimates."""
        p = self._plan
        if p is None:
            raise RuntimeError("observe() before next_chunk()")
        trusted = trusted or {}
        for k, idx in (("j", 0), ("l", 1)):
            frames = p["keys"].count(k)
            commanded = frames * self.rate * p["gain"][idx]                   # degrees the poses asked for
            if self.adapt and frames >= self.min_frames and commanded > 0 and trusted.get(k, True):
                ratio = abs(rendered.get(k, 0.0)) / commanded
                if 0.2 <= ratio <= 5.0:                                       # ignore a wild chunk rather than chase it
                    self.est[k] = (1 - self.beta) * self.est[k] + self.beta * ratio
        self.heading += sum(float(v) for v in rendered.values())
        self.frame += len(p["keys"])
        row = {**p, "keys": "".join({"j": "L", "l": "R"}.get(k, ".") for k in p["keys"]),
               "rendered": {k: round(float(v), 2) for k, v in rendered.items()},
               "heading_after": round(self.heading, 2), "target_after": round(self.target[min(self.frame, len(self.target) - 1)], 2),
               "est_after": {k: round(v, 3) for k, v in self.est.items()}}
        row.update({"gain": [round(g, 3) for g in p["gain"]], "error_before": round(p["error_before"], 2),
                    "heading_before": round(p["heading_before"], 2), "target_before": round(p["target_before"], 2),
                    "est_before": {k: round(v, 3) for k, v in p["est_before"].items()}})
        self.log.append(row)
        self._plan = None
        return row


def split_by_key(keys: list[str]) -> list[tuple[str, int, int]]:
    """Runs of equal keys in a chunk: [(key, first, last)] with frame offsets inside the chunk (last exclusive)."""
    runs, start = [], 0
    for i in range(1, len(keys) + 1):
        if i == len(keys) or keys[i] != keys[start]:
            runs.append((keys[start], start, i))
            start = i
    return runs


def measure_chunk(frames, keys: list[str]) -> tuple[dict, dict]:
    """(rendered, trusted) per key for one chunk. `frames` holds the frame before the chunk followed by the
    chunk's own frames, so frames[a..b] spans the motion of keys[a:b]."""
    rendered = {"j": 0.0, "l": 0.0, "none": 0.0}
    trusted = {"j": True, "l": True, "none": True}
    for key, a, b in split_by_key(keys):
        yaw, _pitch, peak = MT.chunk_turn(frames[a:b + 1])
        k = key if key in rendered else "none"
        rendered[k] += yaw
        trusted[k] = trusted[k] and peak >= MT.MIN_PEAK
    return rendered, trusted


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
        return "servo" if row["servo"]["adapt"] else "open"
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


# ------------------------------------------------------- is it the camera?

def rigid_share(frames, tol_px: float = 1.5, tol_rel: float = 0.3) -> float:
    """Share of consecutive frame pairs whose image motion looks like one camera turn, in [0, 1].

    A yaw shifts the top and bottom halves of the image by the same number of pixels, and the left and right
    halves too. A subject that moves (an animal, a person, a vehicle) shifts only the part of the image it is in.
    For each pair the horizontal shift is measured in the four halves of a 416 px wide grey frame; the pair counts
    as rigid when all four agree within tol_px or tol_rel of their median. A low share means measure() and the
    servo are reading subject motion, not rotation: the trial is not evidence about the camera."""
    gray = []
    for f in frames:
        g = np.asarray(f, dtype=np.float32)
        g = g.mean(axis=2) if g.ndim == 3 else g
        step = max(1, round(g.shape[1] / 416))
        gray.append(g[::step, ::step])
    if len(gray) < 2:
        return 1.0
    h, w = gray[0].shape
    halves = (np.s_[:h // 2, w // 8:w - w // 8], np.s_[h // 2:, w // 8:w - w // 8],
              np.s_[h // 8:h - h // 8, :w // 2], np.s_[h // 8:h - h // 8, w // 2:])
    ok = 0
    for a, b in zip(gray, gray[1:]):
        dx = [MT.shift(a[s], b[s])[0] for s in halves]
        med = float(np.median(dx))
        ok += max(abs(d - med) for d in dx) <= max(tol_px, tol_rel * abs(med))
    return ok / (len(gray) - 1)


RIGID_MIN = 0.7   # under this share of rigid pairs a trial's rotation numbers are not about the camera
