"""CPU-only tests for --lingbot-kv-noise (no GPU, no torch, no API calls): flag parsing, timestep snapping,
the session's KV-write inputs with a mocked torch and pipe, flags lines, and per-arm isolation under main()."""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.lingbot_world2 import flag_stats as F, kv_noise as KVN, run as R, session as S  # noqa: E402

# A hand-made descending table with a sparse low end, like the scheduler's at shift 10 (..., 29, 19, 9).
TABLE = np.array([999, 967, 908, 768, 500, 108, 99, 47, 38, 29, 19, 9], dtype=np.int64)
SIGMAS = np.append(TABLE / 1000.0, 0.0)


def _clean_env(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)


def test_parse_and_configure(monkeypatch):
    _clean_env(monkeypatch)
    flags, rest = R.configure(["run.py", "--tasks", "OE001"], environ={})
    assert flags["kv_noise"] == KVN.KVNoiseConfig(False, 25.0) and rest == ["run.py", "--tasks", "OE001"]
    for argv, t in ((["--lingbot-kv-noise"], 25.0), (["--lingbot-kv-noise", "--lingbot-kv-noise-t", "50"], 50.0),
                    (["--lingbot-kv-noise-t=10", "--lingbot-kv-noise"], 10.0)):
        flags, rest = R.configure(["run.py", *argv, "--tasks", "OE001"], environ={})
        assert flags["kv_noise"] == KVN.KVNoiseConfig(True, t) and rest == ["run.py", "--tasks", "OE001"]
    cfg, _ = KVN.parse(["run.py"], environ={"LINGBOT_KV_NOISE": "1", "LINGBOT_KV_NOISE_T": "100"})
    assert cfg == KVN.KVNoiseConfig(True, 100.0)
    for bad in (["--lingbot-kv-noise-t"], ["--lingbot-kv-noise-t=0"], ["--lingbot-kv-noise-t=-5"],
                ["--lingbot-kv-noise-t=1001"], ["--lingbot-kv-noise-t=251"], ["--lingbot-kv-noise-t=nan"], ["--lingbot-kv-noise-t=x"]):
        with pytest.raises(SystemExit):
            KVN.parse(["run.py", *bad], environ={})


def test_snap_index_picks_nearest_table_entry():
    assert TABLE[KVN.snap_index(TABLE, 25)] == 29
    assert TABLE[KVN.snap_index(TABLE, 10)] == 9
    assert TABLE[KVN.snap_index(TABLE, 1000)] == 999
    assert KVN.snap_index([30, 20], 25) == 0  # ties go to the first entry
    with pytest.raises(ValueError):
        KVN.snap_index([], 25)


# ------------------------------------------------------------ session with a mocked torch

class _T:
    def __init__(self, arr): self.arr = np.asarray(arr); self.shape, self.device, self.dtype = self.arr.shape, "cpu", "f32"
    def to(self, d): return _T(self.arr.astype(d)) if d is np.uint8 else self
    def clamp(self, lo, hi): return _T(np.clip(self.arr, lo, hi))
    def __add__(self, o): return _T(self.arr + (o.arr if isinstance(o, _T) else o))
    def __mul__(self, o): return _T(self.arr * (o.arr if isinstance(o, _T) else o))
    def round(self): return _T(np.round(self.arr))
    def permute(self, *ax): return _T(np.transpose(self.arr, ax))
    def cpu(self): return self
    def numpy(self): return self.arr


class _Gen:
    """Draws 1, 2, 3, ... (main stream) or 1001, 1002, ... (kv stream) so every draw is traceable."""
    def __init__(self, device=None): self.base, self.n, self.draws = 0, 0, []
    def manual_seed(self, s): self.seed = s; return self


def _torch(monkeypatch):
    nc = lambda *a, **kw: contextlib.nullcontext()

    def randn(*shape, generator=None, **kw):
        shape = shape[0] if isinstance(shape[0], tuple) else shape
        generator.n += 1
        generator.draws.append(generator.n)
        return _T(np.full(shape, generator.base + generator.n, dtype=np.float64))

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        amp=SimpleNamespace(autocast=nc), autocast=nc, no_grad=nc, float32="f32", uint8=np.uint8, Generator=_Gen,
        randn=randn, stack=lambda xs: _T([np.asarray(getattr(x, "arr", x)) for x in xs]),
        cat=lambda xs, dim=0: _T(np.concatenate([x.arr for x in xs], axis=dim))))


def _session(kv_noise=None):
    calls = []
    sched = SimpleNamespace(timesteps=TABLE, sigmas=SIGMAS,
                            add_noise=lambda x0, eps, t: _T(x0.arr * (1 - float(t) / 1000) + eps.arr * float(t) / 1000))

    def model(x, t, **kw):
        calls.append((float(np.asarray(t.arr).ravel()[0]), np.array(x[0].arr)))
        return [_T(np.full(x[0].shape, 0.5))]  # flow pred; x0 = pred under the identity conversion below

    pipe = SimpleNamespace(device="cpu", param_dtype="bf16", scheduler=sched, model=model,
                           _convert_flow_pred_to_x0=lambda flow_pred, **kw: flow_pred)
    sess = S.LingBotSession(pipe, 480 * 832, 5.0, stream_decode=True, **({"kv_noise": kv_noise} if kv_noise else {}))
    sess.started, sess.track, sess.y = True, S.PoseTrack(), np.zeros((20, 64, 1, 1))
    sess.lat_h = sess.lat_w = sess.frame_seqlen = 1
    sess.max_seq_len, sess.kv_size, sess.context, sess.kv, sess.cross, sess.cross_init = 4, 16, ["c"], [], [], False
    sess.gen = _Gen()
    sess.timesteps = [999, 967, 908, 768]
    sess._plucker = lambda r: SimpleNamespace(chunk=lambda *a, **kw: ("e",))
    decoded = []
    sess._decode = lambda lat: decoded.append(np.array(lat.arr)) or _T(np.zeros((3, 4 * lat.shape[1] - 3, 2, 2)))
    if kv_noise is not None:
        kv_noise.reset(sched, 42, "cpu")
        kv_noise.gen.base = 1000
    return sess, calls, decoded


def test_session_kv_write_inputs(monkeypatch, capsys):
    _torch(monkeypatch)
    off, off_calls, off_dec = _session()
    kvn = KVN.KVNoise(KVN.KVNoiseConfig(True, 25.0))
    on, on_calls, on_dec = _session(kvn)
    assert "kv-noise: t=25 -> scheduler timestep 29 (sigma 0.0290)" in capsys.readouterr().out
    assert kvn.gen.seed == 42 + KVN.SEED_OFFSET
    for sess in (off, on):
        sess.step(["none"] * 28)  # first step: 2 chunks (chunk 0 holds the input image latent)
        sess.step(["w"] * 32)     # continuation: 2 more chunks
    # the main stream is untouched: same draws, same denoising inputs, same decoded x0
    assert off.gen.draws == on.gen.draws == list(range(1, 17))  # 4 chunks x (1 start + 3 re-noise)
    assert [np.array_equal(a, b) for a, b in zip(off_dec, on_dec)] == [True, True]
    den_off = [c for i, c in enumerate(off_calls) if i % 5 != 4]
    den_on = [c for i, c in enumerate(on_calls) if i % 5 != 4]
    assert all(a[0] == b[0] and np.array_equal(a[1], b[1]) for a, b in zip(den_off, den_on))
    # KV writes: flag off always clean x0 at t=0; flag on clean for chunk 0, noised at the snapped t after
    kv_off, kv_on = off_calls[4::5], on_calls[4::5]
    assert [t for t, _ in kv_off] == [0.0] * 4 and all(np.allclose(x, 0.5) for _, x in kv_off)
    assert [t for t, _ in kv_on] == [0.0, 29.0, 29.0, 29.0] and np.allclose(kv_on[0][1], 0.5)
    for k, (_, x) in enumerate(kv_on[1:], 1):
        assert np.allclose(x, 0.5 * (1 - 0.029) + (1000 + k) * 0.029)
    assert kvn.gen.draws == [1, 2, 3] and (off.kv_noise_chunks, on.kv_noise_chunks) == (0, 3)


def test_reanchored_chunk_stays_clean(monkeypatch):
    _torch(monkeypatch)
    sess, calls, _ = _session(KVN.KVNoise())
    sess.step(["none"] * 12)
    sess._anchored.add(5)  # a latent of chunk 1 re-anchored to the input image (as _anchor_y records it)
    sess.step(["none"] * 32)
    assert [t for t, _ in calls[4::5]] == [0.0, 0.0, 29.0] and sess.kv_noise_chunks == 1


@pytest.mark.parametrize("sink, kv_ts", [(0, [0.0, 29.0, 29.0, 29.0]), (6, [0.0, 0.0, 29.0, 29.0]),
                                          (8, [0.0, 0.0, 29.0, 29.0]), (9, [0.0, 0.0, 0.0, 29.0])])
def test_sink_chunks_stay_clean(monkeypatch, sink, kv_ts):
    # sink slots are never evicted: a chunk whose latents overlap [0, sink) keeps the clean write
    _torch(monkeypatch)
    sess, calls, _ = _session(KVN.KVNoise())
    sess.pipe.sink_size = sink
    sess.step(["none"] * 28)
    sess.step(["w"] * 32)
    assert [t for t, _ in calls[4::5]] == kv_ts and sess.kv_noise_chunks == kv_ts.count(29.0)


def test_flag_stats_lines():
    off = F.FlagStats(False, "goal", False, False)
    assert "kv_noise" not in F.FlagStats.line(off.summary("OE001")) and "kv_noise" not in off.total_line()
    on = F.FlagStats(False, "goal", False, False, kv_noise="on", kv_noise_t=25.0)
    on.kv_noised(59)
    s = on.finish_task("OE001")
    assert (s["kv_noise"], s["kv_noise_t"], s["kv_noise_chunks"]) == ("on", "25", 59)
    assert "kv_noise=on kv_noise_t=25 kv_noise_chunks=59" in on.total_line()
    on.new_task()
    assert on.summary("OE002")["kv_noise_chunks"] == 0


# ------------------------------------------------------------ arms: several main() calls in one process

def test_multi_arm_main_isolation(monkeypatch, capsys):
    _clean_env(monkeypatch)
    pipe = SimpleNamespace(model=SimpleNamespace(blocks=[]), _t5_cache={})
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), pipe, Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)
    seen = []

    def fake_import(fresh=True):
        ra = SimpleNamespace(run_task=lambda task, eng, out, args: {"task_id": task["task_id"], "success": True},
                             decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")

        def run_main():
            eng = ra.SanaWMEngine(SimpleNamespace(max_total_frames=65, seed=0, fps=16))
            seen.append(None if eng.session is None else eng.session.kv_noise)
            ra.run_task({"task_id": "OE001"}, eng, Path("/tmp"), None)
        ra.main = run_main
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    outs = []
    for argv in ([], ["--lingbot-kv-noise", "--lingbot-kv-noise-t=50"], [], ["--lingbot-kv-noise", "--lingbot-stateless"], []):
        assert R.main(["run.py", *argv]) == 0
        outs.append(capsys.readouterr().out)
    assert seen[0] is None and seen[2] is None and seen[3] is None
    assert isinstance(seen[1], KVN.KVNoise) and seen[1].cfg == KVN.KVNoiseConfig(True, 50.0)
    flags = [[ln for ln in o.splitlines() if ln.startswith("[lingbot] flags")] for o in outs]
    modes = [[ln for ln in o.splitlines() if ln.startswith("[lingbot] mode:")][0] for o in outs]
    assert outs[0] == outs[2] == outs[4] and seen[4] is None
    assert "kv" not in " ".join(flags[0]) and "kv-noise" not in modes[0]
    assert flags[1][0].startswith(flags[0][0] + " ") and flags[1][0].endswith("kv_noise=on kv_noise_t=50 kv_noise_chunks=0")
    assert ", kv-noise t=50" in modes[1]
    assert "kv_noise=skip" in flags[3][0] and ", kv-noise ignored (stateless)" in modes[3]
    assert not R.KV_NOISE.enabled
