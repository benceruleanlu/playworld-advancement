"""Start-up cost of a LingBot run: always-on timing lines and opt-in fast paths (all off by default).

Timing (always on, no behaviour change): one `[lingbot] timing <part> <seconds>s ...` line per
load component (import, T5, VAE, DiT, DiT .to(device) and the rest of the pipeline __init__) and,
in session mode, per part of each reset and of the first step after it (text encode, y encode,
first DiT forward, remaining denoise, decode, copy to host).

Opt-in flags (runner args, stripped from argv before run_agent parses it, or env):

  --lingbot-fast-t5    LINGBOT_FAST_T5=1    prompt-embedding cache on disk (EmbeddingCache, under
                       LINGBOT_T5_CACHE_DIR, default $LINGBOT_WEIGHTS/t5_cache) and T5 is not
                       loaded at start-up: it loads on the first prompt the cache does not hold.
  --lingbot-fast-load  LINGBOT_FAST_LOAD=1  read the checkpoint files ahead in parallel threads
                       (page cache) while the pipeline loads, and build T5 on the meta device and
                       load its state dict with mmap + assign, skipping upstream's fp32 random init.
  --lingbot-fast-y     LINGBOT_FAST_Y=1     session mode: encode the image conditioning `y` only as
                       far as the rollout has got, streaming the VAE encoder's causal cache,
                       instead of the full horizon (~1000 frames for 961) on every reset.
  --lingbot-fast       LINGBOT_FAST=1       all three above.
  --lingbot-t5-gpu     LINGBOT_T5_CPU=0     run T5 on the GPU (upstream's default) instead of the
                       CPU. Embeddings differ from the CPU ones at bf16 rounding level, so this one
                       changes outputs; not part of --lingbot-fast.

Everything here is torch-free at import time; torch and wan are imported inside functions.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

FLAG_ARGS = ("--lingbot-fast", "--lingbot-fast-t5", "--lingbot-fast-load", "--lingbot-fast-y", "--lingbot-t5-gpu")


@dataclass(frozen=True)
class FastFlags:
    t5_cache: bool = False   # disk embedding cache + lazy T5
    fast_load: bool = False  # parallel read-ahead + meta/mmap T5 construction
    fast_y: bool = False     # streamed y encode
    t5_gpu: bool = False     # T5 on GPU (changes outputs)

    def describe(self) -> str:
        on = [n for n, v in (("t5-cache", self.t5_cache), ("fast-load", self.fast_load),
                             ("fast-y", self.fast_y), ("t5-gpu", self.t5_gpu)) if v]
        return ",".join(on) or "off"


def parse_flags(argv, environ) -> FastFlags:
    """Flags from runner args or env. Everything defaults off."""
    def on(arg, var):
        return arg in argv or environ.get(var, "0") == "1"
    umbrella = on("--lingbot-fast", "LINGBOT_FAST")
    return FastFlags(
        t5_cache=umbrella or on("--lingbot-fast-t5", "LINGBOT_FAST_T5"),
        fast_load=umbrella or on("--lingbot-fast-load", "LINGBOT_FAST_LOAD"),
        fast_y=umbrella or on("--lingbot-fast-y", "LINGBOT_FAST_Y"),
        t5_gpu="--lingbot-t5-gpu" in argv,
    )


def strip_flags(argv) -> list:
    return [a for a in argv if a not in FLAG_ARGS]


def log(part: str, seconds: float, extra: str = "") -> None:
    print(f"[lingbot] timing {part} {seconds:.2f}s" + (f" {extra}" if extra else ""), flush=True)


# ------------------------------------------------------------ load timing

class LoadTimer:
    """Patches wan.image2video's T5EncoderModel / Wan2_1_VAE / load_dit_model names with timed
    wrappers (same objects returned). `rest(total)` prints the part of WanI2VCausal.__init__ not
    covered by them: mostly the DiT's .to(device)."""

    def __init__(self, i2v):
        self.spent = 0.0
        for name, part in (("T5EncoderModel", "load.t5"), ("Wan2_1_VAE", "load.vae"), ("load_dit_model", "load.dit")):
            setattr(i2v, name, self._wrap(getattr(i2v, name), part))

    def _wrap(self, fn, part):
        def wrapper(*a, **k):
            t0 = time.time()
            out = fn(*a, **k)
            dt = time.time() - t0
            self.spent += dt
            log(part, dt, "(deferred: loads on first cache miss)" if isinstance(out, LazyT5) else "")
            return out
        wrapper.__wrapped__ = fn
        return wrapper

    def rest(self, total: float) -> None:
        log("load.dit_to_device_and_rest", max(0.0, total - self.spent))
        log("load.total", total)


# ------------------------------------------------------------ lazy / fast T5

class LazyT5:
    """Stands in for wan.modules.t5.T5EncoderModel until it is needed: calling it, or touching
    any attribute the real one has (e.g. `.model`), loads it. checkpoint_path, tokenizer_path,
    text_len and dtype are known up front so the cache identity never forces a load."""

    def __init__(self, factory, **kwargs):
        self._factory, self._kwargs, self._real = factory, kwargs, None
        self._lock = threading.Lock()
        self.checkpoint_path = kwargs.get("checkpoint_path")
        self.tokenizer_path = kwargs.get("tokenizer_path")
        self.text_len = kwargs.get("text_len")
        self.dtype = kwargs.get("dtype")

    @property
    def loaded(self) -> bool:
        return self._real is not None

    def load(self):
        with self._lock:
            if self._real is None:
                t0 = time.time()
                self._real = self._factory(**self._kwargs)
                log("load.t5_lazy", time.time() - t0)
        return self._real

    def __call__(self, texts, device):
        return self.load()(texts, device)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.load(), name)


def fast_t5_encoder(text_len, dtype=None, device=None, checkpoint_path=None, tokenizer_path=None, shard_fn=None):
    """Same object as upstream T5EncoderModel(...) (its own class and __call__), built without
    upstream's fp32 random init of ~5.7B params: model on the meta device, state dict loaded with
    mmap and assign=True, cast to `dtype`, made contiguous. Parameter values equal upstream's
    (upstream copies the same checkpoint tensors into `dtype` params). Falls back to upstream on
    any error or with shard_fn."""
    import torch  # noqa: PLC0415
    from wan.modules import t5 as T  # noqa: PLC0415

    dtype = dtype or torch.bfloat16
    device = device if device is not None else torch.device("cpu")
    upstream = T.T5EncoderModel
    if shard_fn is not None:
        return upstream(text_len=text_len, dtype=dtype, device=device, checkpoint_path=checkpoint_path,
                        tokenizer_path=tokenizer_path, shard_fn=shard_fn)
    try:
        t0 = time.time()
        model = T.umt5_xxl(encoder_only=True, return_tokenizer=False, dtype=dtype, device="meta")
        model = model.eval().requires_grad_(False)
        t1 = time.time()
        state = torch.load(checkpoint_path, map_location="cpu", mmap=True, weights_only=True)
        model.load_state_dict(state, assign=True)  # strict: every parameter comes from the file
        model = model.to(dtype=dtype)
        for p in model.parameters():
            if not p.is_contiguous():
                p.data = p.data.contiguous()
        for name, b in model.named_buffers():
            if b.is_meta:
                raise RuntimeError(f"buffer {name} still on meta")
        model.requires_grad_(False)
        model.to(device)
        t2 = time.time()
        enc = object.__new__(upstream)
        enc.text_len, enc.dtype, enc.device = text_len, dtype, device
        enc.checkpoint_path, enc.tokenizer_path = checkpoint_path, tokenizer_path
        enc.model = model
        enc.tokenizer = T.HuggingfaceTokenizer(name=tokenizer_path, seq_len=text_len, clean="whitespace")
        log("load.t5_fast", time.time() - t0, f"(meta build {t1 - t0:.2f}s, mmap load {t2 - t1:.2f}s)")
        return enc
    except Exception as e:  # noqa: BLE001
        print(f"[lingbot] fast T5 load failed ({type(e).__name__}: {e}); using upstream loader", flush=True)
        return upstream(text_len=text_len, dtype=dtype, device=device, checkpoint_path=checkpoint_path,
                        tokenizer_path=tokenizer_path)


def install_t5(i2v, lazy: bool, fast: bool) -> None:
    """Replace wan.image2video.T5EncoderModel (call before WanI2VCausal(...) and before LoadTimer)."""
    if not (lazy or fast):
        return
    base = (lambda **k: fast_t5_encoder(**k)) if fast else i2v.T5EncoderModel
    if lazy:
        def factory(**k):
            return LazyT5(base, **k)
        i2v.T5EncoderModel = factory
    else:
        i2v.T5EncoderModel = base


_LOADER_NAMES = ("T5EncoderModel", "Wan2_1_VAE", "load_dit_model")


@contextmanager
def patched_loaders(i2v, lazy_t5: bool, fast_load: bool):
    """For one WanI2VCausal(...) load: install the T5 replacements (install_t5) and the timed
    wrappers (LoadTimer), yield the timer, then restore wan.image2video's original names, so a
    process that loads more than once (pwa gen-arms) never stacks wrappers."""
    saved = {n: getattr(i2v, n) for n in _LOADER_NAMES}
    try:
        install_t5(i2v, lazy=lazy_t5, fast=fast_load)
        yield LoadTimer(i2v)
    finally:
        for n, v in saved.items():
            setattr(i2v, n, v)


# ------------------------------------------------------------ read-ahead

def read_ahead(paths, threads: int = 8, block: int = 64 << 20) -> threading.Thread:
    """Read `paths` (in order) into the OS page cache with `threads` parallel readers, in a daemon
    thread; returns it. The data is discarded; later loads of the same files hit the cache.
    Prints one timing line when done."""
    files = [Path(p) for p in paths if p and Path(p).is_file()]

    def run():
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
        t0 = time.time()
        ranges = [(f, off) for f in files for off in range(0, f.stat().st_size, block)]
        local = threading.local()

        def read(job):
            f, off = job
            buf = getattr(local, "buf", None)
            if buf is None:
                buf = local.buf = bytearray(block)
            with open(f, "rb", buffering=0) as fh:
                fh.seek(off)
                return fh.readinto(buf) or 0
        try:
            with ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
                total = sum(ex.map(read, ranges))
        except Exception as e:  # noqa: BLE001
            print(f"[lingbot] read-ahead stopped: {type(e).__name__}: {e}", flush=True)
            return
        dt = time.time() - t0
        log("load.read_ahead", dt, f"({total / 1e9:.1f} GB in {len(files)} files, "
                                    f"{total / 1e6 / max(dt, 1e-9):.0f} MB/s, {threads} threads; overlaps the load)")

    th = threading.Thread(target=run, name="lingbot-read-ahead", daemon=True)
    th.start()
    return th


def checkpoint_files(cfg, ckpt, assets, include_t5: bool) -> list:
    """Files WanI2VCausal reads, in its load order (T5, VAE, DiT shards), via upstream's resolvers."""
    from wan.image2video import _resolve_asset_path, _resolve_dit_dir  # noqa: PLC0415
    out = []
    names = ([cfg.t5_checkpoint] if include_t5 else []) + [cfg.vae_checkpoint]
    for n in names:
        try:
            out.append(_resolve_asset_path(n, str(ckpt), str(assets) if assets else None))
        except FileNotFoundError:
            pass
    dit = Path(_resolve_dit_dir(str(ckpt), cfg.fast_checkpoint))
    out += sorted(str(p) for p in dit.glob("*.safetensors"))
    return out


# ------------------------------------------------------------ embedding cache

def prompt_sha(prompt: str) -> str:
    """Upstream's in-memory key (WanI2VCausal._t5_cache)."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _file_digest(path, edge: int = 1 << 20) -> dict:
    """Cheap identity of a large file: name, size and sha256 of its first and last `edge` bytes."""
    p = Path(path)
    size = p.stat().st_size
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read(edge))
        if size > edge:
            f.seek(max(edge, size - edge))
            h.update(f.read(edge))
    return {"name": p.name, "size": size, "edges_sha256": h.hexdigest()}


def _dir_digest(path) -> dict:
    p = Path(path)
    if not p.is_dir():
        return {"name": p.name}
    h = hashlib.sha256()
    for f in sorted(q for q in p.rglob("*") if q.is_file()):
        h.update(f"{f.relative_to(p)}:{f.stat().st_size}\n".encode())
        if f.stat().st_size <= (4 << 20):
            h.update(f.read_bytes())
    return {"name": p.name, "files_sha256": h.hexdigest()}


def t5_identity(checkpoint_path, tokenizer_path, text_len, dtype, device_kind: str, device_name: str,
                torch_version: str, num_threads: int | None = None) -> dict:
    """Everything that decides the bits T5 produces for a prompt: checkpoint and tokenizer files,
    text_len, dtype, torch version, and where it runs (cpu model + thread count, or GPU name)."""
    ident = {
        "checkpoint": _file_digest(checkpoint_path),
        "tokenizer": _dir_digest(tokenizer_path),
        "text_len": int(text_len),
        "dtype": str(dtype),
        "device": device_kind,
        "device_name": device_name,
        "torch": torch_version,
    }
    if num_threads is not None:
        ident["threads"] = int(num_threads)
    return ident


def cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    import platform  # noqa: PLC0415
    return platform.processor() or platform.machine()


def _torch_save(obj, path):
    import torch  # noqa: PLC0415
    obj = dict(obj, ctx=[t.detach().to("cpu").clone() for t in obj["ctx"]])  # clone: drop the 512-token storage
    torch.save(obj, path)


def _torch_load(path):
    import torch  # noqa: PLC0415
    return torch.load(path, map_location="cpu", weights_only=True)


class EmbeddingCache:
    """Prompt -> T5 output (a list of [L, 4096] tensors, as T5EncoderModel.__call__ returns), on
    disk at root/<k[:2]>/<k>.pt with k = sha256(prompt + identity). The stored tensors are the
    ones T5 returned, moved to CPU with dtype and values unchanged. A file whose stored prompt or
    identity does not match, or that fails to load, is a miss. Writes are atomic (tmp + rename);
    a write failure is logged and ignored."""

    def __init__(self, root, identity: dict, save=_torch_save, load=_torch_load):
        self.root = Path(root)
        self.identity = identity
        self._ident_json = json.dumps(identity, sort_keys=True)
        self._save, self._load = save, load
        self.hits = self.misses = 0

    def key(self, prompt: str) -> str:
        return hashlib.sha256(json.dumps({"prompt": prompt, "identity": self._ident_json},
                                         sort_keys=True).encode("utf-8")).hexdigest()

    def path(self, prompt: str) -> Path:
        k = self.key(prompt)
        return self.root / k[:2] / f"{k}.pt"

    def get(self, prompt: str):
        p = self.path(prompt)
        if not p.is_file():
            self.misses += 1
            return None
        try:
            obj = self._load(p)
            if obj.get("prompt") != prompt or obj.get("identity") != self._ident_json:
                raise ValueError("stored prompt/identity mismatch")
            ctx = list(obj["ctx"])
        except Exception as e:  # noqa: BLE001
            print(f"[lingbot] t5 cache: unreadable {p.name} ({type(e).__name__}: {e}); recomputing", flush=True)
            self.misses += 1
            return None
        self.hits += 1
        return ctx

    def put(self, prompt: str, ctx) -> bool:
        p = self.path(prompt)
        tmp = p.with_name(f"{p.name}.tmp{os.getpid()}")
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            self._save({"prompt": prompt, "identity": self._ident_json, "ctx": list(ctx)}, tmp)
            os.replace(tmp, p)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[lingbot] t5 cache: could not write {p} ({type(e).__name__}: {e})", flush=True)
            try:
                tmp.unlink()
            except OSError:
                pass
            return False


def resolve_context(prompt: str, mem: dict, compute, disk: EmbeddingCache | None = None,
                    to_device=lambda ctx: ctx):
    """T5 context for `prompt`: upstream's in-memory dict first (key prompt_sha), then the disk
    cache, then `compute(prompt)` (written to disk). Returns (ctx, source) with source in
    memory | disk | computed. `mem` ends up holding the device-resident ctx, as upstream's does."""
    k = prompt_sha(prompt)
    if k in mem:
        return mem[k], "memory"
    if disk is not None:
        ctx = disk.get(prompt)
        if ctx is not None:
            mem[k] = to_device(ctx)
            return mem[k], "disk"
    ctx = compute(prompt)
    if disk is not None:
        disk.put(prompt, ctx)
    mem[k] = ctx
    return ctx, "computed"
