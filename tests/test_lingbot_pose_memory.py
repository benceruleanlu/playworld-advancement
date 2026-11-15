"""CPU-only tests for --lingbot-pose-memory (no GPU, no torch, no API calls).

The session tests run LingBotSession.step against a fake causal model whose self-attention keeps a per-block
KV cache with the same sink / rolling-window / end-index bookkeeping as the pinned upstream CausalWanSelfAttention
(re-implemented here from its behaviour): a token's key is the content of its input latent and its value the
RoPE latent position it was written at, so the tests can read which chunk sits in which slot and at what time."""
from __future__ import annotations

import contextlib
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.lingbot_world2 import flag_stats as F  # noqa: E402
from adapters.lingbot_world2 import pose_memory as PM  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import run as R  # noqa: E402
from adapters.lingbot_world2 import session as S  # noqa: E402

ON = PM.PoseMemoryConfig(enabled=True)


# ------------------------------------------------------------------ config

def test_parse_defaults_knobs_and_env():
    cfg, rest = PM.parse(["run.py", "--tasks", "OE001"], environ={})
    assert cfg == PM.PoseMemoryConfig() and not cfg.enabled and rest == ["run.py", "--tasks", "OE001"]
    cfg, rest = PM.parse(["run.py", "--lingbot-pose-memory", "--lingbot-pose-mem-deg=20", "--lingbot-pose-mem-trans",
                          "2", "--lingbot-pose-mem-latents", "8", "--lingbot-pose-mem-anchor=0", "--lingbot-pose-mem-time",
                          "recent", "--lingbot-pose-mem-fallback=keep", "--lingbot-pose-mem-tasks", "OE",
                          "--lingbot-pose-mem-max-mb", "64", "--lingbot-pose-mem-leave-deg", "70",
                          "--lingbot-pose-mem-leave-trans=6", "--x"], environ={})
    assert rest == ["run.py", "--x"]
    assert cfg == PM.PoseMemoryConfig(True, 20.0, 2.0, 70.0, 6.0, 8, 0, "recent", "keep", "OE", 64.0)
    assert cfg.chunks == 2
    assert "track" not in ON.describe() and "focus" not in ON.describe() and "rel" not in ON.describe()
    cfg2, rest2 = PM.parse(["run.py", "--lingbot-pose-memory", "--lingbot-pose-mem-track=model",
                            "--lingbot-pose-mem-focus", "16", "--lingbot-pose-mem-rel=still"], environ={})
    assert rest2 == ["run.py"] and (cfg2.track, cfg2.focus, cfg2.rel) == ("model", 16.0, "still")
    assert cfg2.describe().endswith(", track model, focus 16, rel still")
    env = {"LINGBOT_POSE_MEMORY": "1", "LINGBOT_POSE_MEM_TIME": "orig", "LINGBOT_POSE_MEM_TASKS": "GC",
           "LINGBOT_POSE_MEM_TRACK": "model", "LINGBOT_POSE_MEM_FOCUS": "12.5", "LINGBOT_POSE_MEM_REL": "current"}
    cfg, _ = PM.parse(["run.py"], environ=env)
    assert cfg.enabled and cfg.time == "orig" and cfg.tasks == "GC"
    assert (cfg.track, cfg.focus, cfg.rel) == ("model", 12.5, "current")
    assert cfg.applies("GC031_chunk_01") and not cfg.applies("OE047_full")
    assert ON.applies("OE047_full") and ON.applies("GC036_chunk_03") and not ON.applies("IF001_chunk_01")
    assert not PM.PoseMemoryConfig().applies("GC031_chunk_01")
    assert math.isclose(ON.match_overlap, 1 - 32 / PM.HFOV) and math.isclose(PM.HFOV, 79.2, abs_tol=0.05)
    assert math.isclose(PM.VFOV, 51.0, abs_tol=0.05)
    for bad in (["--lingbot-pose-mem-latents", "6"], ["--lingbot-pose-mem-latents=0"], ["--lingbot-pose-mem-deg=x"],
                ["--lingbot-pose-mem-deg=90"], ["--lingbot-pose-mem-time=later"], ["--lingbot-pose-mem-fallback=x"],
                ["--lingbot-pose-mem-tasks=("], ["--lingbot-pose-mem-max-mb=0"], ["--lingbot-pose-mem-anchor=-1"],
                ["--lingbot-pose-mem-deg"], ["--lingbot-pose-mem-deg=60"], ["--lingbot-pose-mem-deg=nan"],
                ["--lingbot-pose-mem-track=x"], ["--lingbot-pose-mem-track"], ["--lingbot-pose-mem-focus=-1"],
                ["--lingbot-pose-mem-focus=nan"], ["--lingbot-pose-mem-rel=x"], ["--lingbot-pose-mem-rel"]):
        with pytest.raises(SystemExit):
            PM.parse(["run.py", "--lingbot-pose-memory", *bad], environ={})


def test_configure_and_refusals(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    flags, rest = R.configure(["run.py", "--tasks", "OE001"], environ={})
    assert flags["pose_mem"] == PM.PoseMemoryConfig() and rest == ["run.py", "--tasks", "OE001"]
    flags, rest = R.configure(["run.py", "--lingbot-pose-memory", "--tasks", "OE001"], environ={})
    assert flags["pose_mem"] == ON and rest == ["run.py", "--tasks", "OE001"]
    flags, _ = R.configure(["run.py", "--lingbot-pose-memory", "--lingbot-pose-mem-latents", "8",
                            "--lingbot-sink-size", "10", "--lingbot-local-attn", "22"], environ={})
    assert flags["pose_mem"].latents == 8 and flags["sink"] == 10
    for bad, match in ((["--lingbot-stateless"], "session mode"), (["--lingbot-sink-size", "0"], "no-op arm"),
                       (["--lingbot-sink-size", "0", "--lingbot-local-attn", "-1"], "no-op arm"),
                       (["--lingbot-sink-size", "4"], "smaller than"),
                       (["--lingbot-pose-mem-latents", "8"], "smaller than"),
                       (["--lingbot-reanchor"], "reanchor"), (["--lingbot-sink-key-scale", "0.7"], "sink-key-scale")):
        with pytest.raises(SystemExit, match=match):
            R.configure(["run.py", "--lingbot-pose-memory", *bad], environ={})
    # knobs without the flag are stripped and leave it off; the refusals only apply with the flag
    flags, rest = R.configure(["run.py", "--lingbot-pose-mem-deg", "20", "--lingbot-stateless"], environ={})
    assert not flags["pose_mem"].enabled and rest == ["run.py"]


# ------------------------------------------------------------------ pose maths and the bank

def _yaw_pose(deg, pitch=0.0, pos=(0.0, 0.0, 0.0)):
    c2w = np.eye(4)
    c2w[:3, :3] = P._rot_y(math.radians(deg)) @ P._rot_x(math.radians(pitch))
    c2w[:3, 3] = pos
    return c2w


def test_view_angles_follow_poses_keys():
    old = P.YAW, P.PITCH
    try:
        P.YAW, P.PITCH = math.radians(1.0), math.radians(1.0)
        c2w = np.eye(4)
        for _ in range(30):
            c2w = c2w @ P.key_delta("l")
        assert np.allclose(PM.view_angles(c2w), (30.0, 0.0))  # 'l' looks right: positive yaw
        for _ in range(10):
            c2w = c2w @ P.key_delta("i")
        assert np.allclose(PM.view_angles(c2w), (30.0, 10.0), atol=1e-6)  # 'i' looks up: positive pitch
    finally:
        P.YAW, P.PITCH = old
    dyaw, dpitch, dpos, o = PM.pose_diff(_yaw_pose(170), _yaw_pose(-170, 0, (3, 0, 4)))
    assert math.isclose(dyaw, 20, abs_tol=1e-9) and abs(dpitch) < 1e-9 and math.isclose(dpos, 5)
    assert math.isclose(o, 1 - 20 / PM.HFOV)
    assert PM.overlap_of(0, 0) == 1 and PM.overlap_of(90, 0) == 0 and PM.overlap_of(0, 60) == 0


def _entry(cid, deg, nbytes=0, pos=(0.0, 0.0, 0.0)):
    return PM.Entry(cid, _yaw_pose(deg, pos=pos), None, np.eye(4)[None].repeat(4, 0), nbytes)


def test_bank_eligibility_latest_and_left():
    pm = PM.PoseMemory(ON, sink=6, local=18)
    assert pm.window == 8 and pm.slots(1) == [2]
    assert [pm.in_cache(j, 10) for j in (0, 1, 2, 7, 8, 9)] == [True, False, False, False, True, True]
    assert [pm.in_cache(1, c) for c in (3, 4, 5)] == [True, False, False]
    assert [pm.in_cache(j, 5) for j in (0, 1, 2, 3)] == [True, False, False, True]
    pm0 = PM.PoseMemory(PM.PoseMemoryConfig(True, anchor=0), sink=6, local=18)
    assert [pm0.in_cache(0, c) for c in (2, 3, 10)] == [True, False, False]
    for cid, deg in ((2, 0), (3, 90), (4, 10), (5, 0)):
        pm.add(_entry(cid, deg))
    far = [_yaw_pose(120)] * 4
    assert pm.select([_yaw_pose(0)] * 4, 10) is None  # the newest sighting has not been looked away from yet
    pm.observe(far)
    assert [e.left for e in pm.entries] == [True, False, True, True]  # 90 vs 120 is still in view
    got = pm.select([_yaw_pose(5)] * 4, 10)
    assert [m.entry.cid for m in got] == [5]  # the most recent sighting wins
    assert [m.entry.cid for m in PM.PoseMemory(PM.PoseMemoryConfig(True, latents=12), 6, 18,
                                               pm.entries).select([_yaw_pose(5)] * 4, 12)] == [5, 4, 2]
    assert pm.select([_yaw_pose(5)] * 4, 7) is None  # chunk 5 is still in chunk 7's window: it shadows 4 and 2
    assert pm.select([_yaw_pose(5)] * 4, 6) is None
    assert pm.select([_yaw_pose(50)] * 4, 10) == []  # 40+ degrees off: no match
    moved = PM.PoseMemory(ON, 6, 18, [_entry(2, 0, pos=(0, 0, 0))])
    moved.observe([_yaw_pose(0, pos=(0, 0, 9))])  # walking 9 units away counts as leaving
    assert moved.entries[0].left
    assert moved.select([_yaw_pose(0, pos=(0, 0, 5))] * 4, 9) == []  # 5 units from where it was seen
    assert [m.entry.cid for m in moved.select([_yaw_pose(0, pos=(0, 0, 3))] * 4, 9)] == [2]


def test_bank_cap_evicts_oldest():
    pm = PM.PoseMemory(PM.PoseMemoryConfig(True, max_mb=1.0), 6, 18)
    for cid in range(2, 7):
        pm.add(_entry(cid, 0, nbytes=300 * 1024))
    assert [e.cid for e in pm.entries] == [4, 5, 6] and pm.evicted == 2 and pm.nbytes <= 2 ** 20
    big = PM.PoseMemory(PM.PoseMemoryConfig(True, max_mb=1.0), 6, 18)
    big.add(_entry(2, 0, nbytes=5 * 2 ** 20))
    assert len(big.entries) == 1  # the newest entry is always kept


def test_rope_times():
    for time, want in (("sink", [2, 6]), ("orig", [40, 20]), ("recent", [20 * 4 - 8 - 4, 20 * 4 - 8 - 8])):
        pm = PM.PoseMemory(PM.PoseMemoryConfig(True, latents=8, time=time), 10, 22)
        if time == "recent":
            want = [20 * 4 - pm.window - 4, 20 * 4 - pm.window - 8]
        es = [_entry(10, 0), _entry(5, 0)]
        assert [pm.rope_latent(i, s, e, 20, 2) for i, (s, e) in enumerate(zip(pm.slots(2), es))] == want


# ------------------------------------------------------------------ fake torch, model and cache

class A(np.ndarray):
    """numpy array with the few torch tensor methods the session calls."""

    def to(self, *a, copy=False, **kw):
        return np.array(self, copy=True).view(A) if copy else self

    def clone(self):
        return np.array(self, copy=True).view(A)

    def fill_(self, v):
        self.fill(v)
        return self

    def numel(self):
        return self.size

    def element_size(self):
        return self.itemsize

    def chunk(self, n, dim=0):
        return (self,)

    def permute(self, *ax):
        return np.transpose(self, ax)

    def cpu(self):
        return self

    def numpy(self):
        return np.asarray(self)

    def float(self):
        return self


def _a(x):
    return np.asarray(x).view(A)


def _fake_torch(counter):
    nc = lambda *a, **kw: contextlib.nullcontext()  # noqa: E731

    def randn(*shape, **kw):
        shape = shape[0] if isinstance(shape[0], tuple) else shape
        counter[0] += 1
        return _a(np.full(shape, float(counter[0])))

    return SimpleNamespace(
        amp=SimpleNamespace(autocast=nc), autocast=nc, no_grad=nc, float32="f32", uint8=np.uint8, long="long",
        cuda=SimpleNamespace(is_available=lambda: False, synchronize=lambda: None),
        randn=randn, stack=lambda xs: _a(np.array([float(x) for x in xs])),
        cat=lambda xs, dim=0: _a(np.concatenate([np.asarray(x) for x in xs], axis=dim)))


def _attend(cache, k_new, v_new, start, max_att, sink_tokens):
    """Write new tokens into one block's cache the way CausalWanSelfAttention does (sink kept, older tokens rolled
    left when full) and return the slice the new tokens attend to."""
    n, size = len(k_new), cache["k"].shape[1]
    end, g, loc = start + n, int(cache["global_end_index"].item()), int(cache["local_end_index"].item())
    if end > g and n + loc > size:
        ev = n + loc - size
        roll = loc - ev - sink_tokens
        for key in ("k", "v"):
            cache[key][:, sink_tokens:sink_tokens + roll] = np.array(cache[key][:, sink_tokens + ev:sink_tokens + ev + roll])
        le = loc + end - g - ev
    else:
        le = loc + end - g
    cache["k"][:, le - n:le, 0, 0] = k_new
    cache["v"][:, le - n:le, 0, 0] = v_new
    seen = (np.array(cache["k"][0, max(0, le - max_att):le, 0, 0]), np.array(cache["v"][0, max(0, le - max_att):le, 0, 0]))
    cache["global_end_index"].fill_(end)
    cache["local_end_index"].fill_(le)
    return seen


def _session(monkeypatch, cfg=None, on=True, fs=2, sink=6, local=18, fail=None):
    counter = [0]
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(counter))
    calls = []
    sess_ref = {}

    def model(x, t, kv_cache, current_start, max_attention_size, frame_seqlen, **kw):
        sess = sess_ref["s"]
        live = kv_cache is sess.kv
        lat = np.asarray(x[0])[0, :, 0, 0]              # content of each latent
        k_new = np.repeat(lat, frame_seqlen)
        v_new = np.repeat(current_start // frame_seqlen + np.arange(len(lat)), frame_seqlen).astype(float)
        before = [(np.array(b["k"]), np.array(b["v"]), int(b["global_end_index"].item()),
                   int(b["local_end_index"].item())) for b in sess.kv]
        seen = [_attend(b, k_new, v_new, current_start, max_attention_size, sink * frame_seqlen) for b in kv_cache]
        rec = {"live": live, "start": current_start // frame_seqlen, "t": float(np.asarray(t)[0]), "seen": seen[0],
               "max_att": max_attention_size}
        if not live:  # a recompute: the live cache outside the written slots and its end indices must not move
            lo, hi = (len(seen[0][0]) - 4 * frame_seqlen), len(seen[0][0])
            rec["outside_ok"] = all(
                np.array_equal(np.delete(np.asarray(b["k"]), np.s_[lo:hi], 1), np.delete(k0, np.s_[lo:hi], 1))
                and np.array_equal(np.delete(np.asarray(b["v"]), np.s_[lo:hi], 1), np.delete(v0, np.s_[lo:hi], 1))
                and int(b["global_end_index"].item()) == g0 and int(b["local_end_index"].item()) == l0
                for b, (k0, v0, g0, l0) in zip(sess.kv, before))
            rec["slots"] = (lo // frame_seqlen, hi // frame_seqlen)
        calls.append(rec)
        if fail is not None and fail(rec, len(calls)):
            raise RuntimeError("boom")
        return x

    pipe = SimpleNamespace(device="cpu", param_dtype="bf16", sink_size=sink, local_attn_size=local, model=model,
                           _convert_flow_pred_to_x0=lambda flow_pred, **kw: flow_pred,
                           scheduler=SimpleNamespace(add_noise=lambda x0, noise, t: noise))
    sess = S.LingBotSession(pipe, 480 * 832, 5.0, stream_decode=True, **({"pose_mem": cfg} if cfg else {}))
    sess_ref["s"] = sess
    sess.started, sess.track, sess.y = True, S.PoseTrack(), _a(np.zeros((20, 1024, 1, 1)))
    sess.lat_h = sess.lat_w = 1
    sess.frame_seqlen = fs
    sess.kv_size = local * fs
    sess.kv = [{"k": _a(np.zeros((1, local * fs, 1, 1))), "v": _a(np.full((1, local * fs, 1, 1), -1.0)),
                "global_end_index": _a(np.zeros(1, dtype=np.int64)), "local_end_index": _a(np.zeros(1, dtype=np.int64))}
               for _ in range(2)]
    sess.max_seq_len, sess.context, sess.cross, sess.cross_init, sess.gen = 4 * fs, ["c"], [], False, None
    sess.timesteps = [1000.0, 750.0, 500.0, 250.0]
    sess._plucker = lambda r: _a(np.zeros(1))
    sess._decode = lambda lat: _a(np.zeros((3, 4 * lat.shape[1], 2, 2)))
    sess.pose_mem_on = on
    return sess, calls, counter


QUARTER = math.radians(90) / 16  # one 16-frame chunk turns 90 degrees


def _turn_rollout(sess, script):
    """script: one entry per chunk after the first two still chunks (0-1, the sink): 'r' turn right 90, 'b' turn back left 90,
    '.' hold. Each step is one chunk."""
    sess.step(["none"] * 28)
    for c in script:
        sess.step([{"r": "l", "b": "j", ".": "none"}[c]] * 16)


def _retrievals(out):
    return [ln.split(" (")[0].removeprefix("[lingbot] pose-mem: ") for ln in out.splitlines() if "pose-mem:" in ln]


@pytest.fixture
def quarter_turns(monkeypatch):
    monkeypatch.setattr(P, "YAW", QUARTER)


def test_flag_off_and_unmatched_task_are_identical(monkeypatch, capsys, quarter_turns):
    runs = []
    for cfg, on in ((None, False), (ON, False), (None, True)):
        sess, calls, counter = _session(monkeypatch, cfg, on)
        _turn_rollout(sess, ".rrbb...")
        runs.append((calls, counter[0], [np.array(b["k"]) for b in sess.kv], [np.array(b["v"]) for b in sess.kv]))
        assert sess.pmem is None and sess.pm_stored == sess.pm_installs == sess.pm_forwards == 0
    assert "pose-mem" not in capsys.readouterr().out
    ref = runs[0]
    for calls, n, k, v in runs[1:]:
        assert n == ref[1] and all(np.array_equal(a, b) for a, b in zip(k + v, ref[2] + ref[3]))
        assert [(c["start"], c["t"], c["seen"][0].tolist(), c["seen"][1].tolist()) for c in calls] == \
               [(c["start"], c["t"], c["seen"][0].tolist(), c["seen"][1].tolist()) for c in ref[0]]


def test_turn_away_and_back_retrieves_departure_chunk_not_before(monkeypatch, capsys, quarter_turns):
    off, off_calls, off_counter = _session(monkeypatch)
    off.pose_mem_on = False
    _turn_rollout(off, ".rrbb...")
    sess, calls, counter = _session(monkeypatch, ON)
    _turn_rollout(sess, ".rrbb...")
    out = capsys.readouterr().out
    # chunks 0-1 sink, 2 the last view of the start before turning; 3: 0->90, 4: 90->180, 5: 180->90, 6: 90->0
    assert _retrievals(out) == ["chunk 6 <- chunk 2"]
    assert "slots 2-5 rope=sink:2" in out and counter[0] == off_counter[0]  # no extra noise drawn
    first = next(i for i, c in enumerate(calls) if not c["live"])
    assert [c for c in calls[:first]] and all(
        (a["start"], a["t"], a["seen"][0].tolist()) == (b["start"], b["t"], b["seen"][0].tolist())
        for a, b in zip(calls[:first], off_calls[:first]))  # identical up to the first retrieval
    rec = calls[first]
    assert rec["outside_ok"] and rec["slots"] == (2, 6) and rec["start"] == 2 and rec["t"] == 0.0
    assert rec["max_att"] == 6 * 2
    content2 = off_calls[4 * 3 + 2]["seen"][0][-8:]  # chunk 2's clean KV write: its 4 latents x 2 tokens
    chunk2 = np.unique(content2)
    assert len(chunk2) == 1
    # every forward of chunk 6 (4 denoising + the KV write) and of chunks 7-8 attends chunk 2's content in slots 2-5,
    # at RoPE positions 2-5, with the anchor latents 0-1 untouched
    anchor_k = off_calls[4]["seen"][0][:4]
    for c in calls[first + 1:]:
        k, v = c["seen"]
        assert np.all(k[4:12] == chunk2[0]) and v[4:12].tolist() == [2, 2, 3, 3, 4, 4, 5, 5]
        assert np.array_equal(k[:4], anchor_k) and v[:4].tolist() == [0, 0, 1, 1]
    assert len(calls) == len(off_calls) + 1  # one extra forward, selection unchanged for chunks 7-8
    assert (sess.pm_installs, sess.pm_latents, sess.pm_forwards, sess.pm_stored, sess.pm_chunks) == (1, 4, 1, 10, 4)
    # the rolling window after the sink is the same as without memory
    for a, b in zip(sess.kv, off.kv):
        assert np.array_equal(np.asarray(a["k"])[:, 12:], np.asarray(b["k"])[:, 12:])
        assert int(a["global_end_index"].item()) == int(b["global_end_index"].item())
        assert int(a["local_end_index"].item()) == int(b["local_end_index"].item())


def test_latest_sighting_wins_and_fallback_restores(monkeypatch, capsys, quarter_turns):
    sess, calls, _ = _session(monkeypatch, ON)
    original = None
    sess.step(["none"] * 28)
    for i, c in enumerate(".rb..rrbb"):
        sess.step([{"r": "l", "b": "j", ".": "none"}[c]] * 16)
        if i == 2:
            original = [(np.array(b["k"][:, 4:12]), np.array(b["v"][:, 4:12])) for b in sess.kv]
    got = _retrievals(capsys.readouterr().out)
    # 3: 0->90, 4: 90->0, 5-6 at 0, 7: 0->90, 8: 90->180, 9: 180->90, 10: 90->0
    # chunk 5 recalls nothing: chunk 4 (back at 0) is in its window and shadows chunk 2
    assert got == ["chunk 7 <- chunk 3", "chunk 8 restore start sink", "chunk 10 <- chunk 6"]
    assert sess.pm_restores == 1 and sess.pm_installs == 2
    restored = next(i for i, c in enumerate(calls) if c["live"] and c["start"] == 8 * 4)
    for b_idx, (k, v) in enumerate(original):  # chunk 8's forwards see the original sink again
        assert np.array_equal(calls[restored]["seen"][0][4:12], k[0, :, 0, 0]) and \
               np.array_equal(calls[restored]["seen"][1][4:12], v[0, :, 0, 0])


def test_keep_fallback_and_dataset_mode_one_step(monkeypatch, capsys, quarter_turns):
    sess, calls, _ = _session(monkeypatch, PM.PoseMemoryConfig(True, fallback="keep"))
    # dataset mode: the whole rollout is one step; memory still acts per latent chunk inside it
    sess.step(["none"] * 28 + [k for c in ".rb..rrbb" for k in [{"r": "l", "b": "j", ".": "none"}[c]] * 16])
    assert _retrievals(capsys.readouterr().out) == ["chunk 7 <- chunk 3", "chunk 10 <- chunk 6"]


def test_newer_sighting_in_window_shadows_older(monkeypatch, capsys, quarter_turns):
    """Back-and-forth turns: the view is in the rolling window each time it comes back, so nothing is recalled."""
    sess, calls, _ = _session(monkeypatch, ON)
    _turn_rollout(sess, "....rb....")
    assert _retrievals(capsys.readouterr().out) == [] and sess.pm_installs == 0 and sess.pm_forwards == 0


def test_leave_deg_must_be_below_fov():
    with pytest.raises(SystemExit, match="field of view"):
        PM.parse(["--lingbot-pose-memory", "--lingbot-pose-mem-leave-deg", "80"], {})
    with pytest.raises(SystemExit):
        PM.parse(["--lingbot-pose-memory", "--lingbot-pose-mem-leave-deg", "79.2"], {})


class _WM:
    """Weight-mod stand-in: records the scales each forward runs at."""
    def __init__(self):
        self.cam_scale, self.text_scale, self._regime, self._base_cam = 0.25, 0.5, "static", 0.25

    def step(self, rel, third_person=False):
        self.cam_scale, self.text_scale, self._regime, self._base_cam = 1.0, 1.0, "move", 1.0
        return False


def test_recompute_uses_stored_chunk_scales_and_restores(monkeypatch, quarter_turns):
    sess, calls, _ = _session(monkeypatch, ON)
    _turn_rollout(sess, ".rrbb")
    entry = next(e for e in sess.pmem.entries if e.cid == 2)
    wm = _WM()
    sess.weight_mod = wm
    seen = []
    monkeypatch.setattr(sess, "_mem_forward", lambda *a, **k: seen.append((wm.cam_scale, wm.text_scale)))
    sess._mem_recompute(entry, 2, 2)
    assert seen == [(1.0, 1.0)]  # chunk 2's own (moving) base scales
    assert (wm.cam_scale, wm.text_scale, wm._regime, wm._base_cam) == (0.25, 0.5, "static", 0.25)


def test_recent_rope_time(monkeypatch, capsys, quarter_turns):
    sess, calls, _ = _session(monkeypatch, PM.PoseMemoryConfig(True, time="recent"))
    _turn_rollout(sess, ".rrbb")
    rec = next(c for c in calls if not c["live"])
    assert rec["start"] == 6 * 4 - 8 - 4 and "rope=recent:12" in capsys.readouterr().out



@pytest.mark.parametrize("time,refresh", [("recent", True), ("sink", False)])
def test_recent_memory_follows_the_window(monkeypatch, capsys, quarter_turns, time, refresh):
    """A memory that stays selected is recomputed at the new RoPE time each chunk with time=recent only."""
    sess, calls, _ = _session(monkeypatch, PM.PoseMemoryConfig(True, time=time))
    _turn_rollout(sess, ".rrbb")
    installed, forwards = sess._pm_installed, sess.pm_forwards
    match = PM.Match(next(e for e in sess.pmem.entries if e.cid == installed[0][0]), 0.0, 0.0, 0.0, 1.0)
    monkeypatch.setattr(sess.pmem, "select", lambda *_a: [match])
    sess._pose_mem_before(7, sess.track.latents[-4:])
    assert (sess.pm_forwards == forwards + 1) is refresh
    if refresh:
        assert sess._pm_installed == ((installed[0][0], 7 * 4 - 8 - 4),)


@pytest.mark.parametrize("when", ["recompute", "denoise"])
def test_exception_restores_original_sink(monkeypatch, when, quarter_turns):
    hit = {"n": 0}

    def fail(rec, n):
        if when == "recompute":
            return not rec["live"]
        hit["n"] += rec["live"] and rec["start"] == 24  # chunk 6 with memory installed
        return hit["n"] == 2

    ref, _, _ = _session(monkeypatch)
    ref.pose_mem_on = False
    _turn_rollout(ref, ".rrb")
    sess, calls, _ = _session(monkeypatch, ON, fail=fail)
    _turn_rollout(sess, ".rrb")
    with pytest.raises(RuntimeError, match="boom"):
        sess.step(["j"] * 16)
    for a, b in zip(sess.kv, ref.kv):  # sink slots 2-5 are the original chunk 0/1 K/V again
        assert np.array_equal(np.asarray(a["k"])[:, :12], np.asarray(b["k"])[:, :12])
        assert np.array_equal(np.asarray(a["v"])[:, :12], np.asarray(b["v"])[:, :12])
    assert sess._pm_installed == ()


def test_bank_cleared_on_reset(monkeypatch, quarter_turns):
    sess, _, _ = _session(monkeypatch, ON)
    _turn_rollout(sess, ".rrbb")
    assert sess.pmem is not None and len(sess.pmem.entries) == 7 and sess._pm_snapshot is not None
    sess._free()  # what reset() calls first
    assert sess.pmem is None and sess._pm_snapshot is None and sess._pm_installed == () and sess.pm_peak_bytes == 0
    import inspect
    assert inspect.getsource(S.LingBotSession.reset).count("self._free()") == 1


def test_two_chunk_memory_with_a_larger_sink(monkeypatch, capsys, quarter_turns):
    cfg = PM.PoseMemoryConfig(True, latents=8, anchor=2)
    sess, calls, _ = _session(monkeypatch, cfg, sink=10, local=22)
    _turn_rollout(sess, ".rb..rrbb")
    got = _retrievals(capsys.readouterr().out)
    assert got and all(c["outside_ok"] for c in calls if not c["live"])
    assert {c["slots"] for c in calls if not c["live"]} <= {(2, 6), (6, 10)}


def test_straddling_chunks_and_zero_anchor_recalled_on_immediate_turn(monkeypatch, capsys):
    """No initial wait: turning starts on frame 1. Chunk 1 (sink=6, anchor=2), chunk 2 (sink=10, anchor=2) and
    chunk 0 (anchor=0) must all be retrievable once evicted from the rolling window."""
    monkeypatch.setattr(P, "YAW", math.radians(22.5) / 16)  # 22.5 deg per 16-frame chunk; centres 11.25, 33.75, 56.25
    # Chunks 0..5 turn right to frame 92 (centres 8, 24, 40, 56, 72, 88); chunk 6 adds 8 right + 8 hold (frame 100);
    # chunks 7..12 turn left by 16 frames each, hitting centres 88, 72, 56, 40 (chunk 2), 24 (chunk 1), 8 (chunk 0).
    immediate = (["l"] * 12 + ["l"] * (16 * 5) + ["l"] * 8 + ["none"] * 8 + ["j"] * (16 * 6))

    # sink=6, anchor=2: chunk 1 (latents 4..7, straddling [2, 6)) is recalled; chunk 0 (pinned in [0, 2)) is not
    sess1, calls1, _ = _session(monkeypatch, PM.PoseMemoryConfig(True, deg=15.0), sink=6, local=18)
    sess1.step(immediate)
    got1 = _retrievals(capsys.readouterr().out)
    assert "chunk 11 <- chunk 1" in got1 and not any(g.endswith("chunk 0") for g in got1)
    assert all(c["outside_ok"] and c["slots"] == (2, 6) for c in calls1 if not c["live"])

    # sink=10, local=22, anchor=2, latents=4: chunk 2 (latents 8..11, straddling [2, 10)) and chunk 1 are recalled
    sess2, calls2, _ = _session(monkeypatch, PM.PoseMemoryConfig(True, deg=15.0, latents=4, anchor=2), sink=10, local=22)
    sess2.step(immediate)
    got2 = _retrievals(capsys.readouterr().out)
    assert "chunk 10 <- chunk 2" in got2 and "chunk 11 <- chunk 1" in got2
    assert all(c["outside_ok"] for c in calls2 if not c["live"])

    # sink=6, anchor=0: nothing pinned in [0, anchor), so chunk 0 itself is recalled into slots 0-3 on return to start
    sess0, calls0, _ = _session(monkeypatch, PM.PoseMemoryConfig(True, deg=15.0, anchor=0), sink=6, local=18)
    sess0.step(immediate)
    got0 = _retrievals(capsys.readouterr().out)
    assert "chunk 12 <- chunk 0" in got0
    assert any(c["slots"] == (0, 4) and c["outside_ok"] for c in calls0 if not c["live"])


def test_pose_mem_track_model_vs_intended_under_yaw_gain(monkeypatch, capsys, quarter_turns):
    """At yaw_gain=0.5 one chunk turns 90 deg intended but 45 deg on the model track: a continuous right pan reaches
    360 deg at chunk 6 on the intended track (180 deg model) and at chunk 10 on the model track (540 deg intended)."""
    outs = {}
    for track in ("intended", "model"):
        sess, _, _ = _session(monkeypatch, PM.PoseMemoryConfig(True, track=track))
        sess.track.yaw_gain = (0.5, 0.5)
        _turn_rollout(sess, "." + "r" * 8)  # chunks 0..2 at 0 deg; chunks 3..10 turn right continuously
        assert not np.allclose(sess.track.model_latents, sess.track.latents)
        outs[track] = _retrievals(capsys.readouterr().out)
    assert outs["intended"] == ["chunk 6 <- chunk 2", "chunk 7 <- chunk 3", "chunk 8 <- chunk 4",
                                "chunk 9 <- chunk 5", "chunk 10 <- chunk 6"]
    assert outs["model"] == ["chunk 10 <- chunk 2"]


def _orbit_pose(theta_deg: float, radius: float, yaw_bias_deg: float = 0.0) -> np.ndarray:
    """Camera on a horizontal circle around (0, 0, radius), looking at the centre (plus optional yaw_bias_deg)."""
    th = math.radians(theta_deg)
    pos = (-radius * math.sin(th), 0.0, radius * (1.0 - math.cos(th)))
    return _yaw_pose(theta_deg + yaw_bias_deg, pos=pos)


def test_focus_depth_orbit_strafe_dolly_and_rotation():
    z = 16.0
    home = _yaw_pose(0.0, pos=(0.0, 0.0, 0.0))
    orbit = _orbit_pose(40.0, z)  # camera moved > 10.9 units and turned 40 deg, still looking at (0, 0, 16)
    assert np.linalg.norm(orbit[:3, 3] - home[:3, 3]) > 10.0

    # focus=0 rejects the 3D orbit on both translation (> 4) and yaw (> 32); focus=16 matches with full overlap
    dy0, _, dpos0, o0 = PM.pose_diff(home, orbit, 0.0)
    assert dpos0 > 10.0 and dy0 == pytest.approx(40.0) and o0 < ON.match_overlap
    dy, dp, dpos, o = PM.pose_diff(home, orbit, z)
    assert (dy, dp, dpos, o) == pytest.approx((0.0, 0.0, 0.0, 1.0), abs=1e-9)

    # slightly off-centre orbit (10 deg yaw bias) still has camera centres > 10 apart, small 3D focus shift, high o
    _, _, dpos_bias, o_bias = PM.pose_diff(home, _orbit_pose(40.0, z, yaw_bias_deg=-10.0), z)
    assert 0.0 < dpos_bias < ON.trans and o_bias > ON.match_overlap

    # pure lateral strafe at fixed heading: 3D focus point shifts by exact camera translation ||pb - pa|| = 10 > trans
    strafe = _yaw_pose(0.0, pos=(10.0, 0.0, 0.0))
    _, _, dpos_s, o_s = PM.pose_diff(home, strafe, z)
    assert dpos_s == pytest.approx(10.0) and dpos_s > ON.leave_trans and o_s < 1.0

    # zoom-out dolly (-z): frustum stays centred (yb=pb=0), overlap scales by depth ratio (Z - d) / Z
    dolly_near = _yaw_pose(0.0, pos=(0.0, 0.0, -3.0))
    dy_d, dp_d, dpos_d, o_d = PM.pose_diff(home, dolly_near, z)
    assert (dy_d, dp_d, dpos_d) == pytest.approx((0.0, 0.0, 3.0)) and o_d == pytest.approx(13.0 / 16.0)
    assert o_d > ON.match_overlap
    # point behind the other camera (qz <= 0): zero overlap
    assert PM.pose_diff(home, _yaw_pose(0.0, pos=(0.0, 0.0, 20.0)), z)[3] == 0.0

    # pure rotation in place: small yaw matches, large yaw (>= 90 deg puts focus behind camera) leaves with o=0
    _, _, dpos_r, o_r = PM.pose_diff(home, _yaw_pose(10.0), z)
    assert dpos_r < ON.trans and o_r > ON.match_overlap
    assert PM.pose_diff(home, _yaw_pose(120.0), z)[3] == 0.0

    # end-to-end bank selection with focus=16: look away (strafe/turn), then revisit via 3D orbit
    cfg = PM.PoseMemoryConfig(True, focus=z)
    pm = PM.PoseMemory(cfg, sink=6, local=18)
    pm.add(PM.Entry(2, home, None, np.eye(4)[None].repeat(4, 0)))
    pm.observe([_yaw_pose(120.0)])
    assert pm.entries[0].left
    assert [m.entry.cid for m in pm.select([orbit] * 4, 8)] == [2]
    assert pm.select([strafe] * 4, 8) == []


class _RelWM:
    """Weight-mod stand-in that records the exact relative-pose array passed to step()."""
    def __init__(self):
        self.cam_scale, self.text_scale, self._regime, self._base_cam = 0.5, 1.0, "3p", 0.5
        self.rels = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def denoise_step(self, i, total):
        return self.cam_scale

    def end_chunk(self):
        self.cam_scale = self._base_cam

    def step(self, rel, third_person=False):
        self.rels.append(np.array(rel, copy=True))
        still = np.allclose(rel, np.eye(4), atol=1e-5)
        self.cam_scale, self.text_scale, self._regime = (0.0, 1.0, "static") if still else (1.0, 1.0, "move")
        self._base_cam = self.cam_scale
        return False


def test_pose_mem_rel_stored_still_and_current(monkeypatch):
    """Verify _plucker and weight_mod.step receive entry.rel (stored), I_4 (still), or rel_c (current) during
    _mem_recompute, on both a moving revisit (stored=right, still=I_4, current=left) and a stopped revisit."""
    monkeypatch.setattr(P, "YAW", math.radians(22.5) / 16)
    eye4 = np.repeat(np.eye(4)[None], 4, axis=0)
    # Chunks 0..5 turn right (+22.5 deg/chunk), chunk 6 holds, chunks 7..11 turn left (-22.5 deg/chunk): chunks 9, 10,
    # 11 match chunks 3, 2, 1 while turning left, so entry.rel (right), I_4 (still), and rel_c (left) are all distinct.
    script = ["l"] * 12 + ["l"] * (16 * 5) + ["l"] * 8 + ["none"] * 8 + ["j"] * (16 * 5)

    results = {}
    for rel_mode in ("stored", "still", "current"):
        sess, _, _ = _session(monkeypatch, PM.PoseMemoryConfig(True, deg=15.0, rel=rel_mode), sink=6, local=18)
        wm = _RelWM()
        sess.weight_mod = wm
        recompute_pluckers, recompute_wms = [], []
        orig_recompute = sess._mem_recompute

        def spy_plucker(r, _rec=recompute_pluckers):
            _rec.append(np.array(r, copy=True))
            return _a(np.zeros(1))

        def wrapped_recompute(entry, slot, rope_lat, cur_rel=None,
                              _orig=orig_recompute, _s=sess, _wm=wm, _spy=spy_plucker, _wrec=recompute_wms):
            n0, prev = len(_wm.rels), _s._plucker
            _s._plucker = _spy
            try:
                return _orig(entry, slot, rope_lat, cur_rel)
            finally:
                _s._plucker = prev
                _wrec.extend(_wm.rels[n0:])

        monkeypatch.setattr(sess, "_mem_recompute", wrapped_recompute)
        sess.step(script)
        entry1 = next(e for e in sess.pmem.entries if e.cid == 1)
        assert not np.allclose(entry1.rel, eye4)  # chunk 1 was turning right
        assert len(recompute_pluckers) == 3 and len(recompute_wms) == 3
        assert all(np.array_equal(w, p) for w, p in zip(recompute_wms, recompute_pluckers))
        results[rel_mode] = (entry1.rel, recompute_pluckers, recompute_wms, sess)

    # stored: recomputes use the stored rightward entry.rel
    e_rel, pl_stored, wm_stored, _ = results["stored"]
    assert all(np.allclose(p, e_rel) and np.allclose(w, e_rel) for p, w in zip(pl_stored, wm_stored))

    # still: recomputes use 4x I_4 (zero velocity) in both _plucker and weight_mod.step
    _, pl_still, wm_still, _ = results["still"]
    assert all(np.allclose(p, eye4) and np.allclose(w, eye4) for p, w in zip(pl_still, wm_still))

    # current: recomputes use the current chunk's leftward rel_c (opposite yaw sign to entry.rel, not I_4)
    e_rel_c, pl_cur, wm_cur, sess_cur = results["current"]
    for p, w in zip(pl_cur, wm_cur):
        assert not np.allclose(p, e_rel_c) and not np.allclose(p, eye4)
        assert np.allclose(p[:, 0, 2], -e_rel_c[:, 0, 2], atol=1e-6) and np.array_equal(p, w)

    # stopped revisit under rel=current: chunk 8 (WAIT, rel_c = I_4) matches chunk 3 (rightward, entry.rel != I_4)
    monkeypatch.setattr(P, "YAW", QUARTER)
    sess_stop, _, _ = _session(monkeypatch, PM.PoseMemoryConfig(True, rel="current"), sink=6, local=18)
    stop_pl = []
    orig_fwd = sess_stop._mem_forward
    monkeypatch.setattr(sess_stop, "_mem_forward",
                        lambda entry, views, rope_lat, slot, mem_rel=None: (
                            stop_pl.append(np.array(mem_rel, copy=True)),
                            orig_fwd(entry, views, rope_lat, slot, mem_rel))[1])
    _turn_rollout(sess_stop, ".rr.")  # chunk 3: 0->90 (centre 67.5), chunk 4: 90->180, chunk 5: hold at 180
    sess_stop.step(["l"] * 12 + ["none"] * 4)  # chunk 6: 180->247.5
    monkeypatch.setattr(P, "YAW", 2 * QUARTER)
    sess_stop.step(["j"] * 16)                 # chunk 7: 247.5->67.5 (centre 112.5, 45 deg off 67.5 -> no shadow)
    sess_stop.step(["none"] * 32)              # chunks 8..9: WAIT at 67.5 -> recalls chunk 3 once with I_4
    assert len(stop_pl) == 1 and np.allclose(stop_pl[0], eye4)

    # direct _mem_recompute without cur_rel falls back to entry.rel
    monkeypatch.setattr(sess_cur, "_mem_recompute", S.LingBotSession._mem_recompute.__get__(sess_cur))
    fallback_pl = []
    sess_cur._plucker = lambda r: (fallback_pl.append(np.array(r, copy=True)), _a(np.zeros(1)))[1]
    sess_cur._mem_recompute(next(e for e in sess_cur.pmem.entries if e.cid == 1), 2, 2)
    assert len(fallback_pl) == 1 and np.allclose(fallback_pl[0], e_rel_c)


# ------------------------------------------------------------------ counters and arm isolation

def test_flag_stats_lines():
    off = F.FlagStats(False, "goal", False, False)
    assert "pose_mem" not in F.FlagStats.line(off.summary("OE001")) and "pose_mem" not in off.total_line()
    on = F.FlagStats(False, "goal", False, False, pose_mem=True)
    on.pose_mem_armed()
    on.pose_mem_counted({"stored": 30, "installs": 2, "latents": 8, "restores": 1, "chunks": 9, "forwards": 2},
                        3 * 2 ** 20)
    s = on.finish_task("OE047")
    assert F.FlagStats.line(s).endswith(" pose_mem=on pose_mem_stored=30 pose_mem_retrievals=2 pose_mem_latents=8 "
                                        "pose_mem_restores=1 pose_mem_chunks=9 pose_mem_forwards=2 pose_mem_evicted=0 "
                                        "pose_mem_mb=3")
    on.new_task()
    assert on.finish_task("IF001")["pose_mem"] == "skip"
    assert on.total_line().endswith(" pose_mem_stored=30 pose_mem_retrievals=2 pose_mem_latents=8 pose_mem_restores=1"
                                    " pose_mem_chunks=9 pose_mem_forwards=2 pose_mem_evicted=0")


def test_multi_arm_main_isolation(monkeypatch, capsys, tmp_path):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    pipe = SimpleNamespace(model=SimpleNamespace(blocks=[]), _t5_cache={}, local_attn_size=18, sink_size=6)
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), pipe, Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)
    seen = []

    def fake_import(fresh=True):
        ra = SimpleNamespace(decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")

        def run_task(task, eng, out, args):
            if eng.session is not None:
                s = eng.session

                def step(keys, **kw):
                    if s.pose_mem_on:
                        s.pm_stored += 2
                        s.pm_installs += 1
                        s.pm_latents += 4
                        s.pm_forwards += 1
                        s.pm_peak_bytes = 5 * 2 ** 20
                    return np.zeros((29, 2, 2, 3), np.uint8)

                s.reset = lambda *a, **kw: (setattr(s, "started", True), setattr(s, "track", S.PoseTrack()),
                                            setattr(s, "pm_peak_bytes", 0))
                s.step = step
                monkeypatch.setitem(sys.modules, "imageio", SimpleNamespace(mimsave=lambda *a, **kw: None))
                monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
                    reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)))
                monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=SimpleNamespace(
                    open=lambda p: SimpleNamespace(convert=lambda m: None))))
                for i in (1, 2):
                    eng._generate_session("img.jpg", "p", "none-33", str(tmp_path), f"{task['task_id']}_chunk_{i:02d}", 33)
            return {"task_id": task["task_id"], "success": True}

        def run_main():
            eng = ra.SanaWMEngine(SimpleNamespace(max_total_frames=65, seed=0, fps=16))
            seen.append(eng.session.pose_mem if eng.session else "stateless")
            for tid in ("OE001", "IF001"):
                ra.run_task({"task_id": tid}, eng, tmp_path, None)

        ra.run_task, ra.main = run_task, run_main
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    arms = [[], ["--lingbot-pose-memory", "--lingbot-pose-mem-time", "recent"], [], []]
    outs = []
    for k, extra in enumerate(arms):
        assert R.main(["run.py", *extra]) == 0
        outs.append(capsys.readouterr().out.splitlines())
        if k == 1:  # refused arms are refused before any load and leave no state behind
            for bad in (["--lingbot-stateless"], ["--lingbot-sink-size", "0"], ["--lingbot-reanchor"]):
                with pytest.raises(SystemExit):
                    R.main(["run.py", "--lingbot-pose-memory", *bad])
    lines = [[ln for ln in o if ln.startswith("[lingbot] flags ")] for o in outs]
    modes = [[ln for ln in o if ln.startswith("[lingbot] mode:")][0] for o in outs]
    assert seen[0] is None and seen[1] == PM.PoseMemoryConfig(True, time="recent") and seen[2] is None and seen[3] is None
    assert lines[0] == lines[2] == lines[3] and modes[0] == modes[2] == modes[3]
    assert not any("pose" in ln for ln in lines[0] + [modes[0]])
    assert "pose memory 4 latents after 2 anchor" in modes[1] and "rope recent" in modes[1]
    assert lines[1][0].startswith(lines[0][0] + " ")
    assert lines[1][0].endswith("pose_mem=on pose_mem_stored=4 pose_mem_retrievals=2 pose_mem_latents=8 "
                                "pose_mem_restores=0 pose_mem_chunks=0 pose_mem_forwards=2 pose_mem_evicted=0 pose_mem_mb=5")
    assert lines[1][1].endswith("pose_mem=skip pose_mem_stored=0 pose_mem_retrievals=0 pose_mem_latents=0 "
                                "pose_mem_restores=0 pose_mem_chunks=0 pose_mem_forwards=0 pose_mem_evicted=0 pose_mem_mb=0")
    assert lines[1][2].endswith(" pose_mem_stored=4 pose_mem_retrievals=2 pose_mem_latents=8 pose_mem_restores=0 "
                                "pose_mem_chunks=0 pose_mem_forwards=2 pose_mem_evicted=0")
    assert not R.POSE_MEM.enabled
