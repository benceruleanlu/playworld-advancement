"""Subset-aware PlayWorld aggregation mirroring upstream metrics/aggregate.py.

Upstream rules (Fail = 1):
  * value = normalized_score(key, verifier_result)  (GC uses weighted categories)
  * gated: all GC, IF when third-person, out-of-sight OE. A gated rollout counts
    its value only if review.instruction_following_score == 1, else 1.0.
    Review = embedded IF/OE check in the score result, else the gate-mode result.
  * missing rollout (no video) counts 1.0
  * a rollout whose score is unusable, or gated with no valid review, is DROPPED
    from the denominator (upstream behaviour). --strict counts those as 1.0.
  * overall = unweighted mean of the 4 family means.
Upstream fills missing tasks over the full benchmark, so it is only correct for
the `all` split; we aggregate over exactly the selected tasks.
"""
from __future__ import annotations

import math
import sys
from typing import Any

from .core import FAMILIES, PLAYWORLD

if str(PLAYWORLD) not in sys.path:
    sys.path.insert(0, str(PLAYWORLD))


def _upstream():
    from metrics import aggregate as up  # noqa: PLC0415  (submodule, imported lazily)
    return up


def score_key(exp: str, task_id: str) -> str:
    return f"pwa::{exp}/{task_id}/{task_id}.mp4"


def valid_review(r: Any) -> dict | None:
    return r if isinstance(r, dict) and r.get("verdict") in {"pass", "partial", "fail"} and not r.get("error") else None


def is_gated(info: dict) -> bool:
    fam = info["family"]
    return fam in ("gc", "outsight") or (fam == "if" and info["view"] == "third-person")


def task_value(exp: str, info: dict, has_video: bool, result: dict | None, gate: dict | None,
               strict: bool = False) -> dict:
    up = _upstream()
    out = {"task_id": info["task_id"], "family": info["family"], "gated": is_gated(info),
           "raw": None, "verdict": None, "value": None, "status": "ok"}
    if not has_video:
        out.update(value=1.0, status="missing")
        return out
    raw = up.normalized_score(score_key(exp, info["task_id"]), result or {}) if result else None
    out["raw"] = raw
    if raw is None:
        out.update(status="unscored", value=1.0 if strict else None)
        return out
    if not out["gated"]:
        out["value"] = raw
        return out
    review = up.embedded_review(result, info["group"], info["view"]) or valid_review(gate)
    if review is None:
        out.update(status="no_review", value=1.0 if strict else None)
        return out
    out["verdict"] = review.get("verdict")
    try:
        passed = float(review.get("instruction_following_score")) == 1
    except (TypeError, ValueError):
        passed = False
    out.update(value=raw if passed else 1.0, status="ok" if passed else "gate_fail")
    return out


def summarize(rows: list[dict]) -> dict:
    fams = {}
    for fam in FAMILIES:
        fr = [r for r in rows if r["family"] == fam]
        if not fr:
            continue
        vals = [r["value"] for r in fr if r["value"] is not None]
        fams[fam] = {
            "mean": sum(vals) / len(vals) if vals else None,
            "n": len(vals), "n_tasks": len(fr),
            "non_fail": sum(1 for r in fr if r["status"] == "ok"),
            "gated": sum(1 for r in fr if r["gated"]),
            "gate_pass": sum(1 for r in fr if r["gated"] and r["status"] == "ok"),
            "gate_fail": sum(1 for r in fr if r["status"] == "gate_fail"),
            "missing": sum(1 for r in fr if r["status"] == "missing"),
            "dropped": sum(1 for r in fr if r["value"] is None),
        }
    means = [f["mean"] for f in fams.values() if f["mean"] is not None]
    return {"families": fams, "overall": sum(means) / len(means) if means else None}


def aggregate_pass(exp: str, sel: list[dict], present: set[str], scores: dict, gates: dict,
                   strict: bool = False) -> dict:
    rows = [task_value(exp, i, i["task_id"] in present, scores.get(i["task_id"]), gates.get(i["task_id"]), strict)
            for i in sel]
    return {"tasks": rows, **summarize(rows)}


def upstream_cross_check(exp: str, sel: list[dict], present: set[str], scores: dict, gates: dict) -> dict:
    """Run upstream aggregate_fail_one_oe_split on the same data (only meaningful for `all`)."""
    up = _upstream()
    videos, sc, comp = [], {}, {}
    for i in sel:
        item = {"model": "pwa", "path": f"{exp}/{i['task_id']}/{i['task_id']}.mp4", "task": i["task_id"],
                "group": i["group"], "view": i["view"]}
        if i["task_id"] not in present:
            item["isPlaceholder"] = True
        videos.append(item)
        key = up.score_key(item)
        if scores.get(i["task_id"]) is not None:
            sc[key] = scores[i["task_id"]]
        if gates.get(i["task_id"]) is not None:
            comp[key] = gates[i["task_id"]]
    row = up.aggregate_fail_one_oe_split(videos, sc, {"results": comp}, models=(("pwa", "pwa"),))[0]
    names = {"gc": "gc", "if": "if", "insight": "insight", "outsight": "out_of_sight"}
    return {"families": {f: row[n]["average"] for f, n in names.items()}, "overall": row["overall"]}


def mean_std(xs: list[float]) -> tuple[float | None, float | None]:
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return m, None
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
