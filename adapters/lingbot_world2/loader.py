"""Load the LingBot-World v2 causal-fast pipeline (shared by run.py and probe.py).

Env: LINGBOT_ROOT, LINGBOT_WEIGHTS, LINGBOT_VARIANT (14b|1.3b), LINGBOT_T5_CPU; see run.py.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

MAX_AREA = 480 * 832  # the released checkpoints' reference resolution
LOCAL_ATTN, SINK = 18, 6  # README settings for causal-fast


def load_pipe(local_attn: int = LOCAL_ATTN, sink: int = SINK):
    """-> (pipe, cfg, variant). local_attn -1 keeps every latent in the KV cache."""
    root = os.environ.get("LINGBOT_ROOT", "/opt/lingbot")
    weights = Path(os.environ.get("LINGBOT_WEIGHTS", "/weights/lingbot"))
    variant = os.environ.get("LINGBOT_VARIANT", "14b").lower()
    if variant not in ("14b", "1.3b"):
        raise SystemExit(f"LINGBOT_VARIANT must be 14b or 1.3b, got {variant!r}")
    ckpt = weights / f"lingbot-world-v2-{variant}-causal-fast"
    # The 1.3B release ships DiT shards only; T5, VAE and tokenizer come from the 14B dir.
    assets = weights / "lingbot-world-v2-14b-causal-fast" if variant == "1.3b" else None
    for p in (Path(root) / "wan", ckpt, *([assets] if assets else [])):
        if not p.exists():
            raise SystemExit(f"[lingbot] missing {p}; set LINGBOT_ROOT / LINGBOT_WEIGHTS or run prefetch_lingbot.py")
    t5_cpu = os.environ.get("LINGBOT_T5_CPU", "1" if variant == "14b" else "0") == "1"

    if root not in sys.path:
        sys.path.insert(0, root)
    import wan  # noqa: PLC0415
    from wan.configs import WAN_CONFIGS  # noqa: PLC0415

    cfg = WAN_CONFIGS["i2v-1.3B" if variant == "1.3b" else "i2v-A14B"]
    t0 = time.time()
    pipe = wan.WanI2VCausal(
        config=cfg, checkpoint_dir=str(ckpt), device_id=0, rank=0, t5_cpu=t5_cpu,
        local_attn_size=local_attn, sink_size=sink, infer_mode="causal_fast",
        assets_dir=str(assets) if assets else None)
    print(f"[lingbot] loaded {variant} from {ckpt} in {time.time() - t0:.0f}s "
          f"(t5_cpu={t5_cpu}, local_attn={local_attn}, sink={sink})", flush=True)
    return pipe, cfg, variant


def set_window(pipe, local_attn: int, sink: int) -> None:
    """Change the KV window of a loaded pipe in place (every self-attention block reads
    its own local_attn_size / sink_size; the session sizes the cache from the pipe)."""
    pipe.local_attn_size, pipe.sink_size = local_attn, sink
    n = 0
    for m in pipe.model.modules():
        if hasattr(m, "local_attn_size") and hasattr(m, "sink_size"):
            m.local_attn_size, m.sink_size = local_attn, sink
            n += 1
    if not n:
        raise RuntimeError("no attention module exposes local_attn_size; upstream layout changed")
