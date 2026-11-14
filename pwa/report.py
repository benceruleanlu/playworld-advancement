"""pwa report / compare / failures / ls."""
from __future__ import annotations

import csv
import io
import math

from .aggregate import aggregate_pass, mean_std, upstream_cross_check
from .core import FAMILIES, current_branch, RESULTS_CSV, RUNS, exp_dir, log, now, read_json, read_meta, video_path, write_json
from .score import eval_dir, passes_present

# Paper numbers, full 171-task benchmark: gc, if, insight, outsight, overall.
REFERENCE = {
    "Genie 3": (2.74, 2.40, 1.51, 1.81, 2.12),
    "SANA-WM": (1.72, 1.89, 1.13, 1.16, 1.48),
    "Matrix-Game-3.0": (1.30, 1.25, 1.00, 1.00, 1.14),
}
# Paper: verifier pass-to-pass variance ~0.011 -> std ~0.105. Used when an exp has 1 pass.
FALLBACK_STD = math.sqrt(0.011)
CSV_FIELDS = ["exp", "split", "timestamp", "git_sha", "runner", "action_source", "gc", "if", "insight",
              "outsight", "overall", "overall_std", "passes", "n_tasks", "n_missing", "notes", "branch"]


def load_pass(exp: str, k: int, sel: list[dict]) -> tuple[dict, dict]:
    d = eval_dir(exp) / f"pass{k}"
    scores, gates = {}, {}
    for t in sel:
        s = read_json(d / f"{t['task_id']}_score.json")
        g = read_json(d / f"{t['task_id']}_gate.json")
        scores[t["task_id"]] = (s or {}).get("score")
        gates[t["task_id"]] = (g or {}).get("score")
    return scores, gates


def build(exp: str, sel: list[dict], strict: bool = False, split: str | None = None) -> dict:
    present = {t["task_id"] for t in sel if video_path(exp, t["task_id"]).is_file()}
    passes = passes_present(exp)
    per_pass = {}
    for k in passes:
        scores, gates = load_pass(exp, k, sel)
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
        tasks[t["task_id"]] = {"family": t["family"], "mean": m, "std": s,
                               "statuses": [r["status"] for r in rows], "values": [r["value"] for r in rows]}
    return {"exp": exp, "generated": now(), "passes": passes, "strict": strict, "n_tasks": len(sel),
            "n_missing": len(sel) - len(present), "families": fams, "overall": om, "overall_std": os_,
            "overall_per_pass": overall_vals, "per_pass": {str(k): {kk: v for kk, v in p.items() if kk != "tasks"}
                                                          for k, p in per_pass.items()},
            "tasks": tasks}


def _avg(xs):
    return sum(xs) / len(xs) if xs else None


def f2(x, w=5) -> str:
    return f"{x:{w}.2f}" if isinstance(x, (int, float)) else f"{'-':>{w}}"


def render(rep: dict, meta: dict) -> str:
    out = io.StringIO()
    p = lambda s="": print(s, file=out)  # noqa: E731
    p(f"{rep['exp']}  runner={meta.get('runner')} action_source={meta.get('action_source')} "
      f"passes={len(rep['passes'])} tasks={rep['n_tasks']} missing={rep['n_missing']}"
      + ("  [strict]" if rep["strict"] else ""))
    p()
    p(f"{'family':<9} {'mean':>5} {'std':>5} {'n':>3} {'gate':>7} {'miss':>4} {'drop':>4}  per-pass")
    for fam, f in rep["families"].items():
        gate = f"{f['gate_pass']:.0f}/{f['gated']}" if f["gated"] and f["gate_pass"] is not None else "-"
        per = " ".join(f2(v, 4) for v in f["per_pass"])
        p(f"{fam:<9} {f2(f['mean'])} {f2(f['std'])} {f['n'] or 0:>3} {gate:>7} {f['missing'] or 0:>4} "
          f"{f['dropped']:>4}  {per}")
    p(f"{'overall':<9} {f2(rep['overall'])} {f2(rep['overall_std'])}"
      f"{'':19}  {' '.join(f2(v, 4) for v in rep['overall_per_pass'])}")
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
    p(f"## {_md_cell(rep['exp'])}" + (" (strict)" if rep["strict"] else ""))
    p()
    p(f"runner `{meta.get('runner')}` | action source `{meta.get('action_source')}` | passes {len(rep['passes'])} "
      f"| tasks {rep['n_tasks']} | missing {rep['n_missing']}")
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


def render_failures_md(rows: list[dict]) -> str:
    if not rows:
        return "No failures.\n"
    out = ["| task | family | mean | status | reason |", "|---|---|---:|---|---|"]
    for r in rows:
        out.append(f"| {r['task_id']} | {r['family']} | {_md2(r['mean'])} | {_md_cell(', '.join(r['status']))} "
                   f"| {_md_cell(r['reason'])} |")
    return "\n".join(out) + "\n"


def upsert_csv(rep: dict, meta: dict, split: str) -> None:
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if RESULTS_CSV.is_file():
        with RESULTS_CSV.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
    fam = rep["families"]
    r4 = lambda x: "" if x is None else f"{x:.4f}"  # noqa: E731
    new = {"exp": rep["exp"], "split": split, "timestamp": rep["generated"], "git_sha": meta.get("git_sha") or "",
           "runner": meta.get("runner", ""), "action_source": meta.get("action_source", ""),
           **{f: r4(fam.get(f, {}).get("mean")) for f in FAMILIES},
           "overall": r4(rep["overall"]), "overall_std": r4(rep["overall_std"]), "passes": len(rep["passes"]),
           "n_tasks": rep["n_tasks"], "n_missing": rep["n_missing"], "notes": meta.get("notes", ""),
           "branch": meta.get("branch") or current_branch()}
    rows = [r for r in rows if not (r.get("exp") == rep["exp"] and r.get("split") == split)] + [new]
    tmp = RESULTS_CSV.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(RESULTS_CSV)


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


def upsert_row_into(exp: str, src, dest) -> int:
    """Copy exp's row(s) from csv `src` into csv `dest` (replace same exp+split, else append), matching columns
    by name. Columns the destination lacks are added to its header; nothing is dropped. Returns rows written."""
    from pathlib import Path
    src, dest = Path(src), Path(dest)
    _, srows = _read_csv_strict(src)
    mine = [r for r in srows if r.get("exp") == exp]
    if not mine:
        raise ValueError(f"{src}: no row for exp {exp!r}")
    if dest.is_file() and dest.stat().st_size:
        head, rows = _read_csv_strict(dest)
    else:
        head, rows = list(CSV_FIELDS), []
    for r in mine:
        for col in r:
            if col not in head:
                head.append(col)
    keys = {(r["exp"], r.get("split", "")) for r in mine}
    rows = [r for r in rows if (r.get("exp"), r.get("split", "")) not in keys] + mine
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head, restval="", extrasaction="raise")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(dest)
    return len(mine)


def report(exp: str, sel: list[dict], split_label: str, strict: bool, write: bool = True) -> dict:
    rep = build(exp, sel, strict, split_label)
    rep["split"] = split_label
    if not rep["passes"]:
        log(f"[pwa] {exp}: no scored passes yet (run `pwa score {exp}`)")
    elif write and not strict:
        write_json(exp_dir(exp) / "report.json", rep)
        upsert_csv(rep, read_meta(exp), split_label)
    return rep


def compare(a: dict, b: dict) -> dict:
    def noise(sa, sb):
        stds = [s for s in (sa, sb) if s is not None]
        return 2 * max(stds) if stds else None

    fams = {}
    for fam in FAMILIES:
        fa, fb = a["families"].get(fam), b["families"].get(fam)
        if not fa or not fb or fa["mean"] is None or fb["mean"] is None:
            continue
        thr = noise(fa["std"], fb["std"]) or 2 * FALLBACK_STD
        d = fb["mean"] - fa["mean"]
        fams[fam] = {"a": fa["mean"], "b": fb["mean"], "delta": d, "threshold": thr, "noise": abs(d) < thr}
    ov = None
    if a["overall"] is not None and b["overall"] is not None:
        thr = noise(a["overall_std"], b["overall_std"]) or 2 * FALLBACK_STD
        d = b["overall"] - a["overall"]
        ov = {"a": a["overall"], "b": b["overall"], "delta": d, "threshold": thr, "noise": abs(d) < thr}
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
            "threshold_source": "2x max pass std (fallback: paper variance 0.011)"}


def render_compare(c: dict) -> str:
    out = io.StringIO()
    p = lambda s="": print(s, file=out)  # noqa: E731
    tag = lambda r: "noise" if r["noise"] else ("?" if r["noise"] is None else "REAL")  # noqa: E731
    p(f"A={c['a']}  B={c['b']}  delta = B - A; noise if |delta| < 2x pass std")
    p(f"{'':<9} {'A':>5} {'B':>5} {'delta':>6} {'thr':>5}")
    for fam, r in list(c["families"].items()) + ([("overall", c["overall"])] if c["overall"] else []):
        p(f"{fam:<9} {f2(r['a'])} {f2(r['b'])} {r['delta']:+6.2f} {f2(r['threshold'])}  {tag(r)}")
    p()
    p("per task (sorted by delta):")
    for tid, r in sorted(c["tasks"].items(), key=lambda kv: kv[1]["delta"]):
        p(f"  {tid:<6} {r['family']:<9} {f2(r['a'])} {f2(r['b'])} {r['delta']:+6.2f}  {tag(r)}")
    return out.getvalue()


def failures(exp: str, sel: list[dict]) -> list[dict]:
    rep = build(exp, sel)
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
        if not bad and not low:
            continue
        reasons = []
        for k in rep["passes"]:
            d = eval_dir(exp) / f"pass{k}"
            s = (read_json(d / f"{tid}_score.json") or {}).get("score") or {}
            g = (read_json(d / f"{tid}_gate.json") or {}).get("score") or {}
            for src in (g, s.get("if_instruction_following_check") or {}, s.get("oe_instruction_following_check") or {}):
                if isinstance(src, dict) and src.get("failure_reason_zh"):
                    reasons.append(src["failure_reason_zh"])
            if s.get("summary_zh"):
                reasons.append(s["summary_zh"])
            if s.get("error"):
                reasons.append(f"verifier error: {s['error']}")
        status = sorted(set(bad)) or ["score_1.0"]
        out.append({"task_id": tid, "family": t["family"], "mean": tr["mean"], "status": status,
                    "reason": reasons[0] if reasons else ""})
    return out


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
