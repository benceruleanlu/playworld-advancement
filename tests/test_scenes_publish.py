"""Publishing scenes to main: an unscored run (screening judge, gen-only) never replaces official scored scenes,
and the manifest is never committed without its index entry. Covers pwa.media.to_main / keeps-official and the
workflow scripts .github/scripts/scenes_to_main.sh and publish_scenes.sh with gh, git and pwa stubbed."""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from pwa import media

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"


def _man(exp="e1", scored=True, generated="2026-11-15T00:00:00Z", **kw):
    m = {"exp": exp, "generated": generated, "release_url": f"https://example.test/rel/{exp}", "scored": scored,
         "labels": [] if scored else ["not scored"],
         "tasks": [{"task_id": "GC005", "family": "gc", "mean": 2.5 if scored else None, "status": ["ok"],
                    "reason": "kept layout" if scored else "", "video": "v.mp4", "poster": "p.jpg"}]}
    m.update(kw)
    return m


def _write(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj))
    return path


@pytest.mark.parametrize("existing,new,expected", [
    (None, _man(scored=False), False),
    (_man(scored=False), _man(scored=False), False),
    (_man(scored=False), _man(scored=True), False),
    (_man(scored=True), _man(scored=True), False),
    (_man(scored=True), _man(scored=False), True),
    ({k: v for k, v in _man().items() if k != "scored"}, _man(scored=False), True),  # pre-`scored` manifests are official
])
def test_would_downgrade(existing, new, expected):
    assert media.would_downgrade(existing, new) is expected


def test_to_main_writes_manifest_and_index(tmp_path):
    src = _write(tmp_path / "out" / "e1.json", _man(scored=False))
    assert media.to_main(tmp_path / "main", src)
    assert json.loads((tmp_path / "main" / "e1.json").read_text())["scored"] is False
    assert [r["exp"] for r in json.loads((tmp_path / "main" / "index.json").read_text())["runs"]] == ["e1"]


def test_to_main_keeps_official_scenes(tmp_path):
    official = _man(scored=True)
    _write(tmp_path / "main" / "e1.json", official)
    media.update_index(tmp_path / "main" / "index.json", official)
    before = {p.name: p.read_text() for p in (tmp_path / "main").iterdir()}
    src = _write(tmp_path / "out" / "e1.json", _man(scored=False, generated="2026-11-16T00:00:00Z"))
    assert media.to_main(tmp_path / "main", src) is False
    assert {p.name: p.read_text() for p in (tmp_path / "main").iterdir()} == before


def test_to_main_official_replaces_unscored(tmp_path):
    _write(tmp_path / "main" / "e1.json", _man(scored=False))
    src = _write(tmp_path / "out" / "e1.json", _man(scored=True))
    assert media.to_main(tmp_path / "main", src)
    assert json.loads((tmp_path / "main" / "e1.json").read_text())["scored"] is True
    assert json.loads((tmp_path / "main" / "index.json").read_text())["runs"][0]["scored"] is True


def test_to_main_malformed_index_writes_nothing(tmp_path):
    _write(tmp_path / "main" / "index.json", "{not json")
    src = _write(tmp_path / "out" / "e1.json", _man())
    with pytest.raises(ValueError):
        media.to_main(tmp_path / "main", src)
    assert sorted(p.name for p in (tmp_path / "main").iterdir()) == ["index.json"]


def _keeps(tmp_path, main_obj):
    main = tmp_path / "main.json"
    if main_obj is not None:
        _write(main, main_obj)
    new = _write(tmp_path / "new.json", _man(scored=False))
    return subprocess.run([sys.executable, "-m", "pwa.media", "keeps-official", str(main), str(new)], cwd=ROOT).returncode


def test_keeps_official_cli(tmp_path):
    assert _keeps(tmp_path, _man(scored=True)) == 0
    assert _keeps(tmp_path / "e", "") == 1  # empty file: main has no manifest for EXP
    assert _keeps(tmp_path / "a", None) == 1
    assert _keeps(tmp_path / "b", _man(scored=False)) == 1
    assert _keeps(tmp_path / "c", "{broken") == 0  # unknown state keeps what is published


def _env(tmp_path, **kw):
    env = dict(os.environ, RUNNER_TEMP=str(tmp_path / "rt"), EXP="e1", MAIN_DIR=str(tmp_path / "main"),
               PYTHONPATH=str(ROOT), **kw)
    env["PATH"] = f"{tmp_path / 'bin'}:{Path(sys.executable).parent}:{env['PATH']}"
    return env


def test_scenes_to_main_script_skips_downgrade(tmp_path):
    official = _man(scored=True)
    _write(tmp_path / "main" / "results" / "media" / "e1.json", official)
    _write(tmp_path / "rt" / "media" / "e1.json", _man(scored=False))
    (tmp_path / "rt" / "media" / ".published").touch()
    (tmp_path / "bin").mkdir()
    r = subprocess.run(["bash", str(SCRIPTS / "scenes_to_main.sh")], env=_env(tmp_path), cwd=ROOT)
    assert r.returncode == 0
    assert json.loads((tmp_path / "main" / "results" / "media" / "e1.json").read_text()) == official
    assert not (tmp_path / "main" / "results" / "media" / "index.json").exists()


def test_scenes_to_main_script_failure_leaves_no_orphan(tmp_path):
    _write(tmp_path / "main" / "results" / "media" / "index.json", "{bad")
    _write(tmp_path / "rt" / "media" / "e1.json", _man())
    (tmp_path / "rt" / "media" / ".published").touch()
    (tmp_path / "bin").mkdir()
    r = subprocess.run(["bash", str(SCRIPTS / "scenes_to_main.sh")], env=_env(tmp_path), cwd=ROOT, capture_output=True)
    assert r.returncode != 0
    assert not (tmp_path / "main" / "results" / "media" / "e1.json").exists()


def _stub(path: Path, body: str):
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _publish(tmp_path, new_scored: bool, main_manifest, fetch_ok=True, stage="score-only"):
    """Run publish_scenes.sh with pwa, gh and git stubbed. Returns (gh call log, .published exists)."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    new = json.dumps(_man(scored=new_scored))
    # pwa media EXP --out DIR ...: writes the manifest, notes, SCENES.md and one clip
    _stub(bin_ / "pwa", f"""out="$4"; mkdir -p "$out"; echo '{new}' > "$out/$2.json"
echo notes > "$out/RELEASE_NOTES.md"; echo scenes > "$out/SCENES.md"; echo clip > "$out/GC005.mp4"\n""")
    _stub(bin_ / "gh", f'echo "$*" >> "{tmp_path}/gh.log"\n[[ "$1 $2" != "release view" ]]\n')
    main_body = "exit 1" if main_manifest is None else f"echo '{json.dumps(main_manifest)}'"
    _stub(bin_ / "git", f"""case "$1" in
  fetch) {'exit 0' if fetch_ok else 'exit 1'};;
  show) {main_body};;
esac\n""")
    work = tmp_path / "work"
    (work / "runs" / "e1").mkdir(parents=True)
    env = _env(tmp_path, GITHUB_REPOSITORY="o/r", GITHUB_REPOSITORY_OWNER="o", GITHUB_SHA="abc",
               GITHUB_STEP_SUMMARY=str(tmp_path / "summary.md"), STAGE=stage, JUDGE_IN="judge-x:low",
               JUDGE_SLUG="judge-x-low", RUNNER_IN="lingbot_world2", ACTION_SOURCE="agent")
    r = subprocess.run(["bash", str(SCRIPTS / "publish_scenes.sh")], env=env, cwd=work, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    log = (tmp_path / "gh.log").read_text() if (tmp_path / "gh.log").exists() else ""
    return log, (tmp_path / "rt" / "media" / ".published").exists()


def test_publish_screening_keeps_official_release(tmp_path):
    log, published = _publish(tmp_path, new_scored=False, main_manifest=_man(scored=True))
    assert log == "" and not published
    assert not (tmp_path / "rt" / "media" / "e1.json").exists()


def test_publish_screening_unreadable_main_publishes_nothing(tmp_path):
    log, published = _publish(tmp_path, new_scored=False, main_manifest=None, fetch_ok=False)
    assert log == "" and not published


def test_publish_screening_without_official_scenes(tmp_path):
    log, published = _publish(tmp_path, new_scored=False, main_manifest=None)  # main has no manifest for EXP
    assert "release create" in log and published


def test_publish_scored_run_skips_main_check(tmp_path):
    log, published = _publish(tmp_path, new_scored=True, main_manifest=_man(scored=True), fetch_ok=False)
    assert "release create" in log and published


def test_scenes_to_main_script_reads_scenes_dir(tmp_path):
    # arms.yml publishes each arm from its own directory: SCENES_DIR=$RUNNER_TEMP/media/NAME EXP=NAME
    arm = tmp_path / "rt" / "media" / "g-a1"
    _write(arm / "g-a1.json", _man("g-a1", scored=False))
    (arm / ".published").touch()
    (tmp_path / "bin").mkdir()
    env = _env(tmp_path, SCENES_DIR=str(arm))
    env["EXP"] = "g-a1"
    r = subprocess.run(["bash", str(SCRIPTS / "scenes_to_main.sh")], env=env, cwd=ROOT)
    assert r.returncode == 0
    media_dir = tmp_path / "main" / "results" / "media"
    assert json.loads((media_dir / "g-a1.json").read_text())["exp"] == "g-a1"
    assert [x["exp"] for x in json.loads((media_dir / "index.json").read_text())["runs"]] == ["g-a1"]


def _arm_man(exp, videos):
    return {"exp": exp, "tasks": [{"task_id": t, "video": f"https://dl.test/{exp}/{t}.mp4" if v else None}
                                  for t, v in videos.items()]}


def test_compare_url_names_up_to_three_slots():
    assert (media.compare_url("https://s.test/base/", "GC036", ["g-a1", "g-a2"])
            == "https://s.test/base/?compare=GC036&a=g-a1&b=g-a2#compare-clips")
    assert media.compare_url("https://s.test", "GC0", ["x", "y", "z", "w"]).endswith("a=x&b=y&c=z#compare-clips")


def test_arms_md_links_every_arm_and_compares_against_arm_one():
    site = "https://benceruleanlu.github.io/playworld-advancement/"
    mans = [_arm_man("g-a1", {"GC036": True, "GC005": True}), _arm_man("g-a2", {"GC036": True, "GC005": False}),
            _arm_man("g-a3", {"GC036": True, "GC005": True}), _arm_man("g-a4", {"GC036": True, "GC005": False})]
    md = media.arms_md(site, mans)
    gc36 = next(x for x in md.splitlines() if x.startswith("| GC036 |"))
    assert f"[g-a1]({site}?scenes=g-a1&scene=GC036#scenes)" in gc36 and "[g-a4](" in gc36
    # three slots: arm 1 is a= in every link, the others fill b= / c=
    assert f"({site}?compare=GC036&a=g-a1&b=g-a2&c=g-a3#compare-clips)" in gc36
    assert f"[g-a1 vs g-a4]({site}?compare=GC036&a=g-a1&b=g-a4#compare-clips)" in gc36
    gc5 = next(x for x in md.splitlines() if x.startswith("| GC005 |"))
    assert "g-a2" not in gc5 and f"({site}?compare=GC005&a=g-a1&b=g-a3#compare-clips)" in gc5
    one = media.arms_md(site, [_arm_man("h-a1", {"GC005": True})])
    assert one.rstrip().endswith(f"| GC005 | [h-a1]({site}?scenes=h-a1&scene=GC005#scenes) | - |")


def test_arms_md_cli(tmp_path):
    a = _write(tmp_path / "a.json", _arm_man("g-a1", {"GC036": True}))
    b = _write(tmp_path / "b.json", _arm_man("g-a2", {"GC036": True}))
    r = subprocess.run([sys.executable, "-m", "pwa.media", "arms-md", "https://s.test/", str(a), str(b)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and "https://s.test/?compare=GC036&a=g-a1&b=g-a2#compare-clips" in r.stdout
