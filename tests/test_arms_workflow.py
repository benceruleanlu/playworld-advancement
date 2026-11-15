""".github/workflows/arms.yml: a failed arm or task must not hide the arms that generated. Step conditions are
checked structurally; the publish loop runs for real with stub `pwa` and `gh` on PATH. No GitHub, no Modal."""
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
    for chunk in re.split(r"^      - (?=name: )", text, flags=re.M)[1:]:
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
    for name in ("Fetch arms", "Publish arm videos", "Dispatch one score-only"):
        cond = _step(name)["if"]
        assert "!cancelled()" in cond and "steps.gen.outcome == 'failure'" in cond, name
    assert _step("Mark final status")["if"] == "always()"


def test_generate_and_listing_use_the_same_shared_args():
    assert '"$ARMS_EXTRA"' in _step("Generate all arms")["run"] and "EXTRA" not in _step("Generate all arms")["env"]
    assert 'python -m pwa.arms "$EXP" "$ARMS" "$EXTRA"' in _step("Validate names")["run"]


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_publish_one_failing_arm_does_not_stop_the_others(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    # pwa media: fails for arm 1 (corrupt mp4), writes a clip and notes for the others
    (bin_ / "pwa").write_text("""#!/usr/bin/env bash
name="$2"; out="$4"
[[ "$name" == g-a1 ]] && { echo "ffmpeg failed" >&2; exit 1; }
mkdir -p "$out"; touch "$out/GC005.mp4" "$out/GC005.jpg"; echo "Unscored rollouts from $name." > "$out/RELEASE_NOTES.md"
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
    (rt / "arms.txt").write_text("g-a1 1/3 base\ng-a2 2/3 --x\ng-a3 3/3 --y\n")
    summary = tmp_path / "summary.md"
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "RUNNER_TEMP": str(rt), "GITHUB_STEP_SUMMARY": str(summary),
           "GITHUB_REPOSITORY": "o/r", "GITHUB_SHA": "abc", "EXP": "g", "STAGE": "gen-only", "JUDGE": ""}
    r = subprocess.run(["bash", "-e", "-c", _step("Publish arm videos")["run"]], env=env, capture_output=True, text=True)
    assert r.returncode == 1  # surfaced, though continue-on-error keeps the job going
    text = summary.read_text()
    assert "| g-a3 | `--y` | GC005 |" in text and "g-a1 |" not in text and "Not published: g-a1 g-a2" in text
    assert "release create run-g-a3" in (tmp_path / "gh.log").read_text()
    notes = (rt / "media" / "g-a3" / "NOTES.md").read_text()
    assert "stage=gen-only and does not score them" in notes and "Unscored rollouts from g-a3." in notes
