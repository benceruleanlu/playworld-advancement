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

  --lingbot-weight-mod                weight_mod=on, weight_mod_steps (generate steps with any modulated latent
                                      chunk: 0 or 1 per task in dataset mode), weight_mod_chunks (latent chunks
                                      whose camera or text scale was not 1.0; stateless: 1 per modulated rollout)

  --lingbot-if-identity-cue           if_identity=on, if_identity_prompts (prompts encoded with the cue: one per
                                      session reset, every call when stateless; third-person IF only)
  --lingbot-measured-turn             measured_turn=on|skip, measured_chunks, measured_unreliable, commanded_yaw,
                                      measured_yaw, commanded_tilt, measured_tilt (totals up to the last decision)
  --lingbot-cond-schedule             cond_sched=on|skip, cond_sched_chunks, cond_sched_calls (session chunks and
                                      DiT forward calls whose early-step cam/text scales differed from 1.0)
  --lingbot-stg                       stg=on|skip, stg_chunks, stg_calls (session latent chunks with a guided
                                      denoising step, and the extra layer-skip DiT forwards; skip = stateless)
  --lingbot-sink-size / --lingbot-local-attn   window=LOCAL:SINK (only when not the default 18:6)
  --lingbot-sink-key-scale            sink_scale=on (session reset of a task matching --lingbot-sink-scale-tasks,
                                      sink > 0) | skip (task not matched; stateless and sink 0
                                      are refused),
                                      sink_scaled_chunks (latent chunks whose denoising forwards ran with
                                      scaled sink keys)
  --lingbot-pose-memory               pose_mem=on (session reset of a task matching --lingbot-pose-mem-tasks) | skip,
                                      pose_mem_stored (latent chunks stored), pose_mem_retrievals (installs of
                                      retrieved memory), pose_mem_latents (latents recomputed into the sink),
                                      pose_mem_restores (original sink copied back: no match), pose_mem_chunks
                                      (chunks generated with memory installed), pose_mem_forwards (extra clean
                                      DiT forwards), pose_mem_evicted (bank entries dropped by the cap),
                                      pose_mem_retimes (an installed memory recomputed at a new RoPE time,
                                      time recent; not a new retrieval), pose_mem_mb (peak host MB held: bank
                                      plus sink snapshot)
  --lingbot-turn-step DEG             turn_step=DEG (yaw degrees one closed-loop chunk turns; turn_cal=1 with it),
                                      or turn_step=inactive for a task run as one dataset call (`<task>_full`)
  --lingbot-scripted-player           scripted=on (the script answered a decision) | skip (no decision asked:
                                      wait-only insight), scripted_planned (script + tail chunks),
                                      scripted_chunks (decisions answered from the script), scripted_end
                                      (1 when the script ran out and the wrapper answered END, 0 when the
                                      harness cap cut it first); the total line adds scripted_chunks and
                                      scripted_ends
  --lingbot-yaw-gain G                yaw_gain=G (or LEFT/RIGHT when they differ), yaw_gain_frames (pixel-frame
                                      deltas sent to the model with scaled j/l yaw)
  --lingbot-turntable-poses           turntable=ground|free, turntable_frames (active rotation/translation pixel
                                      frames), plus turntable_rescaled when --lingbot-turntable-rescale is on
  --lingbot-kv-noise                  kv_noise=on|skip, kv_noise_t (requested T), kv_noise_chunks (session chunks
                                      whose KV write was re-noised; image-anchored chunks stay clean)
  --lingbot-warp-reanchor             warp_reanchor=on (session reset of a task matching --lingbot-warp-tasks) | skip,
                                      warp_events (latents warped and written into y), warp_patches (valid latent cells
                                      written across warp events)

The same fields go into <task_id>_result.json under "lingbot_flags". Nothing here changes
what is generated or what the player is asked.
"""
from __future__ import annotations

import json
from pathlib import Path


# --lingbot-pose-memory session counters (run.LingBotWorld2Engine._pose_mem_counts) and their flags-line names
POSE_MEM_FIELDS = ("stored", "installs", "latents", "restores", "chunks", "forwards", "evicted", "retimes")
POSE_MEM_NAMES = {"installs": "retrievals"}


class FlagStats:
    def __init__(self, turn_cal: bool, prompt_mode: str, reanchor: bool, player_hint: bool,
                 return_stop: bool = False, gc_completion: bool = False,
                 if_horizon: bool = False, if_camera: bool = False, history_endpoints: bool = False,
                 insight_director: bool = False, if_repeat: bool = False, if_slow: bool = False,
                 gc_director: bool = False, gc_ease_turns: bool = False,
                 if_subject: bool = False, weight_mod: bool = False, window: str = "",
                 if_identity: bool = False, measured_turn: bool = False, cond_sched: str = "off", scripted: bool = False,
                 kv_noise: str = "off", kv_noise_t: float = 0.0, stg: str = "off",
                 sink_scale: bool = False, noise_mean: bool = False, turn_step: float = 0.0, yaw_gain: str = "",
                 pose_mem: bool = False, yaw_servo: bool = False, warp_reanchor: bool = False,
                 turntable: str = "", turntable_rescale: bool = False):
        self.warp_reanchor = bool(warp_reanchor)
        self.pose_mem = bool(pose_mem)
        self.yaw_servo = bool(yaw_servo)  # --lingbot-yaw-servo
        self.turntable = str(turntable)  # --lingbot-turntable-poses walk mode ("" = off)
        self.turntable_rescale = bool(turntable_rescale)
        self.yaw_gain = str(yaw_gain)  # --lingbot-yaw-gain tag ("" = off)
        self.sink_scale = bool(sink_scale)
        self.scripted = bool(scripted)
        self.cond_sched = cond_sched
        self.kv_noise, self.kv_noise_t = kv_noise, kv_noise_t
        self.stg = stg
        self.measured_turn = bool(measured_turn)
        self.if_identity = bool(if_identity)
        self.turn_step = float(turn_step or 0)  # --lingbot-turn-step: yaw degrees per closed-loop chunk
        self.window = str(window)  # "local:sink" when --lingbot-local-attn / --lingbot-sink-size differ from 18:6
        self.weight_mod = bool(weight_mod)
        self.weight_mod_late = ""  # set by the engine: WeightModulator.late_schedule()
        self.if_horizon = bool(if_horizon)
        self.if_camera = bool(if_camera)
        self.history_endpoints = bool(history_endpoints)
        self.insight_director = bool(insight_director)
        self.if_repeat = bool(if_repeat)
        self.if_slow = bool(if_slow)
        self.noise_mean = bool(noise_mean)
        self.gc_director = bool(gc_director)
        self.gc_ease_turns = bool(gc_ease_turns)
        self.if_subject = bool(if_subject)
        self.return_stop = bool(return_stop)
        self.turn_cal, self.prompt_mode = bool(turn_cal), prompt_mode
        self.reanchor, self.player_hint = bool(reanchor), bool(player_hint)
        self.gc_completion = bool(gc_completion)
        self.totals = {"tasks": 0, "caption_used": 0, "caption_fallback": 0, "reanchor_events": 0, "player_hints": 0,
                       "noise_mean_samples": 0, "return_stops": 0, "gc_completion_hints": 0, "gc_completion_ends": 0,
                       "if_horizon_tasks": 0, "if_horizon_ends": 0, "if_camera_hints": 0,
                       "player_frames_removed": 0, "insight_director_prompts": 0,
                       "if_repeat_checks": 0, "if_translation_frames": 0,
                       "gc_director_chunks": 0, "gc_director_updates": 0, "gc_eased_turns": 0,
                       "if_subject_prompts": 0, "weight_mod_steps": 0, "weight_mod_chunks": 0,
                       "if_identity_prompts": 0, "cond_sched_chunks": 0, "cond_sched_calls": 0,
                       "scripted_chunks": 0, "scripted_ends": 0,
                       "kv_noise_chunks": 0, "stg_chunks": 0, "stg_calls": 0, "sink_scaled_chunks": 0,
                       "yaw_gain_frames": 0, "yaw_servo_chunks": 0, "yaw_servo_untrusted": 0,
                       "turntable_frames": 0, "turntable_rescaled": 0,
                       **{f"pose_mem_{k}": 0 for k in POSE_MEM_FIELDS},
                       "warp_events": 0, "warp_patches": 0}
        self.new_task()

    # -- hooks (called from run.py and player_hint.wrap) ------------------------
    def new_task(self):
        self.if_camera_hints = 0
        self.player_frames_removed = 0
        self.insight_director_prompts = 0
        self.if_repeat_checks = 0
        self.if_translation_frames = 0
        self.noise_mean_samples = 0
        self.gc_director_chunks = self.gc_director_updates = 0
        self.gc_eased_turns = 0
        self.if_subject_prompts = 0
        self.weight_mod_steps = self.weight_mod_chunks = 0
        self.if_identity_prompts = 0
        self.turn_step_dataset = False  # a `<task>_full` call ran: the step does not apply there
        self.measured = {}
        self.cond_sched_chunks = self.cond_sched_calls = 0
        self.sink_scale_armed, self.sink_scaled_chunks = False, 0
        self.pose_mem_on, self.pose_mem_counts, self.pose_mem_bytes = False, dict.fromkeys(POSE_MEM_FIELDS, 0), 0
        self.warp_reanchor_armed, self.warp_events, self.warp_patches = False, 0, 0
        self.scripted_planned = self.scripted_chunks = self.scripted_end = 0
        self.kv_noise_chunks = 0
        self.yaw_gain_frames = 0
        self.yaw_servo_chunks = self.yaw_servo_untrusted = 0
        self.yaw_servo_locked = False  # the servo stood down on this task (a subject was moving)
        self.turntable_frames = 0
        self.turntable_rescaled = 0
        self.stg_chunks = self.stg_calls = 0
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

    def subject_prompt(self):
        """--lingbot-if-subject-director: one generate() call conditioned on the structured IF prompt."""
        self.if_subject_prompts += 1

    def modulated(self, steps: int = 1, chunks: int = 1):
        """--lingbot-weight-mod: generate steps with any modulated latent chunk, and modulated latent chunks."""
        self.weight_mod_steps += int(steps)
        self.weight_mod_chunks += int(chunks)

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

    def sink_armed(self):
        self.sink_scale_armed = True

    def sink_scaled(self, chunks: int = 0):
        self.sink_scaled_chunks += int(chunks)

    def pose_mem_armed(self):
        self.pose_mem_on = True

    def pose_mem_counted(self, deltas: dict, peak_bytes: int = 0):
        """--lingbot-pose-memory: per-step counter deltas from the session, and the rollout's peak host bytes."""
        for k in POSE_MEM_FIELDS:
            self.pose_mem_counts[k] += int(deltas.get(k, 0))
        self.pose_mem_bytes = max(self.pose_mem_bytes, int(peak_bytes))

    def pose_mem_summary(self, counts: dict) -> dict:
        return {f"pose_mem_{POSE_MEM_NAMES.get(k, k)}": counts[k] for k in POSE_MEM_FIELDS}

    def warp_armed(self):
        self.warp_reanchor_armed = True

    def warp_reanchored(self, events: int = 0, patches: int = 0):
        self.warp_events += int(events)
        self.warp_patches += int(patches)

    def cond_scheduled(self, chunks: int = 0, calls: int = 0):
        self.cond_sched_chunks += int(chunks)
        self.cond_sched_calls += int(calls)

    def kv_noised(self, chunks: int = 0):
        self.kv_noise_chunks += int(chunks)
    def stg_counted(self, chunks: int = 0, calls: int = 0):
        self.stg_chunks += int(chunks)
        self.stg_calls += int(calls)

    def completion_summary(self, counts) -> dict:
        if not self.gc_completion:
            return {}
        return {"gc_completion": "on", **{k: counts[k] for k in
                ("gc_completion_hints", "gc_completion_ends")}}

    def director_summary(self, counts):
        return ({"gc_director": "on", **{k: counts[k] for k in
                 ("gc_director_chunks", "gc_director_updates")}} if self.gc_director else {})

    # -- output ----------------------------------------------------------------
    def measured_turn_event(self, summary: dict):
        """measured_turn.wrap on_event: the task's totals so far (the last call is the whole rollout but
        its final chunk)."""
        self.measured = dict(summary)

    def if_horizon_event(self, kind: str, cap: int):
        """if_horizon.wrap on_event: "armed" or "end", with the task's chunk budget."""
        self.if_horizon_cap = int(cap)
        if kind == "end":
            self.if_horizon_ends += 1

    def scripted_event(self, kind: str, n: int):
        """scripted_player.wrap on_event: "plan", "chunk" or "end", with the plan length."""
        self.scripted_planned = int(n)
        if kind == "chunk":
            self.scripted_chunks += 1
        elif kind == "end":
            self.scripted_end = 1

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
        if self.noise_mean:
            s.update(noise_mean="on", noise_mean_samples=self.noise_mean_samples)
        s.update(self.director_summary(vars(self)))
        if self.gc_ease_turns:
            s.update(gc_ease_turns="on", gc_eased_turns=self.gc_eased_turns)
        if self.if_subject:
            s.update(if_subject="on", if_subject_prompts=self.if_subject_prompts)
        if self.weight_mod:
            s.update(weight_mod="on", weight_mod_steps=self.weight_mod_steps, weight_mod_chunks=self.weight_mod_chunks)
            if self.weight_mod_late:  # LINGBOT_CAM_LATE_STEPS > 0 only, so #87-only arms keep their line
                s.update(weight_mod_late=self.weight_mod_late)
        if self.window:
            s.update(window=self.window)
        if self.turn_step:
            s.update(turn_step="inactive" if self.turn_step_dataset else f"{self.turn_step:g}")
        if self.yaw_gain:
            s.update(yaw_gain=self.yaw_gain, yaw_gain_frames=self.yaw_gain_frames)
        if self.yaw_servo:
            s.update(yaw_servo="locked" if self.yaw_servo_locked else "on" if self.yaw_servo_chunks else "skip",
                     yaw_servo_chunks=self.yaw_servo_chunks, yaw_servo_untrusted=self.yaw_servo_untrusted)
        if self.turntable:
            s.update(turntable=self.turntable, turntable_frames=self.turntable_frames)
            if self.turntable_rescale:
                s.update(turntable_rescaled=self.turntable_rescaled)
        if self.if_identity:
            s.update(if_identity="on", if_identity_prompts=self.if_identity_prompts)
        s.update(self.completion_summary(vars(self)))
        if self.if_horizon:
            s.update(if_horizon="on" if self.if_horizon_cap else "skip", if_horizon_chunks=self.if_horizon_cap,
                     if_horizon_ends=self.if_horizon_ends)
        if self.cond_sched != "off":
            s.update(cond_sched=self.cond_sched, cond_sched_chunks=self.cond_sched_chunks,
                     cond_sched_calls=self.cond_sched_calls)
        if self.kv_noise != "off":
            s.update(kv_noise=self.kv_noise, kv_noise_t=f"{self.kv_noise_t:g}", kv_noise_chunks=self.kv_noise_chunks)
        if self.stg != "off":
            s.update(stg=self.stg, stg_chunks=self.stg_chunks, stg_calls=self.stg_calls)
        if self.measured_turn:
            m = self.measured
            s.update(measured_turn="on" if m else "skip", measured_chunks=m.get("chunks", 0),
                     measured_unreliable=m.get("unreliable", 0),
                     commanded_yaw=round(m.get("commanded_yaw", 0)), measured_yaw=round(m.get("measured_yaw", 0)),
                     commanded_tilt=round(m.get("commanded_tilt", 0)), measured_tilt=round(m.get("measured_tilt", 0)))
        if self.sink_scale:
            s.update(sink_scale="on" if self.sink_scale_armed else "skip", sink_scaled_chunks=self.sink_scaled_chunks)
        if self.pose_mem:
            s.update(pose_mem="on" if self.pose_mem_on else "skip", **self.pose_mem_summary(self.pose_mem_counts),
                     pose_mem_mb=f"{self.pose_mem_bytes / 2 ** 20:.0f}")
        if self.warp_reanchor:
            s.update(warp_reanchor="on" if self.warp_reanchor_armed else "skip",
                     warp_events=self.warp_events, warp_patches=self.warp_patches)
        if self.scripted:
            s.update(scripted="on" if self.scripted_planned else "skip", scripted_planned=self.scripted_planned,
                     scripted_chunks=self.scripted_chunks, scripted_end=self.scripted_end)
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
                + (f" noise_mean=on noise_mean_samples={t['noise_mean_samples']}" if self.noise_mean else "")
                + (f" return_stops={t['return_stops']}" if self.return_stop else "")
                + "".join(f" {k}={v}" for k, v in self.completion_summary(t).items())
                + (f" if_horizon_tasks={t['if_horizon_tasks']} if_horizon_ends={t['if_horizon_ends']}"
                   if self.if_horizon else "")
                + "".join(f" {k}={v}" for k, v in self.director_summary(t).items())
                + (f" gc_ease_turns=on gc_eased_turns={t['gc_eased_turns']}" if self.gc_ease_turns else "")
                + (f" if_subject=on if_subject_prompts={t['if_subject_prompts']}" if self.if_subject else "")
                + (f" cond_sched={self.cond_sched} cond_sched_chunks={t['cond_sched_chunks']}"
                   f" cond_sched_calls={t['cond_sched_calls']}" if self.cond_sched != "off" else "")
                + (f" kv_noise={self.kv_noise} kv_noise_t={self.kv_noise_t:g} kv_noise_chunks={t['kv_noise_chunks']}"
                   if self.kv_noise != "off" else "")
                + (f" stg={self.stg} stg_chunks={t['stg_chunks']} stg_calls={t['stg_calls']}"
                   if self.stg != "off" else "")
                + (f" weight_mod=on weight_mod_steps={t['weight_mod_steps']} weight_mod_chunks={t['weight_mod_chunks']}"
                   if self.weight_mod else "")
                + (f" window={self.window}" if self.window else "")
                + (f" turn_step={self.turn_step:g}" if self.turn_step else "")
                + (f" yaw_gain={self.yaw_gain} yaw_gain_frames={t['yaw_gain_frames']}" if self.yaw_gain else "")
                + (f" yaw_servo=on yaw_servo_chunks={t['yaw_servo_chunks']} yaw_servo_untrusted={t['yaw_servo_untrusted']}"
                   if self.yaw_servo else "")
                + (f" turntable={self.turntable} turntable_frames={t['turntable_frames']}"
                   + (f" turntable_rescaled={t['turntable_rescaled']}" if self.turntable_rescale else "")
                   if self.turntable else "")
                + (f" if_identity=on if_identity_prompts={t['if_identity_prompts']}" if self.if_identity else "")
                + (f" scripted=on scripted_chunks={t['scripted_chunks']} scripted_ends={t['scripted_ends']}"
                   if self.scripted else "")
                + (f" sink_scaled_chunks={t['sink_scaled_chunks']}" if self.sink_scale else "")
                + ("".join(f" {k}={v}" for k, v in self.pose_mem_summary(
                    {k: t[f"pose_mem_{k}"] for k in POSE_MEM_FIELDS}).items()) if self.pose_mem else "")
                + (f" warp_events={t['warp_events']} warp_patches={t['warp_patches']}" if self.warp_reanchor else ""))

    def finish_task(self, task_id) -> dict:
        s = self.summary(task_id)
        t = self.totals
        t["if_camera_hints"] += self.if_camera_hints
        t["player_frames_removed"] += self.player_frames_removed
        t["insight_director_prompts"] += self.insight_director_prompts
        t["if_repeat_checks"] += self.if_repeat_checks
        t["if_translation_frames"] += self.if_translation_frames
        t["tasks"] += 1
        t["noise_mean_samples"] += self.noise_mean_samples
        t["gc_director_chunks"] += self.gc_director_chunks
        t["gc_director_updates"] += self.gc_director_updates
        t["gc_eased_turns"] += self.gc_eased_turns
        t["if_subject_prompts"] += self.if_subject_prompts
        t["weight_mod_steps"] += self.weight_mod_steps
        t["weight_mod_chunks"] += self.weight_mod_chunks
        t["if_identity_prompts"] += self.if_identity_prompts
        t["scripted_chunks"] += self.scripted_chunks
        t["scripted_ends"] += self.scripted_end
        t["caption_used"] += s["caption"] == "used"
        t["caption_fallback"] += s["caption"] == "fallback"
        t["reanchor_events"] += self.reanchor_events
        t["player_hints"] += self.player_hints
        t["return_stops"] += self.return_stops
        t["gc_completion_hints"] += self.gc_completion_hints
        t["gc_completion_ends"] += self.gc_completion_ends
        t["if_horizon_tasks"] += bool(self.if_horizon_cap)
        t["if_horizon_ends"] += self.if_horizon_ends
        t["cond_sched_chunks"] += self.cond_sched_chunks
        t["cond_sched_calls"] += self.cond_sched_calls
        t["kv_noise_chunks"] += self.kv_noise_chunks
        t["stg_chunks"] += self.stg_chunks
        t["stg_calls"] += self.stg_calls
        t["sink_scaled_chunks"] += self.sink_scaled_chunks
        t["yaw_gain_frames"] += self.yaw_gain_frames
        t["yaw_servo_chunks"] += self.yaw_servo_chunks
        t["yaw_servo_untrusted"] += self.yaw_servo_untrusted
        t["turntable_frames"] += self.turntable_frames
        t["turntable_rescaled"] += self.turntable_rescaled
        for k in POSE_MEM_FIELDS:
            t[f"pose_mem_{k}"] += self.pose_mem_counts[k]
        t["warp_events"] += self.warp_events
        t["warp_patches"] += self.warp_patches
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
