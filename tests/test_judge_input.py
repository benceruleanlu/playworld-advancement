"""judge_model input of experiment.yml and arms.yml: the default is the Luna proxy judge (openai:gpt-6-luna, user
decision Nov 15), and "gemini" or an empty value is the official Gemini 3.1 Pro path exactly as before the default
changed. .github/scripts/judge_specs.sh normalises the input; every later step reads its output, never the raw input,
so the official csv row can only come from the official judge. No GitHub, no Modal."""
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
SPECS = ROOT / ".github" / "scripts" / "judge_specs.sh"
LUNA = "openai:gpt-6-luna"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _steps(name: str) -> dict:
    """step name -> {if, env (raw text), run} (PyYAML is not a dependency)."""
    lines = (WF / name).read_text().splitlines()
    out, cur, i = {}, None, 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^      - name:\s*(.*)$", line)
        if m:
            cur = out.setdefault(m.group(1).strip(), {"env": ""})
        elif line.startswith("      - "):  # an unnamed step (e.g. `- uses:`) ends the previous one
            cur = None
        elif cur is not None and (m := re.match(r"^        (if|env|run):\s?(.*)$", line)):
            key, val = m.groups()
            if key in ("env", "run") and val in ("", "|"):
                body = []
                i += 1
                while i < len(lines) and (lines[i].startswith("          ") or not lines[i].strip()):
                    body.append(lines[i])
                    i += 1
                cur[key] = textwrap.dedent("\n".join(body)).strip() + "\n"
                continue
            cur[key] = val.strip()
        i += 1
    return out


def _input_default(name: str, key: str) -> str:
    text = (WF / name).read_text()
    m = re.search(rf"^      {key}:\n(?:        .*\n)*?        default: (.*)$", text, flags=re.M)
    return m.group(1).strip().strip('"')


def _specs(value):
    return subprocess.run([str(SPECS), value], capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("value", ["", "gemini", "GEMINI", " gemini "])
def test_gemini_and_empty_are_the_official_judge(value):
    r = _specs(value)
    assert r.returncode == 0 and r.stdout == "", (r.stdout, r.stderr)


@pytest.mark.parametrize("value, want", [
    (LUNA, LUNA),
    ("gemini-4-hydrogen:low, openai:gpt-6-luna", "gemini-4-hydrogen:low openai:gpt-6-luna"),
    ("gemini:gemini-3.1-pro-preview", "gemini:gemini-3.1-pro-preview"),  # a named Gemini model is a screening judge
    ("openai:A,openai:a", "openai:A openai:a"),  # model names are case-sensitive, so these are two judges
])
def test_screening_judges_pass_through(value, want):
    r = _specs(value)
    assert r.returncode == 0 and r.stdout.strip() == want, r.stderr


@pytest.mark.parametrize("value", ["gemini,openai:gpt-6-luna", "a,,b", "x;y", "a,a", ",", "openai:bad/model",
                                   "openai:gpt-6-luna:HIGH", "gemini:x:Low", "Gemini,openai:x"])
def test_bad_values_are_refused(value):
    assert _specs(value).returncode == 2


def test_both_workflows_default_to_luna():
    assert _input_default("experiment.yml", "judge_model") == LUNA
    assert _input_default("arms.yml", "judge_model") == LUNA


def test_experiment_reads_judge_input_only_in_the_first_step_and_the_title():
    text = (WF / "experiment.yml").read_text()
    uses = [ln for ln in text.splitlines() if "inputs.judge_model" in ln]
    assert len(uses) == 2, uses
    assert uses[0].startswith("run-name:") and "inputs.judge_model != 'gemini'" in uses[0]
    assert uses[1].strip() == "JUDGE_IN: ${{ inputs.judge_model }}"
    steps = _steps("experiment.yml")
    assert "JUDGE_IN: ${{ inputs.judge_model }}" in steps["Validate experiment name"]["env"]
    # official row only without screening specs; screening (incl. the Luna default) commits its own report
    assert steps["Commit experiment log"]["if"] == "inputs.stage != 'gen-only' && env.JUDGE_SPECS == ''"
    assert steps["Commit screening report"]["if"] == "inputs.stage != 'gen-only' && env.JUDGE_SPECS != ''"
    assert "env.JUDGE_SPECS != ''" in steps["Mark final status on main"]["if"]
    assert "JUDGE_IN: ${{ env.JUDGE_LIST }}" in steps["Publish scenes (GitHub Release run-EXP)"]["env"]


def _validate(tmp_path, value):
    step = _steps("experiment.yml")["Validate experiment name"]
    genv = tmp_path / "genv"
    genv.write_text("")
    env = {**os.environ, "EXP": "x", "JUDGE_IN": value, "CAP_IN": "", "ACTION_SOURCE": "agent", "GITHUB_ENV": str(genv)}
    r = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    vals = dict(ln.split("=", 1) for ln in genv.read_text().splitlines() if "=" in ln)
    return r, vals


@pytest.mark.parametrize("value", ["", "gemini", "Gemini"])
def test_experiment_validate_official(tmp_path, value):
    r, vals = _validate(tmp_path, value)
    assert r.returncode == 0, r.stderr
    assert "JUDGE_SPECS" not in vals and "JUDGE_LIST" not in vals  # every later step takes the official path
    assert "official judge" in r.stdout


def test_experiment_validate_default_is_proxy(tmp_path):
    r, vals = _validate(tmp_path, _input_default("experiment.yml", "judge_model"))
    assert r.returncode == 0, r.stderr
    assert vals["JUDGE_SPECS"] == LUNA and vals["JUDGE_LIST"] == LUNA


def test_experiment_validate_refuses_mixing_gemini(tmp_path):
    r, _ = _validate(tmp_path, "gemini,openai:gpt-6-luna")
    assert r.returncode != 0


def test_screening_commit_sends_openai_specs_to_the_proxy_csv_only():
    run = _steps("experiment.yml")["Commit screening report"]["run"]
    assert '--proxy "${proxy_args[@]}" --into "$MAIN_DIR/results/proxy_experiments.csv"' in run
    assert "experiments.csv" not in run.replace("proxy_experiments.csv", "")


def _arms_dispatch(tmp_path, judge):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "gh.log"
    (bin_ / "gh").write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "{log}"\n')
    (bin_ / "sleep").write_text("#!/usr/bin/env bash\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    rt = tmp_path / "rt"
    rt.mkdir()
    (rt / "owned.txt").write_text("g-a1 1/1 base\n")
    (tmp_path / "runs" / "g-a1" / "videos" / "GC005").mkdir(parents=True)
    (tmp_path / "runs" / "g-a1" / "videos" / "GC005" / "GC005.mp4").write_bytes(b"")
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "RUNNER_TEMP": str(rt),
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"), "GITHUB_REF_NAME": "main", "SPLIT": "dev",
           "TASKS": "GC005", "RUNNER": "lingbot_world2_1p3b", "ACTION_SOURCE": "agent", "PASSES": "2",
           "JUDGE": judge, "PLAYER_MODEL_IN": "gpt-6-luna", "GPU": "H100"}
    step = next(s for n, s in _steps("arms.yml").items() if n.startswith("Dispatch one score-only"))
    r = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=tmp_path, env=env, capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0, r.stderr
    return log.read_text().splitlines()


@pytest.mark.parametrize("judge, sent", [(LUNA, LUNA), ("gemini-4-hydrogen:low,openai:gpt-6-luna",
                                                           "gemini-4-hydrogen:low,openai:gpt-6-luna"),
                                         ("", "gemini")])
def test_arms_dispatch_passes_the_judge(tmp_path, judge, sent):
    argv = _arms_dispatch(tmp_path, judge)
    assert argv[:3] == ["workflow", "run", "experiment.yml"]
    assert f"judge_model={sent}" in argv and "stage=score-only" in argv and "exp=g-a1" in argv
    # one argument per -f value: nothing was split by the quoting
    assert all(argv[i] == "-f" for i in range(5, len(argv), 2)), argv


def test_arms_normalises_the_judge_before_generation(tmp_path):
    steps = _steps("arms.yml")
    val = steps["Validate names and list arms"]
    assert "JUDGE_IN: ${{ inputs.judge_model }}" in val["env"] and ".github/scripts/judge_specs.sh" in val["run"]
    disp = next(s for n, s in steps.items() if n.startswith("Dispatch one score-only"))
    assert "JUDGE: ${{ env.ARMS_JUDGE }}" in disp["env"] and "JUDGE: ${{ env.ARMS_JUDGE }}" in \
        steps["Publish arm videos (GitHub Releases run-EXP-aN)"]["env"]
    text = (WF / "arms.yml").read_text()
    assert [ln.strip() for ln in text.splitlines() if "inputs.judge_model" in ln] == ["JUDGE_IN: ${{ inputs.judge_model }}"]
    # the normalisation lines, run as the step runs them
    lines = [ln for ln in val["run"].splitlines() if "judge_specs.sh" in ln or "ARMS_JUDGE=" in ln]
    for value, want in [("gemini", ""), ("", ""), (LUNA, LUNA), ("a:low, b", "a:low,b")]:
        genv = tmp_path / "genv"
        env = {**os.environ, "JUDGE_IN": value, "GITHUB_ENV": str(genv)}
        r = subprocess.run(["bash", "-e", "-c", "\n".join(lines)], cwd=ROOT, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert genv.read_text() == f"ARMS_JUDGE={want}\n"
        genv.unlink()
