"""Every `.github/scripts/push_results.sh MESSAGE SNIPPET` call in .github/workflows/*.yml must pass the whole
snippet as one argument. An apostrophe inside a single-quoted snippet (even in a `#` comment) closes the quote
early: bash then splits the rest into extra arguments, the snippet push_results.sh runs is a fragment (often a
lone comment), nothing is staged, and the step succeeds with nothing on main. Each call runs here under bash with
a stub push_results.sh that records its arguments, so the check sees exactly what bash passes."""
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CALL = ".github/scripts/push_results.sh"

# (workflow, step name) -> strings the snippet must contain. Include the snippet's last command: a quote that
# closes early drops the tail. A new call site must be added here.
EXPECTED = {
    ("arms.yml", "Mark arms running on main"): ['python -m pwa.cli mark "$name" --status running',
                                                'done 3< "$RUNNER_TEMP/arms.txt"'],
    ("arms.yml", "Commit arm scenes to main"): [".github/scripts/scenes_to_main.sh",
                                                'cat "$RUNNER_TEMP/media/$name/SCENES.md"',
                                                'done 3< "$RUNNER_TEMP/published.txt"'],
    ("arms.yml", "Mark final status on main"): ['python -m pwa.cli mark "$name" --status "$status"', "done"],
    ("experiment.yml", "Mark running on main"): ['python -m pwa.cli mark "$EXP" --status running',
                                                 '--max-chunks "$MARK_CAP"'],
    ("experiment.yml", "Commit screening report"): [
        'pwa upsert-row "$EXP" --proxy "${proxy_args[@]}" --into "$MAIN_DIR/results/proxy_experiments.csv"',
        'cp "$RUNNER_TEMP/screening/$slug.md" "$dest"',
        '.github/scripts/scenes_to_main.sh || echo "::warning::scenes manifest not committed"'],
    ("experiment.yml", "Commit scenes (gen-only)"): ['cp "$RUNNER_TEMP/report.md" "$MAIN_DIR/results/reports/$EXP.md"',
                                                     ".github/scripts/scenes_to_main.sh"],
    ("experiment.yml", "Commit experiment log"): ['pwa upsert-row "$EXP" --into "$MAIN_DIR/results/experiments.csv"',
                                                  'cp "$RUNNER_TEMP/report.md" "$MAIN_DIR/results/reports/$EXP.md"',
                                                  ".github/scripts/scenes_to_main.sh"],
    ("experiment.yml", "Mark final status on main"): ['python -m pwa.cli mark "$EXP" --status "$STATUS"'],
    ("translate.yml", "Translate and commit to main"): ['pwa translate-media --dir "$MAIN_DIR/results/media"',
                                                        'unexpected change outside results/media'],
}


def _run_blocks(path: Path):
    """(step name, run script) for each `run: |` block of a workflow (PyYAML is not a dependency)."""
    lines = path.read_text().splitlines()
    name = None
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*- name:\s*(.*)$", lines[i])
        if m:
            name = m.group(1).strip().strip("'\"")
        m = re.match(r"^(\s*)(?:- )?run:\s*\|\s*$", lines[i])
        if m:
            indent = len(m.group(1))
            body = []
            i += 1
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
                body.append(lines[i])
                i += 1
            yield name, textwrap.dedent("\n".join(body)).strip("\n") + "\n"
            continue
        i += 1


def _calls():
    out = []
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        for name, script in _run_blocks(wf):
            start = 0
            while (k := script.find(CALL, start)) >= 0:
                out.append((wf.name, name, script, k))
                start = k + len(CALL)
    return out


CALLS = _calls()


def _bash_args(command: str, tmp_path: Path) -> list:
    """The arguments bash passes to push_results.sh for `command` (the script text from the call onward). The
    stub exits the shell after the first call, so whatever follows is never run."""
    out = tmp_path / "args.bin"
    stub = f'push_results() {{ printf "%s\\0" "$@" > "{out}"; exit 0; }}\n'
    script = stub + command.replace(CALL, "push_results", 1)
    subprocess.run(["bash", "-c", script], check=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=30)
    return out.read_bytes().decode().split("\0")[:-1]


def test_every_call_site_is_listed():
    found = {(wf, name) for wf, name, _, _ in CALLS}
    assert found == set(EXPECTED), (
        f"push_results.sh call sites changed; update EXPECTED: new {found - set(EXPECTED)}, "
        f"gone {set(EXPECTED) - found}")
    assert len(CALLS) == len(EXPECTED), "one push_results.sh call per step"


@pytest.mark.parametrize("wf,name,script,k", CALLS, ids=[f"{c[0]}:{c[1]}" for c in CALLS])
def test_snippet_reaches_push_results_whole(wf, name, script, k, tmp_path):
    args = _bash_args(script[k:], tmp_path)
    assert len(args) == 2, f"{wf} {name!r}: push_results.sh got {len(args)} arguments, want 2: {args}"
    snippet = args[1]
    # the snippet as written, byte for byte: an apostrophe pair inside it would be silently dropped otherwise
    assert f"'{snippet}'" in script, f"{wf} {name!r}: the snippet is not one single-quoted string"
    for want in EXPECTED[(wf, name)]:
        assert want in snippet, f"{wf} {name!r}: snippet lost {want!r}; got:\n{snippet}"
    # the snippet must parse on its own
    subprocess.run(["bash", "-n", "-c", snippet], check=True, timeout=30)


def test_stub_sees_the_quote_bug(tmp_path):
    """The check above fails on the bug it guards against."""
    bad = (f"{CALL} \"msg\" '\n  # this run's rows, not main's\n  cp a b'\n")
    args = _bash_args(bad, tmp_path)
    assert len(args) != 2 or "cp a b" not in args[1] or f"'{args[1]}'" not in bad
