"""Pose-indexed memory (opt-in, session only; numpy only, no torch import).

`--lingbot-pose-memory` (LINGBOT_POSE_MEMORY=1) keeps a bank of every generated latent chunk of a rollout, keyed by
its camera pose (`--lingbot-pose-mem-track intended`, PoseTrack.latents, or `model`, PoseTrack.model_latents). Before
a chunk is generated the bank is searched (PoseMemory.decide, shared by the session and the dry-run planner
`python -m pwa.pose_mem_plan`), the chosen chunk's keys/values are recomputed (one clean t=0 forward of the stored x0
into the sink slots after the first `anchor` latents, session._mem_recompute, with relative motion
`--lingbot-pose-mem-rel stored|still|current`) and stay there until the selection changes; when nothing matches the
original sink is copied back (`fallback start`, default) or the last memory is kept (`fallback keep`).

Selection, `--lingbot-pose-mem-rule coverage` (default). For the upcoming chunk's centre view T:
  * window coverage: the best overlap with T of any latent of the rolling window (the 8 latents the cache still
    holds after the sink);
  * a stored chunk matches when its best latent overlaps T by at least `deg` (and is within `trans` key units), it
    has left the rolling window, and the camera has looked away from it since (some later latent more than
    `leave_deg` away, or `leave_trans` units);
  * it is eligible when it overlaps T strictly better than the window does: the window does not already hold that
    view. Chunks that overlap the sink (the opening view) are candidates too unless `time sink`, where installing
    them at their own sink positions would change almost nothing;
  * pick: `best` overlap (ties to the newest), or `latest` sighting (newest first); `auto` (default) is `latest` for
    Out-of-sight call names (OE*), whose rubric scores a reset to the opening as level 1, and `best` otherwise. With
    `latest`, an opening-only choice is replaced by a later matching sighting whenever one exists.
  Matched but not eligible (the window holds the view): the installed memory is kept, re-timed with `time recent`.
`--lingbot-pose-mem-rule legacy` is the first version (pm14-fx-v1): centre poses only, sink chunks never candidates,
and the newest overlapping sighting shadows older ones, so any smooth turn (18 degrees per chunk under turn-cal,
less than `deg`) finds the previous, in-window chunk first and recalls nothing. The first GPU run (pm14-fx-v1/v2,
30 rollouts) logged pose_mem_retrievals=0 on every task and produced byte-identical clips.

`--lingbot-pose-mem-yaw-scale S` (1.0) multiplies the commanded yaw (unwrapped over the rollout) before any yaw
comparison: the rendered image turned about 1.19x the commanded angle on GC031 (one measurement).
`--lingbot-pose-mem-focus Z` (0.0 = off) projects each camera's 3D look-at point p = t + Z * f into the other camera's
OpenCV frustum and scales angular overlap by min(q_z / Z, Z / q_z), admitting 3D orbits and zoom dollies.

Storage is option (b) of the feasibility study: only the clean latents x0 (16 x 4 x lat_h x lat_w fp32, about
1.5 MB per chunk at 480p), on the host, capped by `max_mb` (oldest entries evicted first). Option (a), the
per-block K/V of each stored latent, is 1.2 GB per latent on 14B and is not implemented.

View overlap between two poses: o = max(0, 1 - |dyaw| / HFOV) * max(0, 1 - |dpitch| / VFOV) with the field of
view of the 480p intrinsics (79.2 x 51.0 degrees). `deg` and `leave_deg` are given as the yaw offset that
gives the threshold overlap at equal pitch (32 degrees: o >= 0.6; 40 degrees, about half the field of view, so
the stored view's centre has left the frame: o < 0.5).
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
RULES = ("coverage", "legacy")
PICKS = ("auto", "best", "latest")
TRACKS = ("intended", "model")
RELS = ("stored", "still", "current")
DEFAULTS = {"deg": 32.0, "trans": 4.0, "leave_deg": 40.0, "leave_trans": 8.0, "latents": 4, "anchor": 2,
            "time": "recent", "fallback": "start", "tasks": "GC|OE", "max_mb": 512.0, "rule": "coverage",
            "pick": "auto", "yaw_scale": 1.0, "track": "intended", "focus": 0.0, "rel": "stored"}
# The first version's behaviour (pm14-fx-v1): pass these to get it back.
LEGACY_ARGS = ("--lingbot-pose-mem-rule", "legacy", "--lingbot-pose-mem-time", "sink",
               "--lingbot-pose-mem-leave-deg", "59")
MEASURED_YAW_SCALE = 1.19  # rendered / commanded yaw, GC031 only
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
    "--lingbot-pose-mem-rule": ("rule", "LINGBOT_POSE_MEM_RULE"),
    "--lingbot-pose-mem-pick": ("pick", "LINGBOT_POSE_MEM_PICK"),
    "--lingbot-pose-mem-yaw-scale": ("yaw_scale", "LINGBOT_POSE_MEM_YAW_SCALE"),
    "--lingbot-pose-mem-track": ("track", "LINGBOT_POSE_MEM_TRACK"),
    "--lingbot-pose-mem-focus": ("focus", "LINGBOT_POSE_MEM_FOCUS"),
    "--lingbot-pose-mem-rel": ("rel", "LINGBOT_POSE_MEM_REL"),
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
    rule: str = DEFAULTS["rule"]
    pick: str = DEFAULTS["pick"]
    yaw_scale: float = DEFAULTS["yaw_scale"]
    track: str = DEFAULTS["track"]
    focus: float = DEFAULTS["focus"]
    rel: str = DEFAULTS["rel"]

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

    def pick_for(self, name: str) -> str:
        """`auto`: latest sighting for Out-of-sight call names, best overlap otherwise."""
        if self.pick != "auto":
            return self.pick
        return "latest" if (name or "").startswith("OE") else "best"

    def applies(self, name: str) -> bool:
        """True when this call name (e.g. 'OE047_chunk_01') matches --lingbot-pose-mem-tasks."""
        return self.enabled and re.match(self.tasks, name or "") is not None

    def describe(self) -> str:
        return (f"pose memory {self.latents} latents after {self.anchor} anchor, match {self.deg:g} deg / "
                f"{self.trans:g} units, leave {self.leave_deg:g} deg / {self.leave_trans:g} units, rope {self.time}, "
                f"fallback {self.fallback}, cap {self.max_mb:g} MB, tasks {self.tasks!r}, rule {self.rule}, "
                f"pick {self.pick}, yaw scale {self.yaw_scale:g}"
                + (f", track {self.track}" if self.track != "intended" else "")
                + (f", focus {self.focus:g}" if self.focus > 0 else "")
                + (f", rel {self.rel}" if self.rel != "stored" else ""))


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
                      ("max_mb", 1.0, 1e6), ("yaw_scale", 0.25, 4.0), ("focus", 0.0, 1e6)):
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
    for f, allowed in (("time", TIMES), ("fallback", FALLBACKS), ("rule", RULES), ("pick", PICKS),
                       ("track", TRACKS), ("rel", RELS)):
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


def wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def pose_diff(a: np.ndarray, b: np.ndarray, focus: float = 0.0) -> tuple[float, float, float, float]:
    """(dyaw, dpitch, dpos, overlap) from pose a to pose b; dyaw wrapped to [-180, 180).
    With focus > 0, projects 3D focus points X = p + focus * forward into each camera's frustum."""
    ma = np.asarray(a, dtype=np.float64)
    mb = np.asarray(b, dtype=np.float64)
    if focus <= 0.0:
        ya, pa = view_angles(ma)
        yb, pb = view_angles(mb)
        dyaw = wrap180(yb - ya)
        dpitch = pb - pa
        dpos = float(np.linalg.norm(mb[:3, 3] - ma[:3, 3]))
        return dyaw, dpitch, dpos, overlap_of(dyaw, dpitch)
    z = float(focus)
    ra, pos_a = ma[:3, :3], ma[:3, 3]
    rb, pos_b = mb[:3, :3], mb[:3, 3]
    xa = pos_a + z * ra[:, 2]
    xb = pos_b + z * rb[:, 2]
    qb = rb.T @ (xa - pos_b)
    qa = ra.T @ (xb - pos_a)
    dpos = float(np.linalg.norm(xb - xa))
    if qb[2] <= 1e-6 or qa[2] <= 1e-6:
        return 180.0, 90.0, dpos, 0.0
    yb = math.degrees(math.atan2(qb[0], qb[2]))
    pb = math.degrees(math.atan2(-qb[1], math.hypot(qb[0], qb[2])))
    ya = math.degrees(math.atan2(qa[0], qa[2]))
    pa = math.degrees(math.atan2(-qa[1], math.hypot(qa[0], qa[2])))
    o_ang = min(overlap_of(yb, pb), overlap_of(ya, pa))
    scale_ratio = min(qb[2] / z, z / qb[2], qa[2] / z, z / qa[2])
    o = o_ang * max(0.0, min(1.0, scale_ratio))
    return yb, pb, dpos, o


def view_of(c2w, prev_yaw: float | None = None) -> np.ndarray:
    """[yaw, pitch, x, y, z] of a pose; yaw unwrapped to within 180 degrees of prev_yaw when given, so a track
    that turns past 180 keeps counting (a 360 ends at 360, not 0)."""
    yaw, pitch = view_angles(c2w)
    if prev_yaw is not None:
        yaw = prev_yaw + wrap180(yaw - prev_yaw)
    return np.array([yaw, pitch, *np.asarray(c2w, dtype=np.float64)[:3, 3]])


def view_diff(a: np.ndarray, b: np.ndarray, yaw_scale: float = 1.0) -> tuple[float, float, float, float]:
    """pose_diff on views: the unwrapped commanded yaw difference times yaw_scale (the rendered turn), wrapped."""
    dyaw = wrap180(yaw_scale * (b[0] - a[0]))
    dpitch = float(b[1] - a[1])
    dpos = float(np.linalg.norm(b[2:5] - a[2:5]))
    return dyaw, dpitch, dpos, overlap_of(dyaw, dpitch)


def centre(latent_c2ws) -> np.ndarray:
    """The pose a chunk is keyed by: its third latent (index 2 of 4)."""
    lat = np.asarray(latent_c2ws)
    return lat[min(2, len(lat) - 1)]


# ------------------------------------------------------------------ the bank

@dataclass
class Entry:
    cid: int                 # latent chunk index in the rollout
    pose: np.ndarray         # centre latent c2w (selected track)
    x0: object               # clean latents [16, 4, h, w] on the host
    rel: np.ndarray          # the chunk's normalised relative poses [4, 4, 4] (its camera input)
    nbytes: int = 0
    left: bool = False       # the camera has looked away from this view since it was generated
    views: np.ndarray | None = None  # [n_latents, 5] view_of each latent (unwrapped yaw); None: the centre only
    c2ws: np.ndarray | None = None   # [n_latents, 4, 4] latent c2ws (coverage rule); None: the centre only

    def latent_views(self) -> np.ndarray:
        return self.views if self.views is not None else view_of(self.pose)[None]

    def latent_c2ws(self) -> np.ndarray:
        return self.c2ws if self.c2ws is not None else np.asarray(self.pose)[None]

    def centre_view(self) -> np.ndarray:
        v = self.latent_views()
        return v[min(2, len(v) - 1)]


@dataclass
class Match:
    entry: Entry
    dyaw: float
    dpitch: float
    dpos: float
    overlap: float
    window: float = 0.0      # best overlap of the rolling window with the same view (coverage rule)
    note: str = ""           # e.g. "opening re-timed", "later sighting preferred over the opening"


@dataclass
class Plan:
    """What select() saw for one chunk (also printed by the dry-run planner)."""
    matches: list | None     # None: the window holds the view (keep); []: nothing matches; else the chosen chunks
    target: np.ndarray       # view_of the chunk's centre latent
    window: float = 0.0      # best overlap of the rolling window with the target
    matched: int = 0         # stored chunks that overlap the target (before the left/window/coverage tests)
    target_pose: np.ndarray | None = None  # centre latent c2w (used by covers() when focus > 0)


@dataclass
class Decision:
    """What the session does before chunk c: warmup (sink still being written), keep (leave whatever is installed,
    possibly nothing), restore (copy the original sink back), install (a new selection) or retime (the same
    chunks recomputed at a new RoPE time, coverage rule with time recent)."""
    kind: str
    plan: Plan | None = None
    matches: list = field(default_factory=list)
    slots: list = field(default_factory=list)
    ropes: list = field(default_factory=list)
    ids: tuple = ()


@dataclass
class PoseMemory:
    cfg: PoseMemoryConfig
    sink: int                # attention sink latents (pipe.sink_size)
    local: int               # whole cache in latents (pipe.local_attn_size), sink included
    entries: list = field(default_factory=list)
    evicted: int = 0         # entries dropped by the cap
    name: str = ""           # call name of the rollout (picks `auto`)
    current: list = field(default_factory=list)  # matches installed now (set by the caller after an install)
    _views: dict = field(default_factory=dict)   # chunk id -> view_of its latents, unwrapped along the rollout

    @property
    def window(self) -> int:
        """Latents of earlier chunks still in the cache while a chunk is generated (18 - 6 - 4 = 8)."""
        return self.local - self.sink - CHUNK

    @property
    def nbytes(self) -> int:
        return sum(e.nbytes for e in self.entries)

    @property
    def pick(self) -> str:
        return self.cfg.pick_for(self.name)

    def in_cache(self, j: int, c: int) -> bool:
        """True when chunk j still has latents in the cache (sink or rolling window) while chunk c is generated."""
        return j * CHUNK < self.sink or (j + 1) * CHUNK > c * CHUNK - self.window

    def in_window(self, j: int, c: int) -> bool:
        """True when chunk j still has latents in the rolling window (after the sink) while chunk c is generated."""
        return (j + 1) * CHUNK > c * CHUNK - self.window

    def opening(self, e: Entry) -> bool:
        """The chunk overlaps the sink: part of the opening view that the sink holds at its original time."""
        return e.cid * CHUNK < self.sink

    def views(self, latent_c2ws, c: int | None = None) -> np.ndarray:
        """view_of each latent of chunk c, yaw unwrapped from chunk c - 1's last latent (cached per chunk; c None:
        not cached, unwrapped only within the chunk)."""
        if c is not None and c in self._views:
            return self._views[c]
        prev = self._views.get(c - 1) if c is not None else None
        y = None if prev is None else float(prev[-1][0])
        out = []
        for c2w in latent_c2ws:
            v = view_of(c2w, y)
            y = float(v[0])
            out.append(v)
        out = np.stack(out)
        if c is not None:
            self._views[c] = out
        return out

    def add(self, entry: Entry) -> None:
        self.entries.append(entry)
        cap = self.cfg.max_mb * 2 ** 20
        while len(self.entries) > 1 and self.nbytes > cap:
            self.entries.pop(0)
            self.evicted += 1

    def observe(self, latent_c2ws, c: int | None = None) -> None:
        """Mark stored views the camera has left: some latent here is far from the entry's pose."""
        if self.cfg.rule == "legacy":
            for e in self.entries:
                if e.left:
                    continue
                for c2w in latent_c2ws:
                    _, _, dpos, o = pose_diff(e.pose, c2w, self.cfg.focus)
                    if o < self.cfg.leave_overlap or dpos > self.cfg.leave_trans:
                        e.left = True
                        break
            return
        vs = self.views(latent_c2ws, c)
        if self.cfg.focus > 0.0:
            for e in self.entries:
                if e.left:
                    continue
                for c2w in latent_c2ws:
                    _, _, dpos, o = pose_diff(e.pose, c2w, self.cfg.focus)
                    if o < self.cfg.leave_overlap or dpos > self.cfg.leave_trans:
                        e.left = True
                        break
            return
        for e in self.entries:
            if e.left:
                continue
            ev = e.centre_view()
            for v in vs:
                _, _, dpos, o = view_diff(ev, v, self.cfg.yaw_scale)
                if o < self.cfg.leave_overlap or dpos > self.cfg.leave_trans:
                    e.left = True
                    break

    def record(self, cid: int, latent_c2ws, x0=None, rel=None, nbytes: int = 0) -> int:
        """After chunk cid: mark the views it left, then store it. Returns entries evicted by the cap."""
        self.observe(latent_c2ws, cid)
        before = self.evicted
        views = None if self.cfg.rule == "legacy" else self.views(latent_c2ws, cid)
        c2ws = None if self.cfg.rule == "legacy" else np.array(latent_c2ws, copy=True)
        self.add(Entry(cid, np.array(centre(latent_c2ws)), x0, rel, int(nbytes), views=views, c2ws=c2ws))
        self._views = {k: v for k, v in self._views.items() if k >= cid}  # only the last chunk is needed to unwrap
        return self.evicted - before

    def select(self, latent_c2ws, c: int) -> list[Match] | None:
        """Up to cfg.chunks matches for chunk c (poses latent_c2ws); None when the window already holds the view
        (keep what is installed), [] when nothing matches. See the module docstring for the rules."""
        return self.plan(latent_c2ws, c).matches

    def plan(self, latent_c2ws, c: int) -> Plan:
        target_pose = np.asarray(centre(latent_c2ws), dtype=np.float64)
        if self.cfg.rule == "legacy":
            return Plan(self._select_legacy(latent_c2ws, c), view_of(target_pose), target_pose=target_pose)
        cfg, s, focus = self.cfg, self.cfg.yaw_scale, self.cfg.focus
        target = self.views(latent_c2ws, c)[min(2, len(latent_c2ws) - 1)]
        lo = c * CHUNK - self.window
        win = 0.0
        for e in self.entries:  # the rolling window's latents: the best overlap the cache already has
            if not self.in_window(e.cid, c) or e.cid >= c:
                continue
            if focus > 0.0:
                for k, c2w in enumerate(e.latent_c2ws()):
                    if e.c2ws is not None and e.cid * CHUNK + k < lo:  # this latent was evicted already
                        continue
                    _, _, dpos, o = pose_diff(c2w, target_pose, focus)
                    if dpos <= cfg.trans:
                        win = max(win, o)
            else:
                for k, v in enumerate(e.latent_views()):
                    if e.views is not None and e.cid * CHUNK + k < lo:  # this latent was evicted already
                        continue
                    _, _, dpos, o = view_diff(v, target, s)
                    if dpos <= cfg.trans:
                        win = max(win, o)
        matched, eligible = 0, []
        for e in reversed(self.entries):  # newest first
            if e.cid >= c or self.in_window(e.cid, c):
                continue
            if self.opening(e) and cfg.time == "sink":  # its own sink positions: almost a no-op
                continue
            best = None
            if focus > 0.0:
                for c2w in e.latent_c2ws():
                    d = pose_diff(c2w, target_pose, focus)
                    if d[2] <= cfg.trans and (best is None or d[3] > best[3]):
                        best = d
            else:
                for v in e.latent_views():
                    d = view_diff(v, target, s)
                    if d[2] <= cfg.trans and (best is None or d[3] > best[3]):
                        best = d
            if best is None or best[3] < cfg.match_overlap:
                continue
            matched += 1
            if e.left:
                eligible.append(Match(e, *best, window=win))
        if not matched:
            return Plan([], target, win, 0, target_pose=target_pose)
        better = [m for m in eligible if m.overlap > win + 1e-9]
        if self.pick == "latest":
            chosen = better[:cfg.chunks]
            later = [m for m in better if not self.opening(m.entry)]  # still must beat the window
            if chosen and all(self.opening(m.entry) for m in chosen) and later:
                chosen = later[:cfg.chunks]  # Out-of-sight: never only the opening when a later sighting exists
                for m in chosen:
                    m.note = "later sighting preferred over the opening"
        else:
            chosen = sorted(better, key=lambda m: (-round(m.overlap, 9), -m.entry.cid))[:cfg.chunks]
        if not chosen:
            return Plan(None, target, win, matched, target_pose=target_pose)
        for m in chosen:
            if self.opening(m.entry) and not m.note:
                m.note = "opening re-timed" if cfg.time != "sink" else "opening"
        return Plan(chosen, target, win, matched, target_pose=target_pose)

    def _select_legacy(self, latent_c2ws, c: int) -> list[Match] | None:
        """The first version: centre poses; the newest overlapping non-sink sighting shadows older ones: if it is
        still in the rolling window or has not been left, this returns None (recall nothing, keep the sink)."""
        target = centre(latent_c2ws)
        out = []
        for e in reversed(self.entries):
            dyaw, dpitch, dpos, o = pose_diff(e.pose, target, self.cfg.focus)
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

    def decide(self, latent_c2ws, c: int, installed: tuple) -> Decision:
        """What to do before chunk c given the (chunk id, rope latent) pairs installed now. The session acts on it;
        the planner replays it. Neither changes `current` here: the caller sets it after acting."""
        if c * CHUNK < self.sink:  # this rollout's first chunks are still writing the sink
            return Decision("warmup")
        plan = self.plan(latent_c2ws, c)
        matches = plan.matches
        retime = False
        if matches is None:  # the window holds the view: keep what is installed
            if self.cfg.rule == "legacy" or self.cfg.time != "recent" or not self.current:
                return Decision("keep", plan)
            # ...re-timed, so it stays just behind the window, while it still covers the view (else restore)
            matches, retime = [m for m in self.current if self.covers(m.entry, plan.target, plan.target_pose)], True
        if self.cfg.time != "sink":  # oldest chunk in the first slot, so the slot order matches the RoPE order
            matches = sorted(matches, key=lambda m: m.entry.cid)
        slots = self.slots(len(matches))
        ropes = [self.rope_latent(i, sl, m.entry, c, len(matches)) for i, (sl, m) in enumerate(zip(slots, matches))]
        # keyed on the RoPE times too: with time=recent they move with every chunk, so the memory is recomputed
        ids = tuple((m.entry.cid, r) for m, r in zip(matches, ropes))
        if ids == installed:
            return Decision("keep", plan, matches, slots, ropes, ids)
        if not ids:
            return Decision("restore" if self.cfg.fallback == "start" else "keep", plan)
        same = self.cfg.rule != "legacy" and tuple(i for i, _ in ids) == tuple(i for i, _ in installed)
        return Decision("retime" if retime or same else "install", plan, matches, slots, ropes, ids)

    def covers(self, e: Entry, target, target_pose: np.ndarray | None = None) -> bool:
        """Whether a stored chunk's best latent still overlaps the target view by match_overlap (coverage rule)."""
        if self.cfg.focus > 0.0:
            if e.c2ws is None and e.views is None:
                return True
            if target_pose is None:
                return True
            for c2w in e.latent_c2ws():
                _, _, dpos, o = pose_diff(c2w, target_pose, self.cfg.focus)
                if dpos <= self.cfg.trans and o >= self.cfg.match_overlap:
                    return True
            return False
        if e.views is None:
            return True
        for v in e.latent_views():
            _, _, dpos, o = view_diff(v, target, self.cfg.yaw_scale)
            if dpos <= self.cfg.trans and o >= self.cfg.match_overlap:
                return True
        return False

    def slots(self, n: int) -> list[int]:
        """First latent slot of each of n retrieved chunks (time sink: retrieval order, most recent first; otherwise
        oldest chunk first, so a later slot never holds an earlier RoPE time)."""
        return [self.cfg.anchor + i * CHUNK for i in range(n)]

    def rope_latent(self, slot_index: int, slot: int, entry: Entry, c: int, n: int) -> int:
        """RoPE time (latent index) the retrieved chunk is recomputed at. sink: its slot (the position pattern
        of today's sink); recent: just behind the rolling window of chunk c, the last slot nearest (recomputed every
        chunk while installed, so it tracks the window); orig: when it was made."""
        if self.cfg.time == "sink":
            return slot
        if self.cfg.time == "orig":
            return entry.cid * CHUNK
        return max(0, c * CHUNK - self.window - CHUNK * (n - slot_index))
