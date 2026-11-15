"""Log-length self-attention query temperature scaling (Chiang & Cholak 2022 / YaRN; opt-in, pure Python).
Scales `blocks[*].self_attn.norm_q` by `gain * sqrt(ln(N_active) / ln(N_ref))` before RoPE and FlashAttention
(`RoPE(s*q) == s*RoPE(q)`): chunks 0..2 (<=12 latents) stay 1.0; chunks 3+ scale smoothly with active KV length."""
from __future__ import annotations
from dataclasses import dataclass
import math, os  # noqa: E401

CHUNK, FLAG, BELOW_FLAG = 4, "--lingbot-yarn-q", "--lingbot-yarn-below-ref"
_VAL_ARGS = {"--lingbot-yarn-ref": ("ref_latents", "LINGBOT_YARN_REF", 12, int),
             "--lingbot-yarn-gain": ("gain", "LINGBOT_YARN_GAIN", 1.0, float)}


@dataclass(frozen=True)
class YarnQConfig:
    enabled: bool = False
    ref_latents: int = 12
    gain: float = 1.0
    below_ref: bool = False
    def describe(self) -> str:
        return f"yarn-q on (ref={self.ref_latents}, gain={self.gain:g}{', below_ref=1' if self.below_ref else ''})"

def _val(label: str, raw: str, typ):
    try: v = typ(raw)  # noqa: E701
    except ValueError as exc: raise SystemExit(f"{label} must be a {typ.__name__}, got {raw!r}") from exc  # noqa: E701
    if (typ is int and v < 4) or (typ is float and not (math.isfinite(v) and v > 0.0)):
        raise SystemExit(f"{label} out of range, got {raw!r}")
    return v

def parse(argv: list[str], environ=os.environ) -> tuple[YarnQConfig, list[str]]:
    seen, rest, i = {}, [], 0
    en, bel = environ.get("LINGBOT_YARN_Q", "0") == "1", environ.get("LINGBOT_YARN_BELOW_REF", "0") == "1"
    while i < len(argv):
        a = argv[i]
        if a in (FLAG, BELOW_FLAG): en, bel, i = en or (a == FLAG), bel or (a == BELOW_FLAG), i + 1  # noqa: E701
        elif (key := next((k for k in _VAL_ARGS if a == k or a.startswith(k + "=")), None)) is None:
            rest.append(a); i += 1  # noqa: E702
        elif a == key and i + 1 < len(argv): seen[key], i = argv[i + 1], i + 2  # noqa: E701
        elif a == key: raise SystemExit(f"{key} needs a value")  # noqa: E701
        else: seen[key], i = a[len(key) + 1:], i + 1  # noqa: E701
    kw = {f: _val(arg, raw, t) if (raw := seen.get(arg)) is not None else (d if (er := environ.get(env, "").strip()) == "" else _val(env, er, t)) for arg, (f, env, d, t) in _VAL_ARGS.items()}
    return YarnQConfig(enabled=en, below_ref=bel, **kw), rest

def scale_for_chunk(cid: int, local_attn_size: int = 18, frame_seqlen: int = 1560, ref_latents: int = 12, gain: float = 1.0, below_ref: bool = False) -> float:
    lat = (max(0, int(cid)) + 1) * CHUNK
    lat, fseq = (lat if local_attn_size < 0 else min(lat, int(local_attn_size))), max(1, int(frame_seqlen))
    n_active, n_ref = max(2, lat * fseq), max(2, int(ref_latents) * fseq)
    return float(gain) if (n_active == n_ref or (not below_ref and n_active < n_ref)) else gain * math.sqrt(math.log(n_active) / math.log(n_ref))

def _wrap(lyr, g):
    had, orig = "forward" in getattr(lyr, "__dict__", {}), lyr.forward
    lyr.forward = lambda *a, **kw: orig(*a, **kw) if (s := g()) == 1.0 else orig(*a, **kw) * s
    return (lyr, had, orig)

def detach_model(model) -> None:
    if (prev := getattr(model, "_yarn_q", None)) is not None: prev.detach()  # noqa: E701


class YarnQScaler:
    def __init__(self, model, cfg: YarnQConfig = YarnQConfig(enabled=True)):
        self.cfg, self.q_scale, self._model = cfg, 1.0, model
        detach_model(model)
        self._hooks = [_wrap(b.self_attn.norm_q, lambda: self.q_scale) for b in model.blocks]
        model._yarn_q = self
    def step(self, cid: int, local_attn_size: int, frame_seqlen: int) -> bool:
        self.q_scale = scale_for_chunk(cid, local_attn_size, frame_seqlen, self.cfg.ref_latents, self.cfg.gain, self.cfg.below_ref)
        return self.q_scale != 1.0
    def reset(self) -> None: self.q_scale = 1.0
    def __enter__(self): return self
    def __exit__(self, *_exc) -> None: self.reset()
    def detach(self) -> None:
        for lyr, had, orig in self._hooks: setattr(lyr, "forward", orig) if had else delattr(lyr, "forward")  # noqa: E701
        self._hooks.clear()
        if getattr(self._model, "_yarn_q", None) is self: delattr(self._model, "_yarn_q")  # noqa: E701
