"""pwa.clip_diff: same video or not, from the frames (numpy + imageio, no network)."""
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("imageio")
import imageio  # noqa: E402

from pwa import clip_diff as cd  # noqa: E402

H, W = 64, 112


def clip(n=24, seed=0, change_at=None, bump=0):
    rng = np.random.default_rng(seed)
    base = np.kron(rng.integers(0, 255, (8, 14, 3), dtype=np.uint8), np.ones((8, 8, 1), dtype=np.uint8))
    frames = []
    for i in range(n):
        f = np.roll(base, i, axis=1).astype(np.int16) + bump
        if change_at is not None and i >= change_at:
            f = 255 - f
        frames.append(np.clip(f, 0, 255).astype(np.uint8))
    return frames


def write(path: Path, frames) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(str(path), frames, fps=16, macro_block_size=1)
    return path


def test_frame_verdicts():
    a = clip()
    assert cd.compare_frames(a, clip())["verdict"] == "same frames"
    near = cd.compare_frames(a, clip(bump=4))
    assert near["verdict"] == "near-identical" and 3 < near["mad_max"] < 5
    div = cd.compare_frames(a, clip(change_at=16))
    assert div["verdict"] == "diverges" and div["at_frame"] == 16 and div["at_s"] == 1.0 and div["frames_over"] == 8
    assert cd.compare_frames(a, clip(seed=1))["verdict"] == "different"
    assert cd.compare_frames(a, [])["verdict"] == "different"


def test_a_shorter_clip_is_reported_as_a_prefix():
    r = cd.compare_frames(clip(24), clip(16))
    assert r["verdict"] == "same frames" and r["compared"] == 16 and r["length"] == "b is shorter by 8 frames"


def test_files_identical_bytes_and_diverging(tmp_path):
    a = write(tmp_path / "a.mp4", clip())
    b = write(tmp_path / "b.mp4", clip())
    c = write(tmp_path / "c.mp4", clip(change_at=12))
    assert cd.compare_files(a, b)["verdict"] == "identical"
    r = cd.compare_files(a, c)
    assert r["verdict"] == "diverges" and 10 <= r["at_frame"] <= 13          # codec smears the cut by a frame


def test_exps_mode_reads_manifests_and_never_downloads_twice(tmp_path, capsys):
    media = tmp_path / "media"
    media.mkdir()
    src = {"ctl/T1": write(tmp_path / "src/ctl_T1.mp4", clip()), "arm/T1": write(tmp_path / "src/arm_T1.mp4", clip()),
           "ctl/T2": write(tmp_path / "src/ctl_T2.mp4", clip()), "arm/T2": write(tmp_path / "src/arm_T2.mp4", clip(seed=3))}
    for exp, tasks in (("ctl", ["T1", "T2", "T3"]), ("arm", ["T1", "T2"])):
        (media / f"{exp}.json").write_text(json.dumps(
            {"exp": exp, "tasks": [{"task_id": t, "video": f"mem://{exp}/{t}"} for t in tasks]}))
    fetched = []

    def fetcher(url, dest):
        fetched.append(url)
        return src[url.removeprefix("mem://")]

    rows = cd.compare_exps(["ctl", "arm"], None, media, tmp_path / "cache", log=lambda m: None, fetcher=fetcher)
    assert [(r["task"], r["verdict"]) for r in rows] == [("T1", "identical"), ("T2", "different"), ("T3", "missing")]
    assert len(fetched) == 4
    assert "identical" in cd.render(rows)
    with pytest.raises(SystemExit):
        cd.manifest("nope", media)
    with pytest.raises(SystemExit):
        cd.main(["only-one.mp4"])
