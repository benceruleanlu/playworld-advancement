"""CPU-only model-camera ablation checks; no weights or external clients."""
import json
import sys
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from adapters.lingbot_world2 import if_fixed_camera as C, run as R, session as S

FLAG = "--lingbot-if-fixed-camera"
CAPTION = "--lingbot-caption-prompt"
TASK = {"task_id": "IF034", "category": "IF", "perspective": "third person",
        "prompt": "The gripper picks up the bowl.", "image_caption": "A gripper above a bowl."}


def test_scope_and_pose_inputs():
    keys = ["w", "j", "W+I", "none"] * 7
    held, n = C.hold(TASK, "IF034_chunk_01", keys)
    assert n == 21 and held == ["none"] * 28 and keys[:4] == ["w", "j", "W+I", "none"]
    track = S.PoseTrack()
    assert np.array_equal(track.advance(held), np.tile(np.eye(4), (8, 1, 1)))
    assert np.array_equal(track.advance(["none"] * 32), np.tile(np.eye(4), (8, 1, 1)))
    for task, name in ((None, "IF034_full"), (TASK, "IF031_full"),
        ({**TASK, "perspective": "first person"}, "IF034_full"),
        ({**TASK, "perspective": ""}, "IF034_full"), ({**TASK, "prompt": ""}, "IF034_full"),
        ({**TASK, "task_id": "GC033"}, "GC033_full"), ({**TASK, "task_id": "OE001"}, "OE001_full")):
        out, n = C.hold(task, name, keys)
        assert out is keys and n == 0
    assert C.hold({**TASK, "perspective": "third-person"}, "IF034_full", ["none"] * 12)[1] == 0


def test_cli_and_invalid_combinations():
    assert not R.configure([], {})[0]["if_fixed_camera"]
    flags, rest = R.configure([FLAG, CAPTION, "--seed", "42"], {})
    assert flags["if_fixed_camera"] and rest == ["--seed", "42"]
    assert R.configure([CAPTION], {"LINGBOT_IF_FIXED_CAMERA": "1"})[0]["if_fixed_camera"]
    for args in ([FLAG], [FLAG, CAPTION, "--lingbot-stateless"]):
        with pytest.raises(SystemExit, match="requires"):
            R.configure(args, {})
    for flag in ("--lingbot-player-hint", "--lingbot-if-camera-hint", "--lingbot-measured-turn"):
        with pytest.raises(SystemExit, match="keys no longer move"):
            R.configure([FLAG, CAPTION, flag], {})
    for args, env in (([FLAG, CAPTION, "--lingbot-if-settle"], {}),
                      ([FLAG, CAPTION], {"LINGBOT_IF_SETTLE": "1"})):
        with pytest.raises(SystemExit, match="are alternatives"):
            R.configure(args, env)


@pytest.mark.parametrize("chunked", [False, True])
def test_engine_arms_prompts_frames_counters_and_resets(monkeypatch, tmp_path, chunked):
    class Session:
        started = False
        def reset(self, image, prompt, seed, **kw):
            self.started, self.track, self.chunk_id, self.reanchor_events = True, S.PoseTrack(), 0, 0
            self.prompt, self.seen = prompt, []
        def step(self, keys):
            rel = self.track.advance(keys)
            self.seen.append((list(keys), rel.copy()))
            self.chunk_id += len(rel) // 4
            return np.zeros((len(keys) + 1, 2, 2, 3), dtype=np.uint8)
    path = tmp_path / "input.png"
    Image.new("RGB", (2, 2)).save(path)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)))
    import imageio
    monkeypatch.setattr(imageio, "mimsave", lambda *a, **kw: None)
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test")
    monkeypatch.delenv("LINGBOT_IF_FIXED_CAMERA", raising=False)
    monkeypatch.setattr(sys, "argv", ["run.py"])
    arms = []
    def fake_import(**kw):
        def task_run(task, engine, out, args):
            tid = task["task_id"]
            dest = tmp_path / tid
            dest.mkdir(exist_ok=True)
            (dest / f"{tid}_result.json").write_text("{}")
            for i in range(1, 3 if chunked else 2):
                name = f"{tid}_chunk_{i:02d}" if chunked else f"{tid}_full"
                engine.generate(path, task["prompt"], "w+j-32", tmp_path, name, 33)
            return {"success": True}
        ra = SimpleNamespace(run_task=task_run)
        def main():
            seen = []
            for task in (TASK, {**TASK, "task_id": "GC033", "category": "GC"}):
                eng = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
                eng.session, eng.weight_mod, eng.yaw_servo, eng._last_chunk = Session(), None, None, None
                eng.args = SimpleNamespace(seed=42, fps=16, action_frame_unit=20)
                result = ra.run_task(task, eng, tmp_path, None)
                saved = json.loads((tmp_path / task["task_id"] / f"{task['task_id']}_result.json").read_text())
                assert saved["lingbot_flags"] == result["lingbot_flags"]
                seen.append((eng.session, result["lingbot_flags"]))
            arms.append((seen, R.STATS.total_line()))
        ra.main = main
        return ra
    monkeypatch.setattr(R, "import_run_agent", fake_import)
    for flags in ([CAPTION], [CAPTION, FLAG], [CAPTION]):
        assert R.main(["run.py", *flags]) == 0
    baseline, treatment, again = arms
    for i in range(2):
        b, t, a = (arm[0][i] for arm in arms)
        assert b[0].prompt == t[0].prompt == a[0].prompt
        assert all(np.array_equal(x[1], y[1]) for x, y in zip(b[0].seen, a[0].seen))
        assert "if_fixed_camera_frames" not in b[1] and "if_fixed_camera_frames" not in a[1]
        if i == 0:
            assert all(np.allclose(rel, np.eye(4)) for _, rel in t[0].seen)
            assert not np.allclose(b[0].seen[0][1], np.eye(4))
            assert TASK["prompt"] in t[0].prompt
        else:
            assert all(np.array_equal(x[1], y[1]) for x, y in zip(b[0].seen, t[0].seen))
        assert t[1]["if_fixed_camera_frames"] == ((60 if chunked else 28) if i == 0 else 0)
    assert f"if_fixed_camera_frames={60 if chunked else 28}" in treatment[1]
    assert "if_fixed_camera" not in again[1]
