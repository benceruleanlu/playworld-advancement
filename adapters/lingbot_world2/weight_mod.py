"""Inference-time DiT conditioning weight modulation (opt-in; pure Python + numpy).
Scales `blocks[*].{cam_scale_layer,cam_shift_layer,cross_attn.o}` via `layer.forward`
(`(s*W)x + s*b == s*(Wx + b)`): zero extra VRAM, zero bfloat16 drift, instant switching."""
from __future__ import annotations
import os
import numpy as np


def _scale(val: float | None, env: str, default: float) -> float:
    if (out := float(os.environ.get(env, str(default))) if val is None else float(val)) < 0.0:
        raise ValueError(f"{env} must be >= 0, got {out}")
    return out

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
    if (prev := getattr(model, "_weight_mod", None)) is not None:
        prev.detach()


class WeightModulator:
    def __init__(self, model, cam_static: float | None = None, cam_move: float | None = None,
                 cam_3p: float | None = None, text_scale: float | None = None, text_move: float | None = None,
                 text_static: float | None = None):
        self.cam_static, self.cam_move = _scale(cam_static, "LINGBOT_CAM_WEIGHT_STATIC", 0.0), _scale(cam_move, "LINGBOT_CAM_WEIGHT_MOVE", 1.0)
        self.cam_3p, self.text_gain = _scale(cam_3p, "LINGBOT_CAM_WEIGHT_3P", 0.85), _scale(text_scale, "LINGBOT_TEXT_WEIGHT_SCALE", 1.0)
        self.text_static = _scale(text_static, "LINGBOT_TEXT_WEIGHT_STATIC", self.text_gain)
        self.text_move, self.cam_scale, self.text_scale, self._model = _scale(text_move, "LINGBOT_TEXT_WEIGHT_MOVE", 1.0), 1.0, 1.0, model
        detach_model(model)
        gc, gt = (lambda: self.cam_scale), (lambda: self.text_scale)
        self._hooks = [h for b in model.blocks for h in (
            _wrap_linear(b.cam_scale_layer, gc), _wrap_linear(b.cam_shift_layer, gc), _wrap_linear(b.cross_attn.o, gt))]
        model._weight_mod = self

    def step(self, rel: np.ndarray, third_person: bool = False) -> bool:
        self.cam_scale, self.text_scale = ((self.cam_static, self.text_static) if is_stationary(rel)
                                           else (self.cam_3p, self.text_gain) if third_person else (self.cam_move, self.text_move))
        return self.cam_scale != 1.0 or self.text_scale != 1.0

    def reset(self) -> None:
        self.cam_scale = self.text_scale = 1.0

    def __enter__(self): return self
    def __exit__(self, *_exc) -> None: self.reset()

    def detach(self) -> None:
        for layer, had, orig in self._hooks:
            setattr(layer, "forward", orig) if had else delattr(layer, "forward")
        self._hooks.clear()
        if getattr(self._model, "_weight_mod", None) is self:
            delattr(self._model, "_weight_mod")

    def describe(self) -> str:
        """The active scales, for the `[lingbot] mode:` line (so env overrides show in gen.log)."""
        extra = [f"{k} {getattr(self, a)}" for k, a, base in (
            ("text static", "text_static", "text_gain"), ("late steps", "late_steps", None),
            ("static late", "cam_static_late", "cam_static"), ("3p late", "cam_3p_late", "cam_3p"))
            if hasattr(self, a) and getattr(self, a) != (getattr(self, base) if base else 0)]
        return ", ".join([f"static {self.cam_static}", f"3p {self.cam_3p}", f"move {self.cam_move}",
                          f"text {self.text_gain}", f"text move {self.text_move}", *extra])
