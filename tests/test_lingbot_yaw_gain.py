"""CPU-only tests for --lingbot-yaw-gain (no GPU, no torch, no API calls)."""
from __future__ import annotations

import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.lingbot_world2 import flag_stats as F, poses as P, run as R, session as S, yaw_gain as YG  # noqa: E402


def _yaw_deg(c2w) -> float:
    """Signed yaw of a pure-yaw rotation, right positive."""
    return math.degrees(math.atan2(c2w[0, 2], c2w[0, 0]))


def test_parse_and_configure():
    flags, rest = R.configure(["run.py", "--tasks", "GC031"], environ={})
    assert flags["yaw_gain"] == YG.YawGain() and not flags["yaw_gain"].enabled and rest == ["run.py", "--tasks", "GC031"]
    flags, rest = R.configure(["run.py", "--lingbot-turn-cal", "--lingbot-yaw-gain", "1.25", "--tasks", "GC031"],
                              environ={})
    assert flags["yaw_gain"] == YG.YawGain(True, 1.25, 1.25) and rest == ["run.py", "--tasks", "GC031"]
    g, rest = YG.parse(["run.py", "--lingbot-yaw-gain=1.2", "--lingbot-yaw-gain-right", "0.9"], environ={})
    assert g == YG.YawGain(True, 1.2, 0.9) and rest == ["run.py"] and g.tag() == "1.2/0.9"
    g, _ = YG.parse(["run.py", "--lingbot-yaw-gain-left=1.1"], environ={})
    assert (g.left, g.right) == (1.1, 1.0)
    g, _ = YG.parse(["run.py"], environ={"LINGBOT_YAW_GAIN": "0.8", "LINGBOT_YAW_GAIN_LEFT": "0.7"})
    assert g == YG.YawGain(True, 0.7, 0.8) and g.describe() == "yaw gain left 0.7 right 0.8"
    g, _ = YG.parse(["run.py", "--lingbot-yaw-gain", "1.5"], environ={"LINGBOT_YAW_GAIN": "0.8"})
    assert (g.left, g.right) == (1.5, 1.5)  # the arg wins over the env
    flags, _ = R.configure(["run.py", "--lingbot-turn-step", "60", "--lingbot-yaw-gain", "1.1"], environ={})
    assert flags["yaw_gain"].enabled and flags["turn_cal"]  # a turn step is a calibrated rate


@pytest.mark.parametrize("argv,env", [
    (["--lingbot-yaw-gain", "1.25"], {}),  # no turn-cal
    ([], {"LINGBOT_YAW_GAIN": "1.25"}),
    (["--lingbot-turn-cal", "--lingbot-yaw-gain", "0.4"], {}),
    (["--lingbot-turn-cal", "--lingbot-yaw-gain=2.5"], {}),
    (["--lingbot-turn-cal", "--lingbot-yaw-gain=nan"], {}),
    (["--lingbot-turn-cal", "--lingbot-yaw-gain=fast"], {}),
    (["--lingbot-turn-cal", "--lingbot-yaw-gain"], {}),
    (["--lingbot-turn-cal", "--lingbot-yaw-gain", "--tasks"], {}),
    (["--lingbot-turn-cal", "--lingbot-yaw-gain-left=0.1"], {}),
    (["--lingbot-turn-cal"], {"LINGBOT_YAW_GAIN_RIGHT": "3"}),
])
def test_refusals(argv, env):
    with pytest.raises(SystemExit):
        R.configure(["run.py", *argv], environ=env)


def test_key_delta_scales_only_yaw():
    P.reset({})
    P.calibrate(True, 0, 20)
    for k in ("w", "s", "a", "d", "i", "k", "none", "j", "l", "w+j", "l+i"):
        assert np.array_equal(P.key_delta(k), P.key_delta(k, yaw_gain=None))  # off: main's call
    for k in ("w", "i", "k", "none", "d+i"):
        assert np.array_equal(P.key_delta(k), P.key_delta(k, yaw_gain=(1.3, 0.7)))
    unit = math.degrees(P.YAW)
    assert _yaw_deg(P.key_delta("l", yaw_gain=(1.0, 1.25))) == pytest.approx(1.25 * unit)
    assert _yaw_deg(P.key_delta("j", yaw_gain=(0.8, 1.25))) == pytest.approx(-0.8 * unit)
    assert _yaw_deg(P.key_delta("w+l", yaw_gain=(1.0, 1.5))) == pytest.approx(1.5 * unit)
    assert np.array_equal(P.key_delta("w+l", yaw_gain=(1.0, 1.5))[:3, 3], P.key_delta("w+l")[:3, 3])
    # dataset mode (`<task>_full`, stateless): "→*18" is 405 intended degrees; the model gets 1.2x
    off, on = P.build_poses("l-360,none-50", 411), P.build_poses("l-360,none-50", 411, yaw_gain=(1.0, 1.2))
    assert np.array_equal(off, P.build_poses("l-360,none-50", 411, yaw_gain=None))
    turned = lambda c: sum(_yaw_deg(np.linalg.inv(a) @ b) for a, b in zip(c[:-1], c[1:]))
    assert turned(off) == pytest.approx(405, abs=1e-3) and turned(on) == pytest.approx(486, abs=1e-3)  # float32
    P.reset({})


def test_pose_track_model_gets_gain_intended_track_does_not():
    P.reset({})
    P.calibrate(True, 0, 20)  # dataset-mode rates: 22.5 degrees per 20-frame token
    keys = ["l"] * 360 + ["none"] * 52  # GC031 "→*18" plus tail, one `_full` step of 26 latent chunks
    off, on = S.PoseTrack(), S.PoseTrack()
    on.yaw_gain = (1.0, 1.25)
    r_off, r_on = off.advance(keys), on.advance(keys)
    assert r_off.shape == r_on.shape
    total = lambda rel: sum(_yaw_deg(r) for r in rel)
    assert total(r_off) == pytest.approx(405, abs=1e-6) and total(r_on) == pytest.approx(1.25 * 405, abs=1e-6)
    assert np.array_equal(on.latents, off.latents)  # ReturnDetector reads the intended track
    assert np.array_equal(on.intended_last, off.last) and not np.allclose(on.last, off.last)
    # a later step continues both tracks: the model's relative poses stay 1.25x, the intended ones 1x
    r_off, r_on = off.advance(["j"] * 32), on.advance(["j"] * 32)
    assert total(r_on) == pytest.approx(total(r_off), abs=1e-6)  # left gain 1.0: only right turns are scaled
    assert np.array_equal(on.latents, off.latents)
    P.reset({})


def test_left_gain_and_return_detector_follows_intended_pose():
    P.reset({})
    P.calibrate(True, 0, 20)
    tr = S.PoseTrack()
    tr.yaw_gain = (1.5, 1.0)
    rel = tr.advance(["j"] * 76)  # 76 left frames, then back
    assert sum(_yaw_deg(r) for r in rel) == pytest.approx(-1.5 * 76 * math.degrees(P.YAW), abs=1e-6)
    det = S.ReturnDetector(tol_deg=6, tol_trans=2)
    assert det.update(tr.latents) == []
    tr.advance(["l"] * 80)
    assert det.update(tr.latents) == [18]  # intended pose is back at the start after 76 right frames (latent 19)
    assert S.pose_offset(tr.intended_last)[0] == pytest.approx(math.degrees(P.YAW) * 4, abs=1e-6)
    P.reset({})


def test_pose_track_off_is_unchanged():
    P.reset({})
    keys = ["l"] * 28 + ["w+j"] * 32 + ["i"] * 16
    a, b = S.PoseTrack(), S.PoseTrack()
    b.yaw_gain = None
    ra, rb = a.advance(keys[:28]), b.advance(keys[:28])
    ra2, rb2 = a.advance(keys[28:60]), b.advance(keys[28:60])
    assert np.array_equal(ra, rb) and np.array_equal(ra2, rb2) and np.array_equal(a.latents, b.latents)
    assert np.array_equal(a.last, a.intended_last)


def test_flag_stats_only_when_on():
    off = F.FlagStats(True, "goal", False, False)
    assert "yaw_gain" not in off.summary("GC031") and "yaw_gain" not in off.total_line()
    on = F.FlagStats(True, "goal", False, False, yaw_gain="1.25")
    on.yaw_gain_frames += 360
    s = on.finish_task("GC031")
    assert (s["yaw_gain"], s["yaw_gain_frames"]) == ("1.25", 360)
    assert "yaw_gain=1.25 yaw_gain_frames=360" in on.total_line()


class _FakeSession:
    """Records the relative poses the model would get (real PoseTrack) and the intended latents."""

    def __init__(self):
        self.started, self.chunk_id, self.reanchor_events, self.track = False, 0, 0, S.PoseTrack()
        self.rels, self.intended = [], []

    def reset(self, *a, **kw):
        self.started, self.chunk_id, self.track = True, 0, S.PoseTrack()

    def step(self, keys, **kw):
        rel = self.track.advance(keys)
        self.rels.append(rel)
        self.intended.append(self.track.latents)
        self.chunk_id += len(rel) // S.CHUNK
        return np.zeros((len(keys) + 1, 2, 2, 3), dtype=np.uint8)


def _stub_modules(monkeypatch):
    torch = ModuleType("torch")
    torch.cuda = SimpleNamespace(reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)
    imageio = ModuleType("imageio")
    imageio.mimsave = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "imageio", imageio)


def test_multi_arm_main_isolation_dataset_and_chunked(monkeypatch, capsys, tmp_path):
    from PIL import Image
    img = tmp_path / "in.png"
    Image.new("RGB", (8, 8)).save(img)
    _stub_modules(monkeypatch)
    pipe = SimpleNamespace(model=None, _t5_cache={})
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), pipe, Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)
    seen = []

    def fake_import(fresh=True):
        def run_task(task, eng, out, args):  # counters are reset when the (wrapped) task starts
            eng.generate(str(img), "p", "l-360,none-50", tmp_path, "GC031_full", 411)  # dataset mode
            eng.generate(str(img), "p", "l-32", tmp_path, "GC033_chunk_01", 33)  # closed loop
            eng.generate(str(img), "p", "j-32", tmp_path, "GC033_chunk_02", 33)
            return {"task_id": task["task_id"], "success": False}

        ra = SimpleNamespace(run_task=run_task, decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")

        def run_main():
            eng = ra.SanaWMEngine(SimpleNamespace(max_total_frames=961, seed=0, fps=16, action_frame_unit=20))
            eng.session = _FakeSession()
            seen.append(eng.session)
            ra.run_task({"task_id": "GC031"}, eng, tmp_path, None)
        ra.main = run_main
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    assert R.main(["run.py", "--lingbot-turn-cal"]) == 0
    assert R.main(["run.py", "--lingbot-turn-cal", "--lingbot-yaw-gain", "1.25"]) == 0
    assert R.main(["run.py", "--lingbot-turn-cal"]) == 0
    base, gained, again = seen
    total = lambda rel: sum(_yaw_deg(r) for r in rel)
    assert total(base.rels[0]) == pytest.approx(405, abs=1e-6)  # 22.5 per dataset token
    assert total(gained.rels[0]) == pytest.approx(1.25 * 405, abs=1e-6)
    assert total(base.rels[1]) == pytest.approx(45, abs=1e-6)  # closed loop: 45 per chunk
    assert total(gained.rels[1]) == pytest.approx(1.25 * 45, abs=1e-6)
    assert total(gained.rels[2]) == pytest.approx(-1.25 * 45, abs=1e-6)
    for a, b in zip(base.intended, gained.intended):
        assert np.allclose(a, b, atol=1e-12)  # the intended track is the no-gain one
    for a, b in zip(base.rels + base.intended, again.rels + again.intended):
        assert np.array_equal(a, b)  # an arm after the gain arm is main's again
    assert R.YAW_GAIN == YG.YawGain()
    out = capsys.readouterr().out
    assert "[lingbot] yaw gain 1.25: model yaw only, intended track unchanged" in out
    modes = [ln for ln in out.splitlines() if ln.startswith("[lingbot] mode:")]
    assert "yaw gain" not in modes[0] and ", yaw gain 1.25," in modes[1] and "yaw gain" not in modes[2]
    flags = [ln for ln in out.splitlines() if ln.startswith("[lingbot] flags task=")]
    assert "yaw_gain" not in flags[0] and "yaw_gain=1.25 yaw_gain_frames=420" in flags[1] and "yaw_gain" not in flags[2]
