"""pwa gen: drive a run_agent.py-compatible runner, one invocation per family."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .core import (DATA, FAMILIES, ROOT, SANA_RUNNER, PLAYWORLD, PwaError, cap_label, exp_dir, log, now,
                   provenance, read_json, runner_num_chunks, scripted_runner, split_label, records, video_path,
                   write_json)


def resolve_runner(runner: str) -> Path:
    if runner == "sana":
        path = SANA_RUNNER
    elif (ROOT / "adapters" / runner / "run.py").is_file():
        path = ROOT / "adapters" / runner / "run.py"
    else:
        path = Path(runner)
    if not path.is_file():
        raise PwaError(f"runner {runner!r} not found (tried 'sana', adapters/{runner}/run.py, path)")
    return path.resolve()


def shard_tasks(family: str, ids: list[str], shard: int, num_shards: int) -> list[str]:
    """Replicate run_agent's sharding: data.json order, filter, then i % n == shard."""
    wanted = set(ids)
    ordered = [t for t in records(family) if t in wanted]
    return [t for i, t in enumerate(ordered) if num_shards <= 1 or i % num_shards == shard]


def runner_cmd(runner: Path, family: str, ids: list[str], out: Path, a) -> list[str]:
    cmd = [sys.executable, "-u", str(runner),
           "--mapping-json", str(DATA / family / "data.json"), "--images-dir", str(DATA),
           "--output-dir", str(out), "--tasks", *ids, "--action-source", a.action_source]
    if a.num_shards > 1:
        cmd += ["--shard", str(a.shard), "--num-shards", str(a.num_shards)]
    if os.environ.get("SANA_ROOT"):
        cmd += ["--sana-root", os.environ["SANA_ROOT"]]
    if getattr(a, "max_chunks", None):
        # upstream run_agent bounds a closed-loop rollout with --num-chunks (default 30)
        cmd += ["--num-chunks", str(a.max_chunks)]
    # Agent URL/model/keys and SANA config/checkpoint are read from the env by
    # run_agent's argparse defaults; keeping keys off argv keeps them out of ps/logs.
    return cmd + list(a.extra or [])


PLAYER_FIELDS = ("decisions", "calls", "empty", "retries", "errors", "fallbacks")  # adapters/common/agent_api.FIELDS


def parse_kv(line: str) -> dict[str, str]:
    return dict(tok.split("=", 1) for tok in line.split() if "=" in tok)


def subprocess_launch(cmd: list[str], env: dict, on_line) -> int:
    """Default: the runner is a child process (one per family); its stdout and stderr go to on_line."""
    p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, bufsize=1)
    for line in p.stdout:
        on_line(line)
    return p.wait()


def gen(a, sel: list[dict], launch=subprocess_launch, meta_extra: dict | None = None) -> dict:
    """launch(cmd, env, on_line) -> returncode runs one family; pwa gen-arms passes an in-process one
    (pwa/arms.py). meta_extra is merged into a new meta.json."""
    d = exp_dir(a.exp)
    tag = f".shard{a.shard}of{a.num_shards}" if a.num_shards > 1 else ""
    meta_path, log_path = d / f"meta{tag}.json", d / f"gen{tag}.log"
    if not a.resume:
        if a.num_shards > 1:
            clash = meta_path.exists() or (d / "meta.json").exists()
        else:
            clash = d.exists()
        if clash:
            raise PwaError(f"{d} already exists. Pick a new experiment name, or pass --resume to reuse its "
                           f"videos (upstream skip-done keeps any existing mp4).")
    scripted = scripted_runner(a.extra, os.environ)
    if a.action_source in ("agent", "refined") and not scripted and not os.environ.get("PLAYER_API_KEY"):
        raise PwaError(f"--action-source {a.action_source} needs PLAYER_API_KEY. Without it upstream silently "
                       f"falls back to dataset/WAIT actions and the rollout is open loop.")
    cap = getattr(a, "max_chunks", None)
    if cap is not None:
        if cap < 1:
            raise PwaError("--max-chunks must be >= 1", 2)
        if a.action_source == "dataset":
            raise PwaError("--max-chunks caps closed-loop agent chunks; --action-source dataset generates one long "
                           "rollout and ignores it. Use --action-source agent or refined.", 2)
        if runner_num_chunks(a.extra or []) is not None:
            raise PwaError("pass the chunk cap once: --max-chunks or `-- --num-chunks`, not both", 2)
    runner = resolve_runner(a.runner)
    # Upstream run_agent labels its lines [SANA_WM] whatever engine runs; relabel for non-SANA runners.
    label = None if a.runner == "sana" else f"[{Path(a.runner).stem if a.runner.endswith('.py') else a.runner}]"
    out = d / "videos"
    out.mkdir(parents=True, exist_ok=True)

    meta = read_json(meta_path) if a.resume else None
    if meta:
        meta.setdefault("resumed", []).append({"at": now(), "argv": sys.argv[1:], **provenance()})
    else:
        meta = {"exp": a.exp, "created": now(), **provenance(), "runner": a.runner, "runner_path": str(runner),
                "action_source": a.action_source, "split": a.split or "dev",
                "split_label": split_label(a.split, a.family, a.tasks), "families": a.family,
                "tasks": [[t["family"], t["task_id"]] for t in sel], "shard": a.shard,
                "num_shards": a.num_shards, "runner_args": a.extra or [], "notes": a.notes or "",
                "argv": sys.argv[1:], **(meta_extra or {})}
        if cap:
            meta["max_chunks"] = cap
            meta["label"] = cap_label(cap)
        if scripted:
            meta["scripted_player"] = True
    if (cap or meta.get("max_chunks")) and meta.get("max_chunks") != cap:
        raise PwaError(f"{a.exp} was generated with max_chunks={meta.get('max_chunks')}; resume it with the same cap", 2)
    write_json(meta_path, meta)
    if cap:
        log(f"[pwa] {a.exp}: {cap_label(cap)}")

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    env.setdefault("WORLDMODEL_BENCHMARK_DIR", str(PLAYWORLD))
    expected, rc_bad = [], []
    agent_errors = agent_fallbacks = agent_empty = 0
    player = dict.fromkeys(PLAYER_FIELDS, 0)  # summed `[agent] player total` lines (agent_api.PlayerStats)
    player_seen = False
    with log_path.open("a") as lf:
        for fam in FAMILIES:
            ids = [t["task_id"] for t in sel if t["family"] == fam]
            mine = shard_tasks(fam, ids, a.shard, a.num_shards)
            if not mine:
                continue
            expected += mine
            cmd = runner_cmd(runner, fam, ids, out, a)
            header = f"[pwa] {now()} family={fam} tasks={len(mine)}\n[pwa] $ {' '.join(cmd)}\n"
            sys.stderr.write(header)
            lf.write(header)
            lf.flush()

            def on_line(line):
                nonlocal agent_errors, agent_fallbacks, agent_empty, player_seen
                if "[agent] error attempt" in line:
                    agent_errors += 1
                elif "[agent] fallback=" in line:
                    agent_fallbacks += 1
                elif "[agent] empty reply" in line:
                    agent_empty += 1
                elif line.startswith("[agent] player total "):
                    player_seen = True
                    for k, v in parse_kv(line).items():
                        if k in player and v.isdigit():
                            player[k] += int(v)
                if label:
                    line = line.replace("[SANA_WM]", label)
                sys.stderr.write(line)
                lf.write(line)

            rc = launch(cmd, env, on_line)
            if rc != 0:
                rc_bad.append({"family": fam, "returncode": rc})
                lf.write(f"[pwa] runner exited {rc}\n")

    produced, failed = [], []
    for tid in expected:
        res = read_json(out / tid / f"{tid}_result.json")
        if video_path(a.exp, tid).is_file() and (res is None or res.get("success", True)):
            produced.append(tid)
        else:
            failed.append({"task_id": tid, "error": (res or {}).get("error", "no mp4 produced")})
    summary = {"exp": a.exp, "expected": len(expected), "produced": len(produced),
               "failed": failed, "runner_errors": rc_bad,
               "agent_errors": agent_errors, "agent_fallbacks": agent_fallbacks, "agent_empty": agent_empty,
               "player": player if player_seen else None, "log": str(log_path)}
    meta["last_gen"] = {"at": now(), "produced": len(produced), "failed": len(failed),
                        "agent_errors": agent_errors, "agent_fallbacks": agent_fallbacks, "agent_empty": agent_empty,
                        **({"player": player} if player_seen else {})}
    write_json(meta_path, meta)
    log(f"[pwa] gen {a.exp}: {len(produced)}/{len(expected)} mp4s" + (f", {len(failed)} failed" if failed else ""))
    if player_seen:
        log(f"[pwa] player: {player['decisions']} decisions, {player['calls']} API calls, {player['empty']} empty "
            f"replies, {player['retries']} retries, {player['errors']} errors, {player['fallbacks']} fallbacks")
    if agent_errors or agent_fallbacks:
        of = f" of {player['decisions']} decisions" if player_seen else ""
        log(f"[pwa] WARNING: {agent_fallbacks} fallback actions{of}, {agent_errors} agent API errors, {agent_empty} "
            f"empty player replies. Upstream swallows these and falls back to dataset/NEXT/WAIT actions, so those "
            f"decisions were not the player's and the rollout is not fully closed loop. Per-task counts: the "
            f"`[agent] player task=` lines in {log_path}. Check PLAYER_API_PROVIDER / key / model and "
            f"PLAYER_MAX_COMPLETION_TOKENS / PLAYER_REASONING_EFFORT (AGENTS.md, player notes).")
    for f in failed:
        log(f"[pwa]   FAILED {f['task_id']}: {f['error']}")
    return summary
