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

We changed how an open world model runs at inference time and built a harness to score it. No full-benchmark run finished, so there is no leaderboard number, and on our six-task comparisons the judge's own noise (about 0.5) is as large as most flag effects.

<div class="mt-10 text-sm opacity-80">

Hackathon entry, November 2026<br>
Repo: github.com/benceruleanlu/playworld-advancement<br>
Site: benceruleanlu.github.io/playworld-advancement

</div>

<!--
One sentence version: we have a working harness, about a hundred logged runs and many inference-time flags, but no full-benchmark score. The full run was stopped by lost judge credits and GPU access, and on six-task comparisons the judge disagrees with itself by about as much as most flags moved scores.

The slides follow that order: benchmark, what we built, the one official score, the judge noise, then what the model does and what our flags changed, then what stopped the full run.

Every number in this deck comes from AGENTS.md ("Status against the timeline" and "Reference scores"), results/experiments.csv or results/reports/ on main.
-->

---

# PlayWorld scores world models on 171 tasks in four families, and Genie 3 leads at 2.12

<div class="grid grid-cols-[1fr_1.1fr] gap-8 mt-4">
<div class="text-sm">

- Families: goal-conditioned camera control (GC), interactive first and third person (IF), insight, out-of-sight.
- An AI player drives the model in a closed loop; Gemini 3.1 Pro scores each rollout from 1 to 5.
- Some tasks have a gate (for example, the camera must return to the start view). A failed gate scores 1.0.
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

LingBot-World v2 is the open model we used. Its web demo already beats Genie 3 on insight, 1.95 against 1.51. Its biggest gap is out-of-sight, 1.16 against 1.81.

The red-team review in research/red-team-and-plan.md estimated that out-of-sight alone cannot reach 2.12, so two or three families would have to move.
-->

---

# We built a scoring harness and 28 opt-in inference-time flags for LingBot-World v2, without retraining

<div class="text-sm mt-4">

- `pwa` CLI: generate, score, report and compare runs; refuses to reuse an existing run name.
- GitHub Actions workflows that generate on Modal H100s in shards, score with the judge and log one row per run.
- 101 runs in `results/experiments.csv` (4 pipeline tests excluded), 44 of them scored. Failed and cancelled runs stay in the log.
- A persistent session that keeps LingBot's attention cache across agent steps (`adapters/lingbot_world2/session.py`).
- 28 method flags on main, all off by default: turn calibration, caption prompt, insight director, attention window sizes, yaw servo, pose memory and others.
- A results site, and every scored run's clips published as a GitHub Release.

</div>

<!--
The model weights and modules run unchanged. The session file re-implements LingBot's sampling loop so that state survives between the player's steps, so our use is not "unmodified".

The run count is the rows of results/experiments.csv minus the four fake_runner pipeline tests. Of 101, 44 have status scored, 34 generated, 15 cancelled, 7 failed and 5 predate the status column.

The flag count, 28, is from AGENTS.md "Status against the timeline". None of them has decision-tier evidence, which the next slides explain.
-->

---

# Our only official score is 1.64 ± 0.13 on 24 dev tasks, with no method, and it is not comparable to the paper

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

- No run covers all 171 tasks, for the base model or any method.
- 24 tasks against 171: the task-sampling error is roughly 0.2 per family.
- The paper's LingBot row (1.82) is all 171 tasks through its web demo. Our run used the `gpt-4.1-mini` player.
- No flag is adopted. The 123 heldout tasks are unscored.

</div>
</div>

<!--
Source: results/experiments.csv row lb14-session-agent-dev-v1 (overall 1.6390, std 0.1258, 2 passes, 24 tasks, 0 missing) and the "Ours" row in AGENTS.md "Reference scores".

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

Two flags change this window: keep-first 10 and attention window 22. They appear in the stack two slides on.
-->

---

# A yaw servo cut the end-heading error on 6 GC tasks; no judge has shown a score change

<div class="grid grid-cols-[1.2fr_1fr] gap-8 mt-3">
<div>
<HeadingChart />
</div>
<div class="text-sm">

- Rendered turns differ from commanded turns. Rendered over commanded, 8 static first-person scenes, one seed: 0.88 to 1.99 left, 0.56 to 1.44 right (PR #125).
- The servo measures the rendered rotation each chunk and corrects the next command (design from PR #125, merged in #131).
- End-of-clip similarity to the first frame: GC033 -0.09 to 0.52, GC036 0.07 to 0.63.
- No Gemini score exists for a servo clip. Under Luna the deltas are noise.

</div>
</div>

<!--
Heading is measured by phase correlation, the same estimator the servo steers with. The similarity of the last frame to frame 0 is the independent check, available for GC033 and GC036. GC022 is from the stack run.

Sources: AGENTS.md "Status against the timeline", the yaw servo bullet, and the camera-response study bullet for the left and right ratios.

GC038 improved least, 96 to 49 degrees. Walking-only GC tasks give byte-identical clips with and without the servo, which is where Luna's identical-clip noise numbers on the previous judge slide came from.

The servo does not support out-of-sight tasks yet.
-->

---

# On GC033 the servo clip ends 0.3 degrees from the intended heading; the control ends 28 degrees off

<ClipPair task="GC033" control="svgc14-fx-v1-a1" treatment="svgc14-fx-v1-a2" treatmentLabel="Yaw servo">
GC033, fixed dataset actions, LingBot-World v2 14B. Control: no servo (<code>svgc14-fx-v1-a1</code>). Treatment: yaw servo (<code>svgc14-fx-v1-a2</code>). End-heading error 28 to 0.3 degrees. The same pair exists for GC036. Clips generated with LingBot-World v2 (Robbyant Team), released under CC BY-NC-SA 4.0, non-commercial.
</ClipPair>

<!--
Play both and compare the last second with the first frame. The servo clip's end-of-clip similarity to frame 0 is 0.52, the control's is -0.09.

These are open-loop clips: both arms replay the dataset's actions, so the only difference is the servo.

The same comparison for GC036 is svgc14-fx-v1-a1 against a2, task GC036. The site's compare view loads either pair.
-->

---

# A stack of six flags scored about a point higher on out-of-sight in three six-task pairs, under the proxy judge only

<div class="grid grid-cols-[1fr_1.25fr] gap-6 mt-2">
<div class="text-sm">

- Stack: turn calibration, caption prompt, insight director, IF slow translation, keep-first 10, attention window 22.
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

The 0.6 bar is the one from the judge-noise slide.
-->

---

# Two flags lowered scores under Gemini, three did not repeat on a second seed, and pose memory showed no gain

<div class="text-sm mt-4">

Lowered scores (Gemini 3.1 Pro, one seed, six tasks or fewer):

- Sink key scale, out-of-sight: control 2.10; scaled arms 1.65, 1.33 and 1.25 (`sks14-fx-v1`).
- Conditioning schedule, insight: 3.00 to 1.50 on two tasks (`dec14-ins-v1`).

Did not repeat on a second seed: turn calibration, caption prompt, larger attention window alone.

Pose memory: retrieves as planned after #129, no geometric gain, +0.20 under Luna against a bar of 0.34. Dropped.

</div>

<!--
Sources: AGENTS.md "Status against the timeline": the sks14-fx-v1 and dec14-ins-v1 bullets, the "What the fixed-action results say so far" bullet, and the pose memory bullet.

Sink key scale 0.7 lowered out-of-sight by 0.45, which is inside the six-task noise from the judge slide; scale 0.4 and 0.7 from chunk 4 are below it. The conditioning schedule halved insight on the two tasks it ran, OE001 and OE018.

These are drops on small samples, the same caution as the stack lead in the other direction.
-->

---

# The full run stopped when judge credits and GPU access ran out; a score we could trust needs 171 tasks at 2 or more passes

<div class="grid grid-cols-2 gap-8 mt-4 text-sm">
<div>

**What stopped it**

- About 03:40 UTC Nov 15: Gemini AI Studio prepaid credits ran out. Later runs have Luna scores only.
- 09:01 UTC Nov 15: the GPU provider workspace was disabled during `clstk14-dev-v1`, the only closed-loop test of stack plus servo. Base 23 of 24 tasks, stack plus servo 8 of 24.

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

No closed-loop comparison of stack plus servo exists, so there is no candidate number to report either.
-->

---

# Every clip is published, so you can compare control and treatment yourself

<div class="text-sm mt-4">

- Results site: benceruleanlu.github.io/playworld-advancement. Every run, its scores, and a compare view that plays control and treatment together.
- Clips: `github.com/benceruleanlu/playworld-advancement/releases/download/run-<EXP>/<TASK>.mp4`, 480p, with a `.jpg` poster.
- Pairs in this deck: GC033 and GC036 in `svgc14-fx-v1` a1 against a2; OE039 in `stk14-fx-dev-v1` a1 against a2.
- Per-task scores with the judge's reasons: `results/reports/<EXP>.md`. Full status and caveats: `AGENTS.md`.

</div>

<!--
The site's compare view opens a pair from the URL, for example ?compare=GC033&b=svgc14-fx-v1-a1&c=svgc14-fx-v1-a2#compare-clips.

Given the judge noise on the earlier slide, looking at the clips is a fair check on any claim here. A blind side-by-side review page is not on main at the time of writing.
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
