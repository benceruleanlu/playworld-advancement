"""Aggregation rules: gate, missing, dropped, subset, and agreement with upstream on `all`."""
import random

import pytest

from pwa import aggregate as ag
from pwa import core


def info(fam, tid, view="first-person"):
    return {"family": fam, "task_id": tid, "view": view, "group": core.GROUP[fam]}


def res(x, **extra):
    return {"final_score_1_to_5": x, **extra}


def review(passed, verdict=None):
    return {"verdict": verdict or ("pass" if passed else "fail"), "instruction_following_score": 1 if passed else 0}


def test_gc_gate_pass_fail_and_no_review():
    sel = [info("gc", "GC001"), info("gc", "GC002"), info("gc", "GC003")]
    scores = {"GC001": res(3.0), "GC002": res(4.0), "GC003": res(5.0)}
    gates = {"GC001": review(True), "GC002": review(False), "GC003": None}
    out = ag.aggregate_pass("e", sel, {"GC001", "GC002", "GC003"}, scores, gates)
    f = out["families"]["gc"]
    # GC003 has no review -> dropped (upstream); GC002 gate fail -> 1.0
    assert f["mean"] == pytest.approx((3.0 + 1.0) / 2)
    assert (f["n"], f["gate_pass"], f["gate_fail"], f["dropped"]) == (2, 1, 1, 1)
    strict = ag.aggregate_pass("e", sel, {"GC001", "GC002", "GC003"}, scores, gates, strict=True)
    assert strict["families"]["gc"]["mean"] == pytest.approx((3.0 + 1.0 + 1.0) / 3)


def test_partial_counts_as_pass():
    sel = [info("gc", "GC001")]
    out = ag.aggregate_pass("e", sel, {"GC001"}, {"GC001": res(2.5)},
                            {"GC001": {"verdict": "partial", "instruction_following_score": 1}})
    assert out["families"]["gc"]["mean"] == 2.5


def test_gc_weighted_categories_identity_weight_2():
    cats = {"identity_id": {"score": 5, "weight": 1}, "background": {"score": 2, "weight": 1}}
    out = ag.aggregate_pass("e", [info("gc", "GC001")], {"GC001"},
                            {"GC001": {"categories": cats, "final_score_1_to_5": 1.0}}, {"GC001": review(True)})
    assert out["families"]["gc"]["mean"] == pytest.approx(round((5 * 2 + 2) / 3, 2))


def test_if_gate_only_third_person_and_embedded_review_wins():
    sel = [info("if", "IF001", "third-person"), info("if", "IF002", "first-person"), info("if", "IF003", "third-person")]
    scores = {
        "IF001": res(4.0, if_instruction_following_check=review(False)),  # embedded fail beats gate pass
        "IF002": res(3.0),                                                   # first person: ungated
        "IF003": res(2.0, ifInstructionFollowingCheck=review(True)),
    }
    gates = {"IF001": review(True)}
    out = ag.aggregate_pass("e", sel, set(scores), scores, gates)
    assert out["families"]["if"]["mean"] == pytest.approx((1.0 + 3.0 + 2.0) / 3)
    assert out["families"]["if"]["gated"] == 2


def test_insight_ungated_outsight_gated_missing_is_one():
    sel = [info("insight", "OE001"), info("insight", "OE002"), info("outsight", "OE014"), info("outsight", "OE015")]
    scores = {"OE001": res(2.0), "OE014": res(3.0, oe_instruction_following_check=review(True))}
    out = ag.aggregate_pass("e", sel, {"OE001", "OE014"}, scores, {})
    assert out["families"]["insight"]["mean"] == pytest.approx(1.5)   # OE002 missing -> 1.0
    assert out["families"]["outsight"]["mean"] == pytest.approx(2.0)  # OE015 missing -> 1.0
    assert out["families"]["insight"]["missing"] == 1
    assert out["overall"] == pytest.approx((1.5 + 2.0) / 2)


def test_error_result_is_dropped():
    out = ag.aggregate_pass("e", [info("insight", "OE001"), info("insight", "OE002")], {"OE001", "OE002"},
                            {"OE001": {"error": "x", "final_score_1_to_5": 5}, "OE002": res(2.0)}, {})
    assert out["families"]["insight"]["mean"] == 2.0
    assert out["families"]["insight"]["dropped"] == 1


def test_subset_does_not_fill_full_benchmark():
    """Upstream would pad OE with 1.0 for every unlisted OE task; ours must not."""
    sel = [info("insight", "OE001")]
    out = ag.aggregate_pass("e", sel, {"OE001"}, {"OE001": res(4.0)}, {})
    assert out["families"]["insight"]["mean"] == 4.0
    up = ag.upstream_cross_check("e", sel, {"OE001"}, {"OE001": res(4.0)}, {})
    assert up["families"]["insight"] < 1.2  # padded by 29 missing tasks


def test_matches_upstream_on_all_split():
    rng = random.Random(0)
    sel = core.select("all")
    assert len(sel) == 171
    present, scores, gates = set(), {}, {}
    for t in sel:
        tid = t["task_id"]
        roll = rng.random()
        if roll < 0.1:
            continue  # missing video
        present.add(tid)
        if roll < 0.15:
            continue  # unscored
        extra = {}
        if t["family"] == "if" and t["view"] == "third-person" and rng.random() < 0.8:
            extra["if_instruction_following_check"] = review(rng.random() < 0.6)
        if t["family"] == "outsight" and rng.random() < 0.8:
            extra["oe_instruction_following_check"] = review(rng.random() < 0.6)
        scores[tid] = res(round(rng.uniform(1, 5), 2), **extra)
        if rng.random() < 0.85:
            gates[tid] = review(rng.random() < 0.7)
    ours = ag.aggregate_pass("e", sel, present, scores, gates)
    up = ag.upstream_cross_check("e", sel, present, scores, gates)
    for fam in core.FAMILIES:
        assert ours["families"][fam]["mean"] == pytest.approx(up["families"][fam]), fam
    assert ours["overall"] == pytest.approx(up["overall"])


def test_family_sets_match_upstream_oe_split():
    up = ag._upstream()
    assert set(core.records("insight")) == set(up.OE_INSIGHT_TASKS)
    assert set(core.records("outsight")) == set(up.OE_OUT_OF_SIGHT_TASKS)


def test_mean_std():
    assert ag.mean_std([]) == (None, None)
    assert ag.mean_std([2.0]) == (2.0, None)
    m, s = ag.mean_std([1.0, 3.0])
    assert m == 2.0 and s == pytest.approx(2 ** 0.5)


def test_env_parsing(monkeypatch):
    monkeypatch.setenv("ALREADY", "keep")
    text = 'export A="x y"\nexport B=\'$NOPE\'\nexport C="$PWD/sub"\n# c\nexport D=plain # comment\nexport ALREADY="new"\n'
    env = core.parse_env_file(text, "/root")
    assert env == {"A": "x y", "B": "$NOPE", "C": "/root/sub", "D": "plain", "ALREADY": "new"}
