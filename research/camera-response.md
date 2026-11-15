# Camera response of the 14B: what a turn command renders, and a servo that corrects it

Date: 2026-11-14 (Pacific evening). Question: when the poses command a turn, how far does the view of LingBot-World v2 14B really rotate; why do "turn out and come back" scripts end away from the start view even with perfect driving; and can a rollout correct itself from its own video?

Provenance: every number in the first five sections comes from scripted trials run by an agent session for benceruleanlu on the 14B, in a private Modal workspace, through the live kernel (`editor_app.py`, `adapters/lingbot_world2/workspace.py`). No player and no judge were involved, and no shared GPU, key or workflow. The per-trial readouts are in `research/camera-response-data/` and `python -m adapters.lingbot_world2.camera_probe research/camera-response-data/*.jsonl` reprints the gain and error tables from them. The last section uses the official scores and published clips of 16 runs on main. Where something was not checked it says so.

## Setup

- LingBot-World v2 14B causal-fast, persistent session, `load_pipe` as the runner calls it, seed 42, full-resolution frames (832x464).
- Text prompt: the task's `image_caption`, as `--lingbot-caption-prompt` uses.
- Turn rate: the calibrated one, 22.5 degrees per 20-frame dataset token (`--lingbot-turn-cal`).
- A script is a list of pose segments replayed through `session.step` with no player: turn left or right by an angle, or wait. `camera_probe.build` pads it with waits to whole latent chunks.
- Scenes: the start images of the 11 first-person camera tasks in dev (GC005, GC031, GC033, GC036, GC038, OE034, OE039, OE047, OE048, OE058, OE069). Held-out tasks are refused by the kernel.
- Rotation is read with `measured_turn.chunk_turn` (phase correlation between consecutive frames, centre half of the image, LingBot's intrinsics), the estimator `--lingbot-measured-turn` uses. "Gain" below is rendered degrees over commanded degrees.
- The end of a script is also compared with frame 0 directly (`camera_probe.closure`): the heading offset between the two frames, and the zero-mean correlation `ncc` of their overlap after undoing that offset (near 1 for the same view, near 0 for unrelated content). This check shares no state with the per-frame sums.
- Two trials with the same scene, script and seed are identical in every pixel, and a rollout generated chunk by chunk is identical to the one-step rollout (both checked on GC033).
- One trial of 173 frames takes 63 to 68 s on an H100. All trials together used about {{GPU_HOURS}} GPU-hours.

## 1. When is the estimator measuring the camera?

It reads image motion, so a subject that moves is read as rotation. `yaw_servo.rigid_share` tests this per frame pair: a yaw shifts the top and bottom halves of the image, and the left and right halves, by the same number of pixels; a moving subject shifts only its own part. The share of pairs where the four halves agree, over the turning frames of the two open-loop 90-degree clips of each scene:

| Scenes | Rigid share | Read as |
|---|---|---|
| GC005, GC031, GC033, GC036, GC038 | 0.97 to 1.00 | camera |
| OE047, OE048, OE069 | 0.81 to 0.97 | camera |
| OE034 (zebras), OE039, OE058 | 0.42 to 0.62 in at least one clip | a moving subject: rotation numbers not trusted |

Everything below uses the eight scenes read as camera. On OE034 the estimator reported a left gain of 2.5 while the picture shows zebras walking.

## 2. The rendered turn is not the commanded one, and left renders more than right

Two mirrored scripts per scene: left 90 then right 90, and right 90 then left 90.

| Scene | Left, first turn | Left, after reversal | Right, first turn | Right, after reversal | Left over right |
|---|---|---|---|---|---|
| GC005 | 1.48 | 1.44 | 1.18 | 1.06 | 1.30 |
| GC031 | 1.72 | 1.44 | 1.36 | 1.29 | 1.19 |
| GC033 | 1.24 | 1.11 | 0.91 | 0.94 | 1.27 |
| GC036 | 1.51 | 1.34 | 1.14 | 1.17 | 1.24 |
| GC038 | 1.24 | 1.36 | 1.12 | 1.20 | 1.13 |
| OE047 | 1.55 | 1.48 | 1.22 | 1.24 | 1.23 |
| OE048 | 1.99 | 1.70 | 1.16 | 1.44 | 1.42 |
| OE069 | 0.88 | 0.89 | 0.56 | 0.85 | 1.26 |

- Left turns render more than right turns in every one of the eight scenes: the ratio of the two gains is 1.13 to 1.42, mean 1.25.
- The level differs by scene. Right-turn gain runs from 0.56 to 1.44 (mean 1.11), left from 0.88 to 1.99 (mean 1.40). No single constant makes "90 degrees" render as 90 everywhere.
- Mirror control: {{MIRROR}}

## 3. It follows the direction, not the reversal

Five scripts on GC033, rendered degrees per commanded 22.5-degree token:

| Script | First turn | Second turn |
|---|---|---|
| left 90, right 90 | L 29.1 28.1 26.8 27.3 | R 21.6 21.1 20.9 20.5 |
| right 90, left 90 | R 21.6 20.8 19.9 19.7 | L 24.2 24.8 25.3 25.2 |
| right 90, right 90 | R 21.6 20.8 19.9 20.1 | R 20.3 20.3 19.2 20.1 |
| left 90, left 90 | L 29.1 28.1 26.8 27.4 | L 25.8 26.4 26.4 27.3 |
| wait 80 frames, right 90, left 90 | R 23.7 23.1 21.2 20.4 | L 25.6 25.0 25.2 26.0 |

- A right turn renders 20 to 22 degrees per token whether it comes first, after a left turn or after another right turn. A left turn renders 24 to 29. In the mirrored script the return leg is the fast one.
- There is no dip after a reversal. Over the 16 open-loop trials on the eight scenes, the first token after reversing is 1.03 times the mean of the next three (0.86 to 1.27).
- The first turn of a rollout starts a little fast: its first token is 1.08 times its fourth on average (0.83 to 1.25; GC005 left 39 to 31). The same happens when the turn starts after an 80-frame wait.
- During that 80-frame wait the view drifted 0.35 degrees.
- So the 54 against 42 degrees per chunk read off `smk14-arms-gc-v2` GC033 (the measurement behind the backlash proposal, #114) is left against right: that script turns left first. A boost that decays over 16 frames after a reversal does not match a steady per-token difference over the whole leg.

## 4. What it does to a script that turns out and comes back

After 90 out and 90 back the view should be where it started. Open loop, on the eight scenes (16 trials), it ends 3 to 49 degrees away, mean 25.6, median 25.4. In 3 of the 14 trials that also ran under the servo pass, the end frame correlates with frame 0 at 0.6 or more.

The start view not coming back is what the official judge writes about the same tasks under perfect scripted driving. For GC033 in `orc14-gc-v1-a1` its reason says the final view did not fully align with the initial window, and for OE058 in `fx14-model-dev-v2-a2` the gate failed because the turn back to the initial view was not carried out (reasons translated; scores in the last section).

## 5. A servo that corrects the heading from the video

`--lingbot-yaw-servo` (`adapters/lingbot_world2/yaw_servo.py`, off by default) generates the rollout one latent chunk at a time. After each chunk it measures the yaw the frames show per direction, keeps a running estimate of rendered over commanded for left and for right, divides it out of the next chunk's command and adds back the heading error so far, through the pose gain `--lingbot-yaw-gain` already uses (limited to 0.5 to 2.0 per chunk). Keys and frame counts do not change, and the intended track that re-anchor, player hint and return stop read is untouched. A run whose image motion is not rigid, or whose correlation peak is weak, is not trusted: its turn is taken as intended and nothing is learned from it, so on a scene with a moving subject the servo leaves the rollout as it would be without the flag.

{{SERVO_RESULTS}}

## 6. Does "the start view is back" predict the official score?

Checked on what main already has: 86 officially scored clips of the nine return-to-start dev tasks (GC031, GC033, GC036, OE034, OE039, OE047, OE048, OE058, OE069) from 16 open-loop 14B runs (`fx14-model-dev-v2`, `orc14-gc-v1`, `mem14-fx-v1`, `sks14-fx-v1`, `sp14-gc-v1`, all arms), 480p release copies. For each clip the best `ncc` between frame 0 and the last 16 frames was computed (`research/camera-response-data/judged-clips.json`).

- The start view is back at the end (`ncc` at least 0.5) in 10 of the 86 clips.
- None of the 19 gate-failed clips is among those 10. With a gate-fail rate of 22%, about two would be expected by chance, so this is suggestive only.
- GC: mean official score 3.35 when the view is back (5 clips) against 2.40 when it is not (30 clips).
- Out-of-sight: 1.95 (5 clips) against 1.77 (46 clips).
- As a rank predictor it is weak: Spearman between `ncc` and the official mean is +0.03 over all 86 clips, +0.29 on the 35 GC clips and -0.07 on the 51 out-of-sight clips. Within OE047, OE048 and OE058 it is negative. That fits the out-of-sight rubric, which wants the hidden state to have moved on: a returned view identical to frame 0 reads as frozen.

So `ncc` with frame 0 is a check on geometry, not a stand-in for the judge. This note shows that the servo returns the camera to the start heading. Whether that raises a score is not shown here and needs the decision tier.

## What this means for other flags

- `--lingbot-yaw-gain` (#119): the left over right ratio is stable enough (1.13 to 1.42) that a fixed pair can close out-and-back turns approximately; the level is not, so absolute angles stay scene-dependent. Tried on the five GC scenes (10 trials, `fixed-gain-and-mirror.jsonl`): the pair left 0.8 / right 1.0 takes the mean end error from 22.7 to 6.4 degrees (largest 15.2), ends further away than no gain in 2 of the 10 trials, and brings the end view back (`ncc` at least 0.6) in 6 of 10. It needs no new code.
- Backlash compensation (#114): the measurements above do not support a reversal transient on these scenes.
- Re-anchor and pose-indexed memory (#123) act when the commanded pose is back at a stored pose. With gains of 0.56 to 1.99 the rendered view is somewhere else at that moment, by tens of degrees after a 90-degree leg. They depend on the heading being right first.

## Limits

- One seed, one turn rate, one prompt mode (caption), 90-degree legs for the tables; {{LONGER}}
- Fixed scripts with no player. Closed-loop behaviour, where the player reacts to what it sees, was not run.
- No official score. Nothing here is a claim about the benchmark.
- Degrees assume LingBot's intrinsics for the rendered image. A different rendered field of view would rescale every angle, but not the left against right comparison or a closure error of zero.
- The estimator and the rigid test are image-motion measures. Three of the six out-of-sight dev scenes have moving subjects and are excluded; on those the servo stands down by design, so it does not help there.
- `ncc` compares pixels. A returned view with a person who has walked on, as the out-of-sight tasks want, scores lower than a frozen copy.
- The first chunk of a turn is generated before any measurement exists, so the servo starts each rollout a few degrees off and recovers over the next chunks.

## Suggested decision-tier test

Fixed actions as in `fx14-model-dev-v2`, 14B, official judge, the six GC dev tasks and OE047, OE048, OE069, two seeds: control `--lingbot-caption-prompt --lingbot-turn-cal`, arm the same plus `--lingbot-yaw-servo`; read with `pwa cells`. Before scoring, grep `yaw_servo_chunks` and `yaw_servo_untrusted` in the flags lines and the `[lingbot] yaw servo:` lines, which give the heading against the intended one after every call. A second pair with `--lingbot-reanchor` in both arms would test whether re-anchoring needs the heading to be right.
