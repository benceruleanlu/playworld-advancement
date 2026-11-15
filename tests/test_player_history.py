"""Player-only observation compression with mocked upstream requests."""
from types import SimpleNamespace

import pytest

from adapters.common import agent_api, upstream
from adapters.lingbot_world2 import player_history as H, run as R
from adapters.lingbot_world2.flag_stats import FlagStats


@pytest.mark.parametrize("count,requested", [(0, 4), (1, 4), (2, 4), (4, 4), (8, 8)])
def test_sampling_preserves_bytes_and_timestamps(count, requested):
    frames = [{"b64": str(i), "timestamp_s": i / 10} for i in range(count)]
    events, calls = [], []
    ra = SimpleNamespace(extract_video_frames_with_timestamps_b64=
                         lambda *a: calls.append(a) or frames)
    H.install(ra, events.append)
    result = ra.extract_video_frames_with_timestamps_b64("clip.mp4", num_frames=requested)
    assert calls == [("clip.mp4", requested)]
    if requested == 4 and count > 2:
        assert result == [frames[0], frames[-1]] and events == [count - 2]
        assert result[0] is frames[0] and result[-1] is frames[-1]
    else:
        assert result is frames and events == []


def test_real_player_keeps_initial_recent_and_action_history(monkeypatch, tmp_path):
    ra = upstream.import_run_agent(fresh=True)
    paths = [tmp_path / name for name in ("initial.jpg", "old.mp4", "new.mp4")]
    for p in paths:
        p.write_bytes(b"x")
    monkeypatch.setattr(ra, "image_file_to_b64", lambda p: "initial")
    monkeypatch.setattr(ra, "extract_video_frames_with_timestamps_b64", lambda path, n:
                        [{"b64": f"{path}:{i}", "timestamp_s": i} for i in range(n)])
    sent = []
    monkeypatch.setattr(ra, "request_agent_action", lambda a, p, images: sent.append((p, images)) or "LEFT")
    stats = FlagStats(False, "goal", False, False, history_endpoints=True)
    H.install(ra, stats.history_removed)
    assert ra.decide_action({"task_id": "GC033", "prompt": "Return.", "image_path": str(paths[0])},
                            None, ["LEFT", "RIGHT"], 2, 30, SimpleNamespace(),
                            chunk_video_paths=paths[1:]) == "LEFT"
    prompt, images = sent[0]
    assert images == ["initial", f"{paths[1]}:0", f"{paths[1]}:3"] + [f"{paths[2]}:{i}" for i in range(8)]
    assert "LEFT -> RIGHT" in prompt and "chunk 01 at local t=3s" in prompt
    assert stats.finish_task("GC033")["player_frames_removed"] == 2
    stats.new_task()
    assert stats.player_frames_removed == 0 and "player_frames_removed=2" in stats.total_line()
    assert "player_frames_removed" not in FlagStats(False, "goal", False, False).total_line()


def test_runner_is_opt_in_and_resets_each_arm(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(agent_api, "patch", lambda ra: "test")
    modules = []
    def fresh(**kw):
        sample = lambda *a: list(range(4))
        ra = SimpleNamespace(extract_video_frames_with_timestamps_b64=sample,
                             run_task=lambda *a: None, main=lambda: 0)
        modules.append((ra, sample))
        return ra
    monkeypatch.setattr(R, "import_run_agent", fresh)
    flag = "--lingbot-player-history-endpoints"
    assert R.configure(["run.py", flag, "--seed", "42"], {})[1] == ["run.py", "--seed", "42"]
    assert R.configure([], {"LINGBOT_PLAYER_HISTORY_ENDPOINTS": "1"})[0]["history_endpoints"]
    R.main(["run.py", flag])
    assert modules[-1][0].extract_video_frames_with_timestamps_b64("x", 4) == [0, 3]
    assert R.STATS.player_frames_removed == 2
    R.main(["run.py"])
    assert modules[-1][0].extract_video_frames_with_timestamps_b64 is modules[-1][1]
    assert not R.STATS.history_endpoints and R.STATS.player_frames_removed == 0
