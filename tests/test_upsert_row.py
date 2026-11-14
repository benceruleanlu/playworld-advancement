"""pwa upsert-row: copy one experiment's row into another results csv by column name."""
import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pwa import report

ROOT = Path(__file__).resolve().parents[1]
OLD = ["exp", "split", "timestamp", "git_sha", "runner", "action_source", "gc", "if", "insight", "outsight",
       "overall", "overall_std", "passes", "n_tasks", "n_missing", "notes"]


def write(path, head, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head, restval="")
        w.writeheader()
        w.writerows(rows)


def read(path):
    with open(path, newline="") as fh:
        r = csv.DictReader(fh)
        return r.fieldnames, list(r)


def row(exp, **kw):
    return {"exp": exp, "split": "dev", "timestamp": "2026-11-15T00:00:00Z", "overall": "1.5000", **kw}


def test_insert_into_missing_dest(tmp_path):
    src, dest = tmp_path / "s.csv", tmp_path / "d" / "e.csv"
    write(src, report.CSV_FIELDS, [row("a", branch="feat/x"), row("b")])
    assert report.upsert_row_into("a", src, dest) == 1
    head, rows = read(dest)
    assert head == report.CSV_FIELDS and [r["exp"] for r in rows] == ["a"] and rows[0]["branch"] == "feat/x"


def test_insert_keeps_existing_and_replaces_same_exp(tmp_path):
    src, dest = tmp_path / "s.csv", tmp_path / "e.csv"
    write(dest, report.CSV_FIELDS, [row("a", overall="1.0000"), row("z")])
    write(src, report.CSV_FIELDS, [row("a", overall="2.0000", branch="main"), row("y")])
    report.upsert_row_into("a", src, dest)
    _, rows = read(dest)
    assert [r["exp"] for r in rows] == ["z", "a"] and rows[1]["overall"] == "2.0000"
    report.upsert_row_into("a", src, dest)  # idempotent
    assert len(read(dest)[1]) == 2


def test_dest_missing_branch_column_gets_it(tmp_path):
    src, dest = tmp_path / "s.csv", tmp_path / "e.csv"
    write(dest, OLD, [row("old", notes="n")])
    write(src, report.CSV_FIELDS, [row("new", branch="feat/y")])
    report.upsert_row_into("new", src, dest)
    head, rows = read(dest)
    assert head[-1] == "branch" and head[:len(OLD)] == OLD
    assert rows[0]["exp"] == "old" and rows[0]["branch"] == "" and rows[1]["branch"] == "feat/y"


def test_quoted_notes_with_commas_and_newlines(tmp_path):
    src, dest = tmp_path / "s.csv", tmp_path / "e.csv"
    note = 'agent, "quoted", with\nnewline'
    write(src, report.CSV_FIELDS, [row("q", notes=note)])
    write(dest, report.CSV_FIELDS, [row("other")])
    report.upsert_row_into("q", src, dest)
    assert read(dest)[1][1]["notes"] == note


def test_malformed_files_fail_loudly(tmp_path):
    src, dest = tmp_path / "s.csv", tmp_path / "e.csv"
    write(src, report.CSV_FIELDS, [row("a")])
    dest.write_text("foo,bar\n1,2\n")
    with pytest.raises(ValueError, match="'exp' column"):
        report.upsert_row_into("a", src, dest)
    dest.write_text(",".join(report.CSV_FIELDS) + "\n" + ",".join(["x"] * (len(report.CSV_FIELDS) + 2)) + "\n")
    with pytest.raises(ValueError, match="fields"):
        report.upsert_row_into("a", src, dest)
    with pytest.raises(ValueError, match="no row for exp"):
        report.upsert_row_into("nope", src, tmp_path / "fresh.csv")


def test_cli(tmp_path):
    src, dest = tmp_path / "s.csv", tmp_path / "e.csv"
    write(src, report.CSV_FIELDS, [row("a", branch="b1")])
    env = {**os.environ, "PWA_RESULTS_CSV": str(src)}
    r = subprocess.run([sys.executable, "-m", "pwa.cli", "upsert-row", "a", "--into", str(dest)], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert read(dest)[1][0]["branch"] == "b1"
    r = subprocess.run([sys.executable, "-m", "pwa.cli", "upsert-row", "zzz", "--into", str(dest)], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 1 and "no row" in r.stderr


def test_branch_passthrough_and_generation_meta_wins(tmp_path, monkeypatch):
    from pwa import core
    # Modal container: no .git, no GITHUB_REF_NAME; the launcher passes PWA_GIT_BRANCH through.
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    monkeypatch.setenv("PWA_GIT_BRANCH", "feat/x")
    monkeypatch.setattr(core, "git", lambda *a, **k: None)
    assert core.current_branch() == "feat/x"
    assert core.provenance()["branch"] == "feat/x"
    # Scoring later on main: the branch stored at generation time wins over the reporting checkout's ref.
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    csv_path = tmp_path / "e.csv"
    monkeypatch.setattr(report, "RESULTS_CSV", csv_path)
    rep = {"exp": "e1", "generated": "2026-11-15T00:00:00Z", "families": {}, "overall": 1.5, "overall_std": None,
           "passes": [1], "n_tasks": 2, "n_missing": 0}
    report.upsert_csv(rep, {"runner": "sana", "branch": "feat/x"}, "dev")
    report.upsert_csv({**rep, "exp": "e2"}, {"runner": "sana"}, "dev")  # no stored branch: reporting ref
    _, rows = read(csv_path)
    assert {r["exp"]: r["branch"] for r in rows} == {"e1": "feat/x", "e2": "main"}
