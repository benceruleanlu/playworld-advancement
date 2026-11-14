"""pwa mark: live run status rows (running / generated / failed / cancelled) in a results csv."""
import os
import subprocess
import sys

import pytest

from pwa import report
from test_upsert_row import OLD, ROOT, read, row, write


def rows_of(path, exp):
    return [r for r in read(path)[1] if r["exp"] == exp]


def test_running_row_then_final_upsert_replaces_it(tmp_path, monkeypatch):
    for k, v in (("GITHUB_SERVER_URL", "https://github.com"), ("GITHUB_REPOSITORY", "o/r"), ("GITHUB_RUN_ID", "7"),
                 ("GITHUB_REF_NAME", "feat/x")):
        monkeypatch.setenv(k, v)
    dest, src = tmp_path / "main.csv", tmp_path / "local.csv"
    write(dest, OLD, [row("old")])  # a csv older than the status column
    assert report.mark_row("e", dest, "running", split="custom", runner="lingbot_world2", action_source="agent",
                           notes="n", git_sha="abc") == 1
    head, _ = read(dest)
    assert "status" in head and "run_url" in head
    (r,) = rows_of(dest, "e")
    assert (r["status"], r["overall"], r["runner"], r["branch"], r["git_sha"]) == ("running", "", "lingbot_world2",
                                                                                 "feat/x", "abc")
    assert r["run_url"] == "https://github.com/o/r/actions/runs/7"
    assert report.mark_row("e", dest, "running", split="custom") == 1 and len(rows_of(dest, "e")) == 1  # refresh
    assert rows_of(dest, "old")[0]["overall"] == "1.5000"
    # the final row is reported under another split label; the running row must not be left behind
    write(src, report.CSV_FIELDS, [row("e", split="dev", status="scored")])
    report.upsert_row_into("e", src, dest)
    (r,) = rows_of(dest, "e")
    assert (r["status"], r["split"], r["overall"]) == ("scored", "dev", "1.5000")


def test_running_never_clobbers_a_scored_row(tmp_path):
    dest = tmp_path / "main.csv"
    write(dest, report.CSV_FIELDS, [row("e", status="scored")])
    assert report.mark_row("e", dest, "running", split="dev") == 0
    assert rows_of(dest, "e")[0]["status"] == "scored"
    write(dest, OLD, [row("e")])  # scored before the status column existed
    assert report.mark_row("e", dest, "running", split="dev") == 0
    assert rows_of(dest, "e")[0]["overall"] == "1.5000"


@pytest.mark.parametrize("status", ["generated", "failed", "cancelled"])
def test_final_status_only_updates_running_rows(tmp_path, status):
    dest = tmp_path / "main.csv"
    write(dest, report.CSV_FIELDS, [row("s", status="scored"), row("x")])
    report.mark_row("e", dest, "running", split="dev")
    assert report.mark_row("e", dest, status) == 1
    assert rows_of(dest, "e")[0]["status"] == status
    assert report.mark_row("e", dest, status) == 0     # no longer running: no-op
    assert report.mark_row("s", dest, status) == 0 and rows_of(dest, "s")[0]["status"] == "scored"
    assert report.mark_row("nope", dest, status) == 0  # unknown exp: nothing written
    assert rows_of(dest, "x")[0]["overall"] == "1.5000"


def test_generated_row_is_replaced_by_a_later_score(tmp_path):
    dest, src = tmp_path / "main.csv", tmp_path / "local.csv"
    report.mark_row("e", dest, "running", split="all")       # dest does not exist yet
    report.mark_row("e", dest, "generated")
    write(src, report.CSV_FIELDS, [row("e", split="all", status="scored")])
    report.upsert_row_into("e", src, dest)
    assert [r["status"] for r in rows_of(dest, "e")] == ["scored"]


def test_bad_input(tmp_path):
    with pytest.raises(ValueError, match="status"):
        report.mark_row("e", tmp_path / "m.csv", "scored")
    bad = tmp_path / "bad.csv"
    bad.write_text("exp,split\na,dev,extra\n")
    with pytest.raises(ValueError, match="fields"):
        report.mark_row("e", bad, "running")
    assert bad.read_text() == "exp,split\na,dev,extra\n"  # malformed file untouched


def test_cli_runs_without_install_or_data(tmp_path):
    dest = tmp_path / "e.csv"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "PWA_"))}
    cmd = [sys.executable, "-m", "pwa.cli", "mark", "e", "--into", str(dest), "--status", "running", "--split", "dev",
           "--runner", "sana", "--action-source", "dataset", "--notes", "a, \"quoted\" note"]
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    (got,) = rows_of(dest, "e")
    assert got["status"] == "running" and got["notes"] == 'a, "quoted" note' and got["run_url"] == ""
    r = subprocess.run([*cmd[:7], "bogus"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 2


def test_score_only_refresh_keeps_generation_metadata(tmp_path):
    dest = tmp_path / "main.csv"
    report.mark_row("e", dest, "running", split="dev", runner="lingbot_world2", action_source="agent", notes="n")
    report.mark_row("e", dest, "generated")
    assert report.mark_row("e", dest, "running") == 1      # score-only launch: no metadata sent
    (r,) = rows_of(dest, "e")
    assert (r["status"], r["split"], r["runner"], r["action_source"], r["notes"]) == (
        "running", "dev", "lingbot_world2", "agent", "n")
    assert report.mark_row("e", dest, "failed") == 1 and rows_of(dest, "e")[0]["status"] == "failed"
    assert report.mark_row("fresh", dest, "running") == 1  # score-only with no earlier row still shows up
    assert rows_of(dest, "fresh")[0]["status"] == "running"


def test_stale_live_row_in_the_checkout_is_not_copied_to_main(tmp_path):
    # main has (e, dev, failed); the rerun reports under another split label from a checkout that inherited that row
    dest, src = tmp_path / "main.csv", tmp_path / "local.csv"
    live = row("e", split="dev", status="failed", overall="")
    write(dest, report.CSV_FIELDS, [live])
    write(src, report.CSV_FIELDS, [live, row("e", split="custom", status="scored")])
    assert report.upsert_row_into("e", src, dest) == 1
    assert [(r["split"], r["status"]) for r in rows_of(dest, "e")] == [("custom", "scored")]
    write(src, report.CSV_FIELDS, [live])
    with pytest.raises(ValueError, match="no row"):
        report.upsert_row_into("e", src, tmp_path / "other.csv")


def test_upsert_csv_drops_live_rows_and_keeps_unknown_columns(tmp_path, monkeypatch):
    path = tmp_path / "experiments.csv"
    monkeypatch.setattr(report, "RESULTS_CSV", path)
    head = report.CSV_FIELDS + ["future_col"]
    write(path, head, [row("e", split="custom", status="running", overall=""), row("keep", future_col="x")])
    rep = {"exp": "e", "generated": "2026-11-15T00:00:00Z", "families": {}, "overall": 2.0, "overall_std": None,
           "passes": [1], "n_tasks": 1, "n_missing": 0}
    report.upsert_csv(rep, {"runner": "sana"}, "dev")
    got_head, rows = read(path)
    assert got_head == head
    assert [(r["exp"], r["split"], r["status"]) for r in rows] == [("keep", "dev", ""), ("e", "dev", "scored")]
    assert rows[0]["future_col"] == "x"


def test_dash_led_notes_parse(tmp_path):
    dest = tmp_path / "e.csv"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "PWA_"))}
    r = subprocess.run([sys.executable, "-m", "pwa.cli", "mark", "e", "--into", str(dest), "--status", "running",
                        "--notes=--lingbot-stateless", "--runner=", "--split="], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert rows_of(dest, "e")[0]["notes"] == "--lingbot-stateless"
