"""Sink key scaling (opt-in, session only; pure Python, no torch import).

`--lingbot-sink-key-scale A` (0 < A <= 1; absent or 1.0 = off) multiplies the cached self-attention keys of the
attention-sink tokens (the first `--lingbot-sink-size` latent frames, which upstream never evicts) by A on the
denoising forwards of every latent chunk with chunk_id >= `--lingbot-sink-scale-after K` (default 8), in tasks whose
call name matches `--lingbot-sink-scale-tasks REGEX` (default ".*"). The cache stores keys after RMSNorm and RoPE
and the kernel computes softmax(Q K^T / sqrt(d)), so Q (A K)^T = A Q K^T: the sink logits are scaled by A inside
the unmodified attention call. Values are untouched. The original key slice of every block is copied before the
chunk's first denoising forward and written back (copied, never divided) after its last one, also on an exception,
so the clean t=0 KV-write pass and every later chunk see the pristine cache.

A < 1 is a temperature on the sink logits: it pulls them toward 0. It does not guarantee less attention mass on
the sink: sink keys with negative logits gain weight; only high-logit sink tokens are damped. A log(A) bias would
cut the mass, but the attention call takes no bias argument. Refused (run.configure) with --lingbot-stateless or
sink 0 (including local -1), where it would be a no-op arm."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

FLAG = "--lingbot-sink-key-scale"
_ARGS = {
    FLAG: ("scale", "LINGBOT_SINK_KEY_SCALE"),
    "--lingbot-sink-scale-after": ("after", "LINGBOT_SINK_SCALE_AFTER"),
    "--lingbot-sink-scale-tasks": ("tasks", "LINGBOT_SINK_SCALE_TASKS"),
}
DEFAULT_AFTER, DEFAULT_TASKS = 8, ".*"


@dataclass(frozen=True)
class SinkScaleConfig:
    scale: float = 1.0
    after: int = DEFAULT_AFTER
    tasks: str = DEFAULT_TASKS

    @property
    def enabled(self) -> bool:
        return self.scale < 1.0

    def applies(self, name: str) -> bool:
        """True when this call name (e.g. 'OE047_chunk_01') matches --lingbot-sink-scale-tasks."""
        return self.enabled and re.match(self.tasks, name or "") is not None

    def describe(self) -> str:
        return f"sink key scale {self.scale:g} from chunk {self.after} tasks {self.tasks!r}"


def _take(argv: list[str]) -> tuple[dict, list[str]]:
    seen, rest, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        key = next((k for k in _ARGS if a == k or a.startswith(k + "=")), None)
        if key is None:
            rest.append(a)
            i += 1
        elif a == key:
            if i + 1 >= len(argv):
                raise SystemExit(f"{key} needs a value")
            seen[key], i = argv[i + 1], i + 2
        else:
            seen[key], i = a[len(key) + 1:], i + 1
    return seen, rest


def parse(argv: list[str], environ=os.environ) -> tuple[SinkScaleConfig, list[str]]:
    """The three knobs out of argv (last value wins; env vars as fallback), and argv without them."""
    seen, rest = _take(argv)
    raw = {f: seen.get(arg, environ.get(env, "").strip() or None) for arg, (f, env) in _ARGS.items()}
    try:
        scale = 1.0 if raw["scale"] is None else float(raw["scale"])
    except ValueError:
        raise SystemExit(f"{FLAG} must be a number in (0, 1], got {raw['scale']!r}") from None
    if not 0.0 < scale <= 1.0:
        raise SystemExit(f"{FLAG} must be in (0, 1], got {raw['scale']!r}")
    try:
        after = DEFAULT_AFTER if raw["after"] is None else int(raw["after"])
    except ValueError:
        raise SystemExit(f"--lingbot-sink-scale-after must be an integer, got {raw['after']!r}") from None
    if after < 0:
        raise SystemExit(f"--lingbot-sink-scale-after must be >= 0, got {after}")
    tasks = DEFAULT_TASKS if raw["tasks"] is None else raw["tasks"]
    try:
        re.compile(tasks)
    except re.error as exc:
        raise SystemExit(f"--lingbot-sink-scale-tasks is not a valid regex: {exc}") from None
    return SinkScaleConfig(scale, after, tasks), rest


def sink_tokens(sink_latents: int, frame_seqlen: int) -> int:
    """Cache tokens held by the sink: upstream's sink_size * frame_seqlen (CausalWanSelfAttention.forward)."""
    return max(0, int(sink_latents)) * max(0, int(frame_seqlen))


def active(cfg: SinkScaleConfig | None, chunk_id: int, chunk_latents: int, sink_latents: int) -> bool:
    """Scale this latent chunk? Only once chunk_id >= after and the sink is fully written by earlier chunks, so
    no forward of this chunk writes into the scaled slice (its new keys land at or after latent chunk_id*CHUNK)."""
    return (cfg is not None and cfg.enabled and sink_latents > 0 and chunk_id >= cfg.after
            and chunk_id * chunk_latents >= sink_latents)


def _copy(t):
    return t.clone() if hasattr(t, "clone") else t.copy()


def scale_keys(kv: list[dict], n_tokens: int, a: float, saved: list | None = None) -> list:
    """Multiply kv[b]['k'][:, :n_tokens] by a in place for every block. The original slices are appended to
    `saved` before each block is touched, so restore_keys(saved) is exact even if this raises part way."""
    saved = [] if saved is None else saved
    for blk in kv:
        orig = _copy(blk["k"][:, :n_tokens])
        saved.append(orig)
        blk["k"][:, :n_tokens] = orig * a
    return saved


def restore_keys(kv: list[dict], n_tokens: int, saved: list) -> None:
    """Write the saved original slices back (exact copy, no division)."""
    for blk, orig in zip(kv, saved):
        blk["k"][:, :n_tokens] = orig
