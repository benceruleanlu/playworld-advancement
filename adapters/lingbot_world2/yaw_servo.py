"""Opt-in yaw servo (off by default): correct the turn the model renders from the rotation its own video shows.

`--lingbot-yaw-servo` (env LINGBOT_YAW_SERVO=1), session mode with turn calibration only.

Why: on the 14B the rendered rotation is not the commanded one, and not by one constant. Measured with fixed
scripts on the first-person dev scenes (PR #125, research/camera-response.md there): left turns render more than right turns in
the same rollout, the ratio to the command differs by scene, and "turn out 90, turn back 90" ends far from the
start heading. A fixed --lingbot-yaw-gain can correct the average; it cannot follow the scene.

What it does: the rollout is generated one latent chunk at a time. After each chunk the yaw the frames show is
measured per direction (measured_turn.chunk_turn, the estimator --lingbot-measured-turn uses). The servo keeps a
running estimate of rendered / commanded for left and for right, divides it out of the next chunk's command, and
adds back the heading error so far, through the pose gain --lingbot-yaw-gain already uses (session.PoseTrack keeps
the intended track beside the model track, so re-anchor, player hint and return stop still see the intended angle).
Each chunk's gain is limited to [0.5, 2.0]. It never adds or removes frames and never changes a key.

Only pure LEFT / RIGHT runs are measured and corrected. Chunks that also move (w/s/a/d) or tilt (i/k) are
generated at the current gain and their yaw is taken as intended, because image shift is not a rotation there.
A run whose correlation peak is under measured_turn.MIN_PEAK, or whose image motion is not one rigid shift
(rigid_share under RIGID_MIN: a subject is moving), is not trusted. Nothing is learned from it and its turn is
booked at what the current estimates predict, so one bad chunk on a static scene does not bias the heading.
After LOCK_AFTER untrusted turn runs in one rollout the scene is taken to have a moving subject: the servo locks,
forgets its estimates and leaves every later chunk at gain 1 (the flags line then says yaw_servo=locked).

Tasks: GC call names only by default (LINGBOT_YAW_SERVO_TASKS, a regex matched at the start of the call name).

Knobs (runner args, else env): --lingbot-yaw-servo-k / LINGBOT_YAW_SERVO_K (1.0: share of the heading error
corrected per chunk), --lingbot-yaw-servo-beta / LINGBOT_YAW_SERVO_BETA (0.6: weight of the newest chunk in the
estimates). Pure Python and numpy; the session is passed in.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass

FLAG = "--lingbot-yaw-servo"
K_FLAG, BETA_FLAG = "--lingbot-yaw-servo-k", "--lingbot-yaw-servo-beta"
K_DEFAULT, BETA_DEFAULT = 1.0, 0.6
LO, HI = 0.5, 2.0
SIGN = {"l": 1.0, "j": -1.0}   # right positive, as measured_turn and player_hint
MIN_FRAMES = 4                 # a run shorter than one latent is not used to update an estimate
RIGID_MIN = 0.7                # under this share of rigid frame pairs the image motion is not a camera turn
LOCK_AFTER = 2                 # untrusted turn runs in one rollout before the servo stands down for the rest of it


def enabled(argv: list[str], environ=os.environ) -> bool:
    return FLAG in argv or environ.get("LINGBOT_YAW_SERVO", "0") == "1"


@dataclass(frozen=True)
class ServoConfig:
    enabled: bool = False
    k: float = K_DEFAULT
    beta: float = BETA_DEFAULT


def _check(k: float, beta: float) -> None:
    if not (math.isfinite(k) and 0.0 <= k <= 2.0) or not (math.isfinite(beta) and 0.0 < beta <= 1.0):
        raise SystemExit(f"yaw servo: k must be in [0, 2] and beta in (0, 1], got k={k} beta={beta}")


def parse(argv: list[str], environ=os.environ) -> tuple[ServoConfig, list[str]]:
    """The servo flag and its knobs in argv (args win over env), and argv without the knobs. Read once per
    main() call. A knob arg without the flag is refused: that arm would silently run without the servo."""
    seen, rest, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        key = next((n for n in (K_FLAG, BETA_FLAG) if a == n or a.startswith(n + "=")), None)
        if key is None:
            rest.append(a)
            i += 1
        elif a == key:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise SystemExit(f"{key} needs a number")
            seen[key], i = argv[i + 1], i + 2
        else:
            seen[key], i = a[len(key) + 1:], i + 1
    on = enabled(rest, environ)
    if seen and not on:
        raise SystemExit(f"{', '.join(seen)} without {FLAG} (or LINGBOT_YAW_SERVO=1) has no effect")
    if not on:
        return ServoConfig(), rest
    vals = {}
    for name, env, default in ((K_FLAG, "LINGBOT_YAW_SERVO_K", K_DEFAULT), (BETA_FLAG, "LINGBOT_YAW_SERVO_BETA", BETA_DEFAULT)):
        raw = seen.get(name, environ.get(env, "").strip() or None)
        try:
            vals[name] = default if raw is None else float(raw)
        except ValueError:
            raise SystemExit(f"{name} needs a number, got {raw!r}") from None
    _check(vals[K_FLAG], vals[BETA_FLAG])
    return ServoConfig(True, vals[K_FLAG], vals[BETA_FLAG]), rest
def applies(name: str, environ=os.environ) -> bool:
    """True when the servo acts on this call name. Default: GC tasks only, as --lingbot-reanchor.
    The GC dev scenes are static, which the yaw estimate needs; three of the six out-of-sight dev scenes have a
    moving subject, where the servo changes the first chunks and then locks. LINGBOT_YAW_SERVO_TASKS (a regex
    matched at the start of the call name) widens it, e.g. "GC|OE048"."""
    return re.match(environ.get("LINGBOT_YAW_SERVO_TASKS", "GC"), name or "") is not None


def split_chunks(keys: list[str], first: bool, chunk: int = 16) -> list[list[str]]:
    """keys of one session.step() call as per-latent-chunk pieces: 12 then 16s on a fresh rollout, else 16s."""
    head = chunk - 4 if first else chunk
    if len(keys) < head or (len(keys) - head) % chunk:
        raise ValueError(f"{len(keys)} keys do not fill whole chunks (first={first})")
    return [keys[:head]] + [keys[i:i + chunk] for i in range(head, len(keys), chunk)]


def runs(keys: list[str]) -> list[tuple[str, int, int]]:
    """Runs of equal keys: [(key, first, last)], last exclusive."""
    out, start = [], 0
    for i in range(1, len(keys) + 1):
        if i == len(keys) or keys[i] != keys[start]:
            out.append((keys[start], start, i))
            start = i
    return out


def yaw_part(key: str) -> str:
    """'j' or 'l' if the key turns that way (also inside a combo such as 'w+j'), else ''."""
    parts = key.lower().split("+")
    return "j" if "j" in parts else "l" if "l" in parts else ""


def measurable(key: str) -> bool:
    """Image shift reads as rotation only for a pure turn or a wait."""
    return key.lower() in ("j", "l") or yaw_part(key) == "" and not any(p in "wsadik" for p in key.lower().split("+") if p)


def rigid_share(frames, tol_px: float = 1.5, tol_rel: float = 0.3) -> float:
    """Share of consecutive frame pairs whose image motion looks like one camera turn, in [0, 1].

    A yaw shifts the top and bottom halves of the image by the same number of pixels, and the left and right
    halves too. A subject that moves (an animal, a person, a vehicle) shifts only the part of the image it is in.
    For each pair the horizontal shift is measured in the four halves of a 416 px wide grey frame; the pair counts
    as rigid when all four agree within tol_px or tol_rel of their median. A low share means the yaw estimate is reading
    subject motion, not rotation (measured: 0.96 to 1.00 on the static GC dev scenes, 0.42 to 0.62 on a zoo scene)."""
    import numpy as np  # noqa: PLC0415

    from adapters.lingbot_world2 import measured_turn as MT  # noqa: PLC0415
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


class YawServo:
    def __init__(self, k: float | None = None, beta: float | None = None, environ=os.environ):
        self.k = float(environ.get("LINGBOT_YAW_SERVO_K", "1.0")) if k is None else float(k)
        self.beta = float(environ.get("LINGBOT_YAW_SERVO_BETA", "0.6")) if beta is None else float(beta)
        _check(self.k, self.beta)
        self.reset()

    def reset(self) -> None:
        """A new rollout: forget the estimates and the heading."""
        self.est = {"j": 1.0, "l": 1.0}     # rendered / commanded, per direction
        self.intended = 0.0                 # heading the keys asked for so far, degrees, right positive
        self.heading = 0.0                  # heading the video showed so far
        self.chunks = self.corrected = self.untrusted = 0
        self.locked = False                 # too many untrusted turn runs: gain 1 for the rest of the rollout
        self.last_gain = (1.0, 1.0)

    def error(self) -> float:
        return self.intended - self.heading

    def plan(self, keys: list[str], rate_deg: float) -> tuple[float, float]:
        """(left gain, right gain) for the next chunk of keys at rate_deg per frame."""
        if self.locked:
            self.last_gain = (1.0, 1.0)
            return self.last_gain
        frames = {"j": 0, "l": 0}
        for key in keys:
            if (y := yaw_part(key)):
                frames[y] += 1
        want = {d: frames[d] * rate_deg for d in ("j", "l")}       # rendered degrees wanted, per direction
        err = self.error()
        turning = [d for d in ("j", "l") if frames[d]]
        if turning and abs(err) > 1e-9:
            helps = "l" if err > 0 else "j"
            if helps in turning:
                want[helps] += self.k * abs(err)
            else:
                want[turning[0]] = max(0.0, want[turning[0]] - self.k * abs(err))
        gain = {}
        for d in ("j", "l"):
            g = want[d] / (frames[d] * rate_deg * self.est[d]) if frames[d] and rate_deg > 0 else 1.0
            gain[d] = min(HI, max(LO, g))
        self.last_gain = (gain["j"], gain["l"])
        return self.last_gain

    def observe(self, keys: list[str], rate_deg: float, gain: tuple[float, float], measured: list[tuple[float, bool]]) -> None:
        """After the chunk: `measured` gives (yaw degrees right positive, trusted) for each run of runs(keys)."""
        self.chunks += 1
        self.corrected += any(abs(g - 1.0) > 0.01 for g in gain)   # chunks sent at a gain outside 1 +- 0.01
        for (key, a, b), (yaw, trusted) in zip(runs(keys), measured):
            n, y = b - a, yaw_part(key)
            asked = SIGN[y] * n * rate_deg if y else 0.0
            self.intended += asked
            # what the estimates say this run rendered: the commanded pose angle times rendered / commanded
            predicted = asked * gain[0 if y == "j" else 1] * self.est[y] if y else 0.0
            if not measurable(key):
                self.heading += predicted        # moving or tilting: image shift is not a rotation here
                continue
            if not trusted:                      # weak peak or a moving subject: learn nothing from it
                self.heading += predicted
                if y:
                    self.untrusted += 1
                    if self.untrusted >= LOCK_AFTER and not self.locked:
                        self.locked, self.est = True, {"j": 1.0, "l": 1.0}
                continue
            self.heading += yaw
            if self.locked:
                continue
            if y and n >= MIN_FRAMES:
                commanded = n * rate_deg * gain[0 if y == "j" else 1]
                # signed: a reading against the command (lag or noise on a small shrunk turn) gives a negative
                # ratio, which the gate below rejects; the heading above still takes the signed yaw
                ratio = SIGN[y] * yaw / commanded if commanded > 0 else 0.0
                if 0.2 <= ratio <= 5.0:          # ignore a wild or reversed chunk rather than chase it
                    self.est[y] = (1 - self.beta) * self.est[y] + self.beta * ratio

    def describe(self) -> str:
        if self.locked:
            return (f"locked after {self.untrusted} untrusted turn runs (a subject is moving): gain 1 from here, "
                    f"intended {self.intended:+.1f}")
        return (f"est L {self.est['j']:.2f} R {self.est['l']:.2f}, gain L {self.last_gain[0]:.2f} R {self.last_gain[1]:.2f}, "
                f"heading {self.heading:+.1f} (intended {self.intended:+.1f})")


def step(session, servo: YawServo, keys: list[str], rate_deg: float, measure, rigid=rigid_share, log=None):
    """session.step(keys) generated chunk by chunk under the servo. Returns the same frames array a single step
    returns (fresh rollout: input frame + 16n-4; continuation: previous last frame + 16n).

    measure(frames) -> (yaw, pitch, peak) is measured_turn.chunk_turn. A run's reading is trusted when its peak is
    at least measured_turn.MIN_PEAK and, with `rigid`, when rigid(frames) is at least RIGID_MIN (the image moved as
    one camera turn, not as a subject walking through it). Untrusted runs do not move the estimates."""
    import numpy as np  # noqa: PLC0415

    from adapters.lingbot_world2 import measured_turn as MT  # noqa: PLC0415
    parts = []
    for piece in split_chunks(keys, first=session.chunk_id == 0):
        gain = servo.plan(piece, rate_deg)
        session.track.yaw_gain = gain
        frames = session.step(piece)            # frames[0] is the frame before this chunk
        measured = []
        for _key, a, b in runs(piece):
            sub = frames[a:b + 1]
            yaw, _pitch, peak = measure(sub)
            ok = peak >= MT.MIN_PEAK and (rigid is None or rigid(sub) >= RIGID_MIN)
            measured.append((yaw, bool(ok)))
        servo.observe(piece, rate_deg, gain, measured)
        if log is not None:
            log(servo.describe())
        parts.append(frames if not parts else frames[1:])
    return np.concatenate(parts)
