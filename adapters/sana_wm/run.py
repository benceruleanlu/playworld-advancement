#!/usr/bin/env python3
"""SANA-WM runner: upstream run_agent.py + provider-aware agent API. Same argv as run_agent.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.common import agent_api  # noqa: E402
from adapters.common.upstream import import_run_agent  # noqa: E402

run_agent = import_run_agent()
print(f"[adapter] agent provider: {agent_api.patch(run_agent)}", flush=True)
raise SystemExit(run_agent.main())
