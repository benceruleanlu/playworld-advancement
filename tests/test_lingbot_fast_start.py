import pickle
import types

from adapters.lingbot_world2 import fast_start as FS
from adapters.lingbot_world2 import session as S


def _pickle_save(obj, path):
    with open(path, "wb") as f:
        pickle.dump(obj, f)


def _pickle_load(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def _cache(tmp_path, **ident):
    base = {"checkpoint": {"name": "t5.pth", "size": 1}, "device": "cpu", "torch": "2.5.1"}
    return FS.EmbeddingCache(tmp_path / "cache", {**base, **ident}, save=_pickle_save, load=_pickle_load)


# ---------------------------------------------------------------- flags

def test_flags_default_off():
    f = FS.parse_flags(["run.py", "--seed", "1"], {})
    assert f == FS.FastFlags() and not (f.t5_cache or f.fast_load or f.fast_y or f.t5_gpu)
    assert f.describe() == "off"
    # unrelated env does not switch anything on
    assert FS.parse_flags([], {"LINGBOT_T5_CPU": "0", "LINGBOT_FAST_T5": "0"}) == FS.FastFlags()


def test_session_defaults_unchanged():
    sess = S.LingBotSession(object(), 480 * 832, 10.0)
    assert sess.stream_encode is False and sess.t5_cache is None


def test_each_flag_and_umbrella():
    assert FS.parse_flags(["--lingbot-fast-t5"], {}) == FS.FastFlags(t5_cache=True)
    assert FS.parse_flags(["--lingbot-fast-load"], {}) == FS.FastFlags(fast_load=True)
    assert FS.parse_flags(["--lingbot-fast-y"], {}) == FS.FastFlags(fast_y=True)
    assert FS.parse_flags(["--lingbot-t5-gpu"], {}) == FS.FastFlags(t5_gpu=True)
    assert FS.parse_flags([], {"LINGBOT_FAST_Y": "1"}) == FS.FastFlags(fast_y=True)
    both = FS.FastFlags(t5_cache=True, fast_load=True, fast_y=True, fast_dit=True)
    assert FS.parse_flags(["--lingbot-fast"], {}) == both  # umbrella excludes t5-gpu (changes outputs)
    assert FS.parse_flags([], {"LINGBOT_FAST": "1"}) == both
    assert both.describe() == "t5-cache,fast-load,fast-y,fast-dit"


def test_strip_flags_keeps_other_args():
    argv = ["run.py", "--lingbot-fast", "--seed", "3", "--lingbot-fast-y", "--lingbot-turn-cal", "--lingbot-t5-gpu"]
    assert FS.strip_flags(argv) == ["run.py", "--seed", "3", "--lingbot-turn-cal"]


# ---------------------------------------------------------------- embedding cache

def test_cache_miss_then_hit(tmp_path):
    c = _cache(tmp_path)
    assert c.get("a red door") is None and c.misses == 1
    assert c.put("a red door", ["CTX"])
    assert c.get("a red door") == ["CTX"] and c.hits == 1
    assert c.get("a blue door") is None
    assert not list((tmp_path / "cache").rglob("*.tmp*"))  # atomic write left no temp file


def test_cache_key_depends_on_prompt_and_identity(tmp_path):
    a = _cache(tmp_path)
    assert a.key("p") != a.key("q")
    assert a.key("p") == _cache(tmp_path).key("p")  # stable
    for other in ({"device": "cuda"}, {"torch": "2.6.0"}, {"checkpoint": {"name": "t5.pth", "size": 2}},
                  {"threads": 8}):
        assert _cache(tmp_path, **other).key("p") != a.key("p"), other
    a.put("p", ["CPU"])
    assert _cache(tmp_path, device="cuda").get("p") is None  # a GPU run never reads a CPU embedding


def test_cache_rejects_mismatch_and_corruption(tmp_path):
    c = _cache(tmp_path)
    c.put("p", ["X"])
    path = c.path("p")
    _pickle_save({"prompt": "other", "identity": c._ident_json, "ctx": ["X"]}, path)
    assert c.get("p") is None
    path.write_bytes(b"not a pickle")
    assert c.get("p") is None
    assert c.put("p", ["Y"]) and c.get("p") == ["Y"]


def test_cache_write_failure_is_not_fatal(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    c = FS.EmbeddingCache(blocker / "sub", {}, save=_pickle_save, load=_pickle_load)
    assert c.put("p", ["X"]) is False and c.get("p") is None


def test_t5_identity_tracks_files(tmp_path):
    ck = tmp_path / "t5.pth"
    ck.write_bytes(b"a" * 3000)
    tok = tmp_path / "tok"
    tok.mkdir()
    (tok / "tokenizer.json").write_text("{}")
    args = dict(text_len=512, dtype="torch.bfloat16", device_kind="cpu", device_name="X", torch_version="2.5.1")
    one = FS.t5_identity(ck, tok, **args)
    assert one == FS.t5_identity(ck, tok, **args)
    ck.write_bytes(b"a" * 2999 + b"b")
    assert FS.t5_identity(ck, tok, **args) != one
    (tok / "tokenizer.json").write_text('{"v": 2}')
    assert FS.t5_identity(ck, tok, **args)["tokenizer"] != one["tokenizer"]


def test_resolve_context_order(tmp_path):
    calls = []

    def compute(p):
        calls.append(p)
        return [f"ctx:{p}"]

    disk, mem = _cache(tmp_path), {}
    ctx, src = FS.resolve_context("p", mem, compute, disk, to_device=lambda c: [x + "@gpu" for x in c])
    assert (ctx, src, calls) == (["ctx:p"], "computed", ["p"])
    assert mem[FS.prompt_sha("p")] == ["ctx:p"]  # upstream's key format
    assert FS.resolve_context("p", mem, compute, disk)[1] == "memory"
    # new process: memory empty, disk hit, compute not called, value moved to device
    mem2 = {}
    ctx, src = FS.resolve_context("p", mem2, compute, disk, to_device=lambda c: [x + "@gpu" for x in c])
    assert (ctx, src, calls) == (["ctx:p@gpu"], "disk", ["p"])
    # no disk cache: plain upstream behaviour
    assert FS.resolve_context("q", {}, compute)[1] == "computed"


# ---------------------------------------------------------------- lazy T5 and load timing

def test_lazy_t5_defers_until_used():
    built = []

    class Real:
        def __init__(self, **k):
            built.append(k)
            self.model = "MODEL"

        def __call__(self, texts, device):
            return [f"{t}@{device}" for t in texts]

    lazy = FS.LazyT5(Real, text_len=512, checkpoint_path="/w/t5.pth", tokenizer_path="/w/tok", dtype="bf16")
    assert (lazy.checkpoint_path, lazy.text_len, lazy.loaded, built) == ("/w/t5.pth", 512, False, [])
    assert lazy(["hi"], "cpu") == ["hi@cpu"] and lazy.loaded and len(built) == 1
    assert lazy.model == "MODEL" and len(built) == 1


def test_install_t5_and_load_timer_patch_module(capsys):
    def real_t5(**k):
        return "T5"
    mod = types.SimpleNamespace(T5EncoderModel=real_t5, Wan2_1_VAE=lambda **k: "VAE", load_dit_model=lambda *a: "DIT")
    FS.install_t5(mod, lazy=False, fast=False)
    assert mod.T5EncoderModel is real_t5  # flags off: untouched
    FS.install_t5(mod, lazy=True, fast=False)
    timer = FS.LoadTimer(mod)
    assert isinstance(mod.T5EncoderModel(text_len=1), FS.LazyT5)
    assert mod.Wan2_1_VAE(vae_pth="x") == "VAE" and mod.load_dit_model() == "DIT"
    timer.rest(10.0)
    out = capsys.readouterr().out
    for part in ("load.t5", "load.vae", "load.dit", "load.dit_to_device_and_rest", "load.total"):
        assert f"[lingbot] timing {part} " in out
    assert "deferred" in out


def test_read_ahead_reads_every_byte(tmp_path, capsys):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"x" * 1000)
    b.write_bytes(b"y" * 2500)
    FS.read_ahead([a, b, tmp_path / "missing"], threads=3, block=512).join()
    assert "(0.0 GB in 2 files" in capsys.readouterr().out


def test_patched_loaders_restore_and_never_stack():
    i2v = types.ModuleType("i2v")
    orig = {n: (lambda *a, **k: None) for n in ("T5EncoderModel", "Wan2_1_VAE", "load_dit_model")}
    for n, f in orig.items():
        setattr(i2v, n, f)
    for _ in range(2):  # a second load in the same process sees the originals, not wrapped wrappers
        with FS.patched_loaders(i2v, lazy_t5=True, fast_load=False):
            assert i2v.load_dit_model.__wrapped__ is orig["load_dit_model"]
            assert isinstance(i2v.T5EncoderModel(text_len=512), FS.LazyT5)
        assert all(getattr(i2v, n) is f for n, f in orig.items())
    try:
        with FS.patched_loaders(i2v, lazy_t5=False, fast_load=False):
            raise RuntimeError("load failed")
    except RuntimeError:
        pass
    assert all(getattr(i2v, n) is f for n, f in orig.items())
