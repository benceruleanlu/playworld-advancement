""".github/workflows/arms.yml: a failed arm or task must not hide the arms that generated. Step conditions are
checked structurally; the publish loop runs for real with stub `pwa` and `gh` on PATH. No GitHub, no Modal."""
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _steps() -> dict:
    """name -> {id, if, env (raw text), run} for each `- name:` step (PyYAML is not a dependency; this file's
    steps are plain `key: value` lines plus one `run: |` block)."""
    text = (ROOT / ".github" / "workflows" / "arms.yml").read_text()
    out = {}
    for chunk in re.split(r"^      - ", text, flags=re.M)[1:]:
        if not chunk.startswith("name: "):
            continue
        lines = chunk.splitlines()
        step = {"name": lines[0][len("name: "):].strip()}
        i = 1
        while i < len(lines):
            m = re.match(r"^        (id|if|env|run):\s?(.*)$", lines[i])
            if m and m.group(1) == "run" and m.group(2) == "|":
                body = []
                i += 1
                while i < len(lines) and (lines[i].startswith("          ") or not lines[i].strip()):
                    body.append(lines[i])
                    i += 1
                step["run"] = textwrap.dedent("\n".join(body)).strip() + "\n"
                continue
            if m and m.group(1) == "env":
                env = []
                i += 1
                while i < len(lines) and lines[i].startswith("          "):
                    env.append(lines[i].strip())
                    i += 1
                step["env"] = "\n".join(env)
                continue
            if m:
                step[m.group(1)] = m.group(2).strip()
            i += 1
        out[step["name"]] = step
    return out


STEPS = _steps()


def _step(prefix):
    return next(s for n, s in STEPS.items() if n.startswith(prefix))


def test_steps_after_generate_run_when_it_failed():
    gen = _step("Generate all arms")
    assert gen["id"] == "gen"
    for name in ("Fetch arms", "Publish arm videos", "Commit arm scenes", "Dispatch one score-only"):
        cond = _step(name)["if"]
        assert "!cancelled()" in cond and "steps.gen.outcome == 'failure'" in cond, name
        # ... but never when modal_app.py refused the launch (reused name): nothing of this run exists then
        assert "steps.gen.outputs.started == 'true'" in cond, name
    assert _step("Mark arms running")["id"] == "mark"
    cond = _step("Mark final status")["if"]
    assert "always()" in cond and "steps.mark.outcome == 'failure'" in cond
    # publish and dispatch read only the arms the fetch step proved are this run's
    for name in ("Publish arm videos", "Dispatch one score-only"):
        assert '3< "$RUNNER_TEMP/owned.txt"' in _step(name)["run"] and "arms.txt" not in _step(name)["run"], name


def test_volume_name_check_runs_before_any_csv_row():
    names = list(STEPS)
    assert names.index("Refuse arm names already in the pwa-runs Volume") < names.index("Mark arms running on main")
    assert "if" not in _step("Refuse arm names")


def _stub(bin_, name, body):
    bin_.mkdir(exist_ok=True)
    (bin_ / name).write_text("#!/usr/bin/env bash\n" + body)
    (bin_ / name).chmod(0o755)


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("claims, rc, started", [(False, 1, False), (True, 1, True), (True, 0, True)])
def test_generate_reports_started_only_after_the_guard(tmp_path, claims, rc, started):
    # modal stub: modal_app.py writes the claim file only once its overwrite guard passed
    claim = tmp_path / "claimed.txt"
    _stub(tmp_path / "bin", "modal", (f'printf "g-a1\\n" > "$PWA_CLAIM_FILE"\n' if claims else "") + f"exit {rc}\n")
    claim.write_text("stale\n")  # from an earlier attempt: must not count
    out = tmp_path / "out"
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "PWA_CLAIM_FILE": str(claim),
           "GITHUB_OUTPUT": str(out)}
    r = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", _step("Generate all arms")["run"]], env=env,
                       capture_output=True, text=True)
    assert r.returncode == rc
    assert ("started=true" in (out.read_text() if out.exists() else "")) == started


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_fetch_keeps_only_arms_this_run_generated(tmp_path):
    vol = tmp_path / "vol"
    for name, rid in (("g-a1", "7-1"), ("g-a2", "6-1"), ("g-a3", "7-1")):
        (vol / name / "videos" / "GC005").mkdir(parents=True)
        (vol / name / "meta.json").write_text(json.dumps({"exp": name, "run_id": rid}))
    # modal volume get pwa-runs /NAME runs/ --force
    _stub(tmp_path / "bin", "modal", f'cp -r "{vol}$4" "$5"\n')
    rt = tmp_path / "rt"
    rt.mkdir()
    (rt / "arms.txt").write_text("g-a1 1/4 base\ng-a2 2/4 --x\ng-a3 3/4 --y\ng-a4 4/4 --z\n")
    (rt / "claimed.txt").write_text("g-a1\ng-a2\ng-a4\n")  # g-a3 not claimed; g-a4 claimed but never written
    work = tmp_path / "work"
    work.mkdir()
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "RUNNER_TEMP": str(rt),
           "PWA_RUN_ID": "7-1", "PWA_RUNS": str(work / "runs"), "PYTHONPATH": str(ROOT)}
    r = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", _step("Fetch arms")["run"]], env=env, cwd=work,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (rt / "owned.txt").read_text() == "g-a1 1/4 base\n", r.stdout + r.stderr
    assert sorted(p.name for p in (work / "runs").iterdir()) == ["g-a1"]
    assert "g-a2: its meta.json is not from this run" in r.stdout and "g-a3: not claimed" in r.stdout


def test_generate_and_listing_use_the_same_shared_args():
    assert '"$ARMS_EXTRA"' in _step("Generate all arms")["run"] and "EXTRA" not in _step("Generate all arms")["env"]
    assert 'python -m pwa.arms "$EXP" "$ARMS" "$EXTRA"' in _step("Validate names")["run"]


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_publish_one_failing_arm_does_not_stop_the_others(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    # pwa media: fails for arm 1 (corrupt mp4), writes a clip and notes for the others
    (bin_ / "pwa").write_text(f"""#!/usr/bin/env bash
printf '%s\\n' "$@" >> {tmp_path}/pwa.log
name="$2"; out="$4"
[[ "$name" == g-a1 ]] && {{ echo "ffmpeg failed" >&2; exit 1; }}
mkdir -p "$out"; touch "$out/GC005.mp4" "$out/GC005.jpg" "$out/$name.json"
echo "Unscored rollouts from $name." > "$out/RELEASE_NOTES.md"
""")
    # gh: no release exists yet; create fails for arm 2
    (bin_ / "gh").write_text(f"""#!/usr/bin/env bash
echo "$*" >> {tmp_path}/gh.log
[[ "$1 $2" == "release view" ]] && exit 1
[[ "$1 $2 $3" == "release create run-g-a2" ]] && exit 1
exit 0
""")
    for f in bin_.iterdir():
        f.chmod(0o755)
    rt = tmp_path / "rt"
    rt.mkdir()
    (rt / "owned.txt").write_text("g-a1 1/3 base\ng-a2 2/3 --x\ng-a3 3/3 --y\n")
    summary = tmp_path / "summary.md"
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "RUNNER_TEMP": str(rt), "GITHUB_STEP_SUMMARY": str(summary),
           "GITHUB_REPOSITORY": "o/r", "GITHUB_REPOSITORY_OWNER": "o", "GITHUB_SHA": "abc", "EXP": "g",
           "STAGE": "gen-only", "JUDGE": ""}
    r = subprocess.run(["bash", "-e", "-c", _step("Publish arm videos")["run"]], env=env, capture_output=True, text=True)
    assert r.returncode == 1  # surfaced, though continue-on-error keeps the job going
    text = summary.read_text()
    assert "| g-a3 | `--y` | GC005 | [play](https://o.github.io/r/?scenes=g-a3&scene=GC005#scenes) |" in text
    assert "g-a1 |" not in text and "Not published: g-a1 g-a2" in text
    assert "release create run-g-a3" in (tmp_path / "gh.log").read_text()
    # only the arm whose every upload succeeded is marked for the commit step
    assert (rt / "published.txt").read_text() == "g-a3 3/3 --y\n"
    assert (rt / "media" / "g-a3" / ".published").exists() and not (rt / "media" / "g-a2" / ".published").exists()
    pwa_args = (tmp_path / "pwa.log").read_text().split("\n")
    assert "--label" in pwa_args and "arm 3/3 of g: --y" in pwa_args and "https://o.github.io/r/" in pwa_args
    notes = (rt / "media" / "g-a3" / "NOTES.md").read_text()
    assert "stage=gen-only and does not score them" in notes and "Unscored rollouts from g-a3." in notes


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("claims, rc, started", [(False, 2, False), (True, 1, True), (True, 0, True)])
def test_warm_generate_reports_started_the_same_way(tmp_path, claims, rc, started):
    # warm=on runs `python -m pwa.warm run`, which (like modal_app.py) writes the claim file after its guard
    claim = tmp_path / "claimed.txt"
    args = tmp_path / "args.txt"
    _stub(tmp_path / "bin", "python", f'printf "%s\\n" "$@" > "{args}"\n'
          + ('printf "g-a1\\n" > "$PWA_CLAIM_FILE"\n' if claims else "") + f"exit {rc}\n")
    _stub(tmp_path / "bin", "modal", "echo modal must not run with warm=on >&2; exit 9\n")
    out = tmp_path / "out"
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "PWA_CLAIM_FILE": str(claim),
           "GITHUB_OUTPUT": str(out), "WARM": "on", "NUM_SHARDS": "1", "EXP": "g", "ARMS": "base",
           "ARMS_EXTRA": " --agent-model m", "RUNNER_TEMP": str(tmp_path)}
    r = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", _step("Generate all arms")["run"]], env=env,
                       capture_output=True, text=True)
    assert r.returncode == rc, r.stderr
    assert ("started=true" in (out.read_text() if out.exists() else "")) == started
    argv = args.read_text().splitlines()
    assert argv[:3] == ["-m", "pwa.warm", "run"] and "--extra= --agent-model m" in argv


def test_warm_generate_gets_the_claim_file_and_run_id():
    gen = _step("Generate all arms")
    assert "PWA_CLAIM_FILE:" in gen["env"] and "PWA_RUN_ID:" in gen["env"] and "WARM:" in gen["env"]
    assert "if" not in gen  # one step for both paths, so fetch, publish and dispatch gate on the same output


def test_arm_scenes_reach_main_before_scoring_is_dispatched():
    names = list(STEPS)
    i = names.index("Commit arm scenes to main")
    assert names.index("Publish arm videos (GitHub Releases run-EXP-aN)") < i < names.index(
        "Dispatch one score-only experiment run per arm")
    run = _step("Commit arm scenes")["run"]
    # the same path as experiment.yml, per arm, and only arms whose clips were all uploaded
    assert ".github/scripts/scenes_to_main.sh" in run and '3< "$RUNNER_TEMP/published.txt"' in run
    assert "owned.txt" not in run and "arms.txt" not in run


def _arm_manifest(name, scored=False, video=True):
    return {"exp": name, "generated": "2026-11-15T00:00:00Z", "release_url": f"https://r.test/{name}", "scored": scored,
            "labels": [] if scored else ["not scored", f"arm of g: {name}"],
            "tasks": [{"task_id": "GC036", "family": "gc", "mean": 2.0 if scored else None, "status": ["ok"],
                       "reason": "", "video": f"https://r.test/{name}/GC036.mp4" if video else None, "poster": None}]}


def _commit_env(tmp_path, push_body):
    """RUNNER_TEMP and a work dir whose .github/scripts has the real scenes_to_main.sh and a push_results.sh stub."""
    rt, work = tmp_path / "rt", tmp_path / "work"
    scripts = work / ".github" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(ROOT / ".github" / "scripts" / "scenes_to_main.sh", scripts)
    _stub(scripts, "push_results.sh", push_body)
    summary = tmp_path / "summary.md"
    env = {**os.environ, "RUNNER_TEMP": str(rt), "GITHUB_STEP_SUMMARY": str(summary), "EXP": "g",
           "GITHUB_REPOSITORY": "o/r", "GITHUB_REPOSITORY_OWNER": "o", "PYTHONPATH": str(ROOT)}
    return rt, work, summary, env


def _arm_out(rt, name, published=True):
    d = rt / "media" / name
    d.mkdir(parents=True)
    (d / f"{name}.json").write_text(json.dumps(_arm_manifest(name)))
    (d / "SCENES.md").write_text(f"### Scenes\n\nplay {name}\n")
    if published:
        (d / ".published").touch()


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_commit_arm_scenes_writes_manifests_index_and_links(tmp_path):
    main = tmp_path / "main"
    media = main / "results" / "media"
    media.mkdir(parents=True)
    (main / "results" / "reports").mkdir()
    # main already has the official scored scenes and report of g-a2 (e.g. its score-only run finished first)
    official = _arm_manifest("g-a2", scored=True)
    (media / "g-a2.json").write_text(json.dumps(official))
    (media / "index.json").write_text(json.dumps({"runs": [{"exp": "g-a2", "generated": "2026-11-15T00:00:00Z"}]}))
    (main / "results" / "reports" / "g-a2.md").write_text("scored report\n")
    # push_results.sh stub: run the snippet against MAIN_DIR, no git
    rt, work, summary, env = _commit_env(tmp_path, f'export MAIN_DIR="{main}"\nbash -euo pipefail -c "$2"\n')
    _arm_out(rt, "g-a1")
    _arm_out(rt, "g-a2")
    _arm_out(rt, "g-a3", published=False)  # its upload failed: not in published.txt
    (rt / "published.txt").write_text("g-a1 1/3 base\ng-a2 2/3 --x\n")
    r = subprocess.run(["bash", "-e", "-c", _step("Commit arm scenes")["run"]], env=env, cwd=work,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads((media / "g-a1.json").read_text())["exp"] == "g-a1"
    assert json.loads((media / "g-a2.json").read_text()) == official  # never downgraded
    assert not (media / "g-a3.json").exists()
    assert sorted(x["exp"] for x in json.loads((media / "index.json").read_text())["runs"]) == ["g-a1", "g-a2"]
    assert (main / "results" / "reports" / "g-a2.md").read_text() == "scored report\n"
    rep = (main / "results" / "reports" / "g-a1.md").read_text()
    assert "arm 1/3 of g, generated, not scored" in rep and "play g-a1" in rep
    text = summary.read_text()
    site = "https://o.github.io/r/"
    assert f"[g-a1]({site}?scenes=g-a1&scene=GC036#scenes)" in text
    assert f"({site}?compare=GC036&a=g-a1&b=g-a2#compare-clips)" in text and "g-a3" not in text


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_commit_arm_scenes_push_failure_is_surfaced(tmp_path):
    rt, work, summary, env = _commit_env(tmp_path, "exit 1\n")
    _arm_out(rt, "g-a1")
    (rt / "published.txt").write_text("g-a1 1/1 base\n")
    r = subprocess.run(["bash", "-e", "-c", _step("Commit arm scenes")["run"]], env=env, cwd=work,
                       capture_output=True, text=True)
    assert r.returncode == 1  # continue-on-error keeps the job going
    assert "Not committed to main" in summary.read_text()
    (rt / "published.txt").write_text("")  # nothing published: a no-op
    r = subprocess.run(["bash", "-e", "-c", _step("Commit arm scenes")["run"]], env=env, cwd=work,
                       capture_output=True, text=True)
    assert r.returncode == 0 and "nothing to commit" in r.stdout
