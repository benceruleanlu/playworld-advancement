"""Early-step self-guidance by layer skip (--lingbot-stg, opt-in, session only; pure Python, torch never imported).

On the first `--lingbot-stg-steps N` (default 1) of the 4 denoising steps of every latent chunk, session.step runs
one extra DiT forward in which the self-attention residual of the chosen blocks is bypassed (that block's
`self_attn` returns zeros, so `x = x + 0 * gate`: identity for the sub-layer), then combines the two flow
predictions before the x0 conversion:

    v = v_full + w * (v_full - v_skip)        (w = --lingbot-stg-w, default 0.3)

The skip pass runs BEFORE the full pass of the same step, so the full pass sees exactly the caches main sees:
every self-attention forward writes its keys/values into the current chunk's KV slot before reading it (upstream
model_fast.CausalWanSelfAttention), and the indices it moves are idempotent within a chunk, so the full pass
overwrites whatever the skip pass wrote. The cross-attention cache is filled from the text context only, so the
skip pass may (re)fill it with the same values. The clean t=0 KV-write pass is never guided or skipped.
Cost: +1 DiT forward on each guided step (+20% per chunk at N=1: 6 forwards instead of 5)."""
from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass

FLAG = "--lingbot-stg"
_VAL_ARGS = {
    "--lingbot-stg-w": ("w", "LINGBOT_STG_W", 0.3, float),
    "--lingbot-stg-blocks": ("blocks", "LINGBOT_STG_BLOCKS", "mid", str),
    "--lingbot-stg-steps": ("steps", "LINGBOT_STG_STEPS", 1, int),
}


@dataclass(frozen=True)
class StgConfig:
    enabled: bool = False
    w: float = 0.3
    blocks: str = "mid"  # "mid" (num_blocks // 2: 20 on 14B, 15 on 1.3B) or comma-separated block indices
    steps: int = 1


def _value(label: str, raw: str, typ):
    if typ is str:
        if not raw.strip():
            raise SystemExit(f"{label} needs a value")
        return raw.strip()
    try:
        v = typ(raw)
    except ValueError as exc:
        raise SystemExit(f"{label} must be a {typ.__name__}, got {raw!r}") from exc
    if typ is int and v < 1:
        raise SystemExit(f"{label} must be >= 1, got {raw!r}")
    if not (v >= 0 and v != float("inf")):
        raise SystemExit(f"{label} must be a finite number >= 0, got {raw!r}")
    return v


def parse(argv: list[str], environ=os.environ) -> tuple[StgConfig, list[str]]:
    """StgConfig from argv (or env), and argv without the --lingbot-stg* args. Read per main() call."""
    seen, enabled, rest, i = {}, environ.get("LINGBOT_STG", "0") == "1", [], 0
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
    kw = {"enabled": enabled}
    for arg, (field, env, default, typ) in _VAL_ARGS.items():
        raw, eraw = seen.get(arg), environ.get(env, "").strip()
        kw[field] = _value(arg, raw, typ) if raw is not None else (default if eraw == "" else _value(env, eraw, typ))
    cfg = StgConfig(**kw)
    resolve_blocks(cfg.blocks, None)  # syntax check now; the range check needs the loaded DiT
    return cfg, rest


def resolve_blocks(spec: str, n: int | None) -> tuple[int, ...]:
    """Block indices for spec: "mid" -> (n // 2,), "18,22" -> (18, 22). n=None checks the syntax only."""
    if spec == "mid":
        return () if n is None else (n // 2,)
    try:
        out = tuple(sorted({int(p) for p in spec.split(",") if p.strip()}))
    except ValueError as exc:
        raise SystemExit(f"--lingbot-stg-blocks must be 'mid' or comma-separated block indices, got {spec!r}") from exc
    if not out:
        raise SystemExit(f"--lingbot-stg-blocks names no block: {spec!r}")
    if n is not None and not all(0 <= b < n for b in out):
        raise SystemExit(f"--lingbot-stg-blocks {spec!r}: the DiT has blocks 0..{n - 1}")
    return out


def _zeros_like(x, *_a, **_kw):
    return x.new_zeros(x.shape)  # self_attn maps [B, L, dim] -> [B, L, dim]


class SkipGuidance:
    """Holds the chosen blocks of one loaded DiT. Installs nothing until skipped() is entered."""

    def __init__(self, model, cfg: StgConfig):
        self.cfg, self._model = cfg, model
        self.blocks = resolve_blocks(cfg.blocks, len(model.blocks))

    def describe(self) -> str:
        return f"stg w={self.cfg.w:g} blocks={','.join(map(str, self.blocks))} steps={self.cfg.steps}"

    def guided(self, step_idx: int) -> bool:
        return step_idx < self.cfg.steps

    @contextlib.contextmanager
    def skipped(self):
        """The chosen blocks' self_attn returns zeros inside the block; restored on exit, also on error."""
        saved = []
        try:
            for b in self.blocks:
                attn = self._model.blocks[b].self_attn
                saved.append((attn, "forward" in getattr(attn, "__dict__", {}), attn.forward))
                attn.forward = _zeros_like
            yield self
        finally:
            for attn, had, orig in reversed(saved):
                setattr(attn, "forward", orig) if had else delattr(attn, "forward")

    def combine(self, v_full, v_skip):
        return v_full + (v_full - v_skip) * self.cfg.w
