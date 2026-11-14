"""Markdown output for $GITHUB_STEP_SUMMARY. Pure functions, no GPU, no ffmpeg."""
from pwa import report


def _rep(**kw):
    fam = {"mean": 2.0, "std": 0.1, "per_pass": [1.9, 2.1], "n_tasks": 3, "n": 3, "gated": 3, "missing": 0,
           "gate_pass": 2.0, "dropped": 0}
    base = {"exp": "e1", "passes": [1, 2], "strict": False, "n_tasks": 3, "n_missing": 0,
            "families": {"gc": fam, "insight": {**fam, "mean": None, "std": None, "per_pass": [], "dropped": 1}},
            "overall": 2.0, "overall_std": 0.1, "overall_per_pass": [1.9, 2.1]}
    base.update(kw)
    return base


def test_render_md_table_and_link():
    md = report.render_md(_rep(), {"runner": "sana", "action_source": "agent"}, "https://x.github.io/r/")
    assert "| family | mean |" in md and "|---|" in md
    assert "| gc | 2.00 | 0.10 | 3 | 2/3 | 0 | 0 | 1.90, 2.10 |" in md
    assert "| insight | - |" in md  # missing means are a dash, never 0
    assert "| Genie 3 | 2.74 |" in md and "| **overall** | **2.00** |" in md
    assert "[All experiments on the results site](https://x.github.io/r/)" in md
    assert "dropped" in md  # explanatory note when something was dropped
    assert "```" not in md


def test_render_md_without_link_and_plain_default_unchanged():
    rep, meta = _rep(), {"runner": "sana", "action_source": "agent"}
    assert "results site" not in report.render_md(rep, meta)
    plain = report.render(rep, meta)
    assert plain.startswith("e1  runner=sana") and "|" not in plain


def test_failures_md_escapes_pipes_and_newlines():
    rows = [{"task_id": "IF002", "family": "if", "mean": 1.0, "status": ["gate_fail"], "reason": "a|b\nc"}]
    md = report.render_failures_md(rows)
    assert "| IF002 | if | 1.00 | gate_fail | a\\|b c |" in md
    assert report.render_failures_md([]).startswith("No failures")
