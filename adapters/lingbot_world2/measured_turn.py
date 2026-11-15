"""Opt-in measured turn: how far each turn chunk rotated the view in the video, next to what was commanded.

Player hint and return stop work from the commanded camera pose. Nothing checks that the video
followed it. This module measures it: for each chunk driven by a turn or tilt key it takes the
image shift between consecutive frames by phase correlation and converts it to degrees with
LingBot's intrinsics (a pure camera rotation shifts the whole image by about fx * tan(angle)).

Checked on synthetic frames ray-cast at a known rotation: within 3% (tests). On published clips
(480p release copies, CPU only): the 14B turns about as commanded, 42 to 54 degrees per chunk
against 45 with turn calibration and 54 to 69 against 48 to 55 without (smk14-arms-gc-v2); the
1.3B does not, GC031 in rs13-arms-v1-a2 measures 60 degrees over its first eight chunks, commanded as
360, and the judge's reason for that video is that the rotation was too small.

`wrap()` measures every finished turn chunk once, prints commanded and measured degrees, and adds
one sentence with both totals to the goal the player reads. It never changes or replaces an
action. Chunks driven by move keys or WAIT are not measured (walking and strafing shift the image
without a rotation). The number is an image-motion estimate: moving subjects, scene changes and
strong parallax add error, and a chunk with a weak correlation peak is reported as unreliable.
numpy only; frames are read with imageio, which the engine already uses.
"""
from __future__ import annotations

import math

import numpy as np

from adapters.lingbot_world2 import player_hint as H
from adapters.lingbot_world2 import poses as P

TURN_KEYS = ("j", "l", "i", "k")
MIN_PEAK = 0.03  # mean correlation peak under this: the estimate is not trusted


def shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """(dx, dy, peak): how far the content of frame b sits right and down of frame a, in pixels."""
    fa, fb = np.fft.rfft2(a - a.mean()), np.fft.rfft2(b - b.mean())
    r = fa.conj() * fb
    c = np.fft.irfft2(r / (np.abs(r) + 1e-9), s=a.shape)
    y, x = np.unravel_index(int(np.argmax(c)), c.shape)

    def sub(line, i):  # parabolic sub-pixel peak, wrapped to a signed shift
        n = len(line)
        lo, mid, hi = line[(i - 1) % n], line[i], line[(i + 1) % n]
        v = i + 0.5 * (lo - hi) / (lo - 2 * mid + hi + 1e-12)
        return v - n if v > n / 2 else v

    return float(sub(c[y], x)), float(sub(c[:, x], y)), float(c[y, x])


def chunk_turn(frames) -> tuple[float, float, float]:
    """(yaw, pitch, peak) in degrees over a chunk's frames: right and up positive, like player_hint.
    Uses the centre half of the image: a rotation shifts pixels off the optical axis by more than
    fx * tan(angle) (by 1 / cos^2 of their own angle), which over the full 832 px width reads 23% high.
    The remaining excess over the centre half is divided out."""
    gray = [np.asarray(f, dtype=np.float32) for f in frames]
    gray = [g.mean(axis=2) if g.ndim == 3 else g for g in gray]
    if len(gray) < 2:
        return 0.0, 0.0, 0.0
    step = max(1, round(gray[0].shape[1] / 416))  # work at about 416 px wide (480p frames: every 2nd pixel)
    gray = [g[::step, ::step] for g in gray]
    h, w = gray[0].shape
    scale = w / (2.0 * P.INTRINSICS_480P[2])  # image width over the 832 px the intrinsics are for
    fx, fy = P.INTRINSICS_480P[0] * scale, P.INTRINSICS_480P[1] * scale
    gray = [g[h // 4:h - h // 4, w // 4:w - w // 4] for g in gray]
    kx, ky = 1 + (w / 4) ** 2 / (3 * fx * fx), 1 + (h / 4) ** 2 / (3 * fy * fy)  # mean 1/cos^2 over the crop
    yaw = pitch = peak = 0.0
    for a, b in zip(gray, gray[1:]):
        dx, dy, pk = shift(a, b)
        yaw -= math.degrees(math.atan(dx / fx)) / kx    # content moves right when the camera turns left
        pitch += math.degrees(math.atan(dy / fy)) / ky  # content moves down when the camera tilts up
        peak += pk
    return yaw, pitch, peak / (len(gray) - 1)


def read_frames(path):
    import imageio.v2 as imageio  # noqa: PLC0415
    return imageio.mimread(str(path), memtest=False)


def _side(v: float, neg: str, pos: str) -> str:
    return f"{abs(v):.0f} degrees" + ("" if round(v) == 0 else f" {pos if v > 0 else neg}")


def wrap(decide_action, to_key, session: bool, turn_cal: bool, on_event=None, read=read_frames):
    """Wrap decide_action. on_event(summary) after each decision with at least one measured chunk:
    {"chunks", "unreliable", "commanded_yaw", "measured_yaw", "commanded_tilt", "measured_tilt"}."""
    cache: dict = {}

    def decide(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw):
        acts, paths = list(recent_actions or []), list(kw.get("chunk_video_paths") or [])
        idx = [i for i, a in enumerate(acts[:len(paths)]) if to_key(a) in TURN_KEYS]
        if kw.get("stationary_only") or not idx:
            return decide_action(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw)
        cf, unit = int(getattr(args, "chunk_frames", 33) or 33), int(getattr(args, "action_frame_unit", 20) or 20)
        tot = {"chunks": 0, "unreliable": 0, "commanded_yaw": 0.0, "measured_yaw": 0.0,
               "commanded_tilt": 0.0, "measured_tilt": 0.0}
        for i in idx:
            if paths[i] not in cache:
                try:
                    yaw, pitch, peak = chunk_turn(read(paths[i]))
                except Exception as e:  # noqa: BLE001  never fail a rollout over a measurement
                    print(f"    [lingbot] measured turn: could not read {paths[i]}: {e}", flush=True)
                    yaw = pitch = peak = 0.0
                key = to_key(acts[i])
                d = H._delta(key, H.step_keys(i, cf, session), turn_cal, unit)
                c_yaw, c_tilt = H._angles(d)
                cache[paths[i]] = (c_yaw, c_tilt, yaw, pitch, peak)
                r = [round(v) + 0 for v in (c_yaw, c_tilt, yaw, pitch)]  # + 0: no "-0" in the log
                print(f"    [lingbot] measured turn: {task.get('task_id')} chunk {i + 1} {acts[i]} commanded "
                      f"yaw {r[0]:+d} tilt {r[1]:+d}, measured yaw {r[2]:+d} tilt {r[3]:+d} "
                      f"(peak {peak:.2f}{'' if peak >= MIN_PEAK else ', unreliable'})", flush=True)
            c_yaw, c_tilt, yaw, pitch, peak = cache[paths[i]]
            tot["chunks"] += 1
            tot["commanded_yaw"] += c_yaw
            tot["commanded_tilt"] += c_tilt
            if peak < MIN_PEAK:
                tot["unreliable"] += 1
                continue
            tot["measured_yaw"] += yaw
            tot["measured_tilt"] += pitch
        if on_event is not None:
            on_event(tot)
        if tot["unreliable"] < tot["chunks"]:
            text = (f"Measured from the video so far (image motion, approximate): your turn actions rotated the view "
                    f"a net {_side(tot['measured_yaw'], 'left', 'right')} and tilted it "
                    f"{_side(tot['measured_tilt'], 'down', 'up')}. The commands sent add up to "
                    f"{_side(tot['commanded_yaw'], 'left', 'right')} and {_side(tot['commanded_tilt'], 'down', 'up')}. "
                    f"Where the two differ, go by the measured numbers and the frames.")
            task = {**task, "prompt": f"{task.get('prompt', '')}\n{text}"}
        return decide_action(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw)

    return decide
