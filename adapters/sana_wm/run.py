#!/usr/bin/env python3
"""SANA-WM runner: upstream run_agent.py + provider-aware agent API. Same argv as run_agent.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.common import agent_api, loop_closure  # noqa: E402
from adapters.common.upstream import import_run_agent  # noqa: E402

player_cfg, sys.argv = agent_api.configure(sys.argv)  # --player-* runner args (agent_api docstring)
run_agent = import_run_agent()
print(f"[adapter] agent provider: {agent_api.patch(run_agent, player_cfg)}", flush=True)
if loop_closure.install(run_agent):  # LOOP_CLOSE=1, off by default (adapters/common/loop_closure.py)
    print("[adapter] loop closure: on", flush=True)
rc = run_agent.main()
loop_closure.finish()
agent_api.finish(run_agent)
raise SystemExit(rc)
