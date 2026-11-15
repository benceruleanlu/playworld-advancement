"""Contrastive T5 representation steering for text conditioning (opt-in; zero import-time deps).
Steers `c_pos + scale * (c_pos - c_neg)` across dynamic vs static T5 contexts in float32
and rescales each tensor to `c_pos`'s RMS norm."""
from __future__ import annotations
import os
from dataclasses import dataclass

FLAG, SCALE_ARG = "--lingbot-repe-steer", "--lingbot-repe-scale"
FAMILIES = ("gc", "if", "insight", "outsight")
POS_CUE = "Active temporal progression: ongoing physical motion and visible state evolution continue steadily over time."
NEG_CUE = "Completely static frozen still photograph: zero motion, unchanging pose, no progression."

@dataclass(frozen=True)
class SteerConfig:
    enabled: bool = False
    scale: float = 0.5
    families: tuple[str, ...] = ("insight", "outsight")
    def describe(self) -> str: return f"repe-steer scale={self.scale:g} families={'+'.join(self.families)}"

def _parse_scale(label: str, raw: str) -> float:
    try: v = float(raw)  # noqa: E701
    except ValueError as exc: raise SystemExit(f"{label} must be a float >= 0, got {raw!r}") from exc  # noqa: E701
    if not (v >= 0.0 and v != float("inf")):
        raise SystemExit(f"{label} must be a finite number >= 0, got {raw!r}")
    return v

def parse(argv: list[str], environ=os.environ) -> tuple[SteerConfig, list[str]]:
    enabled, raw_scale, rest, i = environ.get("LINGBOT_REPE_STEER", "0") == "1", None, [], 0
    while i < len(argv):
        if (a := argv[i]) == FLAG: enabled, i = True, i + 1  # noqa: E701
        elif a == SCALE_ARG:
            if i + 1 >= len(argv): raise SystemExit(f"{SCALE_ARG} needs a value")  # noqa: E701
            raw_scale, i = argv[i + 1], i + 2
        elif a.startswith(SCALE_ARG + "="): raw_scale, i = a[len(SCALE_ARG) + 1:], i + 1  # noqa: E701
        else: rest.append(a); i += 1  # noqa: E701, E702
    es, ef = environ.get("LINGBOT_REPE_SCALE", "").strip(), environ.get("LINGBOT_REPE_FAMILIES", "").strip()
    scale = _parse_scale(SCALE_ARG, raw_scale) if raw_scale is not None else (0.5 if es == "" else _parse_scale("LINGBOT_REPE_SCALE", es))
    items = [x.strip().lower() for x in ef.split(",")] if ef else ["insight", "outsight"]
    if any(x not in FAMILIES for x in items):
        raise SystemExit(f"LINGBOT_REPE_FAMILIES must be a subset of {FAMILIES}, got {ef!r}")
    return SteerConfig(enabled=enabled, scale=scale, families=tuple(dict.fromkeys(items))), rest

def applies_to(task: dict | None, name: str, cfg: SteerConfig) -> bool:
    if not cfg.enabled: return False  # noqa: E701
    s = str(name or "")
    task = task if (task and s.startswith(f"{task.get('task_id')}_")) else None
    sub, cat = str((task or {}).get("sub_category") or "").strip().lower().replace("-", ""), str((task or {}).get("category") or "").strip().upper()
    fam = ("insight" if sub == "insight evolution" else "outsight" if sub == "outofsight evolution"
           else cat.lower() if cat in ("GC", "IF") else "gc" if s.upper().startswith("GC") else "if" if s.upper().startswith("IF") else "")
    return fam in cfg.families

def prompt_pair(base_prompt: str) -> tuple[str, str]:
    return f"{base_prompt}\n{POS_CUE}", f"{base_prompt}\n{NEG_CUE}"

def steer_tensors(c_pos, c_neg, scale: float):
    if hasattr(c_pos, "ndim"): return steer_tensors([c_pos], [c_neg], scale)[0]  # noqa: E701
    if (s := float(scale)) == 0.0: return [t.clone() for t in c_pos]  # noqa: E701
    out = []
    for p, n in zip(c_pos, c_neg):
        pf, nf = p.float(), n.float()
        if pf.shape != nf.shape:
            lp, ln = pf.shape[0], nf.shape[0]
            if ln == 0 or ln >= lp: nf = pf.new_zeros(pf.shape) if ln == 0 else nf[:lp]  # noqa: E701
            else: nf_al = pf.new_empty(pf.shape); nf_al[:ln], nf_al[ln:] = nf, nf.mean(dim=0, keepdim=True); nf = nf_al  # noqa: E701, E702
        raw = pf + s * (pf - nf)
        rms_p, rms_r = (pf * pf).mean().sqrt(), (raw * raw).mean().sqrt()
        out.append((raw * (rms_p / rms_r) if float(rms_r) > 0.0 else pf).to(p.dtype))
    return out

def encode_steered(pipe, base_prompt: str, disk, scale: float, encode_fn):
    pos_p, neg_p = prompt_pair(base_prompt)
    return steer_tensors(encode_fn(pipe, pos_p, disk), encode_fn(pipe, neg_p, disk), scale)
