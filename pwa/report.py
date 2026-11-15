"""pwa report / compare / failures / ls."""
from __future__ import annotations

import csv
import html
import io
import math
import os

from .aggregate import aggregate_pass, mean_std, upstream_cross_check
from .core import (FAMILIES, SCRIPTED_LABEL, SCRIPTED_TAG, cap_label, chunk_cap, current_branch, RESULTS_CSV, RUNS,
                   exp_dir, log, now, read_json, read_meta, scripted_player, video_path, write_json)
from .score import Judge, eval_dir, passes_present

# Paper numbers, full 171-task benchmark: gc, if, insight, outsight, overall.
REFERENCE = {
    "Genie 3": (2.74, 2.40, 1.51, 1.81, 2.12),
    "SANA-WM": (1.72, 1.89, 1.13, 1.16, 1.48),
    "Matrix-Game-3.0": (1.30, 1.25, 1.00, 1.00, 1.14),
}
# Paper: verifier pass-to-pass variance ~0.011 -> std ~0.105. Used when an exp has 1 pass.
FALLBACK_STD = math.sqrt(0.011)
CSV_FIELDS = ["exp", "split", "timestamp", "git_sha", "runner", "action_source", "gc", "if", "insight",
              "outsight", "overall", "overall_std", "passes", "n_tasks", "n_missing", "notes", "branch",
              "n_dropped", "status", "run_url", "max_chunks", "judge_backend"]
# judge_backend: API the Gemini judge was called through: aistudio, gcp, or aistudio+gcp for a run whose passes
# mixed them. Same model either way. Blank on rows older than the column.
# max_chunks: agent-chunk cap of a capped smoke run (pwa gen --max-chunks); blank = uncapped. A capped row is never
# an official score: the site badges it and keeps it out of the headline.
# status: running (launched), generated (gen-only done), scored, failed, cancelled. Blank on rows older than the column.
LIVE_STATUSES = ("running", "generated", "failed", "cancelled")


def load_pass(exp: str, k: int, sel: list[dict], judge: Judge | None = None) -> tuple[dict, dict]:
    d = eval_dir(exp, judge=judge) / f"pass{k}"
    scores, gates = {}, {}
    for t in sel:
        s = read_json(d / f"{t['task_id']}_score.json")
        g = read_json(d / f"{t['task_id']}_gate.json")
        scores[t["task_id"]] = (s or {}).get("score")
        gates[t["task_id"]] = (g or {}).get("score")
    return scores, gates


def judge_backends(exp: str, passes: list[int], sel: list[dict], judge: Judge | None = None) -> str:
    """aistudio / gcp / aistudio+gcp over the result files that hold a score; "" when none do. A result
    without the field (upstream as is, every run before the field) is aistudio."""
    seen = set()
    for k in passes:
        d = eval_dir(exp, judge=judge) / f"pass{k}"
        for t in sel:
            for mode in ("score", "gate"):
                res = read_json(d / f"{t['task_id']}_{mode}.json")
                if isinstance(res, dict) and res.get("score") is not None:
                    seen.add(res.get("judge_backend") or "aistudio")
    return "+".join(sorted(seen))


def judge_dropped(exp: str, passes: list[int], sel: list[dict], judge: Judge | None = None) -> list[str]:
    """Upstream sampling params (e.g. temperature) an openai: judge model rejected in any result of this run, so
    those calls sampled at the provider default (pwa/score.py stamp_dropped). [] for every other judge."""
    if not (judge and judge.provider == "openai"):
        return []
    seen = set()
    for k in passes:
        d = eval_dir(exp, judge=judge) / f"pass{k}"
        for t in sel:
            for mode in ("score", "gate"):
                res = read_json(d / f"{t['task_id']}_{mode}.json")
                if isinstance(res, dict):
                    seen.update(x for x in (res.get("judge_dropped") or []) if isinstance(x, str))
    return sorted(seen)


def dropped_label(params: list[str]) -> str:
    return (f"{', '.join(params)} rejected by the judge model: sampled at the provider default, not upstream's "
            f"setting")


def build(exp: str, sel: list[dict], strict: bool = False, split: str | None = None,
          judge: Judge | None = None) -> dict:
    present = {t["task_id"] for t in sel if video_path(exp, t["task_id"]).is_file()}
    passes = passes_present(exp, judge)
    per_pass = {}
    for k in passes:
        scores, gates = load_pass(exp, k, sel, judge)
        per_pass[k] = aggregate_pass(exp, sel, present, scores, gates, strict)
        if split == "all" and not strict:
            up = upstream_cross_check(exp, sel, present, scores, gates)
            per_pass[k]["upstream_overall"] = up["overall"]
            ours = per_pass[k]["overall"]
            if up["overall"] is not None and ours is not None and abs(up["overall"] - ours) > 1e-9:
                log(f"[pwa] WARNING pass{k}: upstream aggregate {up['overall']:.4f} != ours {ours:.4f}")
    fams = {}
    for fam in FAMILIES:
        vals = [p["families"][fam]["mean"] for p in per_pass.values() if fam in p["families"]]
        if not vals and not any(t["family"] == fam for t in sel):
            continue
        m, s = mean_std(vals)
        first = next((p["families"][fam] for p in per_pass.values() if fam in p["families"]), {})
        fams[fam] = {"mean": m, "std": s, "per_pass": vals,
                     **{k: first.get(k) for k in ("n_tasks", "n", "gated", "missing")},
                     "gate_pass": _avg([p["families"][fam]["gate_pass"] for p in per_pass.values() if fam in p["families"]]),
                     "dropped": max([p["families"][fam]["dropped"] for p in per_pass.values() if fam in p["families"]] or [0])}
    overall_vals = [p["overall"] for p in per_pass.values()]
    om, os_ = mean_std(overall_vals)
    tasks = {}
    for t in sel:
        rows = [next(r for r in p["tasks"] if r["task_id"] == t["task_id"]) for p in per_pass.values()]
        m, s = mean_std([r["value"] for r in rows])
        vals = [r["value"] for r in rows]
        reasons = [pass_reason(exp, t["task_id"], k, judge) for k in passes]
        i = representative(vals, reasons, m)
        # a pass that failed (gate, IF/OE check, error) keeps its own reason next to the representative one, so a
        # failure status is never shown with only a passing pass's comment
        j = next((n for n, r in enumerate(rows) if r["status"] != "ok" and reasons[n]), None)
        j = None if j == i else j
        tasks[t["task_id"]] = {"family": t["family"], "mean": m, "std": s,
                               "statuses": [r["status"] for r in rows], "values": vals,
                               # per-pass task values (the ones the mean is taken over) and the reason of the pass
                               # closest to the mean, so the comment shown matches the score shown
                               "pass_scores": vals, "reason": reasons[i] if i is not None else "",
                               "reason_pass": passes[i] if i is not None else None,
                               "fail_reason": reasons[j] if j is not None else "",
                               "fail_pass": passes[j] if j is not None else None}
    return {"exp": exp, "generated": now(), "passes": passes, "strict": strict, "n_tasks": len(sel),
            "n_missing": len(sel) - len(present), "families": fams, "overall": om, "overall_std": os_,
            "overall_per_pass": overall_vals, "per_pass": {str(k): {kk: v for kk, v in p.items() if kk != "tasks"}
                                                          for k, p in per_pass.items()},
            "tasks": tasks, "judge": judge_json(judge), "judge_backend": judge_backends(exp, passes, sel, judge),
            "judge_dropped": judge_dropped(exp, passes, sel, judge)}


def pass_reason(exp: str, tid: str, k: int, judge: Judge | None = None) -> str:
    """The verifier's reason for task tid in pass k: a gate or embedded IF/OE failure reason first, then the
    score summary, then a verifier error. '' when the pass has none."""
    d = eval_dir(exp, judge=judge) / f"pass{k}"
    s = (read_json(d / f"{tid}_score.json") or {}).get("score") or {}
    g = (read_json(d / f"{tid}_gate.json") or {}).get("score") or {}
    if not isinstance(s, dict):
        s = {}
    for src in (g, s.get("if_instruction_following_check") or {}, s.get("oe_instruction_following_check") or {}):
        if isinstance(src, dict) and src.get("failure_reason_zh"):
            return str(src["failure_reason_zh"])
    if s.get("summary_zh"):
        return str(s["summary_zh"])
    if s.get("error"):
        return f"verifier error: {s['error']}"
    return ""


def representative(values: list, reasons: list[str], mean: float | None) -> int | None:
    """Index of the pass whose reason represents the task: among passes with a reason, the one whose value is
    closest to the pass-mean (ties: earliest). Passes without a value only count when none has one."""
    have = [i for i, r in enumerate(reasons) if r]
    scored = [i for i in have if values[i] is not None]
    if scored and mean is not None:
        return min(scored, key=lambda i: (abs(values[i] - mean), i))
    return have[0] if have else None


def judge_json(judge: Judge | None) -> dict | None:
    """None = official judge. Screening reports carry the model and a label saying they are not comparable."""
    if judge is None:
        return None
    return {"model": judge.model, "thinking": judge.thinking, "provider": judge.provider, "slug": judge.slug,
            "name": judge.name, "spec": judge.spec, "label": judge.label, "proxy": judge.proxy}


def _avg(xs):
    return sum(xs) / len(xs) if xs else None


def f2(x, w=5) -> str:
    return f"{x:{w}.2f}" if isinstance(x, (int, float)) else f"{'-':>{w}}"


def render(rep: dict, meta: dict) -> str:
    out = io.StringIO()
    p = lambda s="": print(s, file=out)  # noqa: E731
    if rep.get("judge"):  # first line, so a pasted screening or proxy report always says what it is
        p(f"*** {rep['judge']['label']} ***")
    p(f"{rep['exp']}  runner={meta.get('runner')} action_source={meta.get('action_source')} "
      f"passes={len(rep['passes'])} tasks={rep['n_tasks']} missing={rep['n_missing']}"
      + (f" judge_backend={rep['judge_backend']}" if rep.get("judge_backend") else "")
      + ("  [strict]" if rep["strict"] else ""))
    if rep.get("judge_dropped"):
        p(f"*** {dropped_label(rep['judge_dropped'])} ***")
    if chunk_cap(meta):
        p(f"*** {cap_label(chunk_cap(meta))} ***")
    if scripted_player(meta):
        p(f"*** {SCRIPTED_LABEL} ***")
    p()
    p(f"{'family':<9} {'mean':>5} {'std':>5} {'n':>3} {'gate':>7} {'miss':>4} {'drop':>4}  per-pass")
    for fam, f in rep["families"].items():
        gate = f"{f['gate_pass']:.0f}/{f['gated']}" if f["gated"] and f["gate_pass"] is not None else "-"
        per = " ".join(f2(v, 4) for v in f["per_pass"])
        p(f"{fam:<9} {f2(f['mean'])} {f2(f['std'])} {f['n'] or 0:>3} {gate:>7} {f['missing'] or 0:>4} "
          f"{f['dropped']:>4}  {per}")
    p(f"{'overall':<9} {f2(rep['overall'])} {f2(rep['overall_std'])}"
      f"{'':19}  {' '.join(f2(v, 4) for v in rep['overall_per_pass'])}")
    if not rep.get("judge"):  # paper numbers are Gemini 3.1 Pro scores: never next to a screening or proxy score
        p()
        p(f"{'reference (paper, full benchmark)':<36}" + " ".join(f"{h:>5}" for h in ("gc", "if", "insi", "outs", "all")))
        for name, r in REFERENCE.items():
            p(f"  {name:<34}" + " ".join(f2(v) for v in r))
    if any(f["dropped"] for f in rep["families"].values()):
        p()
        p("note: 'drop' = unscored or gated-without-review rollouts, excluded from the mean as upstream does; "
          "rerun `pwa score` or use --strict to count them as 1.0")
    return out.getvalue()


def _md_cell(x) -> str:
    return str(x).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _md2(x) -> str:
    return f"{x:.2f}" if isinstance(x, (int, float)) else "-"


def render_md(rep: dict, meta: dict, site_url: str | None = None) -> str:
    """GitHub-flavoured markdown for $GITHUB_STEP_SUMMARY. The plain-text render() stays the default."""
    out = io.StringIO()
    p = lambda s="": print(s, file=out)  # noqa: E731
    j = rep.get("judge")
    if j and j.get("label", "").startswith("PROXY JUDGE"):  # first line, before the heading
        p(f"**{_md_cell(j['label'])}.** A/B between runs scored by this same judge only; uncalibrated against "
          f"Gemini 3.1 Pro. Written to results/proxy_experiments.csv, never results/experiments.csv.")
        p()
    p(f"## {_md_cell(rep['exp'])}" + (" (strict)" if rep["strict"] else ""))
    p()
    if j and not j.get("label", "").startswith("PROXY JUDGE"):
        p(f"> **{_md_cell(j['label'])}.** Dev screening only; not written to results/experiments.csv.")
        p()
    if rep.get("judge_dropped"):
        p(f"> **{_md_cell(dropped_label(rep['judge_dropped']).capitalize())}.**")
        p()
    if chunk_cap(meta):
        p(f"> **{_md_cell(cap_label(chunk_cap(meta)).capitalize())}.** Smoke tier only; never the site headline.")
        p()
    if scripted_player(meta):
        p(f"> **{_md_cell(SCRIPTED_LABEL.capitalize())}.** Moves replayed by the scripted player; never a closed-loop "
          f"score or the site headline.")
        p()
    p(f"runner `{meta.get('runner')}` | action source `{meta.get('action_source')}` | passes {len(rep['passes'])} "
      f"| tasks {rep['n_tasks']} | missing {rep['n_missing']}"
      + (f" | judge backend `{rep['judge_backend']}`" if rep.get("judge_backend") else ""))
    p()
    p("| family | mean | std | n | gate pass | missing | dropped | per pass |")
    p("|---|---:|---:|---:|---:|---:|---:|---|")
    for fam, f in rep["families"].items():
        gate = f"{f['gate_pass']:.0f}/{f['gated']}" if f["gated"] and f["gate_pass"] is not None else "-"
        per = ", ".join(_md2(v) for v in f["per_pass"]) or "-"
        p(f"| {fam} | {_md2(f['mean'])} | {_md2(f['std'])} | {f['n'] or 0} | {gate} | {f['missing'] or 0} "
          f"| {f['dropped']} | {per} |")
    per = ", ".join(_md2(v) for v in rep["overall_per_pass"]) or "-"
    p(f"| **overall** | **{_md2(rep['overall'])}** | {_md2(rep['overall_std'])} | | | | | {per} |")
    if not j:  # paper numbers are Gemini 3.1 Pro scores: never next to a screening or proxy score
        p()
        p("**Reference (paper, full benchmark)**")
        p()
        p("| model | gc | if | insight | outsight | overall |")
        p("|---|---:|---:|---:|---:|---:|")
        for name, r in REFERENCE.items():
            p(f"| {name} | " + " | ".join(_md2(v) for v in r) + " |")
    if any(f["dropped"] for f in rep["families"].values()):
        p()
        p("> `dropped` = unscored or gated-without-review rollouts, excluded from the mean as upstream does. "
          "Rerun `pwa score` or use `--strict` to count them as 1.0.")
    if site_url:
        p()
        p(f"[All experiments on the results site]({site_url})")
    return out.getvalue()


def passes_cell(scores) -> str:
    """Per-pass task values, compact: 4/4/3.5/4 ('-' for a dropped pass)."""
    return "/".join("-" if v is None else f"{v:g}" if float(v).is_integer() else f"{v:.2f}".rstrip("0")
                    for v in scores or []) or "-"


def reason_md(r: dict) -> str:
    """English display copy first with the judge's original under it (the original is authoritative), else the
    original alone."""
    orig, en = r.get("reason") or "", r.get("reason_en") or ""
    if not en:
        out = _md_cell(orig)
    else:
        out = f"{_md_esc(en)}<details><summary>judge's original</summary>{_md_esc(orig)}</details>"
    if r.get("fail_reason"):
        # the failing pass's own reason, when the representative pass is a different one
        st = ", ".join(s for s in r.get("status") or [] if s != "ok") or "failed"
        fen = r.get("fail_reason_en") or ""
        body = (f"{_md_esc(fen)}<details><summary>judge's original</summary>{_md_esc(r['fail_reason'])}</details>"
                if fen else _md_esc(r["fail_reason"]))
        out += f"<br>pass {r.get('fail_pass')} {_md_esc(st)}: {body}"
    return out


def _md_esc(x: str) -> str:
    """A markdown table cell that sits inside HTML tags."""
    return _md_cell(html.escape(x, quote=False))


def render_failures_md(rows: list[dict]) -> str:
    if not rows:
        return "No failures.\n"
    out = ["| task | family | mean | passes | status | reason |", "|---|---|---:|---|---|---|"]
    for r in rows:
        out.append(f"| {r['task_id']} | {r['family']} | {_md2(r['mean'])} | {passes_cell(r.get('pass_scores'))} "
                   f"| {_md_cell(', '.join(r['status']))} | {reason_md(r)} |")
    if any(r.get("reason_en") or r.get("fail_reason_en") for r in rows):
        out += ["", "> Reasons are machine-translated into English for display after scoring; the judge's original "
                "text (under each) is authoritative."]
    return "\n".join(out) + "\n"


def upsert_csv(rep: dict, meta: dict, split: str) -> None:
    rows, head = [], []
    if RESULTS_CSV.is_file():
        with RESULTS_CSV.open(newline="") as fh:
            rd = csv.DictReader(fh)
            rows, head = list(rd), [c for c in (rd.fieldnames or []) if c]
    head += [c for c in CSV_FIELDS if c not in head]  # keep columns this version does not know
    new = _csv_row(rep, meta, split)
    # replace the same exp+split, and exp's score-less live rows (mark_row) under any split label
    rows = [r for r in rows if not (r.get("exp") == rep["exp"]
                                    and (r.get("split") == split or r.get("status") in LIVE_STATUSES))] + [new]
    _write_csv(RESULTS_CSV, head, [{k: v for k, v in r.items() if k in head} for r in rows])


# Proxy judge (`--judge openai`): its rows go to results/proxy_experiments.csv next to the results csv, never into
# it. Same columns plus `judge` (the judge spec); one row per exp, split and judge. The site does not read this file.
PROXY_FIELDS = CSV_FIELDS + ["judge"]
PROXY_KEYS = ("exp", "split", "judge")


def check_proxy_dest(dest) -> None:
    """A proxy row never goes into the official results csv, by path or by name (a checkout of main)."""
    from pathlib import Path
    d = Path(dest)
    if d.name == RESULTS_CSV.name or d.name == "experiments.csv" or d.resolve() == Path(RESULTS_CSV).resolve():
        raise ValueError(f"{dest}: proxy judge rows never go into the results csv; use proxy_experiments.csv")


def proxy_csv():
    from pathlib import Path
    env = os.environ.get("PWA_PROXY_CSV")
    dest = Path(env) if env else RESULTS_CSV.parent / "proxy_experiments.csv"
    check_proxy_dest(dest)
    return dest


def upsert_proxy_csv(rep: dict, meta: dict, split: str, judge: Judge) -> None:
    """Best effort: a bad proxy csv (or destination) is a warning, never a failed report."""
    try:
        dest = proxy_csv()
        head, rows = _read_csv_strict(dest) if dest.is_file() and dest.stat().st_size else (list(PROXY_FIELDS), [])
        head += [c for c in PROXY_FIELDS if c not in head]
        new = {**_csv_row(rep, meta, split), "status": "proxy", "judge": judge.spec}
        rows = [r for r in rows if tuple(r.get(k, "") for k in PROXY_KEYS) != tuple(new[k] for k in PROXY_KEYS)] + [new]
        _write_csv(dest, head, rows)
    except (ValueError, OSError) as e:
        log(f"[pwa] WARNING: proxy csv row not written: {e}")


def _csv_row(rep: dict, meta: dict, split: str) -> dict:
    fam = rep["families"]
    cap = chunk_cap(meta)
    r4 = lambda x: "" if x is None else f"{x:.4f}"  # noqa: E731
    return {"exp": rep["exp"], "split": split, "timestamp": rep["generated"], "git_sha": meta.get("git_sha") or "",
           "runner": meta.get("runner", ""), "action_source": meta.get("action_source", ""),
           **{f: r4(fam.get(f, {}).get("mean")) for f in FAMILIES},
           "overall": r4(rep["overall"]), "overall_std": r4(rep["overall_std"]), "passes": len(rep["passes"]),
           "n_tasks": rep["n_tasks"], "n_missing": rep["n_missing"],
           "notes": scripted_notes(capped_notes(meta.get("notes", ""), cap), scripted_player(meta)),
           "branch": meta.get("branch") or current_branch(),
           # unscored or gated-without-review rollouts excluded from the mean (worst pass per family)
           "n_dropped": sum(f.get("dropped") or 0 for f in fam.values()),
           "status": "scored", "run_url": run_url(), "max_chunks": str(cap or ""),
           "judge_backend": rep.get("judge_backend") or ""}


def capped_notes(notes: str, cap: int | None) -> str:
    """Notes of a capped run start with its label (idempotent), so the csv says so even where max_chunks is not shown."""
    if not cap:
        return notes or ""
    tag = f"[capped smoke: {cap} chunks]"
    return notes if (notes or "").startswith(tag) else (f"{tag} {notes}" if notes else tag)


def scripted_notes(notes: str, scripted: bool) -> str:
    """Notes of a scripted-player run start with its tag (idempotent), so the csv and the site never read it as
    an AI-played closed-loop run."""
    if not scripted or SCRIPTED_TAG in (notes or ""):
        return notes or ""
    return f"{SCRIPTED_TAG} {notes}" if notes else SCRIPTED_TAG


def run_url() -> str:
    """This GitHub Actions run's page, or '' outside Actions."""
    e = os.environ
    if not (e.get("GITHUB_SERVER_URL") and e.get("GITHUB_REPOSITORY") and e.get("GITHUB_RUN_ID")):
        return ""
    return f"{e['GITHUB_SERVER_URL']}/{e['GITHUB_REPOSITORY']}/actions/runs/{e['GITHUB_RUN_ID']}"


def _write_csv(dest, head: list[str], rows: list[dict]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head, restval="", extrasaction="raise")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(dest)


def mark_row(exp: str, dest, status: str, split: str = "", runner: str = "", action_source: str = "",
             notes: str = "", git_sha: str = "", max_chunks: int | None = None) -> int:
    """Record a run's live status in csv `dest` so in-flight runs are visible. Returns rows written.

    running: add a score-less row for exp, or refresh its existing score-less row (empty arguments keep
    what that row recorded, so a score-only run does not overwrite the generation's metadata). A row that
    already holds a score is left alone (score-only reruns, resumed runs). Any other status only updates
    exp's rows that still say running, so a scored row is never downgraded. The final `upsert-row`
    replaces the running row."""
    from pathlib import Path
    if status not in LIVE_STATUSES:
        raise ValueError(f"status must be one of {', '.join(LIVE_STATUSES)}")
    dest = Path(dest)
    if dest.is_file() and dest.stat().st_size:
        head, rows = _read_csv_strict(dest)
    else:
        head, rows = list(CSV_FIELDS), []
    head += [c for c in CSV_FIELDS if c not in head]
    mine = [r for r in rows if r.get("exp") == exp]
    if status == "running":
        if any((r.get("overall") or "").strip() for r in mine):
            return 0
        upd = {"split": split, "git_sha": git_sha, "runner": runner, "action_source": action_source,
               "notes": capped_notes(notes, max_chunks) if notes or max_chunks else "", "branch": current_branch(),
               "run_url": run_url(), "max_chunks": str(max_chunks or "")}
        new = {**(mine[0] if mine else {}), **{k: v for k, v in upd.items() if v},
               "exp": exp, "timestamp": now(), "status": "running"}
        _write_csv(dest, head, [r for r in rows if r.get("exp") != exp] + [new])
        return 1
    live = [r for r in mine if r.get("status") == "running"]
    for r in live:
        r["status"], r["timestamp"] = status, now()
    if live:
        _write_csv(dest, head, rows)
    return len(live)


def _read_csv_strict(path) -> tuple[list[str], list[dict]]:
    """Header + rows of a results CSV. Raises ValueError on a malformed file (never guesses)."""
    with open(path, newline="") as fh:
        try:
            table = list(csv.reader(fh, strict=True))
        except csv.Error as e:
            raise ValueError(f"{path}: malformed csv: {e}") from e
    if not table or "exp" not in table[0]:
        raise ValueError(f"{path}: missing header with an 'exp' column")
    head = table[0]
    if len(set(head)) != len(head):
        raise ValueError(f"{path}: duplicate column names in header")
    rows = []
    for n, cells in enumerate(table[1:], 2):
        if not cells:
            continue
        if len(cells) > len(head):
            raise ValueError(f"{path}: line {n} has {len(cells)} fields, header has {len(head)}")
        rows.append(dict(zip(head, cells + [""] * (len(head) - len(cells)))))
    return head, rows


def upsert_row_into(exp: str, src, dest, keys: tuple[str, ...] = ("exp", "split"),
                    judges: list[str] | None = None) -> int:
    """Copy exp's row(s) from csv `src` into csv `dest` (replace rows with the same `keys`, default exp+split,
    else append), matching columns by name. Columns the destination lacks are added to its header; nothing is
    dropped. Returns rows written. With keys=PROXY_KEYS (proxy rows): `dest` must not be a results csv, and
    `judges` (judge specs) limits the copy to the rows of those judges, so a branch's stale rows of other judges
    never overwrite newer ones. Without it, proxy rows (status=proxy or a judge) are never copied."""
    from pathlib import Path
    proxy = "judge" in keys
    if proxy:
        check_proxy_dest(dest)
    src, dest = Path(src), Path(dest)
    _, srows = _read_csv_strict(src)
    # never copy a score-less live row: the checkout's csv can hold one inherited from main
    mine = [r for r in srows if r.get("exp") == exp and r.get("status") not in LIVE_STATUSES]
    if proxy and judges is not None:
        mine = [r for r in mine if r.get("judge", "") in judges]
    if not proxy:
        mine = [r for r in mine if r.get("status") != "proxy" and not (r.get("judge") or "").strip()]
    if not mine:
        raise ValueError(f"{src}: no row for exp {exp!r}" + (f" and judge {' '.join(judges)}" if proxy and judges else ""))
    if dest.is_file() and dest.stat().st_size:
        head, rows = _read_csv_strict(dest)
    else:
        head, rows = list(CSV_FIELDS), []
    for r in mine:
        for col in r:
            if col not in head:
                head.append(col)
    have = {tuple(r.get(k, "") for k in keys) for r in mine}
    # also drop exp's score-less live rows (mark_row), whatever split label they were launched with
    rows = [r for r in rows if tuple(r.get(k, "") for k in keys) not in have
            and not (r.get("exp") == exp and r.get("status") in LIVE_STATUSES)] + mine
    _write_csv(dest, head, rows)
    return len(mine)


def report(exp: str, sel: list[dict], split_label: str, strict: bool, write: bool = True,
           judge: Judge | None = None) -> dict:
    rep = build(exp, sel, strict, split_label, judge)
    rep["split"] = split_label
    rep["max_chunks"] = chunk_cap(read_meta(exp))
    if not rep["passes"]:
        hint = f" --judge-model {judge.spec}" if judge else ""
        log(f"[pwa] {exp}: no scored passes yet (run `pwa score {exp}{hint}`)" + other_judge_dirs_hint(exp, judge))
        return rep
    add_english(exp, list(rep["tasks"].values()), judge)  # display copy of each reason; the scores are untouched
    if judge:
        # screening judge: never the official report.json, never the results csv
        if write and not strict:
            write_json(exp_dir(exp) / f"report.{judge.slug}.json", rep)
            if judge.proxy:  # proxy judge: its own csv, never results/experiments.csv
                upsert_proxy_csv(rep, read_meta(exp), split_label, judge)
    elif write and not strict:
        write_json(exp_dir(exp) / "report.json", rep)
        upsert_csv(rep, read_meta(exp), split_label)
    return rep


def other_judge_dirs_hint(exp: str, judge: Judge | None) -> str:
    """For an openai: judge with no results: the other eval-openai-* dirs of exp, e.g. when PWA_PROXY_JUDGE_MODEL
    differed between `pwa score` and this command."""
    if not (judge and judge.provider == "openai"):
        return ""
    d = exp_dir(exp)
    others = sorted(p.name for p in d.glob("eval-openai-*") if p.is_dir() and p.name != f"eval-{judge.slug}") \
        if d.is_dir() else []
    return f"; {exp} has {', '.join(others)}: pass that model with --judge-model" if others else ""


def compare(a: dict, b: dict) -> dict:
    def noise(sa, sb):
        stds = [s for s in (sa, sb) if s is not None]
        return 2 * max(stds) if stds else None

    # the paper's pass variance is Gemini 3.1 Pro's: never the noise floor of another judge. Without a measured
    # std (1 pass, or identical passes) a screening or proxy delta is "?", not REAL.
    fallback = None if a.get("judge") or b.get("judge") else 2 * FALLBACK_STD

    def flag(d, thr):
        return None if thr is None else abs(d) < thr

    fams = {}
    for fam in FAMILIES:
        fa, fb = a["families"].get(fam), b["families"].get(fam)
        if not fa or not fb or fa["mean"] is None or fb["mean"] is None:
            continue
        thr = noise(fa["std"], fb["std"]) or fallback
        d = fb["mean"] - fa["mean"]
        fams[fam] = {"a": fa["mean"], "b": fb["mean"], "delta": d, "threshold": thr, "noise": flag(d, thr)}
    ov = None
    if a["overall"] is not None and b["overall"] is not None:
        thr = noise(a["overall_std"], b["overall_std"]) or fallback
        d = b["overall"] - a["overall"]
        ov = {"a": a["overall"], "b": b["overall"], "delta": d, "threshold": thr, "noise": flag(d, thr)}
    tasks = {}
    for tid, ta in a["tasks"].items():
        tb = b["tasks"].get(tid)
        if not tb or ta["mean"] is None or tb["mean"] is None:
            continue
        thr = noise(ta["std"], tb["std"])
        d = tb["mean"] - ta["mean"]
        tasks[tid] = {"family": ta["family"], "a": ta["mean"], "b": tb["mean"], "delta": d, "threshold": thr,
                      "noise": None if thr is None else abs(d) < thr}
    return {"a": a["exp"], "b": b["exp"], "families": fams, "overall": ov, "tasks": tasks,
            "threshold_source": "2x max pass std" + (" (fallback: paper variance 0.011)" if fallback else
                                                      " (no fallback for a screening or proxy judge)"),
            "judge": a.get("judge")}


def render_compare(c: dict) -> str:
    out = io.StringIO()
    p = lambda s="": print(s, file=out)  # noqa: E731
    tag = lambda r: "noise" if r["noise"] else ("?" if r["noise"] is None else "REAL")  # noqa: E731
    if c.get("judge"):
        p(f"*** {c['judge']['label']} ***")
    p(f"A={c['a']}  B={c['b']}  delta = B - A; noise if |delta| < 2x pass std")
    p(f"{'':<9} {'A':>5} {'B':>5} {'delta':>6} {'thr':>5}")
    for fam, r in list(c["families"].items()) + ([("overall", c["overall"])] if c["overall"] else []):
        p(f"{fam:<9} {f2(r['a'])} {f2(r['b'])} {r['delta']:+6.2f} {f2(r['threshold'])}  {tag(r)}")
    p()
    p("per task (sorted by delta):")
    for tid, r in sorted(c["tasks"].items(), key=lambda kv: kv[1]["delta"]):
        p(f"  {tid:<6} {r['family']:<9} {f2(r['a'])} {f2(r['b'])} {r['delta']:+6.2f}  {tag(r)}")
    return out.getvalue()


def translations_path(exp: str, judge: Judge | None = None):
    """Cache of English display copies of this run's reasons (pwa/translate.py), next to the verifier output."""
    return eval_dir(exp, judge=judge) / "translations.json"


def add_english(exp: str, rows: list[dict], judge: Judge | None = None) -> None:
    """Set reason_en on each row (display only, after scoring; '' when untranslated or already English). Never
    raises and never changes a score or the original reason."""
    from . import translate
    try:
        for field in translate.FIELDS:
            translate.fill(rows, translations_path(exp, judge), field=field)
    except Exception as e:  # noqa: BLE001
        log(f"[pwa] translate: skipped ({type(e).__name__})")
        for r in rows:
            for field in translate.FIELDS:
                r.setdefault(field + "_en", "")


def failures(exp: str, sel: list[dict], all_tasks: bool = False, judge: Judge | None = None,
             english: bool = True) -> list[dict]:
    """Tasks that are missing, gate-failed or scored 1.0, with the verifier's reason (from the pass closest to the
    task's mean) and its English display copy; every task with all_tasks."""
    rep = build(exp, sel, judge=judge)
    out = []
    for t in sel:
        tid = t["task_id"]
        tr = rep["tasks"][tid]
        bad = [s for s in tr["statuses"] if s != "ok"]
        low = tr["mean"] is not None and tr["mean"] <= 1.0
        if not rep["passes"] and video_path(exp, tid).is_file():
            continue
        if not rep["passes"]:
            bad = ["missing"]
        if not bad and not low and not all_tasks:
            continue
        status = sorted(set(bad)) or (["score_1.0"] if low else ["ok"])
        out.append({"task_id": tid, "family": t["family"], "mean": tr["mean"], "status": status,
                    "pass_scores": tr["pass_scores"], "reason": tr["reason"], "reason_pass": tr["reason_pass"],
                    "fail_reason": tr["fail_reason"], "fail_pass": tr["fail_pass"]})
    if english and out:
        add_english(exp, out, judge)
    return out


MOVE = 1.0  # a cell "moves" only at a full point on the 1-5 scale


def cells(a: dict, b: dict) -> dict:
    """Per-task decision readout over the tasks both reports share: pass-mean of A and B, delta B - A, and how
    many tasks moved up or down by at least MOVE. Tasks without a usable mean on either side are listed apart."""
    rows, unscored = [], []
    for tid, ta in a["tasks"].items():
        tb = b["tasks"].get(tid)
        if tb is None:
            continue
        if ta["mean"] is None or tb["mean"] is None:
            unscored.append(tid)
            continue
        d = tb["mean"] - ta["mean"]
        rows.append({"task_id": tid, "family": ta["family"], "a": ta["mean"], "b": tb["mean"], "delta": d,
                     "move": "up" if d >= MOVE - 1e-9 else ("down" if d <= -MOVE + 1e-9 else "")})
    rows.sort(key=lambda r: (-r["delta"], r["task_id"]))
    return {"a": a["exp"], "b": b["exp"], "judge": a.get("judge"), "threshold": MOVE, "tasks": rows,
            "n_common": len(rows), "up": sum(r["move"] == "up" for r in rows),
            "down": sum(r["move"] == "down" for r in rows), "unscored": unscored}


def render_cells(c: dict) -> str:
    out = io.StringIO()
    p = lambda s="": print(s, file=out)  # noqa: E731
    if c.get("judge"):
        p(f"*** {c['judge']['label']} ***")
    p(f"A={c['a']}  B={c['b']}  per-task mean over passes; delta = B - A; moved = |delta| >= {c['threshold']:.1f}")
    p(f"{'task':<7} {'family':<9} {'A':>5} {'B':>5} {'delta':>6}  moved")
    for r in c["tasks"]:
        p(f"{r['task_id']:<7} {r['family']:<9} {f2(r['a'])} {f2(r['b'])} {r['delta']:+6.2f}  {r['move']}")
    p()
    p(f"up {c['up']}  down {c['down']}  of {c['n_common']} common tasks"
      + (f"; no usable mean on one side: {' '.join(c['unscored'])}" if c["unscored"] else ""))
    return out.getvalue()


def ls() -> list[dict]:
    out = []
    if not RUNS.is_dir():
        return out
    for d in sorted(p for p in RUNS.iterdir() if p.is_dir()):
        meta = read_json(d / "meta.json") or next((read_json(m) for m in sorted(d.glob("meta.shard*.json"))), None) or {}
        n_exp = len(meta.get("tasks") or [])
        n_vid = len(list((d / "videos").glob("*/*.mp4")))
        rep = read_json(d / "report.json") or {}
        passes = passes_present(d.name)
        out.append({"exp": d.name, "created": meta.get("created"), "runner": meta.get("runner"),
                    "action_source": meta.get("action_source"), "split": meta.get("split"),
                    "videos": n_vid, "expected": n_exp,
                    "gen": "done" if n_exp and n_vid >= n_exp else ("partial" if n_vid else "none"),
                    "passes": passes, "overall": rep.get("overall"), "report_split": rep.get("split")})
    return out
