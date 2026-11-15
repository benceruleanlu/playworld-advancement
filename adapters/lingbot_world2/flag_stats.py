"""Per-task counters for the opt-in LingBot flags, so a flag that silently did nothing shows in gen.log.

After each task's generation run.py prints one line, then one run total after main():

  [lingbot] flags task=GC033 turn_cal=1 caption=used reanchor=on reanchor_events=2 player_hint=on player_hints=30
  [lingbot] flags total tasks=24 turn_cal=1 caption_used=24 caption_fallback=0 reanchor_events=9 player_hints=410

Values:
  turn_cal       1 | 0
  caption        off (flag off) | used (every call got the caption) | fallback (at least one call
                 got the goal instead: no caption, or the task record did not match) | none (no call) |
                 director (no --lingbot-caption-prompt, but --lingbot-insight-director gave the model the
                 caption on this task)
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

Only with --lingbot-if-horizon the line also ends with:
  if_horizon         on (an IF task the player was asked about) | skip (not IF, or no player)
  if_horizon_chunks  the task's chunk budget (0 when skipped)
  if_horizon_ends    1 when the wrapper ended the rollout at the budget, 0 when the player ended it earlier

Each of these flags adds its fields only when it is on (the total line adds the count):
  --lingbot-if-camera-hint            if_camera=on, if_camera_hints (third-person IF decisions that got the reminder)
  --lingbot-player-history-endpoints  history_endpoints=on, player_frames_removed (older-chunk samples dropped
                                      from the player's input, across decisions)
  --lingbot-insight-director          insight_director=on, insight_director_prompts (generate calls whose model
                                      prompt got the caption + cue; insight tasks only)
  --lingbot-if-repeat-check           if_repeat=on, if_repeat_checks (IF decisions that got the repeat reminder)
  --lingbot-if-slow-translation       if_slow=on, if_translation_frames (IF session frames whose W/S/A/D
                                      translation was halved)

The same fields go into <task_id>_result.json under "lingbot_flags". Nothing here changes
what is generated or what the player is asked.
"""
from __future__ import annotations

import json
from pathlib import Path


class FlagStats:
    def __init__(self, turn_cal: bool, prompt_mode: str, reanchor: bool, player_hint: bool,
                 return_stop: bool = False, gc_completion: bool = False,
                 if_horizon: bool = False, if_camera: bool = False, history_endpoints: bool = False,
                 insight_director: bool = False, if_repeat: bool = False, if_slow: bool = False, if_subject: bool = False):
        self.if_horizon = bool(if_horizon)
        self.if_camera = bool(if_camera)
        self.history_endpoints = bool(history_endpoints)
        self.insight_director = bool(insight_director)
        self.if_repeat = bool(if_repeat)
        self.if_slow = bool(if_slow)
        self.if_subject = bool(if_subject)
        self.return_stop = bool(return_stop)
        self.turn_cal, self.prompt_mode = bool(turn_cal), prompt_mode
        self.reanchor, self.player_hint = bool(reanchor), bool(player_hint)
        self.gc_completion = bool(gc_completion)
        self.totals = {"tasks": 0, "caption_used": 0, "caption_fallback": 0, "reanchor_events": 0, "player_hints": 0,
                       "if_subject_prompts": 0, "return_stops": 0, "gc_completion_hints": 0, "gc_completion_ends": 0,
                       "if_horizon_tasks": 0, "if_horizon_ends": 0, "if_camera_hints": 0,
                       "player_frames_removed": 0, "insight_director_prompts": 0,
                       "if_repeat_checks": 0, "if_translation_frames": 0}
        self.new_task()

    # -- hooks (called from run.py and player_hint.wrap) ------------------------
    def new_task(self):
        self.if_camera_hints = 0
        self.player_frames_removed = 0
        self.insight_director_prompts = 0
        self.if_repeat_checks = 0
        self.if_translation_frames = 0
        self.if_subject_prompts = 0
        self.caption_used = self.caption_fallback = 0
        self.reanchor_armed = False
        self.reanchor_events = 0
        self.player_hints = 0
        self.return_stop_armed = False
        self.return_stops = 0
        self.gc_completion_hints = self.gc_completion_ends = 0
        self.if_horizon_cap = 0
        self.if_horizon_ends = 0

    def caption(self, used: bool):
        if used:
            self.caption_used += 1
        else:
            self.caption_fallback += 1

    def armed(self):
        self.reanchor_armed = True

    def reanchored(self, n: int = 1):
        self.reanchor_events += int(n)

    def if_camera_hint(self):
        self.if_camera_hints += 1

    def history_removed(self, n):
        self.player_frames_removed += int(n)

    def director_prompt(self, used):
        self.insight_director_prompts += int(used)

    def if_repeat_hint(self):
        self.if_repeat_checks += 1

    def if_scaled(self, n):
        self.if_translation_frames += int(n)

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

    def completion_summary(self, counts) -> dict:
        if not self.gc_completion:
            return {}
        return {"gc_completion": "on", **{k: counts[k] for k in
                ("gc_completion_hints", "gc_completion_ends")}}

    # -- output ----------------------------------------------------------------
    def if_horizon_event(self, kind: str, cap: int):
        """if_horizon.wrap on_event: "armed" or "end", with the task's chunk budget."""
        self.if_horizon_cap = int(cap)
        if kind == "end":
            self.if_horizon_ends += 1

    def summary(self, task_id) -> dict:
        if self.prompt_mode == "goal":
            caption = "director" if self.insight_director and self.insight_director_prompts else "off"
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
        if self.if_camera:
            s.update(if_camera="on", if_camera_hints=self.if_camera_hints)
        if self.history_endpoints:
            s.update(history_endpoints="on", player_frames_removed=self.player_frames_removed)
        if self.insight_director:
            s.update(insight_director="on", insight_director_prompts=self.insight_director_prompts)
        if self.if_repeat:
            s.update(if_repeat="on", if_repeat_checks=self.if_repeat_checks)
        if self.if_slow:
            s.update(if_slow="on", if_translation_frames=self.if_translation_frames)
        if self.if_subject:
            s.update(if_subject="on", if_subject_prompts=self.if_subject_prompts)
        s.update(self.completion_summary(vars(self)))
        if self.if_horizon:
            s.update(if_horizon="on" if self.if_horizon_cap else "skip", if_horizon_chunks=self.if_horizon_cap,
                     if_horizon_ends=self.if_horizon_ends)
        return s

    @staticmethod
    def line(summary: dict) -> str:
        return "[lingbot] flags " + " ".join(f"{k}={v}" for k, v in summary.items())

    def total_line(self) -> str:
        t = self.totals
        return (f"[lingbot] flags total tasks={t['tasks']} turn_cal={int(self.turn_cal)} "
                f"caption_used={t['caption_used']} caption_fallback={t['caption_fallback']} "
                f"reanchor_events={t['reanchor_events']} player_hints={t['player_hints']}"
                + (f" if_camera_hints={t['if_camera_hints']}" if self.if_camera else "")
                + (f" player_frames_removed={t['player_frames_removed']}" if self.history_endpoints else "")
                + (f" insight_director_prompts={t['insight_director_prompts']}" if self.insight_director else "")
                + (f" if_repeat_checks={t['if_repeat_checks']}" if self.if_repeat else "")
                + (f" if_translation_frames={t['if_translation_frames']}" if self.if_slow else "")
                + (f" if_subject=on if_subject_prompts={t['if_subject_prompts']}" if self.if_subject else "")
                + (f" return_stops={t['return_stops']}" if self.return_stop else "")
                + "".join(f" {k}={v}" for k, v in self.completion_summary(t).items())
                + (f" if_horizon_tasks={t['if_horizon_tasks']} if_horizon_ends={t['if_horizon_ends']}"
                   if self.if_horizon else ""))

    def finish_task(self, task_id) -> dict:
        s = self.summary(task_id)
        t = self.totals
        t["if_camera_hints"] += self.if_camera_hints
        t["player_frames_removed"] += self.player_frames_removed
        t["insight_director_prompts"] += self.insight_director_prompts
        t["if_repeat_checks"] += self.if_repeat_checks
        t["if_translation_frames"] += self.if_translation_frames
        t["tasks"] += 1
        t["if_subject_prompts"] += self.if_subject_prompts
        t["caption_used"] += s["caption"] == "used"
        t["caption_fallback"] += s["caption"] == "fallback"
        t["reanchor_events"] += self.reanchor_events
        t["player_hints"] += self.player_hints
        t["return_stops"] += self.return_stops
        t["gc_completion_hints"] += self.gc_completion_hints
        t["gc_completion_ends"] += self.gc_completion_ends
        t["if_horizon_tasks"] += bool(self.if_horizon_cap)
        t["if_horizon_ends"] += self.if_horizon_ends
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
