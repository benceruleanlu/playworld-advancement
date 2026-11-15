import json
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from adapters.lingbot_world2 import session as S
from adapters.lingbot_world2 import workspace as W
from pwa import kernel as K
from pwa.core import PwaError


def test_execute_behaves_like_a_notebook_cell():
    ns = {}
    r = W.execute(ns, "x = 20\nprint('hi')\nx + 1")
    assert r["ok"] and r["stdout"] == "hi\n21\n" and r["error"] is None
    assert W.execute(ns, "x * 2")["stdout"] == "40\n"      # state persists between cells
    assert W.execute(ns, "y = x")["stdout"] == ""           # no trailing expression, nothing echoed
    assert W.execute(ns, "None")["stdout"] == ""
    r = W.execute(ns, "import sys\nprint('err', file=sys.stderr)\n1/0")
    assert not r["ok"] and "ZeroDivisionError" in r["error"] and "err" in r["stdout"]
    assert not W.execute(ns, "def f(:")["ok"]                # syntax error
    assert not W.execute(ns, "raise SystemExit(3)")["ok"]    # cannot take the kernel down
    assert W.execute(ns, "x")["stdout"] == "20\n"
    r = W.execute(ns, f"print('a' * {W.MAX_STDOUT * 3})")
    assert len(r["stdout"]) < W.MAX_STDOUT + 100 and "characters cut" in r["stdout"]


def test_probe_chunks_cover_the_keys():
    assert [W.probe_chunks(n) for n in (0, 1, 12, 13, 28, 29, 44)] == [1, 1, 1, 2, 2, 3, 3]
    for n in (1, 12, 13, 28, 60, 100):
        c = W.probe_chunks(n)
        assert S.keys_needed(c, first=True) >= n > S.keys_needed(c - 1, first=True) or c == 1


def test_contact_sheet_and_frame_stats():
    frames = np.zeros((29, 464, 832, 3), dtype=np.uint8)
    frames[-1] = 200
    sheet = W.contact_sheet(frames, n=8, width=320)
    assert sheet.dtype == np.uint8 and sheet.shape == (2 * 232, 4 * 416, 3)
    assert sheet[:232, :416].max() == 0 and sheet[232:, -416:].min() == 200  # first and last frame
    assert W.contact_sheet(frames[:3], n=8).shape == (232, 3 * 416, 3)
    with pytest.raises(ValueError):
        W.contact_sheet(np.zeros((4, 4, 3), dtype=np.uint8))
    st = W.frame_stats(frames)
    assert st["frames"] == 29 and st["change_from_first"] == 200 and st["motion_max"] == 200
    assert st["motion_mean"] == pytest.approx(200 / 28)
    assert W.frame_stats(frames[:1])["motion_mean"] == 0


def _repo(tmp_path):
    (tmp_path / "splits").mkdir()
    (tmp_path / "splits" / "dev.tsv").write_text("# dev\ngc\tGC005\nif\tIF010\n")
    data = tmp_path / "data"
    (data / "gc").mkdir(parents=True)
    (data / "if").mkdir()
    (data / "gc" / "data.json").write_text(json.dumps(
        [{"task_id": "GC005", "prompt": "walk", "image_path": "gc/images/a.jpg"},
         {"task_id": "GC099", "prompt": "held out", "image_path": "gc/images/b.jpg"}]))
    (data / "if" / "data.json").write_text(json.dumps([{"task_id": "IF010", "image_path": "if/c.jpg"}]))
    return tmp_path


def test_task_lookup_and_dev_split(tmp_path):
    repo = _repo(tmp_path)
    assert W.dev_ids(repo) == {"GC005", "IF010"}
    assert W.find_task(repo / "data", "IF010") == ("if", {"task_id": "IF010", "image_path": "if/c.jpg"})
    with pytest.raises(KeyError):
        W.find_task(repo / "data", "GC404")
    with pytest.raises(FileNotFoundError):
        W.dev_ids(tmp_path / "elsewhere")  # no split file: refuse rather than allow everything


# ------------------------------------------------------------- torch (CPU)

def _workspace(tmp_path):
    torch = pytest.importorskip("torch")
    torch.manual_seed(0)
    model = torch.nn.Sequential(torch.nn.Linear(8, 16), torch.nn.SiLU(), torch.nn.Linear(16, 4)).requires_grad_(False)
    pipe = SimpleNamespace(model=model)
    commits = []
    ws = W.Workspace(pipe, SimpleNamespace(sample_shift=5.0), "1.3b", repo=_repo(tmp_path),
                     commit=lambda: commits.append(1))
    return ws, model, torch, commits


def test_workspace_reads_parameters_and_status(tmp_path):
    ws, model, torch, _ = _workspace(tmp_path)
    assert ws.params(r"0\.")[0][:2] == ("0.weight", (16, 8)) and len(ws.params()) == 4
    assert ws.modules("^0$") == ["0"]
    with pytest.raises(KeyError, match="similar"):
        ws.W("1.weight")
    assert ws.W("0.weight") is dict(model.named_parameters())["0.weight"]
    st = ws.status()
    assert st["dit_params"] == 8 * 16 + 16 + 16 * 4 + 4 and st["variant"] == "1.3b" and st["passes"] == 0
    assert set(ws.namespace()) == {"ws", "pipe", "model", "torch", "np", "P", "S", "CP", "MT"}


def test_workspace_counts_passes_and_captures(tmp_path):
    ws, model, torch, _ = _workspace(tmp_path)
    x = torch.ones(2, 8)
    with ws.capture(["0", r"\d"], fn=lambda t: tuple(t.shape)) as acts:
        model(x)
        model(x)
    assert ws.passes == 2 and acts == {"0": [(2, 16)] * 2, "1": [(2, 16)] * 2, "2": [(2, 4)] * 2}
    model(x)
    assert ws.passes == 3 and len(acts["0"]) == 2    # hooks removed after the block
    with pytest.raises(KeyError):
        with ws.capture("blocks.99"):
            pass


def test_workspace_task_refuses_heldout(tmp_path, monkeypatch):
    Image = pytest.importorskip("PIL.Image")
    ws, *_ = _workspace(tmp_path)
    (tmp_path / "data" / "gc" / "images").mkdir()
    Image.new("RGB", (8, 6), (10, 20, 30)).save(tmp_path / "data" / "gc" / "images" / "a.jpg")
    t = ws.task("GC005")
    assert (t["family"], t["prompt"], t["image"].size) == ("gc", "walk", (8, 6))
    with pytest.raises(PermissionError, match="held-out"):
        ws.task("GC099")
    monkeypatch.setenv("PWA_EDITOR_ALLOW_HELDOUT", "1")
    with pytest.raises(FileNotFoundError):
        ws.task("GC099")  # allowed now; this fixture simply has no image for it


def test_workspace_show_and_drain(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    ws, *_ = _workspace(tmp_path)
    ws.show(np.zeros((5, 64, 96, 3), dtype=np.uint8), name="base")
    ws.show(Image.new("RGB", (4, 4)))
    note = tmp_path / "note.txt"
    note.write_text("hello")
    ws.show(note)
    arts = ws.drain()
    assert [a["name"] for a in arts] == ["base.jpg", "image1.jpg", "note.txt"]
    assert arts[0]["data"][:2] == b"\xff\xd8" and arts[2]["data"] == b"hello" and ws.drain() == []
    big = tmp_path / "big.bin"
    big.write_bytes(b"0" * (W.MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(ValueError, match="MB of images"):
        ws.show(big)


def test_kernel_namespace_runs_cells(tmp_path):
    ws, model, torch, _ = _workspace(tmp_path)
    ns = ws.namespace()
    r = W.execute(ns, "x = model(torch.ones(1, 8)).shape\nws.passes, tuple(x)")
    assert r["ok"] and r["stdout"] == "(1, (1, 4))\n"
    assert W.execute(ns, "CP.build([('l', 90), ('j', 90)])[2]")["stdout"] == "11\n"


# ---------------------------------------------------------- local client

class _FakeKernel:
    def __init__(self, result=None, fail=None):
        self.calls, self._result, self._fail = [], result, fail
        self.run = SimpleNamespace(remote=self._run)
        self.status = SimpleNamespace(remote=lambda: {"passes": 5})

    def _run(self, code):
        self.calls.append(code)
        if self._fail:
            raise self._fail
        return dict(self._result)


def test_client_saves_images_and_logs(tmp_path):
    res = {"ok": True, "stdout": "42\n", "error": None, "seconds": 0.5,
           "artifacts": [{"name": "../../etc/passwd", "data": b"x"}, {"name": "probe 0.jpg", "data": b"\xff\xd8"}],
           "status": {"passes": 10, "probes": 2}}
    k = _FakeKernel(res)
    out = K.run_cell(k, "40 + 2", tmp_path / "editor", datetime(2026, 11, 14, 21, 0, 0, tzinfo=timezone.utc))
    assert k.calls == ["40 + 2"]
    names = sorted(p.name for p in (tmp_path / "editor").iterdir())
    assert names == ["20261114T210000000_00_passwd", "20261114T210000000_01_probe_0.jpg", "log.jsonl"]
    assert all(str(tmp_path / "editor") in p for p in out["artifacts"])
    log = json.loads((tmp_path / "editor" / "log.jsonl").read_text())
    assert log["code"] == "40 + 2" and log["at"] == "2026-11-14T21:00:00Z" and log["status"]["probes"] == 2
    text = K.render(out)
    assert text.startswith("42\n[image] ") and "ok in 0.5s; passes 10, probes 2" in text
    K.run_cell(k, "1", tmp_path / "editor")
    assert len((tmp_path / "editor" / "log.jsonl").read_text().splitlines()) == 2


def test_client_errors_are_readable(tmp_path):
    with pytest.raises(PwaError, match="modal deploy editor_app.py"):
        K.run_cell(_FakeKernel(fail=RuntimeError("App not found")), "1", tmp_path)
    assert K.call(_FakeKernel(), "status") == {"passes": 5}
    assert "ERROR" in K.render({"ok": False, "stdout": "", "error": "Traceback...", "seconds": 1, "artifacts": [], "status": {}})
    assert K.safe_name("..") == "artifact" and K.safe_name("a/b/c.mp4") == "c.mp4"


def test_client_read_code(tmp_path):
    import io
    f = tmp_path / "cell.py"
    f.write_text("ws.status()")
    assert K.read_code(str(f), None) == "ws.status()"
    assert K.read_code(None, "1 + 1") == "1 + 1"
    assert K.read_code("-", None, io.StringIO("2")) == "2" and K.read_code(None, None, io.StringIO("3")) == "3"
    for args in ((str(f), "1"), (str(tmp_path / "none.py"), None), (None, "  ")):
        with pytest.raises(PwaError):
            K.read_code(*args)


def test_data_root_needs_images_not_just_json(tmp_path):
    ws, *_ = _workspace(tmp_path)                 # the fixture repo has data/gc/data.json but no images dir
    vol = tmp_path / "volume"
    (vol / "gc" / "images").mkdir(parents=True)
    (vol / "gc" / "data.json").write_text("[]")
    ws.data_dir = vol
    assert ws._data_root() == vol                 # falls through to the full copy instead of the JSON-only checkout
    (tmp_path / "data" / "gc" / "images").mkdir()
    assert ws._data_root() == tmp_path / "data"
