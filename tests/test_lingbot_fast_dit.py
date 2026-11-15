"""--lingbot-fast-dit, --lingbot-cpu-threads, --lingbot-dit-checksum (adapters/lingbot_world2/fast_start.py).

The flag and helper tests need no torch. The loader tests build a tiny diffusers model on the CPU
and compare the fast path with diffusers' own from_pretrained bit for bit; they skip when torch,
safetensors, accelerate or diffusers are missing (CI has none of them)."""
import json
import random
import struct
import types

import pytest

from adapters.lingbot_world2 import fast_start as FS

# -- flags -----------------------------------------------------------------------


def test_new_flags_default_off_and_not_in_umbrella():
    f = FS.parse_flags([], {})
    assert (f.fast_dit, f.dit_checksum, f.cpu_threads) == (False, False, "")
    u = FS.parse_flags(["--lingbot-fast"], {})
    assert not u.fast_dit and not u.dit_checksum and u.cpu_threads == ""
    assert FS.parse_flags(["--lingbot-fast-dit"], {}).fast_dit
    assert FS.parse_flags([], {"LINGBOT_FAST_DIT": "1"}).fast_dit
    assert FS.parse_flags(["--lingbot-dit-checksum"], {}).dit_checksum


def test_cpu_threads_forms_and_strip():
    assert FS.parse_flags(["--lingbot-cpu-threads"], {}).cpu_threads == "auto"
    assert FS.parse_flags(["--lingbot-cpu-threads=12"], {}).cpu_threads == "12"
    assert FS.parse_flags([], {"LINGBOT_CPU_THREADS": "8"}).cpu_threads == "8"
    assert FS.parse_flags(["--lingbot-cpu-threads=4"], {"LINGBOT_CPU_THREADS": "8"}).cpu_threads == "4"
    assert FS.parse_flags([], {"LINGBOT_CPU_THREADS": "0"}).cpu_threads == ""
    with pytest.raises(SystemExit):
        FS.parse_flags(["--lingbot-cpu-threads=lots"], {})
    argv = ["run.py", "--tasks", "A", "--lingbot-fast-dit", "--lingbot-cpu-threads=6", "--lingbot-cpu-threads",
            "--lingbot-dit-checksum"]
    assert FS.strip_flags(argv) == ["run.py", "--tasks", "A"]
    assert FS.parse_flags(["--lingbot-fast-dit", "--lingbot-cpu-threads=6"], {}).describe() == "fast-dit,cpu-threads=6"


# -- CPU threads -----------------------------------------------------------------


def test_usable_cpus_and_cgroup(tmp_path):
    assert FS.usable_cpus(cpu_count=32, affinity=16, quota=None) == 16
    assert FS.usable_cpus(cpu_count=32, affinity=None, quota=2.5) == 3
    assert FS.usable_cpus(cpu_count=None, affinity=None, quota=0.125) == 1
    (tmp_path / "cpu.max").write_text("800000 100000\n")
    assert FS._cgroup_cpus(str(tmp_path)) == 8.0
    (tmp_path / "cpu.max").write_text("max 100000\n")
    assert FS._cgroup_cpus(str(tmp_path)) is None
    assert FS._cgroup_cpus(str(tmp_path / "missing")) is None


def test_apply_cpu_threads_sets_and_restores(monkeypatch):
    monkeypatch.setattr(FS, "_DEFAULT_THREADS", [])
    state = {"n": 1}

    def set_t(n):
        state["n"] = n

    def get_t():
        return state["n"]

    assert FS.apply_cpu_threads("") is None and FS._DEFAULT_THREADS == []  # off and never on: untouched
    assert FS.apply_cpu_threads("auto", set_t, get_t, usable=lambda: 16) == 16
    assert FS.apply_cpu_threads("4", set_t, get_t) == 4
    assert FS.apply_cpu_threads("", set_t, get_t) == 1  # a later arm without the flag runs as upstream


# -- shard listing ---------------------------------------------------------------


def test_dit_shards(tmp_path):
    d = tmp_path / "transformers"
    d.mkdir()
    (d / "diffusion_pytorch_model.safetensors.index.json").write_text(json.dumps(
        {"weight_map": {"a": "s-00002.safetensors", "b": "s-00001.safetensors", "c": "s-00002.safetensors"}}))
    assert FS.dit_shards(d, has_config=True) == [str(d / "s-00001.safetensors"), str(d / "s-00002.safetensors")]
    e = tmp_path / "root"
    e.mkdir()
    (e / "model.safetensors").write_bytes(b"")
    assert FS.dit_shards(e, has_config=False) == [str(e / "model.safetensors")]
    with pytest.raises(FileNotFoundError):
        FS.dit_shards(e, has_config=True)  # diffusers never reads model.safetensors


def test_fast_dit_loader_falls_back(tmp_path, capsys):
    calls = []

    def upstream(*a):
        calls.append(a)
        return "upstream-model"

    i2v = types.SimpleNamespace(_resolve_dit_dir=lambda c, s: str(tmp_path))  # no weights there
    load = FS.fast_dit_loader(i2v, upstream, device="cpu")
    assert load.__wrapped__ is upstream
    assert load("cls", str(tmp_path), "transformers", None, "bf16", {"k": 1}) == "upstream-model"
    assert calls == [("cls", str(tmp_path), "transformers", None, "bf16", {"k": 1})]
    assert "fast DiT load failed" in capsys.readouterr().out


def test_patched_loaders_installs_fast_dit_and_restores():
    i2v = types.ModuleType("i2v")
    orig = {n: (lambda *a, **k: None) for n in ("T5EncoderModel", "Wan2_1_VAE", "load_dit_model")}
    for n, f in orig.items():
        setattr(i2v, n, f)
    with FS.patched_loaders(i2v, lazy_t5=False, fast_load=False, fast_dit_device="cuda:0"):
        timed = i2v.load_dit_model
        assert timed.__wrapped__.__wrapped__ is orig["load_dit_model"]  # timer -> fast loader -> upstream
    assert all(getattr(i2v, n) is f for n, f in orig.items())


# -- fp32 -> bf16 rounding (what CUDA's __float2bfloat16_rn also does) ------------


def _rne_bf16_bits(x: float) -> int:
    u = struct.unpack("<I", struct.pack("<f", x))[0]
    if (u & 0x7F800000) == 0x7F800000 and (u & 0x7FFFFF):
        return None  # NaN: payload not compared
    return ((u + 0x7FFF + ((u >> 16) & 1)) >> 16) & 0xFFFF


def test_cpu_cast_is_round_to_nearest_even():
    torch = pytest.importorskip("torch")
    rnd = random.Random(0)
    bits = [rnd.getrandbits(32) for _ in range(20000)]
    bits += [0x3F808000, 0x3F818000, 0x3F80FFFF, 0x7F7FFFFF, 0x00008000, 0x00018000, 0x80000000, 0x7F800000]
    vals = [struct.unpack("<f", struct.pack("<I", b))[0] for b in bits]
    t = torch.tensor(vals, dtype=torch.float32).to(torch.bfloat16).view(torch.int16)
    got = [int(v) & 0xFFFF for v in t.tolist()]
    for v, g in zip(vals, got):
        ref = _rne_bf16_bits(v)
        if ref is not None:
            assert g == ref


# -- the loader against diffusers' from_pretrained (CPU) -----------------------


def _tiny_model_cls():
    torch = pytest.importorskip("torch")
    pytest.importorskip("safetensors")
    pytest.importorskip("accelerate")
    pytest.importorskip("diffusers")
    from diffusers.configuration_utils import ConfigMixin, register_to_config
    from diffusers.models.modeling_utils import ModelMixin
    nn = torch.nn

    class Tiny(ModelMixin, ConfigMixin):
        @register_to_config
        def __init__(self, dim=8, layers=3, window=-1, sink=0):
            super().__init__()
            self.window, self.sink = window, sink
            self.blocks = nn.ModuleList([nn.Linear(dim, dim) for _ in range(layers)])
            self.norm = nn.LayerNorm(dim)
            self.modulation = nn.Parameter(torch.randn(1, 6, dim) / dim ** 0.5)
            self.freqs = torch.polar(torch.ones(4, 2, dtype=torch.float64),
                                     torch.arange(8, dtype=torch.float64).view(4, 2))  # plain attribute
            for b in self.blocks:
                nn.init.xavier_uniform_(b.weight)

    return torch, Tiny


def _fill(torch, model, seed=1):
    g = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for p in model.parameters():
            p.copy_(torch.randn(p.shape, generator=g) * 3)  # fp32 values that need rounding


def _bits_equal(torch, a, b):
    return a.dtype == b.dtype and a.shape == b.shape and torch.equal(a.view(torch.int16), b.view(torch.int16))


def test_fast_load_matches_from_pretrained_bitwise(tmp_path):
    torch, Tiny = _tiny_model_cls()
    src = Tiny(dim=8, layers=3)
    _fill(torch, src)
    ckpt = tmp_path / "ckpt"
    src.save_pretrained(ckpt / "transformers", safe_serialization=True, max_shard_size="1KB")  # fp32, sharded
    assert len(list((ckpt / "transformers").glob("*.safetensors"))) > 1

    extra = {"window": 18, "sink": 6}
    ref = Tiny.from_pretrained(str(ckpt / "transformers"), torch_dtype=torch.bfloat16, **extra)
    i2v = types.SimpleNamespace(_resolve_dit_dir=lambda c, s: str(ckpt / s))
    fast = FS.fast_load_dit(i2v, Tiny, str(ckpt), "transformers", None, torch.bfloat16, extra, device="cpu")

    rp, fp = dict(ref.named_parameters()), dict(fast.named_parameters())
    assert rp.keys() == fp.keys()
    assert all(_bits_equal(torch, rp[k], fp[k]) for k in rp)
    assert torch.equal(ref.freqs, fast.freqs) and ref.freqs.dtype == fast.freqs.dtype
    assert (fast.window, fast.sink) == (18, 6) and dict(fast.config) == dict(ref.config)
    assert not fast.training and type(fast) is Tiny
    assert FS.dit_checksum(ref) == FS.dit_checksum(fast)
    same, checked = FS.verify_dit_sample(fast, fast._lingbot_fast_dit["shards"], torch.bfloat16)
    assert checked > 0 and same == checked
    with torch.no_grad():
        fast.blocks[0].weight.view(-1)[0] += 1
    assert FS.dit_checksum(ref) != FS.dit_checksum(fast)
    same, checked = FS.verify_dit_sample(fast, fast._lingbot_fast_dit["shards"], torch.bfloat16, per_shard=8)
    assert checked > same  # the changed tensor is caught


def test_fast_load_no_config_matches_upstream_steps(tmp_path):
    """wan's non-config path (the 1.3B layout): build fp32, load_state_dict(strict=False), .to(bf16)."""
    torch, Tiny = _tiny_model_cls()
    from safetensors.torch import save_file
    src = Tiny(dim=8, layers=2)
    _fill(torch, src, seed=2)
    sd = {k: v.contiguous() for k, v in src.state_dict().items()}
    (tmp_path / "model.safetensors").write_bytes(b"")
    save_file(sd, str(tmp_path / "model.safetensors"))

    ref = Tiny(dim=8, layers=2)
    ref.load_state_dict(sd, strict=False)
    ref = ref.to(dtype=torch.bfloat16)
    i2v = types.SimpleNamespace(_resolve_dit_dir=lambda c, s: c,
                                _dit_kwargs_from_config=lambda cfg, extra: dict(cfg, **(extra or {})))
    fast = FS.fast_load_dit(i2v, Tiny, str(tmp_path), "transformers", {"dim": 8, "layers": 2}, torch.bfloat16,
                            None, device="cpu")
    rp, fp = dict(ref.named_parameters()), dict(fast.named_parameters())
    assert rp.keys() == fp.keys() and all(_bits_equal(torch, rp[k], fp[k]) for k in rp)


def test_fast_load_missing_parameter_raises(tmp_path):
    torch, Tiny = _tiny_model_cls()
    from safetensors.torch import save_file
    src = Tiny(dim=8, layers=2)
    sd = {k: v.contiguous() for k, v in src.state_dict().items() if k != "norm.bias"}
    save_file(sd, str(tmp_path / "model.safetensors"))
    i2v = types.SimpleNamespace(_resolve_dit_dir=lambda c, s: c,
                                _dit_kwargs_from_config=lambda cfg, extra: dict(cfg, **(extra or {})))
    with pytest.raises(KeyError, match="norm.bias"):
        FS.fast_load_dit(i2v, Tiny, str(tmp_path), "x", {"dim": 8, "layers": 2}, torch.bfloat16, None, device="cpu")
