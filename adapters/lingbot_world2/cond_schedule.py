"""Denoising-step conditioning schedule + stationary text up-scaling (opt-in; pure Python + numpy).
Weakens DiT camera FiLM (`cam_scale_layer`, `cam_shift_layer`) and boosts `cross_attn.o` on early
denoising steps of stationary (`WAIT`) and third-person chunks, restoring `(1.0, 1.0)` on late steps
and on the `t=0` KV-cache write. Moving first-person chunks stay `(1.0, 1.0)` at every step.
The optional GC guard keeps first-person GC at `(1.0, 1.0)` even during WAIT tails."""
from __future__ import annotations
import os
from dataclasses import dataclass
import numpy as np

FLAG = "--lingbot-cond-schedule"
GC_GUARD = "--lingbot-cond-gc-guard"
_VAL_ARGS = {
    "--lingbot-cond-early": ("early_steps", "LINGBOT_COND_EARLY_STEPS", 2, int),
    "--lingbot-cond-cam": ("cam_static", "LINGBOT_COND_CAM_STATIC", 0.0, float),
    "--lingbot-cond-3p": ("cam_3p", "LINGBOT_COND_CAM_3P", 0.85, float),
    "--lingbot-cond-text": ("text_static", "LINGBOT_COND_TEXT_STATIC", 1.15, float),
}


@dataclass(frozen=True)
class ScheduleConfig:
    enabled: bool = False
    early_steps: int = 2
    cam_static: float = 0.0
    cam_3p: float = 0.85
    text_static: float = 1.15
    text_3p: float = 1.0
    gc_guard: bool = False

    def describe(self) -> str:
        return (f"cond-schedule early={self.early_steps} static=({self.cam_static:g},{self.text_static:g}) "
                f"3p=({self.cam_3p:g},{self.text_3p:g})" + (" GC guard on" if self.gc_guard else ""))


def _num(label: str, raw: str, typ):
    try:
        v = typ(raw)
    except ValueError as exc:
        raise SystemExit(f"{label} must be a {typ.__name__}, got {raw!r}") from exc
    if not (v >= 0 and v != float("inf")):
        raise SystemExit(f"{label} must be a finite number >= 0, got {raw!r}")
    return v


def parse(argv: list[str], environ=os.environ) -> tuple[ScheduleConfig, list[str]]:
    guard = GC_GUARD in argv or environ.get("LINGBOT_COND_GC_GUARD", "0") == "1"
    argv = [a for a in argv if a != GC_GUARD]
    seen, enabled, rest, i = {}, environ.get("LINGBOT_COND_SCHEDULE", "0") == "1", [], 0
    while i < len(argv):
        a = argv[i]
        if a == FLAG:
            enabled, i = True, i + 1
        elif (key := next((k for k in _VAL_ARGS if a == k or a.startswith(k + "=")), None)) is None:
            rest.append(a)
            i += 1
        elif a == key:
            if i + 1 >= len(argv):
                raise SystemExit(f"{key} needs a value")
            seen[key], i = argv[i + 1], i + 2
        else:
            seen[key], i = a[len(key) + 1:], i + 1
    kw = {"enabled": enabled, "gc_guard": guard}
    for arg, (field, env, default, typ) in _VAL_ARGS.items():
        raw, eraw = seen.get(arg), environ.get(env, "").strip()
        kw[field] = _num(arg, raw, typ) if raw is not None else (default if eraw == "" else _num(env, eraw, typ))
    t3 = environ.get("LINGBOT_COND_TEXT_3P", "").strip()
    return ScheduleConfig(**kw, text_3p=1.0 if t3 == "" else _num("LINGBOT_COND_TEXT_3P", t3, float)), rest


def is_stationary(rel: np.ndarray, atol: float = 1e-5) -> bool:
    return (a := np.asarray(rel, dtype=np.float64)).size > 0 and bool(np.allclose(a, np.eye(4), atol=atol))


def is_third_person(task: dict | None = None, name: str = "") -> bool:
    if task and name and not str(name).startswith(f"{task.get('task_id')}_"):
        task = None
    if persp := str((task or {}).get("perspective") or "").lower():
        return "third" in persp
    s = str(name or "")
    return str((task or {}).get("category") or "").upper() == "IF" or s.upper().startswith("IF") or "third" in s.lower()


def _wrap_linear(layer, get_scale):
    had, orig = "forward" in getattr(layer, "__dict__", {}), layer.forward
    layer.forward = lambda *a, **kw: orig(*a, **kw) if (s := get_scale()) == 1.0 else orig(*a, **kw) * s
    return (layer, had, orig)


def detach_model(model) -> None:
    if (prev := getattr(model, "_cond_schedule", None)) is not None:
        prev.detach()


class CondScheduler:
    def __init__(self, model, cfg: ScheduleConfig = ScheduleConfig(enabled=True)):
        self.cfg, self.cam_scale, self.text_scale, self._model = cfg, 1.0, 1.0, model
        self.guard_gc, self.guard_calls = False, 0
        detach_model(model)
        gc, gt = (lambda: self.cam_scale), (lambda: self.text_scale)
        self._hooks = [h for b in model.blocks for h in (
            _wrap_linear(b.cam_scale_layer, gc), _wrap_linear(b.cam_shift_layer, gc), _wrap_linear(b.cross_attn.o, gt))]
        model._cond_schedule = self

    def set_task(self, name: str, third_person: bool) -> None:
        self.guard_gc = self.cfg.gc_guard and name.startswith("GC") and not third_person

    def scales_for(self, rel: np.ndarray, step_idx: int, third_person: bool = False) -> tuple[float, float]:
        if step_idx >= self.cfg.early_steps:
            return (1.0, 1.0)
        return (self.cfg.cam_static, self.cfg.text_static) if is_stationary(rel) else (
            (self.cfg.cam_3p, self.cfg.text_3p) if third_person else (1.0, 1.0))

    def set_step(self, rel: np.ndarray, step_idx: int, third_person: bool = False) -> bool:
        self.cam_scale, self.text_scale = self.scales_for(rel, step_idx, third_person)
        if self.guard_gc and (self.cam_scale, self.text_scale) != (1.0, 1.0):
            self.guard_calls += 1  # count only forwards the unguarded schedule would change
            self.reset()
        return self.cam_scale != 1.0 or self.text_scale != 1.0

    def reset(self) -> None:
        self.cam_scale = self.text_scale = 1.0

    def __enter__(self): return self
    def __exit__(self, *_exc) -> None: self.reset()

    def detach(self) -> None:
        for layer, had, orig in self._hooks:
            setattr(layer, "forward", orig) if had else delattr(layer, "forward")
        self._hooks.clear()
        if getattr(self._model, "_cond_schedule", None) is self:
            delattr(self._model, "_cond_schedule")
