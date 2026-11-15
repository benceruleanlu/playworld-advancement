"""pwa.warm: idle-window and container caps, argument checks, and per-call state reset in a warm container.
CPU only: Modal, the GPU and the runner are mocked."""
import ast
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pwa import arms, warm as W  # noqa: E402


# -- settings: idle window and container caps --------------------------------------

def test_settings_defaults():
    s = W.settings({})
    assert s == {"gpu": "H100", "idle_min": 10, "scaledown_window": 600, "max_containers": 3,
                 "timeout": W.CALL_TIMEOUT_S}


def test_settings_accept_up_to_the_caps():
    s = W.settings({"PWA_WARM_IDLE_MIN": "20", "PWA_WARM_MAX_CONTAINERS": "8", "PWA_MODAL_GPU": "L40S"})
    assert (s["scaledown_window"], s["max_containers"], s["gpu"]) == (1200, 8, "L40S")
    assert W.settings({"PWA_WARM_IDLE_MIN": " 1 ", "PWA_WARM_MAX_CONTAINERS": ""})["scaledown_window"] == 60


@pytest.mark.parametrize("env", [
    {"PWA_WARM_IDLE_MIN": "21"}, {"PWA_WARM_IDLE_MIN": "60"}, {"PWA_WARM_IDLE_MIN": "0"},
    {"PWA_WARM_IDLE_MIN": "-5"}, {"PWA_WARM_IDLE_MIN": "10.5"}, {"PWA_WARM_IDLE_MIN": "10; rm -rf /"},
    {"PWA_WARM_MAX_CONTAINERS": "9"}, {"PWA_WARM_MAX_CONTAINERS": "0"},
    {"PWA_MODAL_GPU": "B200"}, {"PWA_MODAL_GPU": "H100 --x"},
])
def test_settings_refuse_out_of_range(env):
    with pytest.raises(W.WarmError):
        W.settings(env)


def test_fingerprint_changes_with_code_and_settings():
    s = W.settings({})
    base = W.fingerprint("abc", False, s)
    assert base == W.fingerprint("abc", False, W.settings({}))
    assert base != W.fingerprint("abd", False, s)
    assert base != W.fingerprint("abc", False, W.settings({"PWA_WARM_IDLE_MIN": "11"}))
    assert base != W.fingerprint("abc", False, W.settings({"PWA_WARM_MAX_CONTAINERS": "2"}))
    assert base != W.fingerprint("abc", False, W.settings({"PWA_MODAL_GPU": "L40S"}))


def test_dirty_checkout_has_no_fingerprint():
    # Two working-tree snapshots on one commit must never share a fingerprint: a dirty checkout gets none,
    # so ensure_deployed always redeploys it.
    s = W.settings({})
    assert W.fingerprint("abc", True, s) is None
    assert W.fingerprint("abc", False, s) is not None


def test_warm_app_reads_settings_and_class_names():
    """warm_app.py passes the capped settings to @app.cls and defines the classes pwa.warm looks up."""
    src = (ROOT / "warm_app.py").read_text()
    assert "scaledown_window=S[\"scaledown_window\"]" in src and "max_containers=S[\"max_containers\"]" in src
    assert "min_containers=0" in src
    tree = ast.parse(src)
    classes = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    assert set(W.CLASSES.values()) <= classes


# -- arguments --------------------------------------------------------------------

def test_gen_arms_argv_matches_modal_app_shape():
    argv = W.gen_arms_argv("g1", "base | --lingbot-turn-cal", "lingbot_world2", "agent", tasks="GC005, IF001",
                           notes="-dash notes", extra="--agent-model gpt-x")
    assert argv == ["g1", "--runner", "lingbot_world2", "--action-source", "agent",
                    "--arms=base | --lingbot-turn-cal", "--tasks", "GC005", "IF001", "--notes=-dash notes",
                    "--", "--agent-model", "gpt-x"]
    sharded = W.gen_arms_argv("g1", "base", "lingbot_world2_1p3b", "dataset", num_shards=2)
    assert sharded == ["g1", "--runner", "lingbot_world2_1p3b", "--action-source", "dataset", "--arms=base",
                       "--split", "dev", "--resume"]


@pytest.mark.parametrize("kw", [
    dict(exp="bad name"), dict(exp="x;rm"), dict(exp="$(id)"), dict(exp=""),
    dict(runner="sana"), dict(runner="tests/fake_runner.py"),
    dict(action_source="agent; ls"), dict(arms=""), dict(arms="--a 'unclosed"),
    dict(tasks="GC005,$(id)"), dict(tasks="GC005 IF001"), dict(split="dev;ls"),
    dict(extra="--x 'unclosed"), dict(num_shards=0), dict(num_shards=65),
])
def test_gen_arms_argv_refuses_bad_input(kw):
    args = dict(exp="g", arms="base", runner="lingbot_world2", action_source="agent")
    args.update(kw)
    with pytest.raises(W.WarmError):
        W.gen_arms_argv(args.pop("exp"), args.pop("arms"), args.pop("runner"), args.pop("action_source"), **args)


def test_base_token_is_a_baseline_arm():
    assert arms.parse_arms("base") == [[]]
    assert arms.parse_arms("base | --lingbot-turn-cal") == [[], ["--lingbot-turn-cal"]]
    assert arms.listing("g", "base") == ["g-a1 1/1 base"]


def test_shard_argv_matches_modal_app():
    tree = ast.parse((ROOT / "modal_app.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "shard_argv")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "modal_app.py", "exec"), ns)  # noqa: S102
    for argv in (["e", "--runner", "r"], ["e", "--runner", "r", "--", "--x", "1"]):
        for shard, n in ((0, 1), (1, 3)):
            assert W.shard_argv(argv, shard, n) == ns["shard_argv"](argv, shard, n)


def test_cli_parses_and_reports_bad_input(capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", None)  # input checks must not need the Modal client (CI has none)
    assert W.main(["run", "--exp", "bad name", "--arms", "base", "--runner", "lingbot_world2"]) == 2
    assert "bad experiment name" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        W.main(["run", "--exp", "g", "--arms", "base", "--runner", "sana"])  # argparse choices


# -- container side: state reset between calls --------------------------------------

class Recorder:
    def __init__(self):
        self.events, self.seen = [], []

    def run_pwa(self, behaviour):
        def fn(argv):
            self.events.append("run")
            self.seen.append({"argv": list(argv), "env": os.environ.get("PWA_GIT_SHA"),
                              "probe": os.environ.get("WARM_TEST_PROBE")})
            os.environ["WARM_TEST_LEAK"] = "1"  # a runner that leaks env, argv, path and cwd
            sys.argv[:] = ["leaked"]
            sys.path.insert(0, "/leaked")
            os.chdir("/")
            return behaviour(argv)
        return fn


def _worker(rec, behaviour=lambda argv: 0, sha="abc123", token=""):
    return W.WarmWorker("lingbot_world2", sha, run_pwa=rec.run_pwa(behaviour),
                        reload=lambda: rec.events.append("reload"), commit=lambda: rec.events.append("commit"),
                        free=lambda: rec.events.append("free"), deploy_token=token)


ARGV = ["g", "--runner", "lingbot_world2", "--action-source", "agent", "--arms=base", "--tasks", "GC005"]


def _crash(argv):
    raise RuntimeError("CUDA OOM")


def _exit3(argv):
    raise SystemExit(3)


@pytest.mark.parametrize("behaviour,rc", [(lambda argv: 0, 0), (lambda argv: 1, 1), (_crash, 1), (_exit3, 3)])
def test_each_call_restores_process_state(tmp_path, monkeypatch, behaviour, rc):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WARM_TEST_PROBE", "kept")
    monkeypatch.delenv("PWA_GIT_SHA", raising=False)
    rec = Recorder()
    w = _worker(rec, behaviour)
    argv0, path0 = list(sys.argv), list(sys.path)
    out = w.run(list(ARGV), 1, 2, {"PWA_GIT_SHA": "abc123", "PWA_GIT_BRANCH": "b"})
    assert out["rc"] == rc
    assert rec.events == ["reload", "run", "free", "commit"]
    assert rec.seen[0]["env"] == "abc123" and rec.seen[0]["probe"] == "kept"
    assert rec.seen[0]["argv"] == ["gen-arms", *W.shard_argv(ARGV, 1, 2)]
    assert "--shard" in rec.seen[0]["argv"]
    assert "WARM_TEST_LEAK" not in os.environ and "PWA_GIT_SHA" not in os.environ
    assert os.environ["WARM_TEST_PROBE"] == "kept"
    assert sys.argv == argv0 and sys.path == path0 and Path.cwd() == tmp_path


def test_second_call_is_warm_and_sees_no_state_from_the_first(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PWA_GIT_BRANCH", raising=False)
    rec = Recorder()
    loads = []
    w = _worker(rec)
    w.load(lambda: loads.append(1))
    a = w.run(list(ARGV), 0, 1, {"PWA_GIT_SHA": "abc123", "PWA_GIT_BRANCH": "first"})
    branch_seen = []
    w.run_pwa = lambda argv: branch_seen.append(os.environ.get("PWA_GIT_BRANCH")) or 0
    b = w.run(["h", *ARGV[1:]], 0, 1, {"PWA_GIT_SHA": "abc123"})
    assert loads == [1]  # the pipe loads once, at enter
    assert (a["call"], a["warm"], b["call"], b["warm"]) == (1, False, 2, True)
    assert branch_seen == [None]  # the first call's provenance env is gone
    assert a["pipe_loaded_in_s"] is not None


@pytest.mark.parametrize("argv,prov,why", [
    (["g", "--runner", "lingbot_world2_1p3b"], {}, "this class runs"),
    (["g"], {}, "no runner"),
    (["bad name", "--runner", "lingbot_world2"], {}, "bad experiment name"),
    ([], {}, "non-empty list"),
    (["g", "--runner", "lingbot_world2"], {"PWA_GIT_SHA": "other"}, "redeploy"),
])
def test_refused_calls_run_nothing(argv, prov, why):
    rec = Recorder()
    out = _worker(rec).run(argv, 0, 1, prov)
    assert out["rc"] == 2 and why in out["error"]
    assert rec.events == []  # no reload, no run, no commit


@pytest.mark.parametrize("deploy_token,call_token,ok", [
    ("", "", True),            # clean deployment, clean caller
    ("t1", "t1", True),        # dirty deployment, the client that deployed it
    ("t1", "t2", False),       # dirty deployment, another dirty snapshot on the same commit
    ("t1", "", False),         # dirty deployment, clean caller on the same commit
    ("", "t2", False),         # clean deployment, dirty caller
])
def test_dirty_deployments_serve_only_their_own_client(deploy_token, call_token, ok):
    rec = Recorder()
    prov = {"PWA_GIT_SHA": "abc123", W.TOKEN_ENV: call_token}
    out = _worker(rec, token=deploy_token).run(list(ARGV), 0, 1, prov)
    assert (out["rc"] == 0) == ok
    if not ok:
        assert out["rc"] == 2 and "uncommitted changes" in out["error"] and rec.events == []


def test_unknown_deploy_sha_does_not_refuse():
    rec = Recorder()
    assert _worker(rec, sha="").run(list(ARGV), 0, 1, {"PWA_GIT_SHA": "anything"})["rc"] == 0


# -- client: deploy only when needed --------------------------------------------------

class FakeDict(dict):
    pass


class FakeModal:
    def __init__(self, state, hydrate_ok=True):
        self.state, self.hydrate_ok, self.hydrated = state, hydrate_ok, []
        outer = self

        class Dict:
            @staticmethod
            def from_name(name, create_if_missing=False):
                assert name == W.STATE_DICT
                return outer.state

        class _C:
            def __init__(self, app, name):
                self.app, self.name = app, name

            def hydrate(self):
                outer.hydrated.append((self.app, self.name))
                if not outer.hydrate_ok:
                    raise RuntimeError("stopped")
                return self

        class Cls:
            @staticmethod
            def from_name(app, name):
                return _C(app, name)

        self.Dict, self.Cls = Dict, Cls


@pytest.fixture
def deploys(monkeypatch):
    calls = []
    monkeypatch.setattr(W.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw["env"])))
    return calls


PROV = {"PWA_GIT_SHA": "abc123", "PWA_GIT_DIRTY": "0"}


def test_ensure_deployed_skips_matching_live_app(monkeypatch, deploys):
    s = W.settings({})
    fake = FakeModal(FakeDict(fingerprint=W.fingerprint("abc123", False, s)))
    monkeypatch.setitem(sys.modules, "modal", fake)
    assert W.ensure_deployed(s, PROV, "lingbot_world2_1p3b") is False
    assert deploys == [] and fake.hydrated == [(W.APP_NAME, "Lingbot1p3b")]


@pytest.mark.parametrize("state,hydrate_ok", [({}, True), ({"fingerprint": "old"}, True), (None, False)])
def test_ensure_deployed_deploys_on_change_or_stopped_app(monkeypatch, deploys, state, hydrate_ok):
    s = W.settings({"PWA_WARM_IDLE_MIN": "15", "PWA_WARM_MAX_CONTAINERS": "2"})
    fp = W.fingerprint("abc123", False, s)
    fake = FakeModal(FakeDict(state if state is not None else {"fingerprint": fp}), hydrate_ok)
    monkeypatch.setitem(sys.modules, "modal", fake)
    assert W.ensure_deployed(s, PROV, "lingbot_world2") is True
    (cmd, env), = deploys
    assert cmd[:2] == ["modal", "deploy"] and cmd[2].endswith("warm_app.py")
    assert (env["PWA_WARM_IDLE_MIN"], env["PWA_WARM_MAX_CONTAINERS"], env["PWA_WARM_DEPLOY_SHA"]) == ("15", "2", "abc123")
    assert fake.state["fingerprint"] == fp
    assert env[W.TOKEN_ENV] == ""


@pytest.mark.parametrize("stored", [None, "match"])
def test_ensure_deployed_always_redeploys_a_dirty_checkout(monkeypatch, deploys, stored):
    s = W.settings({})
    # Even a stored fingerprint of the same commit (clean or from an earlier dirty run) is not reused.
    state = {} if stored is None else {"fingerprint": W.fingerprint("abc123", False, s)}
    fake = FakeModal(FakeDict(state))
    monkeypatch.setitem(sys.modules, "modal", fake)
    tokens = []
    for _ in range(2):  # two snapshots on one commit
        prov = {"PWA_GIT_SHA": "abc123", "PWA_GIT_DIRTY": "1"}
        assert W.ensure_deployed(s, prov, "lingbot_world2") is True
        tokens.append(prov[W.TOKEN_ENV])
    assert len(deploys) == 2 and fake.hydrated == []
    assert [env[W.TOKEN_ENV] for _, env in deploys] == tokens and tokens[0] and tokens[0] != tokens[1]
    assert "fingerprint" not in fake.state  # a clean run on this commit redeploys too


def test_warm_app_passes_the_deploy_token_to_the_worker():
    src = (ROOT / "warm_app.py").read_text()
    assert "W.TOKEN_ENV: os.environ.get(W.TOKEN_ENV" in src and "deploy_token=os.environ.get(W.TOKEN_ENV" in src


def test_cmd_run_calls_one_shard_per_container_and_reports_failures(monkeypatch, tmp_path):
    calls = []

    class Method:
        def starmap(self, items, **kw):
            calls.append((list(items), kw))
            return [{"shard": 0, "call": 2, "warm": True, "pipe_loaded_in_s": 289.0, "rc": 0},
                    RuntimeError("container died")]

    class Obj:
        run_arms = Method()

    fake = FakeModal(FakeDict())
    fake.Cls.from_name = staticmethod(lambda app, name: (lambda: Obj()))
    monkeypatch.setitem(sys.modules, "modal", fake)
    monkeypatch.setattr(W, "existing_names", lambda names: [])
    monkeypatch.setattr(W, "ensure_deployed", lambda s, prov, runner: False)
    monkeypatch.setattr(W, "provenance_env", lambda: dict(PROV))
    claim = tmp_path / "claimed.txt"
    monkeypatch.setenv("PWA_CLAIM_FILE", str(claim))
    monkeypatch.setenv("PWA_RUN_ID", "7-1")
    summary = tmp_path / "warm.json"
    rc = W.main(["run", "--exp", "g", "--arms", "base", "--runner", "lingbot_world2", "--tasks", "GC005",
                 "--num-shards", "2", "--summary", str(summary)])
    assert rc == 1
    (items, kw), = calls
    assert [tuple(i[1:3]) for i in items] == [(0, 2), (1, 2)] and kw["return_exceptions"] is True
    assert all(i[3]["PWA_RUN_ID"] == "7-1" for i in items)  # recorded as run_id, checked by pwa.arms --owned
    assert claim.read_text() == "g-a1\n"  # as modal_app.py: the names this launch generates into
    out = json.loads(summary.read_text())
    assert out["shards"][1]["rc"] == 1 and "container died" in out["shards"][1]["error"]


def test_cmd_run_refuses_existing_names(monkeypatch, capsys, tmp_path):
    monkeypatch.setitem(sys.modules, "modal", FakeModal(FakeDict()))
    claim = tmp_path / "claimed.txt"
    monkeypatch.setenv("PWA_CLAIM_FILE", str(claim))
    monkeypatch.setattr(W, "existing_names", lambda names: [n for n in names if n == "g-a2"])
    assert W.main(["run", "--exp", "g", "--arms", "base|--x", "--runner", "lingbot_world2"]) == 2
    assert "g-a2 already in the pwa-runs Volume" in capsys.readouterr().err
    assert not claim.exists()  # a refused launch claims nothing, so the workflow fetches and publishes nothing
