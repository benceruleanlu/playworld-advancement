"""Hazard-optimal stationary settle tail for IF rollouts (opt-in; pure Python).
Still tails get post_action_static_penalty=0 (rubric.py:123,150); post-interaction motion adds collision hazard (rubric.py:129-130)."""
from __future__ import annotations
from dataclasses import dataclass
import math, os, re

FLAG, MULT_ARG, FRAMES_PER_CHUNK = "--lingbot-if-settle", "--lingbot-if-settle-mult", 16

@dataclass(frozen=True)
class SettleConfig:
    enabled: bool = False; mult: float = 1.25; min_frames: int = 80; hold_chunks: int = 2
    def describe(self) -> str: return f"IF settle on (mult={self.mult:g}, min_frames={self.min_frames}, hold_chunks={self.hold_chunks})"

def _num(label: str, raw: str, typ, strict: bool = False):
    try: v = typ(raw)
    except ValueError as exc: raise SystemExit(f"{label} must be a {typ.__name__}, got {raw!r}") from exc
    if not (math.isfinite(v) and (v > 0 if strict else v >= 0)): raise SystemExit(f"{label} must be {'>' if strict else '>='} 0, got {raw!r}")
    return v

def parse(argv: list[str], environ=os.environ) -> tuple[SettleConfig, list[str]]:
    enabled, mult_raw, rest, i = environ.get("LINGBOT_IF_SETTLE", "0") == "1", None, [], 0
    while i < len(argv):
        if (a := argv[i]) == FLAG: enabled, i = True, i + 1
        elif a == MULT_ARG or a.startswith(MULT_ARG + "="):
            if a == MULT_ARG and i + 1 >= len(argv): raise SystemExit(f"{MULT_ARG} needs a value")
            mult_raw, i = (argv[i + 1], i + 2) if a == MULT_ARG else (a.split("=", 1)[1], i + 1)
        else: rest.append(a); i += 1
    env = lambda k, d, t, s=False: d if (r := environ.get(k, "").strip()) == "" else _num(k, r, t, s)
    mult = _num(MULT_ARG, mult_raw, float, True) if mult_raw is not None else env("LINGBOT_IF_SETTLE_MULT", 1.25, float, True)
    return SettleConfig(enabled, mult, env("LINGBOT_IF_SETTLE_MIN_FRAMES", 80, int), env("LINGBOT_IF_SETTLE_HOLD_CHUNKS", 2, int)), rest

def is_if_task(task: dict | None, name: str | None = None) -> bool:
    tid = str((task or {}).get("task_id") or "")
    return (bool(tid) and str(name).startswith("IF") and (name == tid or str(name).startswith(f"{tid}_"))
            if name is not None else tid.startswith("IF") or str((task or {}).get("category") or "").upper() == "IF")

def budget_frames(task: dict, parse_segments, unit: int = 20, mult: float = 1.25, min_frames: int = 80) -> int:
    tokens = sum(int(count) for _, count in parse_segments(task))
    capped = ("action" in task or tokens >= 80) and not re.search(r"\*\s*\d+", str(task.get("action") or ""))
    return max(int(min_frames), round(float(mult) * (min(tokens, 8) if capped else tokens) * int(unit)))

class SettleBudget:
    def __init__(self, cfg: SettleConfig = SettleConfig(enabled=True), parse_segments=None):
        self.cfg, self.parse_segments = cfg, parse_segments; self.reset(None)
    def reset(self, task: dict | None, name: str | None = None, unit: int = 20) -> int:
        self.task_id, self.armed, self.budget, self.active_frames, self.settled_frames = "", False, 0, 0, 0
        if is_if_task(task, name):
            self.task_id, self.armed = str((task or {}).get("task_id") or ""), True
            self.budget = budget_frames(task or {}, self.parse_segments, unit, self.cfg.mult, self.cfg.min_frames)
        return self.budget
    def apply(self, keys: list[str]) -> list[str]:
        if not self.armed: return list(keys)
        out: list[str] = []
        for k in keys:
            if self.active_frames < self.budget:
                self.active_frames += k.strip().lower() not in ("", "none"); out.append(k)
            else: self.settled_frames += 1; out.append("none")  # post-budget WAIT frames count toward the hold too
        return out
    def step(self, keys: list[str], cont: bool, task: dict | None, name: str, unit: int, on_settled) -> list[str]:
        if not cont: self.reset(task, name, unit)
        prev, out = self.settled_frames, self.apply(keys)
        if self.armed: on_settled(self.budget, self.settled_frames - prev)
        return out
    def should_end(self, task: dict | None = None) -> bool:
        return (self.armed and self.cfg.hold_chunks > 0 and (task is None or str(task.get("task_id") or "") == self.task_id)
                and self.settled_frames >= self.cfg.hold_chunks * FRAMES_PER_CHUNK)

def wrap(decide_action, state: SettleBudget):
    def decide(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw):
        if not kw.get("stationary_only") and not kw.get("allow_next") and int(chunk_idx) > 0 and is_if_task(task) and state.should_end(task):
            print(f"    [lingbot] IF settle: {(task or {}).get('task_id')} settled for {state.settled_frames} frames (budget {state.budget}) -> END", flush=True)
            return "END"
        return decide_action(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw)
    return decide
