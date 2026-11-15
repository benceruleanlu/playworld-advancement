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

No full-benchmark run was launched, so there is no leaderboard number. On six-task comparisons the judge's noise (about 0.5) matches most flag effects.

<div class="mt-10 text-sm">

github.com/benceruleanlu/playworld-advancement

</div>

<!--
One sentence version: we have a working harness, about a hundred logged runs and more than 30 inference-time flags, but no full-benchmark score: no 171-task run was launched before judge credits and GPU access ran out, and on six-task comparisons the judge disagrees with itself by about as much as most flags moved scores.

We changed how an open world model runs at inference time and built a harness to score it. Hackathon entry, November 2026. Site: benceruleanlu.github.io/playworld-advancement (results, Pairs, blind review page).

The slides follow that order: our setup (slides 2 to 4, including what a task looks like) and our approach (slide 5), then the benchmark's published scores for context, our best official score, the judge noise and a seed-repeat pair, what the model remembers and what our flags changed, what stopped a full run, and where to look at the clips.

Every number in this deck comes from AGENTS.md, README.md, results/experiments.csv or results/reports/ on main. Each slide's notes name the section.
-->

---

# We ran LingBot-World v2, mostly the 14B, on PlayWorld tasks through our own harness on Modal GPUs

<div class="dg mt-6">
<div class="flex items-stretch gap-1">
  <div class="box flex-1"><b>Task</b>start image<br>goal<br>action list</div>
  <div class="arr">→</div>
  <div class="box flex-1 fill"><b>Runner</b>LingBot v2 14B<br>persistent session<br>+ our flags</div>
  <div class="arr">→</div>
  <div class="box flex-1"><b>Clip</b>up to 30 chunks<br>about 60 s</div>
  <div class="arr">→</div>
  <div class="box flex-1"><b>Judge</b>scores 1 to 5<br>failed gate: 1.0</div>
  <div class="arr">→</div>
  <div class="box flex-1"><b>Report</b><code>pwa report</code><br>experiments.csv</div>
  <div class="arr">→</div>
  <div class="box flex-1"><b>Site</b>scores<br>and clips</div>
</div>
<div class="grid grid-cols-3 gap-3 mt-6">
  <div class="box dash"><b>Benchmark</b>PlayWorld (Ding et al.), 171 tasks<br>GC 48 · IF 50 · insight 30 · out-of-sight 43<br>dev and dev2: 24 each · heldout 123, unscored</div>
  <div class="box dash"><b>Model</b>LingBot-World v2 (Robbyant Team)<br>14B for most runs, 1.3B for early A/B<br>weights unchanged, sampling loop re-implemented</div>
  <div class="box dash"><b>Compute</b>one H100 per shard on Modal<br>launched from GitHub Actions<br>about 18 min per task, queued</div>
</div>
</div>

<!--
The boxes are the path one task takes. The runner is adapters/lingbot_world2/run.py (or adapters/lingbot_world2_1p3b for the 1.3B), which reuses the upstream PlayWorld harness and swaps in our engine (AGENTS.md "Layout" and "Adapters"). pwa gen, pwa score and pwa report are the CLI steps (AGENTS.md "CLI"); the site reads results/experiments.csv from main (AGENTS.md "Results site"). The experiment and arms workflows launch the Modal shards.

Model size: 9 of the 101 logged runs used lingbot_world2_1p3b, including 4 scored rows (rs13-arms-v1, gch13-arms-v1); the rest used the 14B (results/experiments.csv). The plan of record cut the 1.3B for decisions.

The model weights are not changed. Our use is not "unmodified": adapters/lingbot_world2/session.py re-implements LingBot's sampling loop as a persistent session that keeps the attention cache between the player's steps (AGENTS.md "Scenes and attribution").

Family counts: AGENTS.md "Run speed", the sharding bullet (gc 48, if 50, insight 30, outsight 43; 171 in all). Splits: AGENTS.md "Layout" (dev 24, dev2 24 with 6 per family, heldout 123). The 30-chunk cap and the 60 s figure: "Run speed", Verified (mean 29.7 chunks, about 60 s of video). A task with a gate (for example, return to the start view) scores 1.0 if the gate fails: "Workstreams" in the first AGENTS.md (commit 2d8b8c4) and the PlayWorld harness.

Timings: AGENTS.md "Run speed", measured on lb14-session-agent-dev-v1: model load 267 to 357 s once per family per shard, agent rollouts 522 to 610 s with the first chunk (insight rollouts 367 to 443 s), 142 min wall clock or about 18 min per task on an 8-task shard, including GPU queueing. A later flag (--lingbot-fast-dit, #79) cuts the 14B load to about 31 s.
-->

---

# Most comparisons used fixed actions with no AI player; 35 of 101 logged runs were closed loop

<div class="dg mt-6">
<div class="grid items-stretch gap-x-1 gap-y-4" style="grid-template-columns: 150px 1fr 24px 1fr 24px 1fr 24px 190px;">
  <div class="flex flex-col justify-center"><b style="font-size:16px">Fixed actions</b><span class="small muted">open loop · 62 runs<br>+ 4 scripted player</span></div>
  <div class="box"><b>Dataset actions</b>the task's action list</div>
  <div class="arr">→</div>
  <div class="box fill"><b>Runner</b>same actions in both arms</div>
  <div class="arr">→</div>
  <div class="box"><b>Clip</b>about 60 s</div>
  <div class="arr">→</div>
  <div class="box fill2 flex flex-col justify-center" style="grid-row: span 2;"><b>Judge</b>Gemini 3.1 Pro<br>2 or 4 passes<br><span class="small">42 runs scored<br>34 generated, no Gemini score<br>(some have Luna proxy scores)</span></div>
  <div class="flex flex-col justify-center"><b style="font-size:16px">Closed loop</b><span class="small muted">35 runs</span></div>
  <div class="box"><b>AI player</b>picks each chunk's action from the frames so far</div>
  <div class="arr">⇄</div>
  <div class="box fill"><b>Runner</b>renders one chunk, about 2 s</div>
  <div class="arr">→</div>
  <div class="box"><b>Clip</b>up to 30 chunks</div>
  <div class="arr">→</div>
</div>
</div>

<div class="text-sm mt-8">

Only closed-loop runs can give a final score. Fixed actions are for A/B tests.

</div>

<!--
Sources: AGENTS.md "Rules" (dataset mode for A/B only, the Luna default, verifier settings unchanged: frame rate, resolution, JPEG), "Status against the timeline" ("Dataset actions and a scripted player are open loop"; the bullet that starts "Since about 18:35": both arms of a pair see the same actions), and "Settled" (player gpt-6-luna for compared runs, gpt-4.1-mini baseline is a diagnostic).

The scripted player (#102) replays a fixed plan, so it is also open loop. The AI player picks each chunk's action from the frames so far.

Run counts: results/experiments.csv on main has 105 rows; 4 are fake_runner pipeline tests. Of the other 101, action_source is dataset on 62 and agent on 39. Four of the 39 are the sp14-gc-v1 arms, whose notes say "scripted player: dataset moves, no AI player", so 35 had an AI player. Status: 42 scored, 34 generated, 15 cancelled, 7 failed, 3 predate the status column.

The judge box is Gemini 3.1 Pro, the official judge, at upstream settings. The 34 runs that were generated but never Gemini-scored include later ones with proxy scores from Luna, which are not comparable to the paper (slide 15 has when the credits ran out).

Players: gpt-4.1-mini on the dev baseline (slide 7), gpt-6-luna in later closed-loop arms. The only Luna closed-loop arms with a Gemini score are on the 1.3B or capped at 10 chunks (rs13, gch13, smk14-arms-gc-v2); in gch13, 22 of 110 player decisions fell back. The full-length 14B closed-loop runs (clstk14-dev-v1, stksv14-cl-gc-v1) were generated only.

Pass counts: the dev baseline was scored at 2 passes, the arm groups at 4 (AGENTS.md "Status against the timeline"). "About 2 s" per chunk: a closed-loop step adds 16n frames at 16 fps, 2 latent chunks by default (AGENTS.md "Adapters", session frame accounting).

Luna (openai:gpt-6-luna) as a judge is a proxy only. Its noise and its agreement with Gemini are on slide 8.
-->

---

# One baseline clip per task family: each family asks a different question of the generated world

<div class="dg mt-6">
<ClipRow :items="[
  { exp: 'lb14-session-agent-dev-v1', task: 'GC033', head: 'Geometry consistency', sub: 'layout holds as the camera moves' },
  { exp: 'lb14-session-agent-dev-v1', task: 'IF002', head: 'Interaction fidelity', sub: 'each action does what was asked' },
  { exp: 'lb14-session-agent-dev-v1', task: 'OE001', head: 'Insight evolution', sub: 'an on-screen process keeps going' },
  { exp: 'lb14-session-agent-dev-v1', task: 'OE039', head: 'Out-of-sight evolution', sub: 'hidden things change sensibly' },
]" />
</div>

<div class="cap">One task per family from <code>lb14-session-agent-dev-v1</code>, closed loop, no flags. CC BY-NC-SA 4.0, generated with LingBot-World v2.</div>

<!--
These are clips from the official baseline run, lb14-session-agent-dev-v1: LingBot-World v2 14B, persistent session, no flags, closed loop with the gpt-4.1-mini player, scored by Gemini 3.1 Pro at 2 passes (slide 7). Clip list: results/media/lb14-session-agent-dev-v1.json.

The family questions are the site's one-line questions (site/src/scripts/families.js):
- Geometry consistency: move the camera away and back. Is the place still the same place?
- Interaction fidelity: press a key. Does the subject do what was asked, with real contact?
- Insight evolution: wait and watch. Does a process on screen keep going sensibly?
- Out-of-sight evolution: look away, then back. Did the hidden part of the world move on sensibly?

Insight and out-of-sight task IDs both start with OE; the family is in the task JSON.

Clips load from GitHub Releases (run-lb14-session-agent-dev-v1) and do not autoplay. Press play on each.
-->

---

# Each change is an opt-in flag on the model or the AI player, with no retraining

<div class="dg mt-4">
<div class="grid items-center gap-x-2 gap-y-3" style="grid-template-columns: 1.1fr 24px 1fr 24px 0.9fr 24px 1fr;">
  <div class="box" style="grid-row: span 2;"><b>Same inputs</b>same task image<br>same seed<br>same dataset actions</div>
  <div class="arr" style="grid-row: span 2;">⇉</div>
  <div class="box"><b>Control arm</b>flags off</div>
  <div class="arr" style="grid-row: span 2;">⇉</div>
  <div class="box fill2" style="grid-row: span 2;"><b>Judge</b>same judge<br>2 or 4 passes</div>
  <div class="arr" style="grid-row: span 2;">→</div>
  <div class="box" style="grid-row: span 2;"><b>One comparison</b>treatment minus control,<br>per task and family</div>
  <div class="box fill"><b>Treatment arm</b>flags differ (one, or a stack)</div>
</div>
<div class="grid grid-cols-3 gap-3 mt-6">
  <div class="box dash"><b>Delta over twice the pass spread</b>smaller is noise</div>
  <div class="box dash"><b>Two seeds</b>the gain repeats on both, no gate lost</div>
  <div class="box dash"><b>Heldout untouched</b>123 tasks, unscored</div>
</div>
</div>

<div class="text-sm mt-6">

More than 30 flags are on main, all off by default. No run reached the decision tier, so no flag is adopted.

</div>

<!--
Flags, grouped by the first plan's workstreams:
- Insight: caption prompt, insight director, conditioning schedule.
- Control and gates: turn calibration, yaw gain, yaw servo, re-anchor, IF slow translation, IF fixed camera.
- Player prompts: return stop, player hint. Out-of-sight memory: sink size, attention window, sink key scale, pose memory.

The four groups follow the workstreams of the first plan (AGENTS.md as scaffolded, commit 2d8b8c4); the plan of record in #66 replaced that section and later cut out-of-sight memory and sink work for the event ("Cut for this event"), but fixed-action runs on the sink and window went ahead anyway. The flags under each are documented in AGENTS.md "Adapters". Return stop and player hint change what the AI player is told, not the model (README.md), and were scored only on the 1.3B. The eval infrastructure (pwa CLI, experiment and arms workflows, per-run reports, results site, blind review page) is on slides 2 and 16.

Flag count: AGENTS.md "Status against the timeline" recorded 28 method flags at 22:25, and #115, #116, #121, #132, #133, #139, #144 and #147 added more since; those eight are merged and unscored. None has decision-tier evidence.

What would count. The strip at the bottom is the rule set. Decision tier: closed loop, 14B, full length, all 6 dev tasks of a family, 2 seeds, official judge. Adoption: a task moves a full point, the gain repeats on both seeds, no gate is lost. Rules: AGENTS.md "Rules" and "Testing tiers and the adoption rule". Also in "Rules": a new experiment name for every run (pwa gen refuses an existing run directory because upstream --skip-done silently reuses old videos), heldout unscored until code freeze, and final numbers closed loop with Gemini 3.1 Pro over 2 or more passes.

Practice, not a written rule: since about 18:35 model-side flags were compared with the same actions in both arms (dataset or scripted player) at the same seed. Generation is deterministic, so any difference between such arms is the flag or the judge. AGENTS.md calls these runs a change from the plan as written: they are open loop and cannot meet the decision tier. Some servo groups borrow controls from other groups (sks14, mem14, win14). The stack on slide 13 differs by six flags, not one.

The rest of the deck reads results against these rules. Slide 8 shows why the judge spread sets the bar.
-->

---

# In the PlayWorld paper Genie 3 scores 2.12 overall, and LingBot-World v2's web demo scores 1.82

<div class="dg mt-6" style="font-size: 15px;">
<div class="pchart">
  <div class="prow"><div class="pname">Genie 3</div><div class="ptrack"><span class="pdot" style="left: 74.7%"></span><span class="pval" style="left: 74.7%">2.12</span></div></div>
  <div class="prow"><div class="pname">LingBot-World v2 (web demo)</div><div class="ptrack"><span class="pdot hi" style="left: 54.7%"></span><span class="pval" style="left: 54.7%">1.82</span></div></div>
  <div class="prow"><div class="pname">SANA-WM</div><div class="ptrack"><span class="pdot" style="left: 32%"></span><span class="pval" style="left: 32%">1.48</span></div></div>
  <div class="prow"><div class="pname">Matrix-Game 3.0</div><div class="ptrack"><span class="pdot" style="left: 9.3%"></span><span class="pval" style="left: 9.3%">1.14</span></div></div>
  <div class="paxis"><span style="left: 0%">1.0</span><span style="left: 33.3%">1.5</span><span style="left: 66.7%">2.0</span><span style="left: 100%">2.5</span></div>
  <div class="small muted" style="margin-left: 250px; margin-top: 4px;">Overall score, all 171 tasks (scale 1 to 5; 1 is the lowest)</div>
</div>
<div class="box dash mt-6" style="text-align: left; max-width: 640px;"><b style="display:inline">Ours, not on this axis:</b> 1.64 ± 0.13 on 24 dev tasks, closed loop. Not comparable: 24 of 171 tasks.</div>
</div>

<div class="text-sm mt-5">

Published scores from Ding et al., arXiv:2608.13552, for context.

</div>

<style>
.pchart { position: relative; }
.prow { display: grid; grid-template-columns: 250px 1fr; align-items: center; height: 40px; }
.pname { text-align: right; padding-right: 16px; }
.ptrack { position: relative; height: 100%; border-left: 1px solid currentColor; margin-right: 40px; }
.ptrack::before { content: ''; position: absolute; left: 0; right: 0; top: 50%; border-top: 1px dotted currentColor; opacity: 0.35; }
.pdot { position: absolute; top: 50%; width: 16px; height: 16px; border-radius: 50%; background: #8b8b8b; transform: translate(-50%, -50%); }
.pdot.hi { background: #2f6fd6; }
.pval { position: absolute; top: 50%; transform: translate(14px, -50%); font-variant-numeric: tabular-nums; font-weight: 600; }
.paxis { position: relative; margin-left: 250px; margin-right: 40px; height: 22px; border-top: 1px solid currentColor; }
.paxis span { position: absolute; top: 2px; transform: translateX(-50%); font-size: 14px; }
</style>

<!--
The reference scores are the PlayWorld paper's numbers on all 171 tasks, copied in AGENTS.md "Reference scores". None of our runs is on that footing, so our 1.64 is drawn apart from the axis (slide 7 has the run).

Full table (paper, full benchmark): GC, IF, insight, out-of-sight, overall.
Genie 3: 2.74, 2.40, 1.51, 1.81, 2.12.
LingBot-World v2 (web demo): 2.04, 2.13, 1.95, 1.16, 1.82.
SANA-WM: 1.72, 1.89, 1.13, 1.16, 1.48.
Matrix-Game 3.0: 1.30, 1.25, 1.00, 1.00, 1.14.

LingBot's web demo already leads Genie 3 on insight, 1.95 against 1.51. Its largest gap is out-of-sight, 1.16 against 1.81.

LingBot-World v2 is the open model we used, but the paper scored it through its web demo, not through the released code we run.

The red-team review in research/red-team-and-plan.md estimated that out-of-sight alone cannot reach 2.12 (every out-of-sight task at 2.0 gives about 2.03 overall), so two or three families would have to move.
-->

---

# Our best official closed-loop dev score is 1.64 ± 0.13 on 24 tasks, with no method

<div class="mt-6" style="max-width: 720px;">

| Run | `lb14-session-agent-dev-v1` |
|---|---|
| Model | LingBot-World v2 14B, persistent session, no flags |
| Loop | closed, AI player `gpt-4.1-mini` |
| Tasks | 24 dev (6 per family), 0 missing |
| Judge | Gemini 3.1 Pro, 2 passes |
| GC / IF / insight / out-of-sight | 1.83 / 1.81 / 1.58 / 1.33 |
| Overall | **1.64 ± 0.13** |

</div>

<div class="text-sm mt-6">

Not comparable to the paper: 24 of 171 tasks, with a task-sampling error of roughly 0.2 per family.

</div>

<!--
Source: results/experiments.csv row lb14-session-agent-dev-v1 (overall 1.6390, std 0.1258, 2 passes, 24 tasks, 0 missing) and the "Ours" row in AGENTS.md "Reference scores". Other Gemini-scored rows exist (the arm groups on slide 14), but they are fixed-action or six-task subsets, so this is the best closed-loop dev number.

No run covers all 171 tasks, for the base model or any method. The paper's LingBot row (1.82) is all 171 tasks through its web demo.

This is the base model with every flag off. It is not the starting-model number for the plan, because the plan fixed the player as gpt-6-luna and this run used gpt-4.1-mini.

No flag is adopted. The 123 heldout tasks are unscored: heldout is reserved until code freeze by the repo rules, and code freeze never produced a full run.
-->

---

# The judge gives the same video scores up to 1.3 apart, so six-task comparisons cannot resolve differences under about 0.5

<div class="dg grid grid-cols-2 gap-10 mt-6">
<div>
  <b style="font-size:16px">One clip, GC036, scored separately</b>
  <div class="small muted">Gemini 3.1 Pro, byte-identical video, task score</div>
  <div class="strip mt-10">
    <span class="sdot fail" style="left: 8.75%"></span><span class="slab" style="left: 8.75%">1.35<br>gate failed</span>
    <span class="sdot" style="left: 41.25%"></span><span class="slab" style="left: 41.25%">2.65<br>gate passed</span>
    <span class="sspan" style="left: 8.75%; width: 32.5%"></span><span class="sspanlab" style="left: 25%">1.3 apart</span>
  </div>
  <div class="saxis"><span style="left:0%">1</span><span style="left:25%">2</span><span style="left:50%">3</span><span style="left:75%">4</span><span style="left:100%">5</span></div>
</div>
<div>
  <b style="font-size:16px">Six-task family mean, Gemini</b>
  <div class="small muted">change against control</div>
  <div class="strip mt-10">
    <span class="sband" style="left: 33.3%; width: 33.3%"></span><span class="sbandlab" style="left: 50%">judge swing on<br>identical videos ±0.5</span>
    <span class="sdot flag" style="left: 35%"></span>
    <span class="sdot flag" style="left: 24.3%"></span>
    <span class="sdot flag" style="left: 21.7%"></span>
    <span class="slab" style="left: 12%">sink key scale arms<br>−0.45, −0.77, −0.85</span>
  </div>
  <div class="saxis"><span style="left:0%">−1.5</span><span style="left:33.3%">−0.5</span><span style="left:50%">0</span><span style="left:66.7%">+0.5</span><span style="left:100%">+1.5</span></div>
</div>
</div>

<div class="text-sm mt-8">

Generation is deterministic: the same settings and seed give a byte-identical video, so these spreads are the judge.

</div>

<style>
.strip { position: relative; height: 104px; border-bottom: 1px solid currentColor; margin-right: 20px; margin-left: 20px; }
.saxis { position: relative; height: 22px; margin: 0 20px; font-size: 14px; }
.saxis span { position: absolute; top: 2px; transform: translateX(-50%); }
.sdot { position: absolute; bottom: 10px; width: 16px; height: 16px; border-radius: 50%; background: #2f6fd6; transform: translateX(-50%); }
.sdot.fail { background: #8b8b8b; }
.sdot.flag { background: #8b8b8b; border: 2px solid currentColor; }
.slab { position: absolute; bottom: 32px; transform: translateX(-50%); text-align: center; font-size: 14px; white-space: nowrap; }
.sspan { position: absolute; top: 22px; height: 8px; border: 1px solid currentColor; border-bottom: none; }
.sspanlab { position: absolute; top: 0; transform: translateX(-50%); font-size: 14px; font-weight: 600; white-space: nowrap; }
.sband { position: absolute; top: 0; bottom: 0; background: rgba(47, 111, 214, 0.2); border-left: 1px dashed currentColor; border-right: 1px dashed currentColor; }
.sbandlab { position: absolute; top: 4px; transform: translateX(-50%); font-size: 14px; text-align: center; white-space: nowrap; }
</style>

<!--
This is the central finding. Sources: AGENTS.md "Status against the timeline", the "Same config scored three times" bullet and the Luna bullet.

Left: GC036 comes from pm14-fx-v1 arms 1 and 2, which were checked byte-identical. Gemini gave 2.65 when it passed the gate and 1.35 when it failed it. Single passes differ by up to 2 to 3 points.

Right: a six-task family mean moves about 0.5 on the same videos, drawn as the band from -0.5 to +0.5. The dots are the sink key scale arms on out-of-sight (sks14-fx-v1, Gemini, one seed): control 2.10, arms 1.65, 1.33 and 1.25. Scale 0.7 (-0.45) is inside the band; the two arms that start at chunk 4 are below it (slide 14).

Luna (openai:gpt-6-luna, proxy judge): byte-identical clips give 0.50 per task on average and 0.62 on a five-task mean. It lets 97% of gate checks pass, where Gemini failed a gate on 23% of tasks. Rank correlation with Gemini: 0.62 on 21 clips (0.41 on out-of-sight). Luna's identical-clip numbers come from walking-only GC tasks, where the servo arm and the control are the same file.

We used Luna after Gemini scoring stopped working on Nov 15 (AGENTS.md records the credits running out at about 03:40 UTC, but Gemini-scored rows land in results/experiments.csv until 05:43 and the first failed scoring is at 06:14). Luna's scores are not reported numbers and are not comparable to the leaderboard.

The practical bar: about 0.5 for a six-task family mean under Gemini, about 0.6 under Luna. Any flag effect smaller than that cannot be seen in our dev comparisons. The next slide shows how much a clip changes when only the seed changes.
-->

---

# Two IF002 clips with the same flags and the same actions, where only the seed differs

<div class="mt-6 mx-auto" style="max-width: 760px;">
<ClipPair task="IF002" control="stk14-fx-dev-v1-a1" treatment="stk14-fx-dev-v1-a3" controlLabel="Seed 0" treatmentLabel="Seed 1" />
</div>

<div class="cap text-center">IF002, no flags, fixed actions; seed 0 (<code>stk14-fx-dev-v1-a1</code>) vs seed 1 (<code>-a3</code>). CC BY-NC-SA 4.0, generated with LingBot-World v2.</div>

<!--
Both arms are the no-flag arms of stk14-fx-dev-v1: arm 1 at the default seed 0, arm 3 with --seed 1, the same runner arguments otherwise (results/experiments.csv notes for stk14-fx-dev-v1-a1 and -a3). Both replay the dataset's actions.

Use "Play both from start" to run them together. Nothing but the seed differs, so the difference between the clips is what a second seed adds on top of the judge noise on the previous slide. This is why the adoption rule asks for a gain that repeats on both seeds (slide 5).

These clips have no official score: stk14-fx-dev-v1 was generated after the Gemini credits ran out and has Luna proxy scores only. No claim about scores is made here, only that the two arms differ in seed.

The pair is also in the site's Pairs section.
-->

---

# The LingBot attention cache is configured to keep the opening view permanently and about 2 seconds of recent video

<div class="dg mt-8">
<div class="flex gap-1 text-center items-stretch" style="height: 92px">
  <div class="box fill2 flex flex-col justify-center" style="flex: 6"><b>6 sink latents</b>opening view, kept forever</div>
  <div class="box dash flex flex-col justify-center" style="flex: 5"><b>evicted</b>older views</div>
  <div class="box fill flex flex-col justify-center" style="flex: 8"><b>8 recent latents</b>about 2 s</div>
  <div class="box grey flex flex-col justify-center" style="flex: 4"><b>4 generating</b>next 4 latents (1 s)</div>
</div>
<div class="taxis">
  <span style="left: 0%">0 s</span>
  <span style="left: 26%">about 1.3 s</span>
  <span class="brk" style="left: 37.5%">not to scale</span>
  <span style="left: 47.8%">now − 2 s</span>
  <span style="left: 82.6%">now</span>
  <span style="left: 100%">+1 s</span>
</div>
<div class="small muted mt-1">Time in the clip, at 16 frames per second and 4 frames per latent. One chunk attends to 18 latents: local attention 18, sink 6.</div>
<div class="grid grid-cols-2 gap-3 mt-5">
  <div class="box"><b>Return to the start view</b>can use the sink</div>
  <div class="box dash"><b>Return to any other view</b>seen over about 2 s ago: gone</div>
</div>
</div>

<div class="text-sm mt-5">

This is the loader configuration, not a measurement. The GPU probe that would measure it is unmerged (#37).

</div>

<style>
.taxis { position: relative; height: 28px; border-top: 1px solid currentColor; margin-top: 4px; font-size: 14px; }
.taxis span { position: absolute; top: 4px; transform: translateX(-50%); white-space: nowrap; }
.taxis span:first-child { transform: none; }
.taxis span:last-child { transform: translateX(-100%); }
.taxis .brk { opacity: 0.7; font-style: italic; }
</style>

<!--
Out-of-sight tasks ask the model to show the scene correctly after the camera leaves it and comes back. With this cache, anything seen more than about two seconds ago, other than the opening view, has to be regenerated from nothing.

Source: AGENTS.md "Adapters", the KV window bullet: local_attn_size 18, sink_size 6 (adapters/lingbot_world2/loader.py); upstream keeps the first 6 latents (input image plus about 20 frames) forever and rolls the rest; a chunk sees the sink plus the last 8 latents, about 32 frames (2 s). The time axis uses those figures: 32 frames in 2 s is 16 frames per second, and 4 frames per latent; the sink covers the input image plus about 20 frames, so about 1.3 s. The evicted block is not to scale.

AGENTS.md is explicit that this reach is the configuration, not a measurement. The GPU memory probe that would measure it is in PR #37, unmerged. The cache_model script counts how often dataset actions revisit an evicted view, on CPU.

Two flags change this window: keep-first 10 and attention window 22. They are part of the stack on slide 13.
-->

---

# A yaw servo cut the end-heading error on 6 GC tasks; no judge has shown a score change

<div class="grid grid-cols-[0.8fr_1.2fr] gap-8 mt-4">
<div class="dg">
<div class="grid gap-x-1 gap-y-2 items-center text-center" style="grid-template-columns: 1fr 24px 1fr; grid-template-rows: auto 26px auto;">
  <div class="box"><b>1. Command</b>a turn</div>
  <div class="arr">→</div>
  <div class="box fill"><b>2. Render</b>one chunk</div>
  <div class="arr">↑</div>
  <div></div>
  <div class="arr">↓</div>
  <div class="box"><b>4. Correct</b>the next command</div>
  <div class="arr">←</div>
  <div class="box fill2"><b>3. Measure</b>rendered rotation (phase correlation)</div>
</div>
<div class="small muted mt-3 text-center">Each chunk: 1 → 2 → 3 → 4 → 1.</div>
</div>
<div class="dg">
<HeadingChart />
</div>
</div>

<div class="text-sm mt-5">

No Gemini score exists for a servo clip. Under the proxy judge Luna, the score deltas are noise.

</div>

<!--
The loop: rendered turns differ from commanded turns, so the servo measures the rendered rotation of each chunk and corrects the next command. Design, code and GPU trials by benceruleanlu in PR #125, merged in #131.

Rendered over commanded, 8 static first-person scenes, one seed: 0.88 to 1.99 left, 0.56 to 1.44 right (PR #125, the camera-response study bullet in AGENTS.md).

Heading is measured by phase correlation, the same estimator the servo steers with. The independent check is the similarity of the last frame to frame 0, available for GC033 and GC036 only: GC033 -0.09 to 0.52, GC036 0.07 to 0.63. GC022 is from the stack run.

Sources: AGENTS.md "Status against the timeline", the yaw servo bullet. Under Luna the same-run servo deltas are -0.10 (fixed actions, 6 turning tasks) and +0.05 (closed loop, 4 turning tasks), inside Luna's noise.

GC038 improved least, 96 to 49 degrees. Walking-only GC tasks give byte-identical clips with and without the servo, which is where Luna's identical-clip noise numbers on the judge slide (slide 8) came from.

The servo does not support out-of-sight tasks yet. The clips are on the next slide.
-->

---

# On GC033 and GC036 the servo clips end within 6 degrees of the intended heading; the controls end 28 and 70 degrees off

<div class="dg grid gap-x-6 gap-y-4 mt-3 items-center" style="grid-template-columns: 500px 1fr;">
  <ClipPair task="GC033" control="svgc14-fx-v1-a1" treatment="svgc14-fx-v1-a2" controlLabel="No servo" treatmentLabel="Yaw servo" />
  <div class="box"><b>End-heading error</b>28° → 0.3°</div>
  <ClipPair task="GC036" control="svgc14-fx-v1-a1" treatment="svgc14-fx-v1-a2" controlLabel="No servo" treatmentLabel="Yaw servo" />
  <div class="box"><b>End-heading error</b>70° → 5.6°</div>
</div>

<div class="cap">GC033 and GC036, fixed actions: no servo (<code>svgc14-fx-v1-a1</code>) vs yaw servo (<code>-a2</code>). CC BY-NC-SA 4.0, generated with LingBot-World v2.</div>

<!--
Play each pair with "Play both from start" and compare the last second with the first frame. End-of-clip similarity to frame 0: GC033 control -0.09, servo 0.52; GC036 control 0.07, servo 0.63.

Source: AGENTS.md "Status against the timeline", the yaw servo bullet (end-heading error GC033 28 to 0.3 degrees, GC036 70 to 5.6 degrees); the run names are in results/media/svgc14-fx-v1-a1.json and -a2.json. Clips are LingBot-World v2 14B.

These are open-loop clips: both arms replay the dataset's actions, so the only difference is the servo. No judge score exists for either servo clip under Gemini.

The site's Pairs section loads either pair.
-->

---

# A stack of six flags scored about a point higher on out-of-sight in three six-task pairs, under the proxy judge only

<div class="grid gap-6 mt-2" style="grid-template-columns: 300px 1fr;">
<div class="dg">
  <b style="font-size:15px">Out-of-sight, stack minus no flags</b>
  <div class="small muted">Luna proxy judge, six tasks per pair</div>
  <div class="dbars mt-3">
    <div class="dline" style="left: 50%"><span>Luna noise bar 0.6</span></div>
    <div class="drow"><span class="dl">dev, seed 0</span><span class="db" style="width: 85%"></span><span class="dv" style="left: 85%">+1.02</span></div>
    <div class="drow"><span class="dl">dev, seed 1</span><span class="db" style="width: 76.7%"></span><span class="dv" style="left: 76.7%">+0.92</span></div>
    <div class="drow"><span class="dl">dev2</span><span class="db" style="width: 81.7%"></span><span class="dv" style="left: 81.7%">+0.98</span></div>
  </div>
  <div class="small mt-4">Stack: turn calibration, caption prompt, insight director, IF slow translation, sink 10, window 22</div>
</div>
<div class="dg flex flex-col gap-2">
  <ClipPair task="OE039" control="stk14-fx-dev-v1-a1" treatment="stk14-fx-dev-v1-a2" controlLabel="No flags" treatmentLabel="Stack" :width="200" />
  <ClipPair task="OE047" control="stk14-fx-dev-v1-a1" treatment="stk14-fx-dev-v1-a2" controlLabel="No flags" treatmentLabel="Stack" :width="200" />
</div>
</div>

<div class="cap">OE039 and OE047, fixed actions: no flags (<code>stk14-fx-dev-v1-a1</code>) vs stack (<code>-a2</code>). CC BY-NC-SA 4.0, generated with LingBot-World v2.</div>

<style>
.dbars { position: relative; padding-top: 22px; margin-left: 92px; margin-right: 52px; }
.dline { position: absolute; top: 0; bottom: 0; border-left: 2px dashed currentColor; opacity: 0.8; }
.dline span { position: absolute; top: 0; left: 4px; font-size: 13px; white-space: nowrap; }
.drow { height: 30px; position: relative; border-left: 1px solid currentColor; }
.dl { position: absolute; right: 100%; padding-right: 8px; top: 50%; transform: translateY(-50%); font-size: 14px; white-space: nowrap; }
.drow .db { position: absolute; left: 0; top: 7px; height: 16px; background: #2f6fd6; }
.dv { position: absolute; top: 50%; transform: translate(6px, -50%); font-size: 14px; font-variant-numeric: tabular-nums; }
</style>

<!--
This is a lead from small samples, not a result. The three pairs are stk14-fx-dev-v1 at seeds 0 and 1 (4 passes) and stk14-fx-dev2-v1 (2 passes). Source: AGENTS.md, the stack bullet under "Proxy judge findings". The bars are drawn on a 0 to 1.2 scale; the dashed line is Luna's 0.6 bar from the judge slide (slide 8).

Stack: turn calibration, caption prompt, insight director, IF slow translation, sink 10 (keep the first 10 latents, up from 6) and window 22 (up from 18). Against no flags, fixed actions, six out-of-sight tasks per pair, Luna: +1.02, +0.92, +0.98. Out-of-sight is the only family above Luna's 0.6 bar in all three pairs.

Luna agrees weakly with Gemini on out-of-sight (rank correlation 0.41), so this may not hold under Gemini.

Other families were mixed across the three pairs: GC +0.59, -0.16, +0.30; IF +0.40, -0.25, +0.45.

None of the six parts passed the adoption rule alone, so a gain would not say which part caused it.

Clips: OE039 and OE047 at seed 0, results/media/stk14-fx-dev-v1-a1.json and -a2.json. LingBot-World v2 14B.
-->

---

# No single flag beat the judge noise: on six tasks or fewer, the moves we saw were inside it or downward

<div class="dg grid grid-cols-4 gap-3 mt-6 tiers">
  <div class="box fill2"><b>Measured</b><div class="t">geometry, no score</div><div class="m">Yaw servo: end heading</div></div>
  <div class="box fill"><b>Lead from a small sample</b><div class="t">upward</div><div class="m">Stack: out-of-sight +1 (Luna, 2 seeds + dev2)</div></div>
  <div class="box"><b>Did not repeat</b><div class="t">or inside the noise</div><div class="m">Turn calibration: +1.95 then +0.35</div><div class="m">Sink 10 + window 22: OE039 3.44 (seed 1), 1.75 (seed 0)</div><div class="m">Caption prompt: 2 up, 2 down</div></div>
  <div class="box dash"><b>Dropped</b><div class="t">lowered scores or no gain</div><div class="m">Sink key scale: −0.45 to −0.85</div><div class="m">Conditioning schedule: insight 3.00 → 1.50</div><div class="m">Pose memory: +0.20 (Luna), bar 0.34</div></div>
</div>

<div class="text-sm mt-6">

Gemini 3.1 Pro and one seed unless marked; the servo has no judge score. Nothing is adopted.

</div>

<style>
.tiers .box { text-align: left; display: flex; flex-direction: column; gap: 6px; }
.tiers .t { font-size: 13px; opacity: 0.8; margin-top: -4px; }
.tiers .m { font-size: 14px; border-top: 1px solid rgba(128,128,128,0.4); padding-top: 5px; }
</style>

<!--
Each method sits in one tier. Sources: AGENTS.md "Status against the timeline": the yaw servo bullet, the stack bullet, the sks14-fx-v1 and dec14-ins-v1 bullets, the win14-fx-v1 bullet, the "What the fixed-action results say so far" bullet, and the pose memory bullet.

Measured: the yaw servo's end heading (slides 11 and 12); no judge score change.

Leads from small samples: the stack, about +1 on out-of-sight under Luna (slide 13). Dropped as harmful or null (AGENTS.md, each on one seed and six tasks or fewer): sink key scale lowered out-of-sight: control 2.10; scaled arms 1.65, 1.33 and 1.25 (sks14-fx-v1, Gemini, one seed). Scale 0.7 (-0.45) is inside the six-task noise from the judge slide (slide 8); scale 0.4 and 0.7 from chunk 4 are below it. The conditioning schedule halved insight, 3.00 to 1.50, on the two tasks it ran, OE001 and OE018 (dec14-ins-v1). Both sit in the "Dropped" tier with their numbers; they are drops on small samples, the same caution as the stack lead in the other direction.

Did not repeat or inside the noise: turn calibration, the same comparison run twice on GC031, gave +1.95 and +0.35. Generation is deterministic, so that spread is a config difference or judge spread, not rollout noise. Caption prompt: 2 tasks up and 2 down by a full point in one run. Sink 10 with window 22 raised OE039 1.00 to 3.44 at seed 1, but 1.75 at seed 0, inside the controls (win14-fx-v1).

Dropped: pose memory retrieves as planned after #129, with no geometric gain, +0.20 under Luna against a bar of 0.34.
-->

---

# No full-benchmark run was launched before judge credits and GPU access ran out

<div class="dg mt-8">
<div class="tl">
  <div class="tlband" style="left: 51.9%; right: 0;"><span>Luna proxy scores only</span></div>
  <div class="tlev" style="left: 51.9%"><b>06:14</b>Gemini scoring fails<br>(last Gemini row 05:43)</div>
  <div class="tlev" style="left: 75.1%"><b>09:01</b>GPU workspace disabled<br>during <code>clstk14-dev-v1</code></div>
  <div class="tlaxis"><span style="left:0%">00:00</span><span style="left:25%">03:00</span><span style="left:50%">06:00</span><span style="left:75%">09:00</span><span style="left:100%">12:00 UTC</span></div>
</div>
<div class="small muted" style="margin-top: 30px;">Nov 15, UTC</div>
<div class="grid grid-cols-3 gap-3 mt-8">
  <div class="box"><b>Cut short</b><code>clstk14-dev-v1</code>, closed loop<br>base 23 of 24 tasks<br>stack + servo 8 of 24</div>
  <div class="box dash"><b>A trusted score needs</b>base and method on all 171<br>closed loop, Gemini, 2+ passes</div>
  <div class="box dash"><b>Estimate</b>noise about 0.1 overall<br>one arm on 8 GPUs: 3.8 to 6.9 h</div>
</div>
</div>

<div class="text-sm mt-5">

No closed-loop comparison of stack plus servo exists.

</div>

<style>
.tl { position: relative; height: 110px; margin: 0 30px; }
.tlband { position: absolute; bottom: 0; height: 18px; background: rgba(139,139,139,0.25); }
.tlband span { position: absolute; right: 4px; top: 0; font-size: 13px; white-space: nowrap; }
.tlev { position: absolute; bottom: 0; transform: translateX(-50%); text-align: center; font-size: 14px; padding-bottom: 26px; white-space: nowrap; border-left: none; }
.tlev::after { content: ''; position: absolute; left: 50%; bottom: 0; height: 24px; border-left: 2px solid #2f6fd6; }
.tlev b { display: block; font-size: 15px; }
.tlaxis { position: absolute; left: 0; right: 0; bottom: -24px; height: 22px; border-top: 1px solid currentColor; font-size: 14px; }
.tlaxis span { position: absolute; top: 2px; transform: translateX(-50%); white-space: nowrap; }
.tlaxis span:last-child { transform: translateX(-100%); }
</style>

<!--
Sources: AGENTS.md "Status against the timeline" (credits, the clstk14-dev-v1 bullet, the noise estimate) and "Run speed" for the 171-task budget at 8 shards.

AGENTS.md records the Gemini AI Studio prepaid credits running out (402 RESOURCE_EXHAUSTED) at about 03:40 UTC Nov 15, but results/experiments.csv has Gemini-scored rows (dec14, sks14, pm14-fx-v1/v2, ins14-fx-v2, win14-fx-v1) up to 05:43, and scoring failed at 06:14. The band starts at 06:14. Later runs have Luna scores only.

09:01 UTC Nov 15: the GPU provider workspace was disabled during clstk14-dev-v1, a 24-task dev run and the only closed-loop test of stack plus servo. Base 23 of 24 tasks, stack plus servo 8 of 24, the third arm (stack plus servo without IF slow translation) never started.

What a trusted score needs (estimate): base and method each on all 171 tasks, closed loop, Gemini 3.1 Pro, 2 or more passes. Scaling the 0.5 six-task spread by the square root of 6/171 gives noise of about 0.1 on the overall mean. Generation for one 171-task arm on 8 GPUs: about 3.8 h without queueing (component timings), about 6.9 h at the dev baseline's queued 18 minutes per task; the job cap is 350 minutes.

The 0.1 figure is an estimate, not a measurement. Scoring through Google Cloud is wired (#148) but no live call has been made.

AGENTS.md says the starting-model 171 run was never launched. No closed-loop comparison of stack plus servo exists, so there is no candidate number to report either.
-->

---

# Every clip is published, so you can compare control and treatment yourself

<div class="dg grid grid-cols-3 gap-4 mt-8">
  <div class="box"><b>Results site</b>benceruleanlu.github.io/<br>playworld-advancement<br><span class="muted">every run, scores, Pairs</span></div>
  <div class="box"><b>Clips</b>releases/download/<br>run-&lt;EXP&gt;/&lt;TASK&gt;.mp4<br><span class="muted">480p, with a .jpg poster</span></div>
  <div class="box"><b>Blind review</b>…/playworld-advancement/review/<br><span class="muted">hides the arms until you finish</span></div>
</div>

<div class="text-sm mt-8">

Per-task scores with the judge's reasons are in `results/reports/<EXP>.md`.

</div>

<!--
Results site: benceruleanlu.github.io/playworld-advancement. Every run, its scores, and a Pairs section that plays control and treatment side by side. The site's Pairs section (#166) opens a pair from the URL (?cmp=KEY&pair=TASK#pairs); old links such as ?compare=GC033&b=svgc14-fx-v1-a1&c=svgc14-fx-v1-a2#compare-clips open the same pair.

Clips: github.com/benceruleanlu/playworld-advancement/releases/download/run-<EXP>/<TASK>.mp4, 480p, with a .jpg poster.

Pairs in this deck: GC033, IF002, OE001 and OE039 in lb14-session-agent-dev-v1 (slide 4); IF002 seed 0 against seed 1 in stk14-fx-dev-v1 a1 against a3 (slide 9); GC033 and GC036 in svgc14-fx-v1 a1 against a2 (slide 12); OE039 and OE047 in stk14-fx-dev-v1 a1 against a2 (slide 13).

Blind review page: benceruleanlu.github.io/playworld-advancement/review/. It hides which clip is control and which is treatment until you finish; it records a preference by eye, not a score. Given the judge noise on slide 8, looking at the clips is a fair check on any claim here. The review page (#164, site/src/pages/review.astro) shuffles sides per reviewer and reveals arms and a sign test only after "Finish and reveal". Clips load from release URLs that name the run, so blinding holds only if reviewers do not open developer tools.

Full status and caveats: AGENTS.md.
-->

---

# Credits and licences

<div class="mt-4 credits">

| | |
|---|---|
| **PlayWorld** | Benchmark, harness, verifier and task data: Ding et al., arXiv:2608.13552. Code kxding/PlayWorld (no licence; pinned submodule, not copied). Data jocelynd/playworld-bench. Task images from Pexels and web image search keep their sources' terms. |
| **LingBot-World v2** | Robbyant Team, arXiv:2607.07534, CC BY-NC-SA 4.0. Weights and modules run unchanged; `adapters/lingbot_world2/session.py` re-implements its sampling loop. |
| **Reference scores** | Genie 3 (Google DeepMind), SANA-WM (NVIDIA), Matrix-Game 3.0 (Skywork AI) and LingBot-World v2, as reported in the PlayWorld paper. |
| **Judges and player** | Scoring: Gemini 3.1 Pro (Google). Proxy judge and AI player: OpenAI `gpt-6-luna`; dev baseline player `gpt-4.1-mini`. |
| **Scene videos** | Generated with LingBot-World v2, released under CC BY-NC-SA 4.0, non-commercial. Removal requests: open an issue titled "Scene removal request". |
| **Deck** | Built with Slidev. Source: `slides/` in the repo. |

</div>

<style>
.credits table { font-size: 13px; }
.credits thead { display: none; }
.credits td:first-child { white-space: nowrap; }
</style>

<!--
Wording follows README.md "Credits" and the attribution facts in AGENTS.md "Scenes and attribution".
-->
