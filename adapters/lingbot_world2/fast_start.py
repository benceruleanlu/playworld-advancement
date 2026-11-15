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
  --lingbot-fast       LINGBOT_FAST=1       all three above plus --lingbot-fast-dit.
  --lingbot-t5-gpu     LINGBOT_T5_CPU=0     run T5 on the GPU (upstream's default) instead of the
                       CPU. Embeddings differ from the CPU ones at bf16 rounding level, so this one
                       changes outputs; not part of --lingbot-fast.
  --lingbot-fast-dit   LINGBOT_FAST_DIT=1   DiT built with its parameters on the meta device and each
                       safetensors tensor copied to the GPU in its file dtype, then cast there
                       (fast_dit_loader), instead of upstream's cast on the CPU. Same values (see
                       fast_dit_loader; a 14B GPU run checked it bit-identical). Part of
                       --lingbot-fast. Falls back to the upstream loader on any error.
  --lingbot-cpu-threads[=N]  LINGBOT_CPU_THREADS=N|auto   torch.set_num_threads(N) for the process
                       (auto: the CPUs the container may use, usable_cpus()). Upstream leaves torch's
                       default, which was 1 on Modal. CPU T5 reductions may split differently, so
                       this can change embedding bits; the T5 cache identity includes the count and
                       in-memory embeddings are dropped when it changes (partition_t5_memory).
                       Not part of --lingbot-fast.
  --lingbot-dit-checksum  LINGBOT_DIT_CHECKSUM=1  after the load, log a checksum of every DiT parameter's
                       bits (dit_checksum), and with --lingbot-fast-dit compare sampled tensors with
                       a CPU cast from the file (verify_dit_sample). Diagnostics only.

Always on: one `[lingbot] cpu ...` line (cpu_report) with the CPU count, affinity, cgroup quota,
OMP/MKL env and torch's thread counts.

Everything here is torch-free at import time; torch and wan are imported inside functions.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

FLAG_ARGS = ("--lingbot-fast", "--lingbot-fast-t5", "--lingbot-fast-load", "--lingbot-fast-y", "--lingbot-t5-gpu",
             "--lingbot-fast-dit", "--lingbot-dit-checksum", "--lingbot-cpu-threads")
THREADS_ARG = "--lingbot-cpu-threads"


@dataclass(frozen=True)
class FastFlags:
    t5_cache: bool = False   # disk embedding cache + lazy T5
    fast_load: bool = False  # parallel read-ahead + meta/mmap T5 construction
    fast_y: bool = False     # streamed y encode
    t5_gpu: bool = False     # T5 on GPU (changes outputs)
    fast_dit: bool = False   # meta build + GPU-side cast of the DiT
    dit_checksum: bool = False  # log parameter checksum (+ sample verify with fast_dit)
    cpu_threads: str = ""    # "" = leave torch's default; "auto" or a count

    def describe(self) -> str:
        on = [n for n, v in (("t5-cache", self.t5_cache), ("fast-load", self.fast_load),
                             ("fast-y", self.fast_y), ("t5-gpu", self.t5_gpu), ("fast-dit", self.fast_dit),
                             ("dit-checksum", self.dit_checksum)) if v]
        if self.cpu_threads:
            on.append(f"cpu-threads={self.cpu_threads}")
        return ",".join(on) or "off"


def parse_flags(argv, environ) -> FastFlags:
    """Flags from runner args or env. Everything defaults off."""
    def on(arg, var):
        return arg in argv or environ.get(var, "0") == "1"
    umbrella = on("--lingbot-fast", "LINGBOT_FAST")
    threads = environ.get("LINGBOT_CPU_THREADS", "").strip()
    for a in argv:
        if a == THREADS_ARG:
            threads = "auto"
        elif a.startswith(THREADS_ARG + "="):
            threads = a.split("=", 1)[1].strip()
    if threads in ("0", "off"):
        threads = ""
    if threads and threads != "auto" and not (threads.isdigit() and int(threads) > 0):
        raise SystemExit(f"--lingbot-cpu-threads / LINGBOT_CPU_THREADS must be auto or a positive count, got {threads!r}")
    return FastFlags(
        t5_cache=umbrella or on("--lingbot-fast-t5", "LINGBOT_FAST_T5"),
        fast_load=umbrella or on("--lingbot-fast-load", "LINGBOT_FAST_LOAD"),
        fast_y=umbrella or on("--lingbot-fast-y", "LINGBOT_FAST_Y"),
        t5_gpu="--lingbot-t5-gpu" in argv,
        fast_dit=umbrella or on("--lingbot-fast-dit", "LINGBOT_FAST_DIT"),
        dit_checksum=on("--lingbot-dit-checksum", "LINGBOT_DIT_CHECKSUM"),
        cpu_threads=threads,
    )


def strip_flags(argv) -> list:
    return [a for a in argv if a not in FLAG_ARGS and not a.startswith(THREADS_ARG + "=")]


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
def patched_loaders(i2v, lazy_t5: bool, fast_load: bool, fast_dit_device=None, dit_threads: int = 4):
    """For one WanI2VCausal(...) load: install the T5 replacements (install_t5), the fast DiT loader
    when fast_dit_device is set (fast_dit_loader), and the timed wrappers (LoadTimer); yield the
    timer, then restore wan.image2video's original names, so a process that loads more than once
    (pwa gen-arms) never stacks wrappers."""
    saved = {n: getattr(i2v, n) for n in _LOADER_NAMES}
    try:
        install_t5(i2v, lazy=lazy_t5, fast=fast_load)
        if fast_dit_device is not None:
            i2v.load_dit_model = fast_dit_loader(i2v, i2v.load_dit_model, fast_dit_device, threads=dit_threads)
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


# ------------------------------------------------------------ CPU threads

_DEFAULT_THREADS: list = []  # torch's thread count before the first apply_cpu_threads, for later arms


def _cgroup_cpus(root: str = "/sys/fs/cgroup") -> float | None:
    """CPU quota of this container in CPUs (cgroup v2 cpu.max or v1 cfs files), None if unlimited."""
    try:
        quota, period = Path(root, "cpu.max").read_text().split()[:2]
        return None if quota == "max" else int(quota) / int(period)
    except (OSError, ValueError):
        pass
    try:
        quota = int(Path(root, "cpu", "cpu.cfs_quota_us").read_text())
        period = int(Path(root, "cpu", "cpu.cfs_period_us").read_text())
        return None if quota <= 0 else quota / period
    except (OSError, ValueError):
        return None


def _affinity() -> int | None:
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return None


def usable_cpus(cpu_count=None, affinity=None, quota=None) -> int:
    """CPUs this process may run on: affinity (else cpu_count), capped by the cgroup quota (rounded up)."""
    n = affinity or cpu_count or 1
    if quota:
        n = min(n, max(1, math.ceil(quota)))
    return max(1, n)


def cpu_report(environ=os.environ) -> dict:
    """What decides the CPU thread count; printed once per load as `[lingbot] cpu ...`."""
    import torch  # noqa: PLC0415
    cpus, aff, quota = os.cpu_count(), _affinity(), _cgroup_cpus()
    rep = {"cpu_count": cpus, "affinity": aff, "cgroup_cpus": quota, "usable": usable_cpus(cpus, aff, quota),
           "torch_threads": torch.get_num_threads(), "torch_interop_threads": torch.get_num_interop_threads()}
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        if var in environ:
            rep[var] = environ[var]
    return rep


def apply_cpu_threads(spec: str, set_threads=None, get_threads=None, usable=None) -> int:
    """--lingbot-cpu-threads: set torch's intra-op thread count ("auto" = usable_cpus(), or a count).
    With spec "" restore the count the process started with, so an arm without the flag after one
    with it (pwa gen-arms) runs as upstream. Returns the count now in effect (None when the flag
    is off and was never on: nothing touched, torch not imported)."""
    if not spec and not _DEFAULT_THREADS:
        return None
    if set_threads is None or get_threads is None:
        import torch  # noqa: PLC0415
        set_threads, get_threads = torch.set_num_threads, torch.get_num_threads
    if not _DEFAULT_THREADS:
        _DEFAULT_THREADS.append(get_threads())
    if not spec:
        if get_threads() != _DEFAULT_THREADS[0]:
            set_threads(_DEFAULT_THREADS[0])
        return get_threads()
    if spec == "auto":
        n = usable() if usable else usable_cpus(os.cpu_count(), _affinity(), _cgroup_cpus())
    else:
        n = int(spec)
    before = get_threads()
    set_threads(n)
    print(f"[lingbot] cpu threads: {before} -> {get_threads()} ({spec})", flush=True)
    return get_threads()


def thread_tag(applied):
    """The CPU thread setting T5 embeddings are computed under, from apply_cpu_threads' return value:
    None for torch's own default (never changed, or restored to it), else the count."""
    if applied is None or (_DEFAULT_THREADS and applied == _DEFAULT_THREADS[0]):
        return None
    return applied


def partition_t5_memory(pipe, tag) -> bool:
    """Keep upstream's in-memory prompt embeddings (pipe._t5_cache, keyed by prompt only) from crossing
    CPU thread settings: when `tag` differs from the one the entries were computed under, clear them, so
    an arm of pwa gen-arms with another --lingbot-cpu-threads (or back to the default) encodes at its own
    count. Returns True when entries were dropped."""
    mem = getattr(pipe, "_t5_cache", None)
    prev = getattr(pipe, "_lingbot_t5_tag", None)
    dropped = bool(mem) and prev != tag
    if dropped:
        print(f"[lingbot] t5 memory: dropped {len(mem)} embedding(s) computed under cpu threads {prev}; "
              f"now {tag}", flush=True)
        mem.clear()
    try:
        pipe._lingbot_t5_tag = tag
    except AttributeError:
        pass
    return dropped


# ------------------------------------------------------------ fast DiT load

def dit_shards(dit_dir, has_config: bool) -> list:
    """The safetensors files the upstream path reads from dit_dir: diffusers' file names when
    config.json is there (from_pretrained), else wan's _load_safetensors_state_dict names. Shards
    of an index are its weight_map values, sorted."""
    d = Path(dit_dir)
    bases = ["diffusion_pytorch_model"] if has_config else ["model", "diffusion_pytorch_model"]
    for b in bases:
        idx = d / f"{b}.safetensors.index.json"
        if idx.is_file():
            return [str(d / s) for s in sorted(set(json.loads(idx.read_text())["weight_map"].values()))]
    for b in bases:
        single = d / f"{b}.safetensors"
        if single.is_file():
            return [str(single)]
    raise FileNotFoundError(f"no safetensors weights in {d}")


@contextmanager
def _default_dtype(dtype):
    import torch  # noqa: PLC0415
    prev = torch.get_default_dtype()
    torch.set_default_dtype(dtype)
    try:
        yield
    finally:
        torch.set_default_dtype(prev)


def fast_load_dit(i2v, model_cls, checkpoint_dir, subfolder, config, torch_dtype, extra=None, *,
                  device, threads: int = 4):
    """wan's load_dit_model(...) with the same result, built faster:

    1. The module is constructed with every parameter on the meta device (accelerate's
       init_empty_weights, which diffusers' from_pretrained also uses), so no random init and no
       host allocation. Plain tensor attributes (e.g. `freqs`) are still built for real, as upstream.
       With config.json the default dtype is torch_dtype during construction, as in from_pretrained.
    2. Each shard is opened with safetensors; every tensor is copied to `device` in its file dtype
       and floating tensors are cast to torch_dtype there (`threads` shards at a time). Upstream
       casts the same tensor on the CPU, with torch's CPU thread count (1 on Modal).
    3. load_state_dict(assign=True); every parameter must come from the files (upstream's
       non-config path tolerates missing keys and keeps random init for them; here that raises,
       so the caller falls back to upstream).

    Values: fp32 -> bf16 is round-to-nearest-even on both CPU and CUDA (c10::BFloat16), so every
    finite value is the same bits; a bf16 file is not cast at all. Unexpected keys are ignored, as
    upstream does. Returns the module on `device`, eval mode, same class and config."""
    import accelerate  # noqa: PLC0415
    import torch  # noqa: PLC0415
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
    from safetensors import safe_open  # noqa: PLC0415

    extra = extra or {}
    dit_dir = i2v._resolve_dit_dir(checkpoint_dir, subfolder)
    has_config = os.path.isfile(os.path.join(dit_dir, "config.json"))
    shards = dit_shards(dit_dir, has_config)
    t0 = time.time()
    with accelerate.init_empty_weights(include_buffers=False):
        if has_config:
            with _default_dtype(torch_dtype):
                model = model_cls.from_config(model_cls.load_config(dit_dir), **extra)
        else:
            model = model_cls(**i2v._dit_kwargs_from_config(config, extra))
    want = model.state_dict()  # meta parameters (and any real buffers): names, shapes, dtypes
    t1 = time.time()

    def load_shard(path):
        out, nbytes, skipped = {}, 0, 0
        with safe_open(path, framework="pt", device="cpu") as f:
            for k in f.keys():
                if k not in want:
                    skipped += 1
                    continue
                t = f.get_tensor(k)
                if tuple(t.shape) != tuple(want[k].shape):
                    raise ValueError(f"{k}: file shape {tuple(t.shape)} != model {tuple(want[k].shape)}")
                nbytes += t.numel() * t.element_size()
                t = t.to(device)
                out[k] = t.to(torch_dtype) if t.is_floating_point() else t.to(want[k].dtype)
        return out, nbytes, skipped

    state, total, skipped = {}, 0, 0
    with ThreadPoolExecutor(max_workers=max(1, min(threads, len(shards)))) as ex:
        for out, nbytes, sk in ex.map(load_shard, shards):
            state.update(out)
            total += nbytes
            skipped += sk
    if str(device).startswith("cuda"):
        torch.cuda.synchronize(device)
    t2 = time.time()
    missing = [n for n, _ in model.named_parameters() if n not in state]
    if missing:
        raise KeyError(f"{len(missing)} parameters not in the checkpoint, e.g. {missing[:3]}")
    model.load_state_dict(state, strict=False, assign=True)
    del state
    left = [n for n, p in list(model.named_parameters()) + list(model.named_buffers()) if p.is_meta]
    if left:
        raise RuntimeError(f"{len(left)} tensors still on meta, e.g. {left[:3]}")
    if has_config:
        model.register_to_config(_name_or_path=dit_dir)
        model.eval()
    else:
        model = model.to(dtype=torch_dtype)  # upstream's last step on this path (buffers, if any)
    t3 = time.time()
    log("load.dit_fast_build", t1 - t0, "(parameters on meta)")
    log("load.dit_fast_tensors", t2 - t1, f"({total / 1e9:.1f} GB in {len(shards)} files to {device}, "
                                          f"{total / 1e6 / max(t2 - t1, 1e-9):.0f} MB/s, cast there, {threads} threads"
                                          + (f", {skipped} unexpected keys skipped)" if skipped else ")"))
    log("load.dit_fast_assign", t3 - t2)
    model._lingbot_fast_dit = {"shards": shards, "dtype": torch_dtype}
    return model


def fast_dit_loader(i2v, upstream, device, threads: int = 4):
    """A load_dit_model replacement: fast_load_dit, or upstream's loader if anything goes wrong."""
    def load(model_cls, checkpoint_dir, subfolder, config, torch_dtype, extra=None):
        try:
            return fast_load_dit(i2v, model_cls, checkpoint_dir, subfolder, config, torch_dtype, extra,
                                 device=device, threads=threads)
        except Exception as e:  # noqa: BLE001
            print(f"[lingbot] fast DiT load failed ({type(e).__name__}: {e}); using upstream loader", flush=True)
            import gc  # noqa: PLC0415
            gc.collect()
            try:
                import torch  # noqa: PLC0415
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:  # noqa: BLE001
                pass
            return upstream(model_cls, checkpoint_dir, subfolder, config, torch_dtype, extra)
    load.__wrapped__ = upstream
    return load


# ------------------------------------------------------------ DiT checks (--lingbot-dit-checksum)

def _int_dtype(element_size: int):
    import torch  # noqa: PLC0415
    return {1: torch.uint8, 2: torch.int16, 4: torch.int32, 8: torch.int64}[element_size]


def dit_checksum(model) -> tuple[str, int]:
    """sha256 over (name, shape, dtype, sum of the raw bit patterns, position-weighted sum) of every
    parameter, computed where the parameters live. Equal for bit-identical parameters; compare the
    line from a run with and one without --lingbot-fast-dit. Returns (hex, tensor count)."""
    import torch  # noqa: PLC0415
    h = hashlib.sha256()
    n = 0
    for name, p in sorted(model.named_parameters(), key=lambda kv: kv[0]):
        bits = p.detach().contiguous().reshape(-1).view(_int_dtype(p.element_size())).to(torch.int64)
        w = torch.arange(bits.numel(), device=bits.device, dtype=torch.int64) % 65521 + 1
        s1, s2 = int(bits.sum()), int((bits * w).sum())
        h.update(f"{name}|{tuple(p.shape)}|{p.dtype}|{s1}|{s2}\n".encode())
        n += 1
    return h.hexdigest(), n


def verify_dit_sample(model, shards, dtype, per_shard: int = 2) -> tuple[int, int]:
    """Compare up to `per_shard` tensors of each shard (its first and its largest) with the same
    tensor read from the file and cast on the CPU, as upstream does. Returns (bit-identical, checked)."""
    import torch  # noqa: PLC0415
    from safetensors import safe_open  # noqa: PLC0415
    params = dict(model.named_parameters())
    same = checked = 0
    for path in shards:
        with safe_open(path, framework="pt", device="cpu") as f:
            keys = [k for k in f.keys() if k in params]
            if not keys:
                continue
            size = {k: math.prod(f.get_slice(k).get_shape()) for k in keys}
            for k in list(dict.fromkeys([keys[0], max(keys, key=size.get)]))[:per_shard]:
                ref = f.get_tensor(k)
                ref = ref.to(dtype) if ref.is_floating_point() else ref
                got = params[k].detach().to("cpu")
                checked += 1
                same += int(ref.dtype == got.dtype and ref.shape == got.shape and torch.equal(
                    ref.reshape(-1).view(_int_dtype(ref.element_size())),
                    got.reshape(-1).view(_int_dtype(got.element_size()))))
    return same, checked
