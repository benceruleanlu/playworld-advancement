"""Opt-in yaw servo (off by default): correct the turn the model renders from the rotation its own video shows.

`--lingbot-yaw-servo` (env LINGBOT_YAW_SERVO=1), session mode with turn calibration only.

Why: on the 14B the rendered rotation is not the commanded one, and not by one constant. Measured with fixed
scripts on the first-person dev scenes (research/camera-response.md): left turns render more than right turns in
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
A chunk whose correlation peak is under measured_turn.MIN_PEAK moves the heading but not the estimates.

Constants (env): LINGBOT_YAW_SERVO_K (1.0: share of the heading error corrected per chunk), LINGBOT_YAW_SERVO_BETA
(0.6: weight of the newest chunk in the estimates). Pure Python and numpy; the session is passed in.
"""
from __future__ import annotations

import os

FLAG = "--lingbot-yaw-servo"
LO, HI = 0.5, 2.0
SIGN = {"l": 1.0, "j": -1.0}   # right positive, as measured_turn and player_hint
MIN_FRAMES = 4                 # a run shorter than one latent is not used to update an estimate


def enabled(argv: list[str], environ=os.environ) -> bool:
    return FLAG in argv or environ.get("LINGBOT_YAW_SERVO", "0") == "1"


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


class YawServo:
    def __init__(self, k: float | None = None, beta: float | None = None, environ=os.environ):
        self.k = float(environ.get("LINGBOT_YAW_SERVO_K", "1.0")) if k is None else float(k)
        self.beta = float(environ.get("LINGBOT_YAW_SERVO_BETA", "0.6")) if beta is None else float(beta)
        if not 0.0 <= self.k <= 2.0 or not 0.0 < self.beta <= 1.0:
            raise SystemExit(f"yaw servo: k must be in [0, 2] and beta in (0, 1], got k={self.k} beta={self.beta}")
        self.reset()

    def reset(self) -> None:
        """A new rollout: forget the estimates and the heading."""
        self.est = {"j": 1.0, "l": 1.0}     # rendered / commanded, per direction
        self.intended = 0.0                 # heading the keys asked for so far, degrees, right positive
        self.heading = 0.0                  # heading the video showed so far
        self.chunks = self.corrected = self.untrusted = 0
        self.last_gain = (1.0, 1.0)

    def error(self) -> float:
        return self.intended - self.heading

    def plan(self, keys: list[str], rate_deg: float) -> tuple[float, float]:
        """(left gain, right gain) for the next chunk of keys at rate_deg per frame."""
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
        self.corrected += gain != (1.0, 1.0)
        for (key, a, b), (yaw, trusted) in zip(runs(keys), measured):
            n, y = b - a, yaw_part(key)
            asked = SIGN[y] * n * rate_deg if y else 0.0
            self.intended += asked
            if not measurable(key):
                self.heading += asked            # moving or tilting: take the turn as intended
                continue
            self.heading += yaw
            if not trusted:
                self.untrusted += 1
                continue
            if y and n >= MIN_FRAMES:
                commanded = n * rate_deg * gain[0 if y == "j" else 1]
                ratio = abs(yaw) / commanded if commanded > 0 else 0.0
                if 0.2 <= ratio <= 5.0:          # ignore a wild chunk rather than chase it
                    self.est[y] = (1 - self.beta) * self.est[y] + self.beta * ratio

    def describe(self) -> str:
        return (f"est L {self.est['j']:.2f} R {self.est['l']:.2f}, gain L {self.last_gain[0]:.2f} R {self.last_gain[1]:.2f}, "
                f"heading {self.heading:+.1f} (intended {self.intended:+.1f})")


def step(session, servo: YawServo, keys: list[str], rate_deg: float, measure, log=None):
    """session.step(keys) generated chunk by chunk under the servo. Returns the same frames array shape a single
    step returns (fresh rollout: input frame + 16n-4; continuation: previous last frame + 16n).

    measure(frames) -> (yaw, pitch, peak) is measured_turn.chunk_turn; min_peak its trust threshold."""
    import numpy as np  # noqa: PLC0415

    from adapters.lingbot_world2 import measured_turn as MT  # noqa: PLC0415
    parts = []
    for piece in split_chunks(keys, first=session.chunk_id == 0):
        gain = servo.plan(piece, rate_deg)
        session.track.yaw_gain = gain
        frames = session.step(piece)            # frames[0] is the frame before this chunk
        measured = []
        for _key, a, b in runs(piece):
            yaw, _pitch, peak = measure(frames[a:b + 1])
            measured.append((yaw, peak >= MT.MIN_PEAK))
        servo.observe(piece, rate_deg, gain, measured)
        if log is not None:
            log(servo.describe())
        parts.append(frames if not parts else frames[1:])
    return np.concatenate(parts)
