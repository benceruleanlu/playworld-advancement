---
theme: default
title: PlayWorld advancement
info: |
  What was built and measured when running LingBot-World v2 on the PlayWorld benchmark at inference time, and why there is no leaderboard number.
  Source: https://github.com/benceruleanlu/playworld-advancement
colorSchema: auto
routerMode: hash
aspectRatio: 16/9
canvasWidth: 980
transition: none
download: false
drawings:
  enabled: false
---

# LingBot-World v2 on PlayWorld: what we built and what we measured

We changed how an open world model runs at inference time and built a harness to score it. No full-benchmark run was launched, so there is no leaderboard number, and on our six-task comparisons the judge's own noise (about 0.5) is as large as most flag effects.

<div class="mt-10 text-sm">

Hackathon entry, November 2026<br>
Repo: github.com/benceruleanlu/playworld-advancement<br>
Site: benceruleanlu.github.io/playworld-advancement

</div>

<!--
One sentence version: we have a working harness, about a hundred logged runs and more than 30 inference-time flags, but no full-benchmark score: no 171-task run was launched before judge credits and GPU access ran out, and on six-task comparisons the judge disagrees with itself by about as much as most flags moved scores.

The slides follow that order: our setup (slides 2 and 3) and our approach (slide 4), then the benchmark's published scores for context, our best official score, the judge noise, what the model remembers and what our flags changed, what stopped a full run, and where to look at the clips.

Every number in this deck comes from AGENTS.md, README.md, results/experiments.csv or results/reports/ on main. Each slide's notes name the section.
-->

---

# We ran LingBot-World v2, mostly the 14B, on PlayWorld tasks through our own harness on Modal GPUs

<div class="flow mt-5 text-xs">
  <div class="box"><b>Task</b><br>start image, goal, action list</div>
  <div class="arr">→</div>
  <div class="box"><b>Runner</b><br>LingBot v2 14B<br>session + flags</div>
  <div class="arr">→</div>
  <div class="box"><b>Clip</b><br>up to 30 chunks<br>about 60 s</div>
  <div class="arr">→</div>
  <div class="box"><b>Judge</b><br>scores 1 to 5<br>failed gate: 1.0</div>
  <div class="arr">→</div>
  <div class="box"><b>Report</b><br><code>pwa report</code><br>experiments.csv</div>
  <div class="arr">→</div>
  <div class="box"><b>Site</b><br>scores and clips</div>
</div>

<div class="text-sm mt-5">

- Model: LingBot-World v2 (Robbyant Team), 14B for most runs and 1.3B for early A/B tests. Weights unchanged; our session code re&#8209;implements its sampling loop.
- Benchmark: PlayWorld (Ding et al.), 171 tasks: GC 48, IF 50, insight 30, out-of-sight 43. Splits: dev and dev2 (24 each), heldout 123 (unscored).
- Compute: one H100 per shard on Modal, launched from GitHub Actions.

</div>

<style>
.flow { display: flex; align-items: stretch; gap: 0.3rem; }
.flow .box { flex: 1; border: 1px solid currentColor; border-radius: 4px; padding: 0.35rem 0.4rem; line-height: 1.3; text-align: center; }
.flow .box code { font-size: 0.65rem; }
.flow .arr { display: flex; align-items: center; opacity: 0.7; }
</style>

<!--
The boxes are the path one task takes. The runner is adapters/lingbot_world2/run.py (or adapters/lingbot_world2_1p3b for the 1.3B), which reuses the upstream PlayWorld harness and swaps in our engine (AGENTS.md "Layout" and "Adapters"). pwa gen, pwa score and pwa report are the CLI steps (AGENTS.md "CLI"); the site reads results/experiments.csv from main (AGENTS.md "Results site"). The experiment and arms workflows launch the Modal shards.

Model size: 9 of the 101 logged runs used lingbot_world2_1p3b, including 4 scored rows (rs13-arms-v1, gch13-arms-v1); the rest used the 14B (results/experiments.csv). The plan of record cut the 1.3B for decisions.

The model weights are not changed. Our use is not "unmodified": adapters/lingbot_world2/session.py re-implements LingBot's sampling loop as a persistent session that keeps the attention cache between the player's steps (AGENTS.md "Scenes and attribution").

Family counts: AGENTS.md "Run speed", the sharding bullet (gc 48, if 50, insight 30, outsight 43; 171 in all). Splits: AGENTS.md "Layout" (dev 24, dev2 24 with 6 per family, heldout 123). The 30-chunk cap and the 60 s figure: "Run speed", Verified (mean 29.7 chunks, about 60 s of video). A task with a gate (for example, return to the start view) scores 1.0 if the gate fails: "Workstreams" in the first AGENTS.md (commit 2d8b8c4) and the PlayWorld harness.

Timings: AGENTS.md "Run speed", measured on lb14-session-agent-dev-v1: model load 267 to 357 s once per family per shard, agent rollouts 522 to 610 s with the first chunk (insight rollouts 367 to 443 s), 142 min wall clock or about 18 min per task on an 8-task shard, including GPU queueing. A later flag (--lingbot-fast-dit, #79) cuts the 14B load to about 31 s.
-->

---

# Most comparisons used fixed actions with no AI player; 35 of 101 logged runs were closed loop

<div class="grid grid-cols-2 gap-8 mt-4 text-sm">
<div>

**Actions (101 logged runs)**

- Dataset actions: open loop, A/B tests only. 62 runs.
- Scripted player (#102): replays a fixed plan, also open loop. 4 runs.
- AI player, closed loop: picks each chunk's action from the frames so far. 35 runs.

</div>
<div>

**Judge**

- Gemini 3.1 Pro, the official judge, at upstream settings, 2 or 4 passes. 42 runs scored.
- 34 runs were generated but never Gemini-scored. Later ones have proxy scores from Luna, which are not comparable to the paper (slide 13).

</div>
</div>

<!--
Sources: AGENTS.md "Rules" (dataset mode for A/B only, the Luna default, verifier settings unchanged: frame rate, resolution, JPEG), "Status against the timeline" ("Dataset actions and a scripted player are open loop"; the bullet that starts "Since about 18:35": both arms of a pair see the same actions), and "Settled" (player gpt-6-luna for compared runs, gpt-4.1-mini baseline is a diagnostic).

Run counts: results/experiments.csv on main has 105 rows; 4 are fake_runner pipeline tests. Of the other 101, action_source is dataset on 62 and agent on 39. Four of the 39 are the sp14-gc-v1 arms, whose notes say "scripted player: dataset moves, no AI player", so 35 had an AI player. Status: 42 scored, 34 generated, 15 cancelled, 7 failed, 3 predate the status column.

Players: gpt-4.1-mini on the dev baseline (slide 6), gpt-6-luna in later closed-loop arms. The only Luna closed-loop arms with a Gemini score are on the 1.3B or capped at 10 chunks (rs13, gch13, smk14-arms-gc-v2); in gch13, 22 of 110 player decisions fell back. The full-length 14B closed-loop runs (clstk14-dev-v1, stksv14-cl-gc-v1) were generated only.

Pass counts: the dev baseline was scored at 2 passes, the arm groups at 4 (AGENTS.md "Status against the timeline").

Luna (openai:gpt-6-luna) as a judge is a proxy only. Its noise and its agreement with Gemini are on slide 7; when the Gemini credits ran out is on slide 13.
-->

---

# Each change is an opt-in flag on the model or the AI player, with no retraining

<div class="grid grid-cols-[1.1fr_1fr] gap-6 mt-4 text-sm">
<div>

**Flags, grouped by the first plan's workstreams**

- Insight: caption prompt, insight director, conditioning schedule.
- Control and gates: turn calibration, yaw gain, yaw servo, re-anchor, IF slow translation, IF fixed camera.
- Player prompts: return stop, player hint.
- Out-of-sight memory: sink size, attention window, sink key scale, pose memory.

More than 30 flags on main, all off by default.

</div>
<div>

**What would count**

- A delta of at least twice the pass-to-pass spread.
- Decision tier: closed loop, 14B, full length, all 6 dev tasks of a family, 2 seeds, official judge.
- Adoption: a task moves a full point, the gain repeats on both seeds, no gate is lost.
- No run reached the decision tier, so no flag is adopted.

</div>
</div>

<!--
The four groups follow the workstreams of the first plan (AGENTS.md as scaffolded, commit 2d8b8c4); the plan of record in #66 replaced that section and later cut out-of-sight memory and sink work for the event ("Cut for this event"), but fixed-action runs on the sink and window went ahead anyway. The flags under each are documented in AGENTS.md "Adapters". Return stop and player hint change what the AI player is told, not the model (README.md), and were scored only on the 1.3B. The eval infrastructure (pwa CLI, experiment and arms workflows, per-run reports, results site, blind review page) is on slides 2 and 14.

Flag count: AGENTS.md "Status against the timeline" recorded 28 method flags at 22:25, and #115, #116, #121, #132, #133, #139, #144 and #147 added more since; those eight are merged and unscored. None has decision-tier evidence.

Rules: AGENTS.md "Rules" and "Testing tiers and the adoption rule". Also in "Rules": a new experiment name for every run (pwa gen refuses an existing run directory because upstream --skip-done silently reuses old videos), heldout unscored until code freeze, and final numbers closed loop with Gemini 3.1 Pro over 2 or more passes.

Practice, not a written rule: since about 18:35 model-side flags were compared with the same actions in both arms (dataset or scripted player) at the same seed. Generation is deterministic, so any difference between such arms is the flag or the judge. AGENTS.md calls these runs a change from the plan as written: they are open loop and cannot meet the decision tier. Some servo groups borrow controls from other groups (sks14, mem14, win14).

The rest of the deck reads results against these rules. Slide 7 shows why the judge spread sets the bar.
-->

---

# In the PlayWorld paper Genie 3 scores 2.12 overall, and LingBot-World v2's web demo scores 1.82

<div class="grid grid-cols-[1fr_1.1fr] gap-8 mt-4">
<div class="text-sm">

- These are the benchmark's published scores on all 171 tasks, for context. None of our runs is on that footing.
- LingBot's web demo already leads Genie 3 on insight, 1.95 against 1.51.
- Its largest gap is out-of-sight, 1.16 against 1.81.
- Ding et al., arXiv:2608.13552.

</div>
<div>

| Model (paper, full benchmark) | GC | IF | Insight | Out-of-sight | Overall |
|---|---|---|---|---|---|
| Genie 3 | 2.74 | 2.40 | 1.51 | 1.81 | **2.12** |
| LingBot-World v2 (web demo) | 2.04 | 2.13 | 1.95 | 1.16 | 1.82 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game 3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |

</div>
</div>

<!--
The reference scores are the PlayWorld paper's numbers, copied in AGENTS.md "Reference scores".

LingBot-World v2 is the open model we used, but the paper scored it through its web demo, not through the released code we run.

The red-team review in research/red-team-and-plan.md estimated that out-of-sight alone cannot reach 2.12 (every out-of-sight task at 2.0 gives about 2.03 overall), so two or three families would have to move.
-->

---

# Our best official closed-loop dev score is 1.64 ± 0.13 on 24 tasks, with no method

<div class="grid grid-cols-2 gap-8 mt-4 text-sm">
<div>

| Run | `lb14-session-agent-dev-v1` |
|---|---|
| Model | LingBot-World v2 14B, persistent session, no flags |
| Loop | closed, AI player `gpt-4.1-mini` |
| Tasks | 24 dev (6 per family), 0 missing |
| Judge | Gemini 3.1 Pro, 2 passes |
| GC / IF / insight / out-of-sight | 1.83 / 1.81 / 1.58 / 1.33 |
| Overall | **1.64 ± 0.13** |

</div>
<div>

- Not comparable to the paper: no run covers all 171 tasks, for the base model or any method.
- 24 tasks against 171: the task-sampling error is roughly 0.2 per family.
- The paper's LingBot row (1.82) is all 171 tasks through its web demo.
- No flag is adopted. The 123 heldout tasks are unscored.

</div>
</div>

<!--
Source: results/experiments.csv row lb14-session-agent-dev-v1 (overall 1.6390, std 0.1258, 2 passes, 24 tasks, 0 missing) and the "Ours" row in AGENTS.md "Reference scores". Other Gemini-scored rows exist (the arm groups on slide 12), but they are fixed-action or six-task subsets, so this is the best closed-loop dev number.

This is the base model with every flag off. It is not the starting-model number for the plan, because the plan fixed the player as gpt-6-luna and this run used gpt-4.1-mini.

Heldout is reserved until code freeze by the repo rules, and code freeze never produced a full run.
-->

---

# The judge gives the same video scores up to 1.3 apart, so six-task comparisons cannot resolve differences under about 0.5

<div class="grid grid-cols-2 gap-8 mt-4 text-sm">
<div>

**Gemini 3.1 Pro (official judge)**

- GC036, byte-identical clips: 2.65 when it passed the gate, 1.35 when it failed it.
- A six-task family mean moves about 0.5 on the same videos.
- Single passes differ by up to 2 to 3 points.

</div>
<div>

**Luna (`openai:gpt-6-luna`, proxy judge)**

- Byte-identical clips: 0.50 per task on average, 0.62 on a five-task mean.
- Lets 97% of gate checks pass; Gemini failed a gate on 23% of tasks.
- Rank correlation with Gemini: 0.62 on 21 clips (0.41 on out-of-sight).

</div>
</div>

<div class="mt-6 text-sm">

Generation is deterministic: the same settings and seed give a byte-identical video, so these spreads are the judge, not the model.

</div>

<!--
This is the central finding. Sources: AGENTS.md "Status against the timeline", the "Same config scored three times" bullet and the Luna bullet.

GC036 comes from pm14-fx-v1 arms 1 and 2, which were checked byte-identical. Luna's identical-clip numbers come from walking-only GC tasks, where the servo arm and the control are the same file.

We used Luna after the Gemini credits ran out at about 03:40 UTC on Nov 15. Luna's scores are not reported numbers and are not comparable to the leaderboard.

The practical bar: about 0.5 for a six-task family mean under Gemini, about 0.6 under Luna. Any flag effect smaller than that cannot be seen in our dev comparisons.
-->

---

# The LingBot attention cache is configured to keep the opening view permanently and about 2 seconds of recent video

<div class="mt-8">
<div class="flex gap-1 text-xs text-center items-stretch" style="height: 4.2rem">
  <div class="cache sink" style="flex: 6">6 sink latents<br>opening view, kept forever</div>
  <div class="cache gone" style="flex: 5">evicted<br>older views</div>
  <div class="cache recent" style="flex: 8">8 recent latents<br>about 2 s</div>
  <div class="cache gen" style="flex: 4">4 being<br>generated</div>
</div>
<div class="text-xs mt-1 opacity-80">One chunk's view of the 18-latent cache (local attention 18, sink 6). Widths are latent counts; the evicted block is not to scale.</div>
</div>

<div class="text-sm mt-6">

- A return to the start view can use the sink. Any other view seen more than about 2 s earlier is gone.
- This is the loader configuration (`adapters/lingbot_world2/loader.py`), not a measurement. The GPU memory probe that would measure it is unmerged (#37).

</div>

<style>
.cache { display: flex; flex-direction: column; justify-content: center; border: 1px solid currentColor; border-radius: 3px; padding: 0.2rem; line-height: 1.25; }
.cache.sink { background: rgba(47, 111, 214, 0.28); }
.cache.recent { background: rgba(47, 111, 214, 0.14); }
.cache.gone { border-style: dashed; opacity: 0.6; }
.cache.gen { background: rgba(139, 139, 139, 0.2); }
</style>

<!--
Out-of-sight tasks ask the model to show the scene correctly after the camera leaves it and comes back. With this cache, anything seen more than about two seconds ago, other than the opening view, has to be regenerated from nothing.

Source: AGENTS.md "Adapters", the KV window bullet: local_attn_size 18, sink_size 6; a chunk sees the sink plus the last 8 latents, about 32 frames.

AGENTS.md is explicit that this reach is the configuration, not a measurement. The cache_model script counts how often dataset actions revisit an evicted view, on CPU.

Two flags change this window: keep-first 10 and attention window 22. They are part of the stack on slide 11.
-->

---

# A yaw servo cut the end-heading error on 6 GC tasks; no judge has shown a score change

<div class="grid grid-cols-[1.2fr_1fr] gap-8 mt-3">
<div>
<HeadingChart />
</div>
<div class="text-sm">

- Rendered turns differ from commanded turns. Rendered over commanded, 8 static first-person scenes, one seed: 0.88 to 1.99 left, 0.56 to 1.44 right (PR #125).
- The servo measures the rendered rotation each chunk and corrects the next command (design, code and GPU trials by benceruleanlu in PR #125, merged in #131).
- Heading is read with the servo's own estimator; independent frame check on GC033 and GC036 only. GC022 is from the stack run.
- End-of-clip similarity to the first frame: GC033 -0.09 to 0.52, GC036 0.07 to 0.63.
- No Gemini score exists for a servo clip. Under Luna the deltas are noise.

</div>
</div>

<!--
Heading is measured by phase correlation, the same estimator the servo steers with. The similarity of the last frame to frame 0 is the independent check, available for GC033 and GC036. GC022 is from the stack run.

Sources: AGENTS.md "Status against the timeline", the yaw servo bullet, and the camera-response study bullet for the left and right ratios.

GC038 improved least, 96 to 49 degrees. Walking-only GC tasks give byte-identical clips with and without the servo, which is where Luna's identical-clip noise numbers on the judge slide (slide 7) came from.

The servo does not support out-of-sight tasks yet.
-->

---

# On GC033 the servo clip ends 0.3 degrees from the intended heading; the control ends 28 degrees off

<ClipPair task="GC033" control="svgc14-fx-v1-a1" treatment="svgc14-fx-v1-a2" treatmentLabel="Yaw servo">
GC033, fixed dataset actions, LingBot-World v2 14B. Control: no servo (<code>svgc14-fx-v1-a1</code>). Treatment: yaw servo (<code>svgc14-fx-v1-a2</code>). End-heading error 28 to 0.3 degrees. The same pair exists for GC036. Clips generated with LingBot-World v2 (Robbyant Team), released under CC BY-NC-SA 4.0, non-commercial.
</ClipPair>

<!--
Play both and compare the last second with the first frame. The servo clip's end-of-clip similarity to frame 0 is 0.52, the control's is -0.09.

Source: AGENTS.md "Status against the timeline", the yaw servo bullet (end-heading error 28 to 0.3 degrees, end similarity -0.09 to 0.52); the run names are in results/media/svgc14-fx-v1-a1.json and -a2.json.

These are open-loop clips: both arms replay the dataset's actions, so the only difference is the servo.

The same comparison for GC036 is svgc14-fx-v1-a1 against a2, task GC036. The site's Pairs section loads either pair.
-->

---

# A stack of six flags scored about a point higher on out-of-sight in three six-task pairs, under the proxy judge only

<div class="grid grid-cols-[1fr_1.25fr] gap-6 mt-2">
<div class="text-sm">

- Stack: turn calibration, caption prompt, insight director, IF slow translation, sink 10 (keep the first 10 latents, up from 6), window 22 (up from 18).
- Against no flags, fixed actions, six out-of-sight tasks per pair, Luna: +1.02, +0.92, +0.98.
- Out-of-sight is the only family above Luna's 0.6 bar in all three pairs.
- Luna agrees weakly with Gemini on out-of-sight (0.41), so this may not hold under Gemini.

</div>
<div>
<ClipPair task="OE039" control="stk14-fx-dev-v1-a1" treatment="stk14-fx-dev-v1-a2" controlLabel="No flags" treatmentLabel="Stack">
OE039, fixed dataset actions, LingBot-World v2 14B. Control: no flags (<code>stk14-fx-dev-v1-a1</code>). Treatment: the stack (<code>stk14-fx-dev-v1-a2</code>). CC BY-NC-SA 4.0, generated with LingBot-World v2.
</ClipPair>
</div>
</div>

<!--
This is a lead from small samples, not a result. The three pairs are stk14-fx-dev-v1 at seeds 0 and 1 (4 passes) and stk14-fx-dev2-v1 (2 passes). Source: AGENTS.md, the stack bullet under "Proxy judge findings".

Other families were mixed across the three pairs: GC +0.59, -0.16, +0.30; IF +0.40, -0.25, +0.45.

None of the six parts passed the adoption rule alone, so a gain would not say which part caused it.

The 0.6 bar is the one from the judge-noise slide (slide 7).
-->

---

# No single flag beat the judge noise: on six tasks or fewer, the moves we saw were inside it or downward

<div class="text-sm mt-4">

Lowered scores (Gemini 3.1 Pro, one seed, six tasks or fewer):

- Sink key scale, out-of-sight: control 2.10; scaled arms 1.65, 1.33 and 1.25 (`sks14-fx-v1`).
- Conditioning schedule, insight: 3.00 to 1.50 on two tasks (`dec14-ins-v1`).

Inside the noise:

- Turn calibration: the same comparison run twice on GC031 gave +1.95 and +0.35.
- Caption prompt: 2 tasks up and 2 down by a full point in one run.
- Sink 10 with window 22: raised OE039 1.00 to 3.44 at seed 1, but 1.75 at seed 0, inside the controls (`win14-fx-v1`).

Pose memory: retrieves as planned after #129, no geometric gain, +0.20 under Luna against a bar of 0.34. Dropped.

</div>

<!--
Sources: AGENTS.md "Status against the timeline": the sks14-fx-v1 and dec14-ins-v1 bullets, the win14-fx-v1 bullet, the "What the fixed-action results say so far" bullet, and the pose memory bullet. Generation is deterministic, so the +1.95 against +0.35 spread is a config difference or judge spread, not rollout noise.

Sink key scale 0.7 lowered out-of-sight by 0.45, which is inside the six-task noise from the judge slide (slide 7); scale 0.4 and 0.7 from chunk 4 are below it. The conditioning schedule halved insight on the two tasks it ran, OE001 and OE018.

These are drops on small samples, the same caution as the stack lead in the other direction.
-->

---

# No full-benchmark run was launched before judge credits and GPU access ran out

<div class="grid grid-cols-2 gap-8 mt-4 text-sm">
<div>

**What ran out**

- About 03:40 UTC Nov 15: Gemini AI Studio prepaid credits ran out. Later runs have Luna scores only.
- 09:01 UTC Nov 15: the GPU provider workspace was disabled during `clstk14-dev-v1`, a 24-task dev run and the only closed-loop test of stack plus servo. Base 23 of 24 tasks, stack plus servo 8 of 24.

</div>
<div>

**What a trusted score needs (estimate)**

- Base and method each on all 171 tasks, closed loop, Gemini 3.1 Pro, 2 or more passes.
- Scaling the 0.5 six-task spread by the square root of 6/171 gives noise of about 0.1 on the overall mean.
- Generation estimate for one 171-task arm on 8 GPUs: about 3.8 h without queueing, about 6.9 h at the queued rate measured on the dev baseline.

</div>
</div>

<!--
Sources: AGENTS.md "Status against the timeline" (credits, the clstk14-dev-v1 bullet, the noise estimate) and "Run speed" for the 171-task budget at 8 shards (3.8 h from component timings, 6.9 h at the dev baseline's queued 18 minutes per task; the job cap is 350 minutes).

The 0.1 figure is an estimate, not a measurement. Scoring through Google Cloud is wired (#148) but no live call has been made.

AGENTS.md says the starting-model 171 run was never launched. No closed-loop comparison of stack plus servo exists, so there is no candidate number to report either.
-->

---

# Every clip is published, so you can compare control and treatment yourself

<div class="text-sm mt-4">

- Results site: benceruleanlu.github.io/playworld-advancement. Every run, its scores, and a Pairs section that plays control and treatment side by side.
- Clips: `github.com/benceruleanlu/playworld-advancement/releases/download/run-<EXP>/<TASK>.mp4`, 480p, with a `.jpg` poster.
- Blind review page: benceruleanlu.github.io/playworld-advancement/review/. It hides which clip is control and which is treatment until you finish; it records a preference by eye, not a score.
- Pairs in this deck: GC033 and GC036 in `svgc14-fx-v1` a1 against a2; OE039 in `stk14-fx-dev-v1` a1 against a2.
- Per-task scores with the judge's reasons: `results/reports/<EXP>.md`. Full status and caveats: `AGENTS.md`.

</div>

<!--
The site's Pairs section (#166) opens a pair from the URL (?cmp=KEY&pair=TASK#pairs); old links such as ?compare=GC033&b=svgc14-fx-v1-a1&c=svgc14-fx-v1-a2#compare-clips open the same pair.

Given the judge noise on slide 7, looking at the clips is a fair check on any claim here. The review page (#164, site/src/pages/review.astro) shuffles sides per reviewer and reveals arms and a sign test only after "Finish and reveal". Clips load from release URLs that name the run, so blinding holds only if reviewers do not open developer tools.
-->

---

# Credits and licences

<div class="text-xs mt-4">

- **PlayWorld** benchmark, harness, verifier and task data: Ding et al., arXiv:2608.13552. Code kxding/PlayWorld (no licence; used as a pinned submodule, not copied). Data jocelynd/playworld-bench. Task images come from Pexels and web image search and keep their sources' terms.
- **LingBot-World v2**: Robbyant Team, arXiv:2607.07534, CC BY-NC-SA 4.0. Weights and modules run unchanged; `adapters/lingbot_world2/session.py` re-implements its sampling loop.
- Reference scores for Genie 3 (Google DeepMind), SANA-WM (NVIDIA), Matrix-Game 3.0 (Skywork AI) and LingBot-World v2 are as reported in the PlayWorld paper.
- Scoring: Gemini 3.1 Pro (Google). Proxy judge and AI player: OpenAI `gpt-6-luna`; the dev baseline player was `gpt-4.1-mini`.
- Scene videos in this deck were generated with LingBot-World v2 and are released under CC BY-NC-SA 4.0, non-commercial. Removal requests: open an issue titled "Scene removal request".
- Deck built with Slidev. Source: `slides/` in the repo.

</div>

<!--
Wording follows README.md "Credits" and the attribution facts in AGENTS.md "Scenes and attribution".
-->
