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

Only with --lingbot-return-stop the line also ends with (so lines without the flag are unchanged):
  return_stop    on (the goal armed the stop) | skip (no single final return in the goal, or no player)
  return_stops   decisions answered by the stop (WAIT or END) instead of the player

With --lingbot-gc-completion-hint, also add gc_completion=on,
gc_completion_hints (GC decisions receiving the reminder), and gc_completion_ends
(END replies from those decisions). They are observations, not forced stops.

The same fields go into <task_id>_result.json under "lingbot_flags". Nothing here changes
what is generated or what the player is asked.
"""
from __future__ import annotations

import json
from pathlib import Path


class FlagStats:
    def __init__(self, turn_cal: bool, prompt_mode: str, reanchor: bool, player_hint: bool,
                 return_stop: bool = False, gc_completion: bool = False, weight_mod: bool = False):
        self.return_stop = bool(return_stop)
        self.turn_cal, self.prompt_mode = bool(turn_cal), prompt_mode
        self.reanchor, self.player_hint = bool(reanchor), bool(player_hint)
        self.gc_completion, self.weight_mod = bool(gc_completion), bool(weight_mod)
        self.totals = {"tasks": 0, "caption_used": 0, "caption_fallback": 0, "reanchor_events": 0, "player_hints": 0,
                       "return_stops": 0, "gc_completion_hints": 0, "gc_completion_ends": 0, "weight_mod_steps": 0}
        self.new_task()

    # -- hooks (called from run.py and player_hint.wrap) ------------------------
    def new_task(self):
        self.caption_used = self.caption_fallback = 0
        self.reanchor_armed = False
        self.reanchor_events = 0
        self.player_hints = 0
        self.return_stop_armed = False
        self.return_stops = 0
        self.gc_completion_hints = self.gc_completion_ends = 0
        self.weight_mod_steps = 0

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

    def return_stop_event(self, kind: str):
        """return_stop.wrap on_event: "armed" or "stop"."""
        if kind == "armed":
            self.return_stop_armed = True
        elif kind == "stop":
            self.return_stops += 1

    def completion_hint(self):
        self.gc_completion_hints += 1

    def completion_end(self):
        self.gc_completion_ends += 1

    def modulated(self, n: int = 1):
        self.weight_mod_steps += int(n)

    def completion_summary(self, counts) -> dict:
        if not self.gc_completion:
            return {}
        return {"gc_completion": "on", **{k: counts[k] for k in
                ("gc_completion_hints", "gc_completion_ends")}}

    # -- output ----------------------------------------------------------------
    def summary(self, task_id) -> dict:
        if self.prompt_mode == "goal":
            caption = "off"
        elif self.caption_fallback:
            caption = "fallback"
        else:
            caption = "used" if self.caption_used else "none"
        reanchor = "off" if not self.reanchor else ("on" if self.reanchor_armed else "skip")
        s = {"task": task_id, "turn_cal": int(self.turn_cal), "caption": caption,
             "reanchor": reanchor, "reanchor_events": self.reanchor_events,
             "player_hint": "on" if self.player_hint else "off", "player_hints": self.player_hints}
        if self.return_stop:
            s.update(return_stop="on" if self.return_stop_armed else "skip", return_stops=self.return_stops)
        s.update(self.completion_summary(vars(self)))
        if self.weight_mod:
            s.update(weight_mod="on", weight_mod_steps=self.weight_mod_steps)
        return s

    @staticmethod
    def line(summary: dict) -> str:
        return "[lingbot] flags " + " ".join(f"{k}={v}" for k, v in summary.items())

    def total_line(self) -> str:
        t = self.totals
        return (f"[lingbot] flags total tasks={t['tasks']} turn_cal={int(self.turn_cal)} "
                f"caption_used={t['caption_used']} caption_fallback={t['caption_fallback']} "
                f"reanchor_events={t['reanchor_events']} player_hints={t['player_hints']}"
                + (f" return_stops={t['return_stops']}" if self.return_stop else "")
                + "".join(f" {k}={v}" for k, v in self.completion_summary(t).items())
                + (f" weight_mod_steps={t['weight_mod_steps']}" if self.weight_mod else ""))

    def finish_task(self, task_id) -> dict:
        s = self.summary(task_id)
        t = self.totals
        t["tasks"] += 1
        t["caption_used"] += s["caption"] == "used"
        t["caption_fallback"] += s["caption"] == "fallback"
        t["reanchor_events"] += self.reanchor_events
        t["player_hints"] += self.player_hints
        t["return_stops"] += self.return_stops
        t["gc_completion_hints"] += self.gc_completion_hints
        t["gc_completion_ends"] += self.gc_completion_ends
        t["weight_mod_steps"] += self.weight_mod_steps
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
