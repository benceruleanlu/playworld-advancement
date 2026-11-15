# Census of the first local baseline: `lb14-session-agent-dev-v1`

Date: 2026-11-15. Question: in our own harness, where does LingBot-World v2 lose points, and is it the world model or the player?

Provenance: every number below was recomputed from the run artifact (GitHub Actions run 19 of the `experiment` workflow): the per-pass verifier output `eval/pass1/` and `eval/pass2/` (`<task>_score.json`, plus `<task>_gate.json` for GC), the per-task action logs `videos/<task>/<task>_result.json`, the four `meta.shard*.json` files and the four `gen.shard*.log` files. Gate verdicts and final values use `pwa/aggregate.py::task_value()`, the same code `pwa report` uses. The first version of this census was posted on issue #49; where this note differs from it, this note is the recount (see "Corrections"). The videos were not watched.

## The run

- LingBot-World v2 14B causal-fast, persistent session (`adapters/lingbot_world2/session.py`), turn calibration off, no runner arguments (so upstream's default seed, 42).
- Closed loop (`--action-source agent`). Player: OpenAI `gpt-4.1-mini`, the adapter's default at the time. Insight tasks are wait-only and use no player.
- Dev split, 24 tasks (6 per family), 4 shards on Modal H100s, main at `9b44b4e`.
- Judge: Gemini 3.1 Pro (`gemini-3.1-pro-preview`) at upstream settings, 2 passes on the same videos. 0 missing, 0 dropped.
- Agent API: 3 calls timed out once and succeeded on retry; 0 fallbacks to dataset actions.

This run is a diagnostic. The plan of record (issue #9) changes the player to `gpt-6-luna` for every compared run, so this row is not the starting-model number.

## Family means

| Family | Pass 1 | Pass 2 | Mean | Gate passes (of 6, mean of passes) | Paper, LingBot web demo |
|---|---|---|---|---|---|
| GC | 1.70 | 1.97 | 1.83 | 4.5 | 2.04 |
| IF | 2.00 | 1.61 | 1.81 | 5.5 | 2.13 |
| Insight | 1.50 | 1.67 | 1.58 | no gate | 1.95 |
| Out-of-sight | 1.00 | 1.67 | 1.33 | 4.0 | 1.16 |
| Overall | 1.55 | 1.73 | **1.64** (pass std 0.13) | | 1.82 |

Each family mean covers 6 tasks with scores spread from 1 to 4, so it has a task-sampling error of roughly 0.2. The paper row covers all 171 tasks and was produced through LingBot's web demo, which has a prompt-writing model and cache scheduling that the released code lacks. The two rows are not like for like.

## Per task

Chunks: video chunks generated (the harness caps a rollout at 30 player steps, about 60 s of video). Last action: `END` if the player's last step was END, `cap` if the rollout hit the step limit. Reversals: consecutive steps in opposite directions on any axis (LEFT/RIGHT, UP/DOWN, W/S, A/D). Gate: the trajectory or instruction review that decides whether the task's score counts; `partial` with `instruction_following_score` 1 counts as a pass. Final: the value that enters the family mean (1.0 on a gate fail). Evolution level and Static: `oe_dynamicity_check.evolution_quality_level_1_to_5` and `static_or_near_static`, where the judge filled them.

| Task | Family | Chunks | Last action | Reversals | Gate (p1 / p2) | Final (p1 / p2) | Evolution level (p1 / p2) | Static (p1 / p2) | Start view revisited |
|---|---|---|---|---|---|---|---|---|---|
| GC005 | GC | 29 | END | 6 | fail / fail | 1 / 1 | - / 1 | no / no | - |
| GC016 | GC | 29 | END | 0 | pass / pass | 2.2 / 2 | 3 / 3 | no / no | - |
| GC031 | GC | 30 | cap | 11 | partial / partial | 1 / 1.8 | - / - | no / no | - |
| GC033 | GC | 30 | cap | 21 | partial / partial | 2 / 4 | 3 / - | no / no | - |
| GC036 | GC | 30 | cap | 25 | partial / fail | 2 / 1 | - / - | no / no | - |
| GC038 | GC | 30 | cap | 8 | pass / partial | 2 / 2 | - / 3 | no / no | - |
| IF002 | IF | 29 | END | 0 | partial / partial | 2 / 2 | - / 1 | no / no | - |
| IF010 | IF | 29 | END | 0 | fail / partial | 1 / 1 | 2 / - | no / - | - |
| IF017 | IF | 30 | cap | 0 | pass / partial | 2 / 2 | - / - | - / - | - |
| IF031 | IF | 28 | END | 0 | partial / partial | 2 / 1 | 3 / 1 | - / no | - |
| IF034 | IF | 30 | cap | 0 | pass / pass | 3 / 2.67 | 1 / - | no / - | - |
| IF052 | IF | 29 | END | 0 | pass / pass | 2 / 1 | 1 / 1 | no / no | - |
| OE001 | Insight | 30 | cap | 0 | - | 1 / 2 | 1 / 2 | yes / yes | - |
| OE005 | Insight | 30 | cap | 0 | - | 1 / 2 | 1 / 2 | no / yes | - |
| OE018 | Insight | 30 | cap | 0 | - | 2 / 1 | 2 / 1 | no / yes | - |
| OE035 | Insight | 30 | cap | 0 | - | 1 / 1 | 1 / 1 | yes / yes | - |
| OE064 | Insight | 30 | cap | 0 | - | 2 / 2 | 3 / 2 | no / no | - |
| OE074 | Insight | 30 | cap | 0 | - | 2 / 2 | 2 / 2 | no / no | - |
| OE034 | Out-of-sight | 30 | cap | 17 | partial / partial | 1 / 1 | 1 / 1 | no / no | no / no |
| OE039 | Out-of-sight | 30 | cap | 9 | fail / fail | 1 / 1 | 1 / 2 | no / no | no / no |
| OE047 | Out-of-sight | 29 | END | 15 | pass / pass | 1 / 4 | 1 / 4 | no / no | yes / yes |
| OE048 | Out-of-sight | 30 | cap | 13 | pass / pass | 1 / 2 | 1 / 2 | no / no | yes / yes |
| OE058 | Out-of-sight | 30 | cap | 11 | fail / fail | 1 / 1 | 1 / 1 | no / no | no / no |
| OE069 | Out-of-sight | 30 | cap | 13 | partial / partial | 1 / 1 | 1 / 1 | no / no | no / no |

Action sequences for the camera tasks, as run lengths (R = RIGHT, L = LEFT, U = UP, Dn = DOWN, Wt = WAIT, E = END; W/A/S/D move):

| Task | Prompt | Actions |
|---|---|---|
| OE034 | Turn the camera right 90 degrees, then return to the starting view. | `R2 L1 R3 L1 R4 L1 R3 L1 R2 L2 R1 L1 R1 L1 R1 L2 R1 L2` |
| OE039 | Rotate the camera 360 degrees in place, then return to the original view, then step backward 2 steps. | `R4 L1 R3 L1 R1 L1 R2 L5 R1 L2 S7 L1 S1` |
| OE047 | Turn the camera right 90 degrees, then turn back to the original view, then look up 40 degrees. | `R1 L1 U2 R1 L1 R1 L1 R1 L1 R1 U1 R1 U1 R1 L1 R1 L2 R2 U1 L1 R1 L1 U1 R1 L1 R1 E1` |
| OE048 | Turn the camera right 90 degrees, then turn back to the original view. | `R1 L1 R1 L1 R5 L1 R2 L1 R1 L3 R2 L1 R1 L9` |
| OE058 | Turn the camera right 180 degrees, then turn back to the original view. | `R2 L1 R5 L1 R2 L1 R5 L1 R1 L1 R1 L9` |
| OE069 | Turn the camera left 180 degrees, then turn back to the original view. | `L4 R1 L1 R1 L1 R4 L2 R4 L1 R1 L1 R1 L1 R7` |
| GC031 | Rotate the camera 360 degrees in place at the crossroads, then return to the original angle facing the original view. | `R10 L1 R2 L1 R1 L1 R1 L1 R3 L1 R3 L5` |
| GC033 | Turn the camera left 90 degrees, then turn back to face the display window. | `L1 R1 L2 R1 L2 R1 L1 R1 L2 R1 L2 R1 L1 R2 L1 R2 L1 R1 L1 R1 L1 R3` |
| GC036 | Pan slowly from left to right, then back to center | `R1 L1` repeated 10 times, then `R1 L2 R1 L3 R2 L1` |
| IF017 | The sword-wielding man walks forward. | `R29 Wt1` |

## Findings

### 1. The player, not the world model, decides most out-of-sight and GC outcomes

- No rollout ended early in a useful sense. 23 of 24 ran all 30 steps. The player sent END on 7 of 18 agent tasks, always as its 29th or 30th step.
- The player reverses direction for whole rollouts: 9 to 17 reversals on each out-of-sight task, 25 on GC036, 21 on GC033 and 11 on GC031.
- In 4 of 6 out-of-sight rollouts (OE034, OE039, OE058, OE069) the judge recorded `starting_pose_revisited: no` in both passes. All four score 1 in both passes. Two of them fail the gate (OE039, OE058); the other two pass it as `partial` and still score 1, because with no return there is no state to compare. No content was graded on these four.
- By the rule set for this census before it ran (2 or more of 6 out-of-sight tasks with a trajectory fault), out-of-sight content work stops until control and the player are fixed. That is now the plan (issue #9).

Contributing causes, none tested in this run:

- At the default rate one LEFT or RIGHT chunk turns about 55 degrees (0.03 rad per frame over 32 frames), so 90 degrees is not a whole number of chunks. Turn calibration (#23) makes a chunk 45 degrees.
- The player sees 8 frames of the last chunk plus its own action history and is asked to decide each step independently. It is not told what one action does or where the camera is relative to the start. PR #59 adds that hint (opt-in).
- The player model is gpt-4.1-mini. Upstream's default player is Claude Haiku 4.5 (`--agent-model claude-haiku-4-5-20251001` in `run_agent.py`); that the paper used it too is stated in our review notes and not re-checked against the paper.

### 2. Where the camera did return, the judge is noisy

| Task | Gate (p1 / p2) | Final (p1 / p2) | Evolution level (p1 / p2) |
|---|---|---|---|
| OE047 | pass / pass | 1 / 4 | 1 / 4 |
| OE048 | pass / pass | 1 / 2 | 1 / 2 |

The two passes read the same video. Across all 24 tasks, the two passes differ by 0.5 or more on 10 tasks (GC031, GC033, GC036, IF031, IF052, OE001, OE005, OE018, OE047, OE048), and by up to 3 points. Out-of-sight's 1.33 comes almost entirely from these two cells in pass 2. This is why the adoption rule in the plan moves a task only at a full point on the mean of its passes.

### 3. Insight is below the paper with no player involved

All six insight rollouts are 30 WAIT chunks with the camera still. Evolution levels are 1 to 3, mostly 1 or 2. Four of the six (OE001, OE005, OE018, OE035) are flagged static or near static in at least one pass, and two of those (OE001, OE035) in both. The model's only text input here is the task prompt, "wait and observe". This is the still-camera control: LingBot does evolve some scenes, weakly. The caption prompt (#32) targets this.

### 4. IF rollouts are mostly one key held for the whole rollout

IF002 and IF052 are `W29 E1`, IF031 is `W24 Wt1 W3 E1`, and IF010 is two LEFT steps then forward. IF017 ("The sword-wielding man walks forward") is `R29 Wt1`: the player turned right for 29 chunks. Finals are 1 to 3. One IF gate failed, in one pass (IF010).

## What this changes

1. On GC and out-of-sight, the first-order problem is control: turn calibration and the player. The plan replaces the player with `gpt-6-luna` and tests the player hint (#59).
2. The caption prompt is the first lever for insight.
3. Sink and memory work for out-of-sight cannot be tested until rollouts leave and return. It is parked for the event ([out-of-sight-evolution.md](out-of-sight-evolution.md)).
4. Every rollout running to the 30-step cap is part of why runs are long ([autoresearch-loop.md](autoresearch-loop.md)).

## Corrections to the first census (issue #49) and PR #60

- "Three [insight tasks] are flagged static in at least one pass": it is four (OE001, OE005, OE018, OE035).
- "`W29 E1` on three of six" IF tasks: it is two (IF002, IF052). IF031 is `W24 Wt1 W3 E1`.
- "The player returned END on almost none": it sent END on 7 of 18 agent tasks, but only as its last or second-to-last step, so no rollout was shortened by more than one chunk.

## Limits

- One seed. The two passes measure judge noise, not seed noise.
- 6 tasks per family. The dev split has no out-of-sight task with translation, a wait while away, or no return.
- The verifier's free-text reasons are in Chinese; this note uses only the structured fields.
- Nobody watched the videos for this census.
- The upstream harness writes `"model": "SANA_WM"` into every `_result.json`. That is a label from the upstream runner; the runner was `lingbot_world2` (`meta.shard*.json`).
- The run used gpt-4.1-mini. Whether a stronger player removes the reversals is the first check of the plan of record (`lb14-luna-*` runs) and is not covered here.
