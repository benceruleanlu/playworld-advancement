"""Screening-judge panels and judge calibration. Screening only: reads report.build() output, writes nothing.

panel()        one experiment, several screening judges: per-task mean under each judge.
panel_cells()  `pwa cells A B` under several judges: a task moves only if every judge moves it the same way
               by a full point; also whether the judges agree on the direction of the delta.
calibrate()    each screening judge against the official judge on the same videos (`pwa judges EXP`).
"""
from __future__ import annotations

import io
import math

from .core import cap_label
from .report import MOVE, _avg, _md2, _md_cell, cells, f2

NOTE = "screening, not comparable to the leaderboard"
FAR = 1.0  # a screening task mean this far from the official one would flip a cell on its own
SPLIT = 0.5  # pass-to-pass spread reported for self-agreement (the dev baseline had 10/24 at 0.5+)


def _sign(d: float) -> int:
    return 0 if abs(d) < 1e-9 else (1 if d > 0 else -1)


def _names(judges: list[dict]) -> str:
    return ", ".join(j.get("name") or j["slug"] for j in judges)


def panel(reps: list[dict]) -> dict:
    slugs = [r["judge"]["slug"] for r in reps]
    tasks = []
    for tid, t0 in reps[0]["tasks"].items():
        means = {r["judge"]["slug"]: r["tasks"].get(tid, {}).get("mean") for r in reps}
        vals = [m for m in means.values() if m is not None]
        tasks.append({"task_id": tid, "family": t0["family"], "means": means,
                      "spread": max(vals) - min(vals) if len(vals) == len(reps) else None})
    # every report of one experiment reads the same meta.json, so any judge's cap is the run's cap
    cap = next((r["max_chunks"] for r in reps if r.get("max_chunks")), None)
    return {"exp": reps[0]["exp"], "panel": True, "note": NOTE, "judges": [r["judge"] for r in reps],
            "max_chunks": cap,
            "slugs": slugs, "overall": {r["judge"]["slug"]: r["overall"] for r in reps}, "tasks": tasks,
            "reports": reps}


def render_panel(p: dict, md: bool = False) -> str:
    out = io.StringIO()
    pr = lambda s="": print(s, file=out)  # noqa: E731
    slugs = p["slugs"]
    if md:
        pr(f"## {_md_cell(p['exp'])}: screening panel")
        pr()
        if p.get("max_chunks"):
            pr(f"> **{_md_cell(cap_label(p['max_chunks']).capitalize())}.** Smoke tier only; never the site headline.")
            pr()
        pr(f"> **Screening panel ({_md_cell(_names(p['judges']))}): {NOTE}.** Dev screening only; "
           "not written to results/experiments.csv.")
        pr()
        pr("| task | family | " + " | ".join(slugs) + " | spread |")
        pr("|---|---|" + "---:|" * (len(slugs) + 1))
        for t in p["tasks"]:
            pr(f"| {t['task_id']} | {t['family']} | " + " | ".join(_md2(t["means"][s]) for s in slugs)
               + f" | {_md2(t['spread'])} |")
        pr("| **overall** | | " + " | ".join(f"**{_md2(p['overall'][s])}**" for s in slugs) + " | |")
        return out.getvalue()
    if p.get("max_chunks"):
        pr(f"*** {cap_label(p['max_chunks'])} ***")
    pr(f"*** screening panel: {NOTE} ***")
    for i, s in enumerate(slugs, 1):
        pr(f"  J{i} = {s}")
    pr(f"{p['exp']}  per-task mean over passes under each judge")
    pr(f"{'task':<7} {'family':<9} " + " ".join(f"{'J' + str(i):>5}" for i in range(1, len(slugs) + 1)) + "  spread")
    for t in p["tasks"]:
        pr(f"{t['task_id']:<7} {t['family']:<9} " + " ".join(f2(t["means"][s]) for s in slugs) + f"  {f2(t['spread'])}")
    pr(f"{'overall':<17} " + " ".join(f2(p["overall"][s]) for s in slugs))
    return out.getvalue()


def panel_cells(pairs: list[tuple[dict, dict]]) -> dict:
    """pairs = [(report A, report B) per judge]. Per shared task: each judge's A, B, delta and move; agree =
    every judge's delta has the same sign (all up, all down or all zero); panel move = "up"/"down" only if
    every judge moves the task that way by at least MOVE. Tasks without a usable mean under some judge on
    either side are listed apart."""
    per = [cells(a, b) for a, b in pairs]
    slugs = [a["judge"]["slug"] for a, _ in pairs]
    by = [{r["task_id"]: r for r in c["tasks"]} for c in per]
    a0 = pairs[0][0]
    shared = [tid for tid in a0["tasks"] if all(tid in a["tasks"] and tid in b["tasks"] for a, b in pairs)]
    rows, unscored = [], []
    for tid in shared:
        if not all(tid in b for b in by):
            unscored.append(tid)
            continue
        js = {s: {k: b[tid][k] for k in ("a", "b", "delta", "move")} for s, b in zip(slugs, by)}
        moves = {j["move"] for j in js.values()}
        rows.append({"task_id": tid, "family": a0["tasks"][tid]["family"], "judges": js,
                     "agree": len({_sign(j["delta"]) for j in js.values()}) == 1,
                     "move": moves.pop() if len(moves) == 1 else "",
                     "min_delta": min(j["delta"] for j in js.values())})
    rows.sort(key=lambda r: (-r["min_delta"], r["task_id"]))
    return {"a": a0["exp"], "b": pairs[0][1]["exp"], "panel": True, "note": NOTE,
            "judges": [a["judge"] for a, _ in pairs], "slugs": slugs, "threshold": MOVE, "tasks": rows,
            "n_common": len(rows), "up": sum(r["move"] == "up" for r in rows),
            "down": sum(r["move"] == "down" for r in rows), "n_agree": sum(r["agree"] for r in rows),
            "per_judge": {s: {"up": c["up"], "down": c["down"]} for s, c in zip(slugs, per)},
            "unscored": unscored}


def render_panel_cells(c: dict) -> str:
    out = io.StringIO()
    p = lambda s="": print(s, file=out)  # noqa: E731
    p(f"*** screening panel: {NOTE} ***")
    for i, s in enumerate(c["slugs"], 1):
        pj = c["per_judge"][s]
        p(f"  J{i} = {s}  (alone: up {pj['up']}  down {pj['down']})")
    p(f"A={c['a']}  B={c['b']}  delta = B - A under each judge; moved = every judge moves |delta| >= "
      f"{c['threshold']:.1f} the same way; agree = every judge's delta has the same sign")
    head = " ".join(f"{'J' + str(i) + ':A':>5} {'B':>5} {'delta':>6}" for i in range(1, len(c["slugs"]) + 1))
    p(f"{'task':<7} {'family':<9} {head}  agree  moved")
    for r in c["tasks"]:
        cols = " ".join(f"{f2(j['a'])} {f2(j['b'])} {j['delta']:+6.2f}" for j in (r["judges"][s] for s in c["slugs"]))
        p(f"{r['task_id']:<7} {r['family']:<9} {cols}  {'yes' if r['agree'] else 'no':<5}  {r['move']}")
    p()
    p(f"panel up {c['up']}  down {c['down']}  of {c['n_common']} common tasks; direction agrees on {c['n_agree']}"
      + (f"; no usable mean under some judge: {' '.join(c['unscored'])}" if c["unscored"] else ""))
    return out.getvalue()


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1  # ties share their average rank
        i = j + 1
    return r


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation (Pearson on average ranks). None with fewer than 3 pairs or a constant side."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx, syy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    return None if sxx == 0 or syy == 0 else sxy / math.sqrt(sxx * syy)


def self_agreement(rep: dict) -> dict:
    """One judge's passes on the same videos: mean pairwise |difference| per task (mad), tasks whose passes
    spread by SPLIT or more, and Spearman between pass 1 and pass 2 values."""
    mads, split, p1, p2 = [], 0, [], []
    for t in rep["tasks"].values():
        vals = t.get("values") or []
        v = [x for x in vals if x is not None]
        if len(v) < 2:
            continue
        diffs = [abs(v[i] - v[j]) for i in range(len(v)) for j in range(i + 1, len(v))]
        mads.append(sum(diffs) / len(diffs))
        split += max(v) - min(v) >= SPLIT - 1e-9
        if vals[0] is not None and vals[1] is not None:
            p1.append(vals[0])
            p2.append(vals[1])
    return {"n": len(mads), "mad": _avg(mads), "split": split if mads else None, "spearman": spearman(p1, p2)}


def calibrate(official: dict, screening: list[dict]) -> dict:
    """Each screening judge against the official judge's per-task means, over tasks both scored."""
    rows = []
    for rep in screening:
        both = [(tid, t["mean"], official["tasks"][tid]["mean"]) for tid, t in rep["tasks"].items()
                if t["mean"] is not None and (official["tasks"].get(tid) or {}).get("mean") is not None]
        diffs = [j - o for _, j, o in both]
        far = [tid for tid, j, o in both if abs(j - o) >= FAR - 1e-9]
        rows.append({"judge": rep["judge"], "n": len(both),
                     "spearman": spearman([j for _, j, _ in both], [o for _, _, o in both]),
                     "mad": _avg([abs(d) for d in diffs]), "bias": _avg(diffs), "n_far": len(far), "far": far,
                     "passes": len(rep["passes"]), "self": self_agreement(rep), "overall": rep["overall"]})
    return {"exp": official["exp"], "note": NOTE, "far_threshold": FAR, "split_threshold": SPLIT,
            "official": {"passes": len(official["passes"]), "self": self_agreement(official),
                         "n": sum(t["mean"] is not None for t in official["tasks"].values()),
                         "overall": official["overall"]},
            "judges": rows}


def _sgn(x) -> str:
    return f"{x:+.2f}" if isinstance(x, (int, float)) else "-"


def _cnt(s: dict) -> str:
    return "-" if s["split"] is None else f"{s['split']}/{s['n']}"


def render_calibration(c: dict, md: bool = False) -> str:
    out = io.StringIO()
    p = lambda s="": print(s, file=out)  # noqa: E731
    o = c["official"]
    head = ["tasks", "spearman", "MAD", "bias", f">={c['far_threshold']:.1f} off", "passes", "self MAD",
            "self rho", f"self >={c['split_threshold']:.1f}"]
    rows = [("official (reference)", [str(o["n"]), "-", "-", "-", "-", str(o["passes"]), _md2(o["self"]["mad"]),
                                      _md2(o["self"]["spearman"]), _cnt(o["self"])])]
    rows += [(r["judge"]["slug"], [str(r["n"]), _md2(r["spearman"]), _md2(r["mad"]), _sgn(r["bias"]), str(r["n_far"]),
                                   str(r["passes"]), _md2(r["self"]["mad"]), _md2(r["self"]["spearman"]),
                                   _cnt(r["self"])]) for r in c["judges"]]
    if md:
        p(f"### Judge calibration: {_md_cell(c['exp'])}")
        p()
        p(f"> **{NOTE.capitalize()}.** Each screening judge against the official judge's per-task means on the "
          "same videos. bias = screening minus official; self = agreement between the judge's own passes.")
        p()
        p("| judge | " + " | ".join(head) + " |")
        p("|---|" + "---:|" * len(head))
        for name, f in rows:
            p(f"| {_md_cell(name)} | " + " | ".join(f) + " |")
        for r in c["judges"]:
            if r["far"]:
                p()
                p(f"{_md_cell(r['judge']['slug'])} is {c['far_threshold']:.1f} or more off official on: "
                  + ", ".join(r["far"]))
        return out.getvalue()
    p(f"*** judge calibration: {NOTE} ***")
    p(f"{c['exp']}: screening vs official per-task means; bias = screening - official; self = own passes")
    w = max(len(n) for n, _ in rows)
    p(f"{'judge':<{w}} " + " ".join(f"{h:>10}" for h in head))
    for name, f in rows:
        p(f"{name:<{w}} " + " ".join(f"{x:>10}" for x in f))
    for r in c["judges"]:
        if r["far"]:
            p(f"{r['judge']['slug']}: {c['far_threshold']:.1f} or more off official on {' '.join(r['far'])}")
    return out.getvalue()
