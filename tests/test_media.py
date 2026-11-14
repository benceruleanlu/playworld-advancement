"""pwa media: web copies of rollouts and the manifest the results site reads. Needs ffmpeg, not the dataset."""
import json
import re
import subprocess

import pytest

from pwa import media


def _have_ffmpeg():
    try:
        media.ffmpeg_exe()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _have_ffmpeg(), reason="needs ffmpeg")


def _clip(path, w=832, h=480, seconds=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([media.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=16",
                    "-t", str(seconds), "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _height(path):
    r = subprocess.run([media.ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True)
    line = next(l for l in r.stderr.splitlines() if "Video:" in l)
    return int(re.search(r"\b(\d{2,5})x(\d{2,5})\b", line).group(2))


def test_encode_downscales_and_writes_poster(tmp_path):
    src = _clip(tmp_path / "src.mp4", 1280, 720)
    media.encode(src, tmp_path / "a.mp4", tmp_path / "a.jpg", height=480)
    assert (tmp_path / "a.mp4").stat().st_size > 0 and (tmp_path / "a.jpg").stat().st_size > 0
    assert _height(tmp_path / "a.mp4") == 480


def test_encode_never_upscales(tmp_path):
    src = _clip(tmp_path / "src.mp4", 640, 360)
    media.encode(src, tmp_path / "a.mp4", tmp_path / "a.jpg", height=480)
    assert _height(tmp_path / "a.mp4") == 360


def test_build_manifest(tmp_path, monkeypatch):
    vids = {"GC005": _clip(tmp_path / "runs" / "GC005.mp4")}
    monkeypatch.setattr(media, "video_path", lambda exp, tid: vids.get(tid, tmp_path / "none.mp4"))
    monkeypatch.setattr(media, "read_meta", lambda exp: {"git_sha": "abc123", "runner": "lingbot_world2"})
    monkeypatch.setattr(media, "failures", lambda exp, sel, all_tasks=False: [
        {"task_id": "GC005", "family": "gc", "mean": 2.2, "status": ["ok"], "reason": "scene kept its layout"}])
    sel = [{"task_id": "GC005", "family": "gc"}, {"task_id": "IF010", "family": "if"}]
    man = media.build("e1", sel, tmp_path / "out", "https://example.test/dl", "https://example.test/rel")
    assert man["license"] == "CC BY-NC-SA 4.0" and man["git_sha"] == "abc123" and man["release_tag"] == "run-e1"
    gc, if_ = man["tasks"]
    assert gc["video"] == "https://example.test/dl/GC005.mp4" and gc["poster"] == "https://example.test/dl/GC005.jpg"
    assert gc["mean"] == 2.2 and gc["reason"] == "scene kept its layout"
    assert if_["video"] is None and if_["status"] == ["missing"]  # no rollout: listed, no clip
    assert json.loads((tmp_path / "out" / "e1.json").read_text()) == man


def test_index_replaces_and_sorts_newest_first(tmp_path):
    idx = tmp_path / "media" / "index.json"
    media.update_index(idx, {"exp": "a", "generated": "2026-11-14T10:00:00Z", "tasks": [1], "release_url": "u"})
    media.update_index(idx, {"exp": "b", "generated": "2026-11-14T12:00:00Z", "tasks": [1, 2], "release_url": "v"})
    media.update_index(idx, {"exp": "a", "generated": "2026-11-14T13:00:00Z", "tasks": [1, 2, 3], "release_url": "w"})
    runs = json.loads(idx.read_text())["runs"]
    assert [r["exp"] for r in runs] == ["a", "b"] and runs[0]["n_tasks"] == 3 and runs[0]["release_url"] == "w"
