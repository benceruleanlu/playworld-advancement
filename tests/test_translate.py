"""English display copies of judge reasons, representative pass, per-pass scores. CPU only, no network."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from pwa import report, translate

ROOT = Path(__file__).resolve().parents[1]
ZH = ["主体静止不动", "镜头没有回到起点", "场景保持一致"]


class Fake:
    """(model, prompt) -> JSON array reply; records each call's input strings."""
    def __init__(self, fail=False, reply=None, reverse=False):
        self.calls, self.fail, self.reply, self.reverse = [], fail, reply, reverse

    def __call__(self, model, prompt):
        objs = json.loads(prompt[len(translate.PROMPT):])
        items = [o["text"] for o in objs]
        self.calls.append((model, items))
        if self.fail:
            raise OSError("network down")
        if self.reply is not None:
            return self.reply
        out = [{"id": o["id"], "en": f"EN<{o['text']}>"} for o in objs]
        if self.reverse:  # right count, right ids, reversed order: must still map by id
            out = out[::-1]
        return json.dumps(out, ensure_ascii=False)


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("PWA_TRANSLATE_MODEL", raising=False)


def test_needs_translation_skips_english():
    assert translate.needs_translation("主体静止")
    assert not translate.needs_translation("subject static, score 2/5")
    assert not translate.needs_translation("café “quoted” — dash, 90°")
    assert not translate.needs_translation("")


def test_one_batched_call_and_ascii_skip(tmp_path):
    fake = Fake()
    out = translate.translate(ZH + ["already English", ZH[0]], tmp_path / "t.json", fake)
    assert len(fake.calls) == 1 and fake.calls[0][1] == ZH  # deduplicated, English never sent
    assert fake.calls[0][0] == translate.DEFAULT_MODEL
    assert out == {z: f"EN<{z}>" for z in ZH}


def test_batches_split_at_batch_size(tmp_path, monkeypatch):
    monkeypatch.setattr(translate, "BATCH", 2)
    fake = Fake()
    out = translate.translate(ZH, None, fake)
    assert [c[1] for c in fake.calls] == [ZH[:2], ZH[2:]] and len(out) == 3


def test_cache_hit_is_free_and_keyed_by_sha256(tmp_path):
    cache = tmp_path / "eval" / "translations.json"
    translate.translate(ZH, cache, Fake())
    data = json.loads(cache.read_text())
    assert set(data) == {translate.key(z) for z in ZH} and data[translate.key(ZH[0])]["en"] == f"EN<{ZH[0]}>"
    again = Fake()
    assert translate.translate(ZH, cache, again) == {z: f"EN<{z}>" for z in ZH}
    assert again.calls == []
    more = Fake()
    translate.translate(ZH + ["新的评论"], cache, more)
    assert [c[1] for c in more.calls] == [["新的评论"]]


def test_model_env_override(monkeypatch):
    monkeypatch.setenv("PWA_TRANSLATE_MODEL", "small-model")
    fake = Fake()
    translate.translate(ZH[:1], None, fake)
    assert fake.calls[0][0] == "small-model"


@pytest.mark.parametrize("fake", [Fake(fail=True), Fake(reply="not json"), Fake(reply='["only one"]'),
                                  Fake(reply='["a", "b", "c"]'),  # bare strings: not matched by id
                                  Fake(reply='[{"id": 0, "en": "a"}, {"id": 0, "en": "b"}, {"id": 2, "en": "c"}]'),
                                  Fake(reply='[{"id": 0, "en": "a"}, {"id": 1, "en": "b"}]')])
def test_errors_give_no_translation(tmp_path, fake):
    cache = tmp_path / "t.json"
    assert translate.translate(ZH, cache, fake) == {}
    assert not cache.exists()


def test_reordered_reply_maps_by_id():
    # right count and ids in reverse order: each source keeps its own translation
    assert translate.translate(["甲", "乙"], None, Fake(reverse=True)) == {"甲": "EN<甲>", "乙": "EN<乙>"}


def test_no_key_no_call():
    assert translate.default_client() is None
    assert translate.translate(ZH, None) == {}
    rows = [{"reason": ZH[0]}, {"reason": "fine"}]
    assert translate.fill(rows) == 0 and [r["reason_en"] for r in rows] == ["", ""]


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("PWA_TRANSLATE", "0")
    assert translate.default_client() is None


def test_fill_keeps_original_and_existing():
    rows = [{"reason": ZH[0]}, {"reason": "English"}, {"reason": ZH[1], "reason_en": "kept"}]
    fake = Fake()
    assert translate.fill(rows, None, fake) == 1
    assert rows[0] == {"reason": ZH[0], "reason_en": f"EN<{ZH[0]}>"}
    assert rows[1]["reason_en"] == "" and rows[2]["reason_en"] == "kept"
    assert fake.calls[0][1] == [ZH[0]]


# -- representative pass ---------------------------------------------------------------------------------------

def test_representative_pass_closest_to_mean():
    # mean 4.0 of 5/4/1/... : the 1.0 pass says the task failed; its reason must not be the one shown
    vals, reasons = [5.0, 4.0, 1.0, 6.0], ["great", "good", "failed", "x"]
    assert report.representative(vals, reasons, 4.0) == 1
    assert report.representative([3.0, 5.0], ["a", "b"], 4.0) == 0  # tie: earliest
    assert report.representative([None, 2.0], ["dropped", "kept"], 2.0) == 1
    assert report.representative([4.0, 2.0], ["", "only reason"], 3.5) == 1  # passes without a reason skipped
    assert report.representative([None, None], ["", "err"], None) == 1
    assert report.representative([1.0], [""], 1.0) is None


def _pass(d, tid, score, summary, gate=None):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tid}_score.json").write_text(json.dumps({"score": {"final_score_1_to_5": score, "summary_zh": summary}}))
    if gate is not None:
        (d / f"{tid}_gate.json").write_text(json.dumps({"score": gate}))


def test_pass_reason_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "eval_dir", lambda exp, judge=None: tmp_path)
    _pass(tmp_path / "pass1", "GC005", 3, "总结", {"verdict": "fail", "failure_reason_zh": "没有移动"})
    _pass(tmp_path / "pass2", "GC005", 3, "总结二", {"verdict": "pass", "failure_reason_zh": ""})
    assert report.pass_reason("e", "GC005", 1) == "没有移动"
    assert report.pass_reason("e", "GC005", 2) == "总结二"
    assert report.pass_reason("e", "GC005", 3) == ""


# -- rendering ---------------------------------------------------------------------------------------------------

def test_passes_cell():
    assert report.passes_cell([4.0, 4.0, 3.5, None]) == "4/4/3.5/-"
    assert report.passes_cell([2.25]) == "2.25" and report.passes_cell([]) == "-"


def test_failures_md_english_first_original_kept():
    rows = [{"task_id": "IF002", "family": "if", "mean": 4.0, "status": ["ok"], "pass_scores": [4.0, 4.0, 4.0, 4.0],
             "reason": "主体<静止>|", "reason_en": "subject <static>"},
            {"task_id": "GC005", "family": "gc", "mean": 2.0, "status": ["ok"], "pass_scores": [2.0], "reason": "plain"}]
    md = report.render_failures_md(rows)
    assert "| task | family | mean | passes | status | reason |" in md
    assert ("| IF002 | if | 4.00 | 4/4/4/4 | ok | subject &lt;static&gt;<details><summary>judge's original</summary>"
            "主体&lt;静止&gt;\\|</details> |") in md
    assert "| GC005 | gc | 2.00 | 2 | ok | plain |" in md
    assert "original" in md.splitlines()[-1] and "authoritative" in md


# -- manifests ---------------------------------------------------------------------------------------------------

def _manifest(path, tasks):
    path.write_text(json.dumps({"exp": path.stem, "scored": True, "tasks": tasks}, ensure_ascii=False))


def test_translate_media_fills_in_place(tmp_path):
    _manifest(tmp_path / "a.json", [{"task_id": "GC005", "mean": 3.0, "reason": ZH[0]},
                                    {"task_id": "GC016", "mean": 2.0, "reason": "English already"}])
    _manifest(tmp_path / "b.json", [{"task_id": "IF002", "mean": 1.0, "reason": ZH[1], "reason_en": "kept"}])
    _manifest(tmp_path / "c.json", [{"task_id": "OE001", "mean": 1.0, "reason": ZH[2]}])
    (tmp_path / "index.json").write_text('{"runs": []}')
    before_b = (tmp_path / "b.json").read_text()
    fake = Fake()
    done = translate.translate_media(tmp_path, ["a", "b", "nosuch"], fake)
    assert done == {"a": 1, "b": 0} and len(fake.calls) == 1 and fake.calls[0][1] == [ZH[0]]
    a = json.loads((tmp_path / "a.json").read_text())
    assert a["tasks"][0] == {"task_id": "GC005", "mean": 3.0, "reason": ZH[0], "reason_en": f"EN<{ZH[0]}>"}
    assert "reason_en" not in a["tasks"][1] and a["scored"] is True
    assert (tmp_path / "b.json").read_text() == before_b
    assert "reason_en" not in json.loads((tmp_path / "c.json").read_text())["tasks"][0]  # not selected
    assert json.loads((tmp_path / "index.json").read_text()) == {"runs": []}
    # all manifests, failing client: nothing changes, no error
    snap = {p.name: p.read_text() for p in tmp_path.iterdir()}
    stats = {}
    translate.translate_media(tmp_path, None, Fake(fail=True), stats=stats)
    assert {p.name: p.read_text() for p in tmp_path.iterdir()} == snap
    assert stats == {"pending": 1, "untranslated": 1}  # only c's reason is still pending


def test_translate_media_fills_fail_reason(tmp_path):
    _manifest(tmp_path / "a.json", [{"task_id": "GC005", "reason": ZH[0], "fail_reason": ZH[1], "fail_pass": 1}])
    stats = {}
    assert translate.translate_media(tmp_path, None, Fake(), stats=stats) == {"a": 2}
    t = json.loads((tmp_path / "a.json").read_text())["tasks"][0]
    assert t["reason_en"] == f"EN<{ZH[0]}>" and t["fail_reason_en"] == f"EN<{ZH[1]}>"
    assert stats == {"pending": 2, "untranslated": 0}


def test_translate_media_cli_without_key_changes_nothing_and_fails(tmp_path):
    _manifest(tmp_path / "a.json", [{"task_id": "GC005", "reason": ZH[0]}])
    before = (tmp_path / "a.json").read_text()
    env = {k: v for k, v in __import__("os").environ.items() if k != "GEMINI_API_KEY"}
    r = subprocess.run([sys.executable, "-m", "pwa.cli", "translate-media", "--dir", str(tmp_path), "--exps", "all",
                        "--json"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 1, r.stderr  # a backfill that translated nothing fails
    assert json.loads(r.stdout) == {"a": 0} and (tmp_path / "a.json").read_text() == before
    assert "1 of 1 reason(s) left untranslated" in r.stderr


def test_media_manifest_carries_pass_scores_and_reason_en(tmp_path, monkeypatch):
    from pwa import media
    monkeypatch.setattr(media, "video_path", lambda exp, tid: tmp_path / "none.mp4")
    monkeypatch.setattr(media, "read_meta", lambda exp: {"runner": "lingbot_world2"})
    monkeypatch.setattr(media, "passes_present", lambda exp: [1, 2])
    monkeypatch.setattr(media, "failures", lambda exp, sel, all_tasks=False: [
        {"task_id": "GC005", "family": "gc", "mean": 4.0, "status": ["ok"], "pass_scores": [4.0, 4.0],
         "reason": ZH[0], "reason_en": ""}])
    monkeypatch.setattr(report, "translations_path", lambda exp, judge=None: tmp_path / "translations.json")
    fake = Fake()
    monkeypatch.setattr(translate, "default_client", lambda: fake)
    man = media.build("e1", [{"task_id": "GC005", "family": "gc"}], tmp_path / "out", "", "")
    t = man["tasks"][0]
    assert t["pass_scores"] == [4.0, 4.0] and t["mean"] == 4.0
    assert t["reason"] == ZH[0] and t["reason_en"] == f"EN<{ZH[0]}>"
    assert json.loads((tmp_path / "out" / "e1.json").read_text())["tasks"][0]["reason_en"] == f"EN<{ZH[0]}>"
    assert (tmp_path / "translations.json").is_file()
