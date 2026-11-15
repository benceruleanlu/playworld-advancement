"""CPU-only tests for --lingbot-turntable-poses / --lingbot-turntable-walk / --lingbot-turntable-rescale."""
from __future__ import annotations

import ast
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.common import prompts  # noqa: E402
from adapters.lingbot_world2 import (  # noqa: E402
    flag_stats as F,
    pose_memory as PM,
    poses as P,
    run as R,
    session as S,
    turntable as TT,
)


def _roll_deg(c2w: np.ndarray) -> float:
    """Intrinsic horizon roll in degrees around the camera optical axis z_cam."""
    yaw_deg, pitch_deg = PM.view_angles(c2w)
    r_level = TT.rotation(math.radians(yaw_deg), math.radians(pitch_deg))
    r_roll = r_level.T @ c2w[:3, :3]
    return math.degrees(math.atan2(r_roll[1, 0], r_roll[0, 0]))


def test_turntable_module_imports_no_torch():
    tree = ast.parse((ROOT / "adapters" / "lingbot_world2" / "turntable.py").read_text())
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "torch" not in imported


def test_parse_and_configure(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)

    cfg, rest = TT.parse(["run.py", "--tasks", "GC031"], environ={})
    assert cfg == TT.TurntableConfig() and not cfg.enabled and rest == ["run.py", "--tasks", "GC031"]

    cfg, rest = TT.parse(["run.py", "--lingbot-turntable-poses", "--tasks", "GC031"], environ={})
    assert cfg == TT.TurntableConfig(True, "ground", False) and rest == ["run.py", "--tasks", "GC031"]
    assert cfg.describe() == "walk=ground"

    cfg, rest = TT.parse(
        ["run.py", "--lingbot-turntable-poses", "--lingbot-turntable-walk=free", "--lingbot-turntable-rescale"],
        environ={},
    )
    assert cfg == TT.TurntableConfig(True, "free", True) and rest == ["run.py"]
    assert cfg.describe() == "walk=free, rescale"

    # Env vars and CLI precedence over env
    cfg, _ = TT.parse(
        ["run.py"],
        environ={"LINGBOT_TURNTABLE_POSES": "1", "LINGBOT_TURNTABLE_WALK": "free", "LINGBOT_TURNTABLE_RESCALE": "1"},
    )
    assert cfg == TT.TurntableConfig(True, "free", True)
    cfg, _ = TT.parse(["run.py", "--lingbot-turntable-walk", "ground"], environ={"LINGBOT_TURNTABLE_WALK": "free"})
    assert cfg == TT.TurntableConfig(False, "ground", False)

    # Walk knob without main flag is validated and stripped, leaving enabled=False (pose_memory convention)
    flags, rest = R.configure(["run.py", "--lingbot-turntable-walk", "free", "--tasks", "GC016"], environ={})
    assert flags["turntable"] == TT.TurntableConfig(False, "free", False)
    assert not flags["turntable"].enabled and rest == ["run.py", "--tasks", "GC016"]

    # Rescale works with --lingbot-turn-cal and with --lingbot-turn-step (which implies turn_cal)
    flags, rest = R.configure(
        ["run.py", "--lingbot-turntable-poses", "--lingbot-turntable-rescale", "--lingbot-turn-cal"],
        environ={},
    )
    assert flags["turntable"] == TT.TurntableConfig(True, "ground", True) and rest == ["run.py"]
    flags, _ = R.configure(
        ["run.py", "--lingbot-turntable-poses", "--lingbot-turntable-rescale", "--lingbot-turn-step", "60"],
        environ={},
    )
    assert flags["turntable"].rescale and flags["turn_cal"]


@pytest.mark.parametrize("argv,env,match", [
    (["--lingbot-turntable-rescale", "--lingbot-turn-cal"], {}, "requires --lingbot-turntable-poses"),
    (["--lingbot-turn-cal"], {"LINGBOT_TURNTABLE_RESCALE": "1"}, "requires --lingbot-turntable-poses"),
    (["--lingbot-turntable-poses", "--lingbot-turntable-rescale"], {}, "requires --lingbot-turn-cal"),
    ([], {"LINGBOT_TURNTABLE_POSES": "1", "LINGBOT_TURNTABLE_RESCALE": "1"}, "requires --lingbot-turn-cal"),
    (["--lingbot-turntable-walk"], {}, "needs a value"),
    (["--lingbot-turntable-walk", "--tasks"], {}, "needs a value"),
    (["--lingbot-turntable-walk=hover"], {}, "must be one of"),
    (["--lingbot-turntable-poses", "--lingbot-turntable-walk", "hover"], {}, "must be one of"),
    ([], {"LINGBOT_TURNTABLE_WALK": "hover"}, "must be one of"),
])
def test_refusals(monkeypatch, argv, env, match):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    with pytest.raises(SystemExit, match=match):
        R.configure(["run.py", *argv], environ=env)


def test_zero_horizon_roll_and_exact_pan_tilt_rectangle_closure():
    P.reset({})
    P.calibrate(True, 0, 20)  # 22.5 deg yaw / 20 frames, 20 deg pitch / 20 frames
    rect = ["i"] * 40 + ["l"] * 80 + ["k"] * 40 + ["j"] * 80  # u*2, r*4, d*2, l*4

    # Local composition in poses.key_delta rolls the horizon 40 deg and leaves 40 deg residual pitch
    local = np.eye(4)
    for k in rect:
        local = local @ P.key_delta(k)
    _, pitch_err = PM.view_angles(local)
    assert _roll_deg(local) == pytest.approx(40.0, abs=1e-9)
    assert pitch_err == pytest.approx(40.0, abs=1e-9)
    assert not np.allclose(local, np.eye(4), atol=0.1)

    # Turntable maintains 0 deg horizon roll at EVERY frame and closes back to exact np.eye(4)
    st = TT.TurntableState()
    for k in rect:
        c2w = st.step(k, P.YAW, P.PITCH)
        assert c2w[1, 0] == 0.0 and abs(_roll_deg(c2w)) < 1e-12
        assert np.allclose(c2w[:3, :3].T @ c2w[:3, :3], np.eye(3), atol=1e-14)
    assert np.allclose(c2w, np.eye(4), atol=1e-12)

    # Arbitrary mixed pan/tilt/diagonal sequence + pitch clamping at +/-85 deg never introduces roll
    st_clamp = TT.TurntableState()
    mixed = ["i"] * 120 + ["w+l"] * 35 + ["k"] * 250 + ["a+j+i"] * 50 + ["s+d+k"] * 25
    for k in mixed:
        m = st_clamp.step(k, P.YAW, P.PITCH, walk="free")
        assert m[1, 0] == 0.0 and abs(_roll_deg(m)) < 1e-12
        assert abs(st_clamp.pitch) <= math.radians(85.0) + 1e-15

    # Stateless build_poses and session PoseTrack + ReturnDetector also close the rectangle
    cfg = TT.TurntableConfig(enabled=True)
    built = P.build_poses("i-40,l-80,k-40,j-80,none-16", 245, turntable=cfg)
    assert np.allclose(built[:, 1, 0], 0.0, atol=1e-7)
    assert np.allclose(built[240], np.eye(4), atol=1e-6)

    tr = S.PoseTrack()
    tr.turntable = cfg
    tr.advance(rect + ["none"] * 12)  # 252 keys -> +4 on first step = 256 = 16 chunks
    assert np.allclose(tr.last, np.eye(4), atol=1e-12)
    det = S.ReturnDetector(tol_deg=6, tol_trans=2)
    anchors = det.update(tr.latents)
    assert anchors and anchors[0] == 60  # frame 240 is latent 60: exact return detected
    P.reset({})


@pytest.mark.parametrize("walk", ["ground", "free"])
def test_exact_equivalence_to_main_when_pitch_is_zero(walk):
    P.reset({})
    P.calibrate(True, 0, 20)
    seq = (
        ["w"] * 12
        + ["l"] * 19
        + ["w+j"] * 15
        + ["d+l"] * 11
        + ["s+a"] * 9
        + ["none"] * 8
        + ["s+j"] * 14
        + ["a+l"] * 12
    )
    for gain in (None, (0.85, 1.25)):
        for t_gain, r_scale in ((1.0, 1.0), (0.5, 1.3)):
            cur = np.eye(4, dtype=np.float64)
            st = TT.TurntableState()
            for k in seq:
                cur = cur @ P.key_delta(k, translation_gain=t_gain, rotation_scale=r_scale, yaw_gain=gain)
                got = st.step(
                    k, P.YAW, P.PITCH,
                    translation_gain=t_gain, rotation_scale=r_scale, yaw_gain=gain, walk=walk,
                )
                assert np.allclose(got, cur, atol=1e-14)

    # PoseTrack equivalence (including yaw_gain and ease_turns) when pitch == 0
    cfg = TT.TurntableConfig(enabled=True, walk=walk)
    for gain in (None, (0.8, 1.2)):
        off, on = S.PoseTrack(translation_gain=0.5), S.PoseTrack(translation_gain=0.5)
        off.yaw_gain = on.yaw_gain = gain
        on.turntable = cfg
        r_off_1 = off.advance(["l"] * 28, ease_turns=True)
        r_on_1 = on.advance(["l"] * 28, ease_turns=True)
        r_off_2 = off.advance(["w+j"] * 16 + ["d"] * 16)
        r_on_2 = on.advance(["w+j"] * 16 + ["d"] * 16)
        assert np.allclose(r_on_1, r_off_1, atol=1e-13)
        assert np.allclose(r_on_2, r_off_2, atol=1e-13)
        assert np.allclose(on.latents, off.latents, atol=1e-13)
        assert np.allclose(on.intended_last, off.intended_last, atol=1e-13)
    P.reset({})


def test_ground_walk_stays_level_while_free_walk_follows_pitch():
    P.reset({})
    P.calibrate(True, 0, 20)
    keys = ["i"] * 20 + ["w+i"] * 20 + ["w"] * 20  # tilt up 20 deg, tilt+walk, walk while tilted 40 deg

    ground, free = TT.TurntableState(), TT.TurntableState()
    for k in keys:
        cg = ground.step(k, P.YAW, P.PITCH, walk="ground")
        cf = free.step(k, P.YAW, P.PITCH, walk="free")
        assert cg[1, 3] == 0.0  # ground walk never leaves y = 0

    assert ground.pos[1] == 0.0 and ground.pos[2] == pytest.approx(40.0, abs=1e-12)
    assert free.pos[1] < -20.0  # OpenCV -y is up: pitched forward walk climbs in -y
    assert free.pos[2] < ground.pos[2]
    assert np.allclose(ground.rotation, free.rotation, atol=1e-14)
    with pytest.raises(ValueError, match="walk"):
        ground.step("w", P.YAW, P.PITCH, walk="invalid")
    P.reset({})


def test_effective_frame_unit_and_calibrate_restore_360_on_compressed_script(capsys):
    segs = lambda task: [("RIGHT", 16)]
    task = {"task_id": "GC031", "action": "→*16"}

    # Uncompressed 16 * 20 = 320 active frames + 50 tail -> stays 20.0
    assert TT.effective_frame_unit(task, "l-320,none-50", 20, tail_frames=50, parse_segments=segs) == 20.0
    # Budget-compressed 240 active frames + 50 tail -> 240 / 16 = 15.0 frames/token
    assert TT.effective_frame_unit(task, "l-240,none-50", 20, tail_frames=50, parse_segments=segs) == pytest.approx(15.0)
    # Script ending with explicit wait*2 before the 50-frame tail strips at most tail_frames=50
    wait_task = {"task_id": "OE033", "action": "→*14 -> wait*2"}
    wait_segs = lambda _t: [("RIGHT", 14), ("WAIT", 2)]
    assert TT.effective_frame_unit(
        wait_task, "l-200,none-30,none-50", 20, tail_frames=50, parse_segments=wait_segs,
    ) == pytest.approx(230.0 / 16.0)
    # Wait-only insight ("none-1121") has no active motion keys -> untouched
    assert TT.effective_frame_unit({"action": "wait and observe"}, "none-1121", 20, tail_frames=50) == 20.0
    assert TT.effective_frame_unit(None, "l-240,none-50", 20, parse_segments=segs) == 20.0

    # End-to-end with upstream run_agent.build_full_sana_action + LingBotWorld2Engine._calibrate
    from adapters.common.upstream import import_run_agent
    ra = import_run_agent()
    sana, recs = ra.build_full_sana_action(task, frame_unit=20, tail_frames=50, max_total_frames=291)
    assert sana == "l-240,none-50" and sum(r["frames"] for r in recs) == 290

    eng = object.__new__(R.LingBotWorld2Engine)
    eng.args = SimpleNamespace(action_frame_unit=20, tail_frames=50)
    old_state = (R.TURN_CAL, R.TURNTABLE, R.STATS, R._PARSE_SEGMENTS)
    try:
        P.reset({})
        prompts._current["task"] = task
        R.TURN_CAL = True
        R._PARSE_SEGMENTS = ra.parse_segments

        # Without rescale: 240 frames at 22.5/20 deg/frame only turns 270 deg
        R.TURNTABLE = TT.TurntableConfig(enabled=True, rescale=False)
        R.STATS = F.FlagStats(True, "goal", False, False, turntable="ground", turntable_rescale=False)
        eng._calibrate("GC031_full", 290, sana)
        assert math.degrees(P.YAW) * 240 == pytest.approx(270.0, abs=1e-9)
        assert R.STATS.turntable_rescaled == 0

        # With rescale: 240 frames at 22.5/15 deg/frame restores exact 360.0 deg!
        R.TURNTABLE = TT.TurntableConfig(enabled=True, rescale=True)
        R.STATS = F.FlagStats(True, "goal", False, False, turntable="ground", turntable_rescale=True)
        eng._calibrate("GC031_full", 290, sana)
        assert math.degrees(P.YAW) * 240 == pytest.approx(360.0, abs=1e-9)
        c2ws = P.build_poses(sana, 291, turntable=R.TURNTABLE)
        assert np.allclose(c2ws[240], np.eye(4), atol=1e-6)
        assert R.STATS.turntable_rescaled == 1
        assert "[lingbot] turntable: GC031_full rescaled dataset unit 20 -> 15.000 frames/token" in capsys.readouterr().out
    finally:
        R.TURN_CAL, R.TURNTABLE, R.STATS, R._PARSE_SEGMENTS = old_state
        prompts.reset()
        P.reset({})


def test_flag_off_bit_identical():
    P.reset({})
    act = "i-20,l-40,w+k-20,j-40,none-12"
    a = P.build_poses(act, 133)
    b = P.build_poses(act, 133, turntable=None)
    c = P.build_poses(act, 133, turntable=TT.TurntableConfig(enabled=False))
    assert np.array_equal(a, b) and np.array_equal(a, c)

    keys = P.parse_action("i-12,l-16,w+j-16,k-16")  # 60 keys -> +4 on first step = 64 = 4 chunks
    t1, t2, t3 = S.PoseTrack(), S.PoseTrack(), S.PoseTrack()
    t3.turntable = TT.TurntableConfig(enabled=False)
    r1, r2, r3 = t1.advance(keys), t2.advance(keys), t3.advance(keys)
    assert np.array_equal(r1, r2) and np.array_equal(r1, r3)
    assert np.array_equal(t1.latents, t3.latents) and np.array_equal(t1.last, t3.last)

    off = F.FlagStats(False, "goal", False, False)
    assert off.summary("GC033") == {
        "task": "GC033", "turn_cal": 0, "caption": "off",
        "reanchor": "off", "reanchor_events": 0, "player_hint": "off", "player_hints": 0,
    }
    assert "turntable" not in F.FlagStats.line(off.summary("GC033"))
    assert "turntable" not in off.total_line()


class _FakeSession:
    def __init__(self):
        self.started, self.chunk_id, self.reanchor_events, self.track = False, 0, 0, S.PoseTrack()
        self.rels, self.latents = [], []

    def reset(self, *a, **kw):
        self.started, self.chunk_id, self.track = True, 0, S.PoseTrack()

    def step(self, keys, **kw):
        rel = self.track.advance(keys)
        self.rels.append(rel)
        self.latents.append(self.track.latents)
        self.chunk_id += len(rel) // S.CHUNK
        return np.zeros((len(keys) + 1, 2, 2, 3), dtype=np.uint8)


def _stub_modules(monkeypatch):
    torch = ModuleType("torch")
    torch.cuda = SimpleNamespace(reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)
    imageio = ModuleType("imageio")
    imageio.mimsave = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "imageio", imageio)


def test_multi_arm_main_isolation(monkeypatch, capsys, tmp_path):
    from PIL import Image

    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    img = tmp_path / "in.png"
    Image.new("RGB", (8, 8)).save(img)
    _stub_modules(monkeypatch)
    pipe = SimpleNamespace(model=None, _t5_cache={})
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), pipe, Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)
    seen = []

    def fake_import(fresh=True):
        def run_task(task, eng, out, args):
            # Compressed 16-token script ("l-240,none-50", 290 keys -> 284 fitted on first session step)
            eng.generate(str(img), "p", "l-240,none-50", tmp_path, "GC031_full", 291)
            # Closed-loop pan/tilt rectangle across two chunks
            eng.generate(str(img), "p", "i-14,l-14", tmp_path, "GC033_chunk_01", 33)
            eng.generate(str(img), "p", "k-16,j-16", tmp_path, "GC033_chunk_02", 33)
            return {"task_id": task["task_id"], "success": False}

        ra = SimpleNamespace(
            run_task=run_task,
            decide_action=lambda *a, **kw: "WAIT",
            to_sana_key=lambda a: "none",
            parse_segments=lambda t: [("RIGHT", 16)],
        )

        def run_main():
            eng = ra.SanaWMEngine(
                SimpleNamespace(max_total_frames=291, seed=0, fps=16, action_frame_unit=20, tail_frames=50)
            )
            eng.session = _FakeSession()
            seen.append(eng.session)
            ra.run_task({"task_id": "GC031", "action": "→*16"}, eng, tmp_path, None)
            return 0

        ra.main = run_main
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)

    arms = [
        [],
        ["--lingbot-turntable-poses", "--lingbot-turn-cal"],
        ["--lingbot-turntable-poses", "--lingbot-turntable-walk=free", "--lingbot-turntable-rescale", "--lingbot-turn-cal"],
        [],
    ]
    for extra in arms:
        assert R.main(["run.py", *extra]) == 0

    base, tt_arm, tt_rescaled, again = seen
    # Arm 0 and Arm 3 (flag off before and after) are 100% bit-identical
    for a, b in zip(base.rels + base.latents, again.rels + again.latents):
        assert np.array_equal(a, b)
    assert R.TURNTABLE == TT.TurntableConfig()

    # Arm 1 & Arm 2 keep zero roll on the pan/tilt chunks, whereas Arm 0 drifts in roll
    assert abs(_roll_deg(base.latents[2][-1])) > 1.0
    assert abs(_roll_deg(tt_arm.latents[2][-1])) < 1e-12
    assert abs(_roll_deg(tt_rescaled.latents[2][-1])) < 1e-12

    # Arm 2 rescales GC031_full ("l-240,none-50") from 270 deg to 360 deg -> ends back at identity!
    assert not np.allclose(tt_arm.latents[0][-1], np.eye(4), atol=0.1)
    assert np.allclose(tt_rescaled.latents[0][-1], np.eye(4), atol=1e-12)

    out = capsys.readouterr().out.splitlines()
    modes = [ln for ln in out if ln.startswith("[lingbot] mode:")]
    flags = [ln for ln in out if ln.startswith("[lingbot] flags task=")]
    totals = [ln for ln in out if ln.startswith("[lingbot] flags total")]

    assert modes[0] == modes[3] and "turntable" not in modes[0]
    assert ", turntable poses (walk=ground)," in modes[1]
    assert ", turntable poses (walk=free, rescale)," in modes[2]

    assert flags[0] == flags[3] and "turntable" not in flags[0]
    assert totals[0] == totals[3] and "turntable" not in totals[0]
    assert "turntable=ground turntable_frames=300" in flags[1] and "turntable_rescaled" not in flags[1]
    assert "turntable=free turntable_frames=300 turntable_rescaled=1" in flags[2]
    assert "turntable=free turntable_frames=300 turntable_rescaled=1" in totals[2]


def test_stateless_turntable_and_yaw_gain_saved_poses(monkeypatch, tmp_path):
    from PIL import Image

    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    img = tmp_path / "in.png"
    Image.new("RGB", (8, 8)).save(img)

    class _FakeVideo:
        def clamp(self, *_a): return self
        def __add__(self, _v): return self
        def __mul__(self, _v): return self
        def round(self): return self
        def to(self, _d): return self
        def permute(self, *_a): return self
        def cpu(self): return SimpleNamespace(numpy=lambda: np.zeros((29, 2, 2, 3), dtype=np.uint8))

    _stub_modules(monkeypatch)
    sys.modules["torch"].uint8 = "uint8"
    monkeypatch.setattr(S, "encode_prompt", lambda *_a, **_kw: None)
    saved_dirs = []
    pipe = SimpleNamespace(
        model=None, _t5_cache={},
        generate=lambda *_a, **kw: saved_dirs.append(Path(kw["action_path"])) or _FakeVideo(),
    )
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), pipe, Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)

    def fake_import(fresh=True):
        def run_task(task, eng, out, args):
            eng.generate(str(img), "p", "i-14,l-14", out, "GC033_chunk_01", 29)
            return {"task_id": task["task_id"], "success": False}

        ra = SimpleNamespace(
            run_task=run_task, decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none",
        )
        ra.main = lambda: ra.run_task(
            {"task_id": "GC033"},
            ra.SanaWMEngine(SimpleNamespace(max_total_frames=961, seed=0, fps=16, action_frame_unit=20)),
            tmp_path, None,
        ) and 0
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    assert R.main(["run.py", "--lingbot-stateless", "--lingbot-turn-cal", "--lingbot-turntable-poses",
                   "--lingbot-yaw-gain", "1.2"]) == 0
    c2ws = np.load(saved_dirs[0] / "poses.npy")
    assert c2ws.shape == (29, 4, 4) and np.allclose(c2ws[:, 1, 0], 0.0, atol=1e-7)
    yaw_deg, pitch_deg = PM.view_angles(c2ws[-1])
    assert pitch_deg == pytest.approx(20.0, abs=1e-4)
    assert yaw_deg == pytest.approx(1.2 * 22.5, abs=1e-4)

