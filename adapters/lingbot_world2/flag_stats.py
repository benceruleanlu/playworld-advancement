"""Per-task counters for the opt-in LingBot flags, so a flag that silently did nothing shows in gen.log.

After each task's generation run.py prints one line, then one run total after main():

  [lingbot] flags task=GC033 turn_cal=1 caption=used reanchor=on reanchor_events=2 player_hint=on player_hints=30
  [lingbot] flags total tasks=24 turn_cal=1 caption_used=24 caption_fallback=0 reanchor_events=9 player_hints=410

Values:
  turn_cal       1 | 0
  caption        off (flag off) | used (every call got the caption) | fallback (at least one call
                 got the goal instead: no caption, or the task record did not match) | none (no call)
  reanchor       off (flag off) | on (armed for this task) | skip (flag on, but stateless or not a
                 LINGBOT_REANCHOR_TASKS name)
  reanchor_events   latents re-anchored to the input image
  player_hint    off | on
  player_hints   decide_action calls that got the hint appended

The same fields go into <task_id>_result.json under "lingbot_flags". Nothing here changes
what is generated or what the player is asked.
"""
from __future__ import annotations

import json
from pathlib import Path


class FlagStats:
    def __init__(self, turn_cal: bool, prompt_mode: str, reanchor: bool, player_hint: bool):
        self.turn_cal, self.prompt_mode = bool(turn_cal), prompt_mode
        self.reanchor, self.player_hint = bool(reanchor), bool(player_hint)
        self.totals = {"tasks": 0, "caption_used": 0, "caption_fallback": 0, "reanchor_events": 0, "player_hints": 0}
        self.new_task()

    # -- hooks (called from run.py and player_hint.wrap) ------------------------
    def new_task(self):
        self.caption_used = self.caption_fallback = 0
        self.reanchor_armed = False
        self.reanchor_events = 0
        self.player_hints = 0

    def caption(self, used: bool):
        if used:
            self.caption_used += 1
        else:
            self.caption_fallback += 1

    def armed(self):
        self.reanchor_armed = True

    def reanchored(self, n: int = 1):
        self.reanchor_events += int(n)

    def hint(self):
        self.player_hints += 1

    # -- output ----------------------------------------------------------------
    def summary(self, task_id) -> dict:
        if self.prompt_mode == "goal":
            caption = "off"
        elif self.caption_fallback:
            caption = "fallback"
        else:
            caption = "used" if self.caption_used else "none"
        reanchor = "off" if not self.reanchor else ("on" if self.reanchor_armed else "skip")
        return {"task": task_id, "turn_cal": int(self.turn_cal), "caption": caption,
                "reanchor": reanchor, "reanchor_events": self.reanchor_events,
                "player_hint": "on" if self.player_hint else "off", "player_hints": self.player_hints}

    @staticmethod
    def line(summary: dict) -> str:
        return "[lingbot] flags " + " ".join(f"{k}={v}" for k, v in summary.items())

    def total_line(self) -> str:
        t = self.totals
        return (f"[lingbot] flags total tasks={t['tasks']} turn_cal={int(self.turn_cal)} "
                f"caption_used={t['caption_used']} caption_fallback={t['caption_fallback']} "
                f"reanchor_events={t['reanchor_events']} player_hints={t['player_hints']}")

    def finish_task(self, task_id) -> dict:
        s = self.summary(task_id)
        t = self.totals
        t["tasks"] += 1
        t["caption_used"] += s["caption"] == "used"
        t["caption_fallback"] += s["caption"] == "fallback"
        t["reanchor_events"] += self.reanchor_events
        t["player_hints"] += self.player_hints
        print(self.line(s), flush=True)
        return s

    def install(self, run_agent):
        """Wrap run_agent.run_task (looked up by main() at call time): reset the counters,
        call through unchanged, then print the summary line and record it in the result."""
        original = run_agent.run_task

        def run_task(task, engine, output_dir, args, *rest, **kw):
            self.new_task()
            result = None
            try:
                result = original(task, engine, output_dir, args, *rest, **kw)
                return result
            finally:
                tid = (task or {}).get("task_id")
                s = self.finish_task(tid)
                if isinstance(result, dict) and result.get("success"):
                    result["lingbot_flags"] = s
                    _add_to_result_json(Path(output_dir) / str(tid) / f"{tid}_result.json", s)

        run_agent.run_task = run_task


def _add_to_result_json(path: Path, summary: dict):
    """Best effort: never fail a rollout over bookkeeping."""
    try:
        data = json.loads(path.read_text())
        data["lingbot_flags"] = summary
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        print(f"[lingbot] flags: could not update {path}: {e}", flush=True)
