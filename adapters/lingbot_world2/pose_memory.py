"""Pose-indexed memory (opt-in, session only; numpy only, no torch import).

`--lingbot-pose-memory` (LINGBOT_POSE_MEMORY=1) keeps a bank of every generated latent chunk of a rollout, keyed by
its commanded camera pose (PoseTrack.latents, the intended track). Before a chunk is generated, the bank is
searched for a chunk that (1) has left the KV cache (older than the rolling window and not part of the sink),
(2) whose view the camera has left since (a later latent looked more than `leave_deg` away or moved more than
`leave_trans` key units), and (3) whose view overlaps the upcoming chunk's (within `deg` degrees and `trans` key
units). The most recent such sighting wins, so the scene state put back is the latest one seen, not frame 0.
Its keys/values are recomputed (one clean t=0 forward of the stored x0 into the sink slots after the first
`anchor` latents, session._mem_recompute) and stay there until the selection changes; when nothing matches the
original sink is copied back (`fallback start`, default) or the last memory is kept (`fallback keep`).

Storage is option (b) of the feasibility study: only the clean latents x0 (16 x 4 x lat_h x lat_w fp32, about
1.5 MB per chunk at 480p), on the host, capped by `max_mb` (oldest entries evicted first). Option (a), the
per-block K/V of each stored latent, is 1.2 GB per latent on 14B and is not implemented.

View overlap between two poses: o = max(0, 1 - |dyaw| / HFOV) * max(0, 1 - |dpitch| / VFOV) with the field of
view of the 480p intrinsics (79.2 x 51.0 degrees). `deg` and `leave_deg` are given as the yaw offset that
gives the threshold overlap at equal pitch (32 degrees: o >= 0.6; 59 degrees: o < 0.25).
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

import numpy as np

from adapters.lingbot_world2 import poses as P

FLAG = "--lingbot-pose-memory"
CHUNK = P.LATENT_CHUNK
HFOV = math.degrees(2 * math.atan(P.INTRINSICS_480P[2] / P.INTRINSICS_480P[0]))  # 79.2
VFOV = math.degrees(2 * math.atan(P.INTRINSICS_480P[3] / P.INTRINSICS_480P[1]))  # 51.0
TIMES = ("sink", "recent", "orig")
FALLBACKS = ("start", "keep")
DEFAULTS = {"deg": 32.0, "trans": 4.0, "leave_deg": 59.0, "leave_trans": 8.0, "latents": 4, "anchor": 2,
            "time": "sink", "fallback": "start", "tasks": "GC|OE", "max_mb": 512.0}
_ARGS = {  # flag -> (field, env var)
    "--lingbot-pose-mem-deg": ("deg", "LINGBOT_POSE_MEM_DEG"),
    "--lingbot-pose-mem-trans": ("trans", "LINGBOT_POSE_MEM_TRANS"),
    "--lingbot-pose-mem-leave-deg": ("leave_deg", "LINGBOT_POSE_MEM_LEAVE_DEG"),
    "--lingbot-pose-mem-leave-trans": ("leave_trans", "LINGBOT_POSE_MEM_LEAVE_TRANS"),
    "--lingbot-pose-mem-latents": ("latents", "LINGBOT_POSE_MEM_LATENTS"),
    "--lingbot-pose-mem-anchor": ("anchor", "LINGBOT_POSE_MEM_ANCHOR"),
    "--lingbot-pose-mem-time": ("time", "LINGBOT_POSE_MEM_TIME"),
    "--lingbot-pose-mem-fallback": ("fallback", "LINGBOT_POSE_MEM_FALLBACK"),
    "--lingbot-pose-mem-tasks": ("tasks", "LINGBOT_POSE_MEM_TASKS"),
    "--lingbot-pose-mem-max-mb": ("max_mb", "LINGBOT_POSE_MEM_MAX_MB"),
}


@dataclass(frozen=True)
class PoseMemoryConfig:
    enabled: bool = False
    deg: float = DEFAULTS["deg"]
    trans: float = DEFAULTS["trans"]
    leave_deg: float = DEFAULTS["leave_deg"]
    leave_trans: float = DEFAULTS["leave_trans"]
    latents: int = DEFAULTS["latents"]
    anchor: int = DEFAULTS["anchor"]
    time: str = DEFAULTS["time"]
    fallback: str = DEFAULTS["fallback"]
    tasks: str = DEFAULTS["tasks"]
    max_mb: float = DEFAULTS["max_mb"]

    @property
    def chunks(self) -> int:
        """Latent chunks retrieved at once."""
        return self.latents // CHUNK

    @property
    def match_overlap(self) -> float:
        return overlap_of(self.deg, 0.0)

    @property
    def leave_overlap(self) -> float:
        return overlap_of(self.leave_deg, 0.0)

    def applies(self, name: str) -> bool:
        """True when this call name (e.g. 'OE047_chunk_01') matches --lingbot-pose-mem-tasks."""
        return self.enabled and re.match(self.tasks, name or "") is not None

    def describe(self) -> str:
        return (f"pose memory {self.latents} latents after {self.anchor} anchor, match {self.deg:g} deg / "
                f"{self.trans:g} units, leave {self.leave_deg:g} deg / {self.leave_trans:g} units, rope {self.time}, "
                f"fallback {self.fallback}, cap {self.max_mb:g} MB, tasks {self.tasks!r}")


def _take(argv: list[str]) -> tuple[dict, list[str]]:
    seen, rest, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        key = next((k for k in _ARGS if a == k or a.startswith(k + "=")), None)
        if key is None:
            rest.append(a)
            i += 1
        elif a == key:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise SystemExit(f"{key} needs a value")
            seen[key], i = argv[i + 1], i + 2
        else:
            seen[key], i = a[len(key) + 1:], i + 1
    return seen, rest


def _num(name, raw, kind, lo, hi=math.inf):
    try:
        v = kind(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a {kind.__name__}, got {raw!r}") from None
    if not lo <= v <= hi or (isinstance(v, float) and not math.isfinite(v)):
        raise SystemExit(f"{name} must be in [{lo}, {hi}], got {raw!r}")
    return v


def parse(argv: list[str], environ=os.environ) -> tuple[PoseMemoryConfig, list[str]]:
    """The flag and its knobs out of argv (last value wins; env vars as fallback), and argv without them.
    Knobs given without the flag are parsed and validated but leave the memory off."""
    enabled = FLAG in argv or environ.get("LINGBOT_POSE_MEMORY", "0") == "1"
    argv = [a for a in argv if a != FLAG]
    seen, rest = _take(argv)
    raw = {f: seen.get(arg, environ.get(env, "").strip() or None) for arg, (f, env) in _ARGS.items()}
    names = {f: arg for arg, (f, _) in _ARGS.items()}
    v = dict(DEFAULTS)
    for f, lo, hi in (("deg", 0.0, HFOV), ("leave_deg", 0.0, 360.0), ("trans", 0.0, 1e6), ("leave_trans", 0.0, 1e6),
                      ("max_mb", 1.0, 1e6)):
        if raw[f] is not None:
            v[f] = _num(names[f], raw[f], float, lo, hi)
    for f, lo in (("latents", CHUNK), ("anchor", 0)):
        if raw[f] is not None:
            v[f] = _num(names[f], raw[f], int, lo, 1024)
    if v["latents"] % CHUNK:
        raise SystemExit(f"--lingbot-pose-mem-latents must be a multiple of {CHUNK} (whole latent chunks), "
                         f"got {v['latents']}")
    if v["leave_deg"] >= HFOV:
        raise SystemExit(f"--lingbot-pose-mem-leave-deg must be below the {HFOV:.1f} degree field of view, got "
                         f"{v['leave_deg']:g}: at or above it the overlap is 0 and no view ever counts as left")
    if v["leave_deg"] <= v["deg"]:
        raise SystemExit(f"--lingbot-pose-mem-leave-deg ({v['leave_deg']:g}) must exceed --lingbot-pose-mem-deg "
                         f"({v['deg']:g}), or a view never counts as left")
    for f, allowed in (("time", TIMES), ("fallback", FALLBACKS)):
        if raw[f] is not None:
            if raw[f] not in allowed:
                raise SystemExit(f"{names[f]} must be one of {allowed}, got {raw[f]!r}")
            v[f] = raw[f]
    if raw["tasks"] is not None:
        try:
            re.compile(raw["tasks"])
        except re.error as exc:
            raise SystemExit(f"--lingbot-pose-mem-tasks is not a valid regex: {exc}") from None
        v["tasks"] = raw["tasks"]
    return PoseMemoryConfig(enabled, **v), rest


def check_window(cfg: PoseMemoryConfig, local: int, sink: int) -> None:
    """Refuse a window the memory cannot use: full attention (nothing is evicted, sink 0) or a sink too small
    for the anchor plus the retrieved latents."""
    if local == -1 or sink == 0:
        raise SystemExit(f"{FLAG} needs a rolling window with an attention sink (local != -1, sink > 0); "
                         "here it would run as a no-op arm")
    if sink < cfg.anchor + cfg.latents:
        raise SystemExit(f"{FLAG}: --lingbot-sink-size {sink} is smaller than --lingbot-pose-mem-anchor "
                         f"{cfg.anchor} + --lingbot-pose-mem-latents {cfg.latents}; raise the sink (and the "
                         "local window by the same amount to keep the recent window)")


# ------------------------------------------------------------------ pose maths

def view_angles(c2w: np.ndarray) -> tuple[float, float]:
    """(yaw, pitch) in degrees of an OpenCV camera-to-world pose (x right, y down, z forward); yaw positive to the
    right ('l'), pitch positive up ('i')."""
    f = np.asarray(c2w, dtype=np.float64)[:3, 2]
    return math.degrees(math.atan2(f[0], f[2])), math.degrees(math.atan2(-f[1], math.hypot(f[0], f[2])))


def overlap_of(dyaw: float, dpitch: float) -> float:
    return max(0.0, 1.0 - abs(dyaw) / HFOV) * max(0.0, 1.0 - abs(dpitch) / VFOV)


def pose_diff(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float, float]:
    """(dyaw, dpitch, dpos, overlap) from pose a to pose b; dyaw wrapped to [-180, 180)."""
    ya, pa = view_angles(a)
    yb, pb = view_angles(b)
    dyaw = (yb - ya + 180.0) % 360.0 - 180.0
    dpitch = pb - pa
    dpos = float(np.linalg.norm(np.asarray(b, dtype=np.float64)[:3, 3] - np.asarray(a, dtype=np.float64)[:3, 3]))
    return dyaw, dpitch, dpos, overlap_of(dyaw, dpitch)


def centre(latent_c2ws) -> np.ndarray:
    """The pose a chunk is keyed by: its third latent (index 2 of 4)."""
    lat = np.asarray(latent_c2ws)
    return lat[min(2, len(lat) - 1)]


# ------------------------------------------------------------------ the bank

@dataclass
class Entry:
    cid: int                 # latent chunk index in the rollout
    pose: np.ndarray         # centre latent c2w (intended track)
    x0: object               # clean latents [16, 4, h, w] on the host
    rel: np.ndarray          # the chunk's normalised relative poses [4, 4, 4] (its camera input)
    nbytes: int = 0
    left: bool = False       # the camera has looked away from this view since it was generated


@dataclass
class Match:
    entry: Entry
    dyaw: float
    dpitch: float
    dpos: float
    overlap: float


@dataclass
class PoseMemory:
    cfg: PoseMemoryConfig
    sink: int                # attention sink latents (pipe.sink_size)
    local: int               # whole cache in latents (pipe.local_attn_size), sink included
    entries: list = field(default_factory=list)
    evicted: int = 0         # entries dropped by the cap

    @property
    def window(self) -> int:
        """Latents of earlier chunks still in the cache while a chunk is generated (18 - 6 - 4 = 8)."""
        return self.local - self.sink - CHUNK

    @property
    def nbytes(self) -> int:
        return sum(e.nbytes for e in self.entries)

    def in_cache(self, j: int, c: int) -> bool:
        """True when chunk j still has latents in the cache (sink or rolling window) while chunk c is generated."""
        return j * CHUNK < self.sink or (j + 1) * CHUNK > c * CHUNK - self.window

    def add(self, entry: Entry) -> None:
        self.entries.append(entry)
        cap = self.cfg.max_mb * 2 ** 20
        while len(self.entries) > 1 and self.nbytes > cap:
            self.entries.pop(0)
            self.evicted += 1

    def observe(self, latent_c2ws) -> None:
        """Mark stored views the camera has left: some latent here is far from the entry's pose."""
        for e in self.entries:
            if e.left:
                continue
            for c2w in latent_c2ws:
                _, _, dpos, o = pose_diff(e.pose, c2w)
                if o < self.cfg.leave_overlap or dpos > self.cfg.leave_trans:
                    e.left = True
                    break

    def select(self, latent_c2ws, c: int) -> list[Match] | None:
        """Up to cfg.chunks matches for chunk c (poses latent_c2ws), most recent first: evicted, left, overlapping.
        The newest overlapping non-sink sighting shadows older ones: if it is still in the rolling window or has
        not been left, the window already holds the view and this returns None (recall nothing, keep the sink)."""
        target = centre(latent_c2ws)
        out = []
        for e in reversed(self.entries):
            dyaw, dpitch, dpos, o = pose_diff(e.pose, target)
            if o < self.cfg.match_overlap or dpos > self.cfg.trans or e.cid * CHUNK < self.sink:
                continue
            if self.in_cache(e.cid, c) or not e.left:
                if not out:
                    return None
                continue
            out.append(Match(e, dyaw, dpitch, dpos, o))
            if len(out) == self.cfg.chunks:
                break
        return out

    def slots(self, n: int) -> list[int]:
        """First latent slot of each of n retrieved chunks, in retrieval order (most recent first)."""
        return [self.cfg.anchor + i * CHUNK for i in range(n)]

    def rope_latent(self, slot_index: int, slot: int, entry: Entry, c: int, n: int) -> int:
        """RoPE time (latent index) the retrieved chunk is recomputed at. sink: its slot (the position pattern
        of today's sink); recent: just behind the rolling window of chunk c, most recent nearest (recomputed every
        chunk while installed, so it tracks the window); orig: when it was made."""
        if self.cfg.time == "sink":
            return slot
        if self.cfg.time == "orig":
            return entry.cid * CHUNK
        return max(0, c * CHUNK - self.window - CHUNK * (slot_index + 1))
