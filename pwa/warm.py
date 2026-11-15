"""Warm LingBot containers for smoke runs: settings, argument checks, per-call state reset, and the client.

warm_app.py deploys the Modal app `playworld-warm` with one class per LingBot runner. A container loads the
pipe once in @modal.enter and then runs `pwa gen-arms` in-process for each call, so only the first call
pays the model load (289 s measured for 14B) and first-step warm-up (~85 s). After its last call a
container stays up for the idle window (scaledown_window) and bills the GPU rate the whole time.

    python -m pwa.warm run --exp NAME --arms "base | --lingbot-turn-cal" --tasks GC005 --runner lingbot_world2
    python -m pwa.warm stop      # modal app stop playworld-warm: terminates every warm container now

`run` deploys warm_app.py first when the deployed code or settings differ from this checkout (a redeploy
starts cold containers), refuses experiment names already in the pwa-runs Volume, then calls one shard per
container and prints one JSON line per shard. Outputs are those of `pwa gen-arms` (runs/EXP-a<i>/ with
meta.json, gen.log, videos), written to the Volume like modal_app.py's gen_arms_shard.

Only this module's pure parts are imported by warm_app.py and the tests; `modal` is imported lazily.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import time
from pathlib import Path

APP_NAME = "playworld-warm"
STATE_DICT = "playworld-warm-state"  # Modal Dict: fingerprint of the deployed code and settings
CLASSES = {"lingbot_world2": "Lingbot14b", "lingbot_world2_1p3b": "Lingbot1p3b"}
VARIANTS = {"lingbot_world2": "14b", "lingbot_world2_1p3b": "1.3b"}
GPUS = ("H100", "A100-80GB", "L40S")
ACTION_SOURCES = ("dataset", "agent", "dataset_then_agent", "refined")
IDLE_DEFAULT_MIN, IDLE_MAX_MIN = 10, 20  # hard cap: a forgotten container bills at most 20 idle minutes
CONTAINERS_DEFAULT, CONTAINERS_MAX = 3, 8
CALL_TIMEOUT_S = 5 * 3600  # one call; the arms job itself times out at 350 min
NAME = re.compile(r"[A-Za-z0-9._-]+")
TASK = re.compile(r"[A-Za-z0-9_-]+")
ROOT = Path(__file__).resolve().parents[1]
TOKEN_ENV = "PWA_WARM_DEPLOY_TOKEN"  # per-deploy id, only for deployments of a checkout with uncommitted changes


class WarmError(ValueError):
    pass


# -- settings (read at deploy time from the environment) --------------------------

def _int_in(environ, key: str, default: int, lo: int, hi: int) -> int:
    raw = (environ.get(key) or "").strip() or str(default)
    if not raw.isdigit() or not lo <= int(raw) <= hi:
        raise WarmError(f"{key} must be a whole number from {lo} to {hi}, got {raw!r}")
    return int(raw)


def settings(environ=os.environ) -> dict:
    """GPU, idle window and container cap for the deployed classes. Out-of-range values are refused, not
    clamped, so a typo cannot silently keep an H100 up for an hour."""
    gpu = (environ.get("PWA_MODAL_GPU") or "H100").strip()
    if gpu not in GPUS:
        raise WarmError(f"PWA_MODAL_GPU must be one of {', '.join(GPUS)}, got {gpu!r}")
    idle = _int_in(environ, "PWA_WARM_IDLE_MIN", IDLE_DEFAULT_MIN, 1, IDLE_MAX_MIN)
    cap = _int_in(environ, "PWA_WARM_MAX_CONTAINERS", CONTAINERS_DEFAULT, 1, CONTAINERS_MAX)
    return {"gpu": gpu, "idle_min": idle, "scaledown_window": idle * 60, "max_containers": cap,
            "timeout": CALL_TIMEOUT_S}


def fingerprint(git_sha: str, dirty: bool, s: dict) -> str | None:
    """What a deployment is: the code (commit) and the class settings. A mismatch means redeploy.

    None for a checkout with uncommitted changes: the commit does not identify that code (two snapshots on one
    commit would share a fingerprint), so a dirty checkout never reuses a deployment and always redeploys."""
    if dirty:
        return None
    blob = json.dumps({"sha": git_sha, "gpu": s["gpu"], "idle": s["scaledown_window"],
                       "max": s["max_containers"]}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# -- arguments ------------------------------------------------------------------------

def shard_argv(argv: list[str], shard: int, num_shards: int) -> list[str]:
    """Same as modal_app.shard_argv: shard flags go before the `--` that starts the runner args."""
    if num_shards <= 1:
        return list(argv)
    flags = ["--shard", str(shard), "--num-shards", str(num_shards)]
    i = argv.index("--") if "--" in argv else len(argv)
    return [*argv[:i], *flags, *argv[i:]]


def gen_arms_argv(exp: str, arms: str, runner: str, action_source: str, *, tasks: str = "", split: str = "dev",
                  num_shards: int = 1, notes: str = "", extra: str = "", resume: bool = False) -> list[str]:
    """`pwa gen-arms` argv (without the command) built like modal_app.main does for --arms, after checking
    every value. The result is a list handed to Modal as data; nothing here goes through a shell."""
    from .arms import parse_arms  # noqa: PLC0415
    from .core import PwaError  # noqa: PLC0415

    if not NAME.fullmatch(exp or ""):
        raise WarmError(f"bad experiment name {exp!r}: use [A-Za-z0-9._-]+")
    if runner not in CLASSES:
        raise WarmError(f"warm containers run {', '.join(CLASSES)}; got runner {runner!r}")
    if action_source not in ACTION_SOURCES:
        raise WarmError(f"bad action source {action_source!r}")
    try:
        parse_arms(arms)
        shlex.split(extra or "")
    except (PwaError, ValueError) as e:
        raise WarmError(str(e)) from e
    if not isinstance(num_shards, int) or not 1 <= num_shards <= 64:
        raise WarmError(f"num_shards must be 1..64, got {num_shards!r}")
    argv = [exp, "--runner", runner, "--action-source", action_source, f"--arms={arms}"]
    if tasks.strip():
        ids = [t.strip() for t in tasks.split(",") if t.strip()]
        bad = [t for t in ids if not TASK.fullmatch(t)]
        if bad:
            raise WarmError(f"bad task id(s) {bad}")
        argv += ["--tasks", *ids]
    else:
        if not NAME.fullmatch(split or ""):
            raise WarmError(f"bad split {split!r}")
        argv += ["--split", split]
    if resume or num_shards > 1:
        argv.append("--resume")  # shards share runs/EXP-a<i>; pwa keeps per-shard meta files
    if notes:
        argv.append(f"--notes={notes}")
    if extra.strip():
        argv += ["--", *shlex.split(extra)]
    return argv


def argv_runner(argv: list[str]) -> str:
    return argv[argv.index("--runner") + 1] if "--runner" in argv[:-1] else ""


# -- container side: one call, then every piece of process state put back -----------

class WarmWorker:
    """What a warm container does per call. Kept free of Modal so CPU tests can drive it.

    run_pwa(argv) -> rc is pwa.cli.main; reload/commit sync the runs Volume; free releases cached GPU memory.
    Each call: reload the Volume (so the name guard and --resume see other containers' writes), apply the
    caller's provenance env, run, then restore os.environ, sys.argv, sys.path and the working directory,
    free GPU memory and commit, whatever the call did. Runner module state (flags, turn rates, upstream
    run_agent, counters) is reset by the runner's own main() on every call; only the loaded pipe is kept."""

    def __init__(self, runner: str, deploy_sha: str, run_pwa, reload=lambda: None, commit=lambda: None,
                 free=lambda: None, clock=time.time, deploy_token: str = ""):
        # deploy_token: set only when the deployed code had uncommitted changes (a random id per deploy);
        # a call is accepted only with the same token, i.e. from the client that made this deployment.
        self.runner, self.deploy_sha, self.deploy_token = runner, deploy_sha, deploy_token
        self.run_pwa, self.reload, self.commit, self.free, self.clock = run_pwa, reload, commit, free, clock
        self.calls, self.loaded_in, self.started = 0, None, clock()

    def load(self, load_fn) -> None:
        t0 = self.clock()
        load_fn()
        self.loaded_in = round(self.clock() - t0, 1)

    def run(self, argv: list[str], shard: int, num_shards: int, prov: dict) -> dict:
        self.calls += 1
        info = {"call": self.calls, "runner": self.runner, "shard": shard, "num_shards": num_shards,
                "pipe_loaded_in_s": self.loaded_in, "container_age_s": round(self.clock() - self.started),
                "warm": self.calls > 1, "deploy_sha": self.deploy_sha}
        bad = self._refuse(argv, prov)
        if bad:
            print(f"[warm] refused: {bad}", flush=True)
            return {**info, "rc": 2, "error": bad}
        print(f"[warm] call {self.calls} on this container ({'warm' if self.calls > 1 else 'first call'}), "
              f"pipe loaded at enter in {self.loaded_in}s", flush=True)
        saved = dict(os.environ), list(sys.argv), list(sys.path), os.getcwd()
        t0 = self.clock()
        rc = 1
        try:
            self.reload()
            os.environ.update({k: str(v) for k, v in prov.items()})
            try:
                rc = int(self.run_pwa(["gen-arms", *shard_argv(argv, shard, num_shards)]) or 0)
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            except Exception as e:  # noqa: BLE001 - reported to the caller; the container stays usable
                print(f"[warm] call {self.calls} crashed: {e!r}", flush=True)
                rc = 1
        finally:
            env, sys.argv, sys.path[:], cwd = saved[0], saved[1], saved[2], saved[3]
            os.environ.clear()
            os.environ.update(env)
            with contextlib.suppress(OSError):
                os.chdir(cwd)
            self.free()
            self.commit()
        return {**info, "rc": rc, "seconds": round(self.clock() - t0, 1)}

    def _refuse(self, argv, prov) -> str:
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            return "argv must be a non-empty list of strings"
        if not NAME.fullmatch(argv[0]):
            return f"bad experiment name {argv[0]!r}"
        if argv_runner(argv) != self.runner:
            return f"this class runs {self.runner}, argv asks for {argv_runner(argv) or 'no runner'}"
        sha = prov.get("PWA_GIT_SHA", "")
        if self.deploy_sha and sha and sha != self.deploy_sha:
            # The container runs the code baked in at deploy time; recording another commit would lie.
            return f"deployed code is {self.deploy_sha[:12]}, caller is {sha[:12]}; redeploy (python -m pwa.warm run does)"
        token = prov.get(TOKEN_ENV, "")
        if token != self.deploy_token:
            # A deployment of uncommitted code is used only by the client that deployed it, and a dirty caller
            # only uses its own deployment: the commit alone does not say which code either side has.
            if self.deploy_token:
                return "deployed code had uncommitted changes and this call is not from that deploy; redeploy"
            return "caller has uncommitted changes but this deployment is not its own; redeploy"
        return ""


# -- client side (GitHub Actions runner or a laptop with Modal credentials) ---------

def _git(*args: str, cwd: Path = ROOT) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def provenance_env() -> dict:
    """Env applied for one warm call only: git provenance, plus this dispatch's non-secret player settings
    (a warm container's Modal secret is the one it started with; keys are never passed here)."""
    player = {k: os.environ[k] for k in ("PLAYER_API_PROVIDER", "PLAYER_API_URL", "PLAYER_MODEL")
              if os.environ.get(k)}
    return {**player,
        "PWA_GIT_SHA": _git("rev-parse", "HEAD"),
        "PWA_GIT_BRANCH": os.environ.get("GITHUB_REF_NAME") or _git("rev-parse", "--abbrev-ref", "HEAD"),
        "PWA_GIT_DIRTY": "1" if _git("status", "--porcelain", "--", ".", ":!runs", ":!results") else "0",
        "PWA_SUBMODULE_SHA": _git("rev-parse", "HEAD", cwd=ROOT / "third_party" / "PlayWorld"),
    }


def ensure_deployed(s: dict, prov: dict, runner: str) -> bool:
    """Deploy warm_app.py unless the deployed app has this fingerprint and the runner's class resolves.
    A checkout with uncommitted changes always deploys, with a fresh TOKEN_ENV that is also put in prov, so
    its containers accept only this client's calls. Returns True when it deployed (the next call is cold)."""
    import modal  # noqa: PLC0415

    fp = fingerprint(prov["PWA_GIT_SHA"], prov["PWA_GIT_DIRTY"] == "1", s)
    token = "" if fp else secrets.token_hex(8)
    prov[TOKEN_ENV] = token
    state = modal.Dict.from_name(STATE_DICT, create_if_missing=True)
    if fp and state.get("fingerprint") == fp:
        try:
            modal.Cls.from_name(APP_NAME, CLASSES[runner]).hydrate()
            print(f"[warm] {APP_NAME} already deployed at {fp}; reusing its containers", flush=True)
            return False
        except Exception as e:  # noqa: BLE001 - stopped or never deployed: deploy below
            print(f"[warm] {APP_NAME} class {CLASSES[runner]} not reachable ({type(e).__name__}); deploying",
                  flush=True)
    env = {**os.environ, "PWA_MODAL_GPU": s["gpu"], "PWA_WARM_IDLE_MIN": str(s["idle_min"]),
           "PWA_WARM_MAX_CONTAINERS": str(s["max_containers"]), "PWA_WARM_DEPLOY_SHA": prov["PWA_GIT_SHA"],
           TOKEN_ENV: token}
    print(f"[warm] deploying {APP_NAME} ({s['gpu']}, idle {s['idle_min']} min, max {s['max_containers']} "
          f"containers per class) at {prov['PWA_GIT_SHA'][:12]}"
          f"{' with uncommitted changes (always redeployed)' if token else ''}", flush=True)
    # Forget the old fingerprint first: if the deploy fails halfway, the next run must not trust it.
    with contextlib.suppress(KeyError):
        state.pop("fingerprint")
    subprocess.run(["modal", "deploy", str(ROOT / "warm_app.py")], cwd=ROOT, env=env, check=True)
    if fp:
        state["fingerprint"] = fp  # a dirty deployment leaves no fingerprint, so nothing ever reuses it
    return True


def existing_names(names: list[str]) -> list[str]:
    import modal  # noqa: PLC0415
    have = {e.path.strip("/") for e in modal.Volume.from_name("pwa-runs", create_if_missing=True).listdir("/")}
    return [n for n in names if n in have]


def cmd_run(a) -> int:
    from .arms import arm_names, parse_arms  # noqa: PLC0415
    import modal  # noqa: PLC0415

    s = settings()
    argv = gen_arms_argv(a.exp, a.arms, a.runner, a.action_source, tasks=a.tasks, split=a.split,
                         num_shards=a.num_shards, notes=a.notes, extra=a.extra, resume=a.resume)
    names = arm_names(a.exp, len(parse_arms(a.arms)))
    taken = [] if a.resume else existing_names(names)
    if taken:
        raise WarmError(f"{', '.join(taken)} already in the pwa-runs Volume; pick a new name or pass --resume")
    if a.num_shards > s["max_containers"]:
        print(f"[warm] {a.num_shards} shards but at most {s['max_containers']} containers: shards queue", flush=True)
    prov = provenance_env()
    if os.environ.get("PWA_RUN_ID"):
        prov["PWA_RUN_ID"] = os.environ["PWA_RUN_ID"]  # recorded as run_id in each meta.json (pwa.arms --owned)
    claim = os.environ.get("PWA_CLAIM_FILE")
    if claim:
        # As modal_app.py: written only after every check and the overwrite guard passed.
        Path(claim).write_text("".join(f"{n}\n" for n in names))
    deployed = ensure_deployed(s, prov, a.runner)
    obj = modal.Cls.from_name(APP_NAME, CLASSES[a.runner])()
    t0 = time.time()
    raw = obj.run_arms.starmap([(argv, i, a.num_shards, prov) for i in range(a.num_shards)],
                               return_exceptions=True, wrap_returned_exceptions=False)
    results = [r if isinstance(r, dict) else {"shard": i, "call": None, "warm": None, "pipe_loaded_in_s": None,
                                              "rc": 1, "error": repr(r)} for i, r in enumerate(raw)]
    out = {"deployed": deployed, "settings": s, "wall_s": round(time.time() - t0, 1), "shards": results}
    print(json.dumps(out), flush=True)
    if a.summary:
        Path(a.summary).write_text(json.dumps(out, indent=2) + "\n")
    return 1 if any(r.get("rc") for r in results) else 0


def cmd_stop(_a) -> int:
    import modal  # noqa: PLC0415
    r = subprocess.run(["modal", "app", "stop", APP_NAME, "--yes"], capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    with contextlib.suppress(Exception):
        modal.Dict.from_name(STATE_DICT, create_if_missing=True).pop("fingerprint")
    if r.returncode != 0 and re.search(r"already stopped|not found|could not find", r.stdout + r.stderr, re.I):
        print(f"[warm] {APP_NAME} was not running")
        return 0
    return r.returncode


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m pwa.warm", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="deploy if needed, then run arms on warm containers")
    r.add_argument("--exp", required=True)
    r.add_argument("--arms", required=True, help="'|'-separated runner arg strings; 'base' or empty = baseline")
    r.add_argument("--runner", required=True, choices=sorted(CLASSES))
    r.add_argument("--action-source", default="agent", choices=ACTION_SOURCES)
    r.add_argument("--tasks", default="")
    r.add_argument("--split", default="dev")
    r.add_argument("--num-shards", type=int, default=1)
    r.add_argument("--notes", default="")
    r.add_argument("--extra", default="")
    r.add_argument("--resume", action="store_true")
    r.add_argument("--summary", default="", help="write the result JSON here")
    sub.add_parser("stop", help="modal app stop playworld-warm (terminates warm containers now)")
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        return cmd_run(a) if a.cmd == "run" else cmd_stop(a)
    except WarmError as e:
        print(f"pwa.warm: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
