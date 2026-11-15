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

# No leaderboard score: the official judge's noise matched our effects; a yaw servo cut the end-heading error

<div class="dg hnums mt-6">
  <div><span class="n">2.12</span>Genie 3, PlayWorld paper, 171 tasks</div>
  <div><span class="n">1.64 ± 0.13</span>ours, 24 dev tasks, no flags, closed loop</div>
  <div><span class="n">about 0.5</span>official judge noise on a six-task family mean (1 to 5 scale)</div>
</div>

<div class="mt-8 text-sm">

github.com/benceruleanlu/playworld-advancement

</div>

<style>
.hnums { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; font-size: 15px; }
.hnums .n { display: block; font-size: 34px; font-weight: 700; line-height: 1.1; font-variant-numeric: tabular-nums; color: #2f6fd6; }
html.dark .hnums .n { color: #7fa8ee; }
</style>

<!--
One sentence version: we built a harness and more than 30 opt-in inference-time flags for LingBot-World v2, but no 171-task run was launched, so there is no leaderboard score; on six-task comparisons the official judge (Gemini 3.1 Pro) disagrees with itself on identical videos by about as much as the effects we measured; the one result that needs no judge is a yaw servo that cut the end-heading error on turning GC tasks.

Numbers: 2.12 is Genie 3 overall in the PlayWorld paper (AGENTS.md "Reference scores"). 1.64 +/- 0.13 is lb14-session-agent-dev-v1 (results/experiments.csv: overall 1.6390, std 0.1258, 2 passes, 24 tasks, 0 missing), every flag off. About 0.5 is the official judge's swing on a six-task family mean for the same videos (AGENTS.md "Status against the timeline", "What is measured and what is a lead").

Site: benceruleanlu.github.io/playworld-advancement (results, Pairs, blind review page). Hackathon entry, November 2026.

DEMO CUT (8 slides, about two minutes), by title:
1. this title slide;
2. "One coordinating agent session ran the proposal flow, and GitHub held the state";
3. "A task is an image, a goal and actions, played out by LingBot-World v2 and scored 1 to 5";
4. "In the PlayWorld paper Genie 3 scores 2.12; our only official closed-loop dev score is 1.64 on 24 tasks";
5. "The official judge scored the same video 1.3 apart, and the seed alone changes the video";
8. "A yaw servo cut the end-heading error on turning GC tasks; it has no official judge score";
9. "A stack of six flags scored about a point higher on out-of-sight, under the proxy judge only";
11. "No 171-task run was launched, so there is no leaderboard score".
Skip in the demo: the flags and adoption rule slide, the attention cache slide, the per-flag results slide, credits.

Every number in this deck comes from AGENTS.md, README.md, results/experiments.csv, results/media/ or results/reports/ on main; the pull request counts on the coordinator slide come from the pull request record as of PR #169. Each slide's notes name the source.
-->

---

# One coordinating agent session ran the proposal flow, and GitHub held the state

<div class="grid gap-6 mt-3" style="grid-template-columns: 1fr 190px;">
<div class="dg">
<svg viewBox="0 0 640 330" width="100%" role="img" aria-label="The proposal loop: research agents open proposal pull requests, review agents check them, the coordinating session merges or closes them, dispatches experiment runs, and results are written back to GitHub and feed the next proposals." style="overflow: visible;">
<defs><marker id="ahA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="currentColor"/></marker></defs>
<g fill="none" stroke="currentColor" stroke-width="1">
<rect x="12" y="12" width="190" height="84" rx="4" opacity="0.45"/>
<rect x="8" y="8" width="190" height="84" rx="4" opacity="0.7"/>
<rect x="4" y="4" width="190" height="84" rx="4" class="opq" stroke="none"/>
<rect x="4" y="4" width="190" height="84" rx="4" fill="rgba(47,111,214,0.16)"/>
<rect x="225" y="4" width="190" height="84" rx="4"/>
<rect x="446" y="4" width="190" height="84" rx="4" fill="rgba(47,111,214,0.16)"/>
<rect x="225" y="123" width="190" height="84" rx="4" fill="rgba(47,111,214,0.38)" stroke-width="2"/>
<rect x="446" y="123" width="190" height="84" rx="4"/>
<rect x="446" y="242" width="190" height="84" rx="4"/>
<rect x="225" y="242" width="190" height="84" rx="4"/>
<rect x="4" y="242" width="190" height="84" rx="4" stroke-dasharray="5 4"/>
</g>
<g stroke="currentColor" stroke-width="1.5" fill="none" marker-end="url(#ahA)">
<path d="M196,46 H222"/>
<path d="M417,46 H443"/>
<path d="M470,90 L400,121"/>
<path d="M417,165 H443"/>
<path d="M444,284 H418"/>
<path d="M223,284 H197"/>
<path d="M99,240 V100"/>
<path d="M400,209 L470,240"/>
</g>
<g class="lbl">
<text x="99" y="34" class="h">Research agents</text>
<text x="99" y="56">coordinator subagents,</text>
<text x="99" y="74">one idea each</text>
<text x="320" y="30" class="h">Proposal pull request</text>
<text x="320" y="52" class="mono">proposal/&lt;idea&gt;</text>
<text x="320" y="72">one flag, tests, smoke plan</text>
<text x="541" y="34" class="h">Review agents</text>
<text x="541" y="56">merge, merge with fixes,</text>
<text x="541" y="74">or reject</text>
<text x="320" y="152" class="h">Coordinating</text>
<text x="320" y="172" class="h">agent session</text>
<text x="320" y="193">one session</text>
<text x="541" y="149" class="h">Merge to main</text>
<text x="541" y="171">opt-in flag, off by default,</text>
<text x="541" y="191">or close with a reason</text>
<text x="541" y="268" class="h">Experiment run</text>
<text x="541" y="290">GitHub Actions to Modal</text>
<text x="541" y="310">GPUs, arm 1 is the control</text>
<text x="320" y="268" class="h">Written back to GitHub</text>
<text x="320" y="290">results row, report,</text>
<text x="320" y="310">clips in a Release</text>
<text x="99" y="272" class="h">Findings</text>
<text x="99" y="294">AGENTS.md status,</text>
<text x="99" y="314">PR comments</text>
<text x="108" y="166" class="st">feed the next</text>
<text x="108" y="184" class="st">proposals</text>
<text x="440" y="119" class="lab">verdicts</text>
<text x="452" y="222" class="lab">dispatches</text>
</g>
</svg>
</div>
<div class="dg nums">
  <div><span class="n">150</span>pull requests in 24 hours, as of #169</div>
  <div><span class="n">36</span>proposal pull requests</div>
  <div><span class="n">33</span>proposals on main, off by default, 0 adopted</div>
  <div><span class="n">101</span>runs logged, excluding 4 pipeline tests</div>
</div>
</div>

<div class="dg sstrip">
  <span class="sk">State on GitHub</span>
  <span class="chip"><b>Decisions</b> pull requests</span>
  <span class="chip"><b>Log, reports</b> main</span>
  <span class="chip"><b>Runs</b> Actions</span>
  <span class="chip"><b>Clips</b> Releases</span>
  <span class="chip"><b>Instructions</b> <code>AGENTS.md</code></span>
  <span class="off">Off GitHub: raw rollouts, full review notes</span>
</div>

<style>
.opq { fill: var(--slidev-theme-background, #fff); }
html.dark .opq { fill: #121212; }
.lbl text { fill: currentColor; font-size: 14px; text-anchor: middle; }
.lbl text.h { font-size: 16px; font-weight: 700; }
.lbl text.mono { font-family: ui-monospace, monospace; font-size: 13px; }
.lbl text.st { text-anchor: start; }
.lbl text.lab { text-anchor: start; font-size: 13px; }
.nums { display: flex; flex-direction: column; justify-content: space-between; gap: 10px; }
.nums div { line-height: 1.25; }
.sstrip { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; margin-top: 10px; font-size: 14px; }
.sstrip .sk { font-weight: 700; margin-right: 2px; }
.sstrip .chip { border: 1px solid currentColor; border-radius: 4px; padding: 2px 8px; white-space: nowrap; }
.sstrip .chip b { font-weight: 700; color: #2f6fd6; margin-right: 3px; }
html.dark .sstrip .chip b { color: #7fa8ee; }
.sstrip .chip code { font-size: 1em; background: none; padding: 0; }
.sstrip .off { opacity: 0.8; font-style: italic; }
.nums .n { display: block; font-size: 34px; font-weight: 700; line-height: 1.05; font-variant-numeric: tabular-nums; color: #2f6fd6; }
html.dark .nums .n { color: #7fa8ee; }
</style>

<!--
This is how the proposal work was organised. It was not all of the project: the owner's own agent session ran the yaw servo study (#125, the lead on the yaw servo slide) in a separate Modal workspace and posted the replays that closed #114; #129 opens with "The project owner asked to 'fix pose memory'"; teammate Hcoder10 opened #162 (SANA-WM in the infra) and #163 (a loop-closure wrapper); jpoehnelt opened #1, #12 and #21. One coordinating agent session ran the proposal flow: it gave each proposal to review agents, folded accepted proposals into main, closed or held the rest with a written reason, dispatched the experiment and arms workflow runs, and kept AGENTS.md and issue #9 current. AGENTS.md "Settled" gives it that role: "The coordinator session launches experiment runs, merges the integration branch when CI is green ... and freezes and launches the final run." The owner gave it standing authority to dispatch.

The loop on the slide, as the pull request record shows it:
- A research agent (a subagent of the coordinating session in most cases; the 36 proposal branches carry commit trailers from only two sessions, the coordinator's and one other) writes one idea as an off-by-default runner flag with unit tests, on a proposal/<idea> branch, and opens a PR whose body is the proposal: hypothesis, how it works, how it differs from earlier work, smoke recipe, kill criterion, risks, an Unverified list, tests (template from #80). Proposals state that flag-off output is byte-identical to main and refuse flag combinations it cannot support.
- Review agents return merge, merge_with_fixes or reject. Their verdicts are recorded only in the coordinator's PR text ("Every review came back merge or merge_with_fixes", #90); they leave no GitHub reviews of their own. An automated code-review app also posted findings on proposal PRs, which the coordinator answered in comments and fix commits.
- The coordinator merged a proposal directly, or folded several into a batch PR (#63, #90, #100, #104, #112) that merges each proposal branch with --no-ff, applies the review fixes, and closes the originals with "Landed via #N". Some it held and later merged ("On hold, no GPU slot", #132 and #133, merged at 07:05 and 07:07) or closed with measured reasons (#114, #117, #126).
- Experiments are Actions runs of experiment.yml or arms.yml on Modal GPUs; arm 1 of each group is the control. The workflow writes the results row, the report and the clips back to GitHub (the strip under the diagram; full map below).
- Findings go into AGENTS.md status and PR comments, and the next proposals cite them by commit-pinned link (#147 has a "Duplicate check" against earlier PRs).

The first version was an hourly "autoresearch loop" in a fresh session, whose only memory was the ledger in issue #24. It could not dispatch GPU runs, so in its first hours its 4 ideas got 0 evaluations; AR-002 to AR-004 were later folded into the integration branch (#63), and the caption prompt and re-anchor ran in sp14-gc-v1. It was paused with a PAUSE line in #24 at 00:50 UTC Nov 15 "at the owner's direction", and the proposal PRs took over (research/autoresearch-loop.md).

Counts. 150 pull requests: #1 to #169 minus 19 issue numbers, first opened 19:22 UTC Nov 14, last (#169) opened 19:21 UTC Nov 15; 110 merged, 27 closed unmerged, 13 open. 36 proposal PRs (proposal/* branches, #75 to #147): 15 merged directly, 18 closed and landed through batch PRs #90, #100, #104 and #112, and 3 closed without landing (#114, #117, #126), so 33 reached main as off-by-default flags. 105 rows in results/experiments.csv on main: 101 real runs and 4 pipeline tests (fake_runner); the slide counts the 101. 0 adopted: AGENTS.md "Status against the timeline" ("Nothing is adopted on official scores").

Who is who. 143 of the 150 PRs were opened under one shared bot login. Session links do not tell research agents apart: most proposal PR bodies carry none, and those that do (#103, #105, #108, #119, #123) carry the coordinator's. Main's commit messages carry 24 distinct session links, 35 across all branches, both lower bounds because squash merges drop branch trailers. #125 is the owner's servo PR; #131 carried its result to main.

What the pattern cost (sources under "What it cost" below): sessions collided on the same files (#143 rewrote site/src/scripts/app.js and AGENTS.md asked others to hold site edits; #166 had to absorb #164); runs were launched before the path was checked (three sharded runs before the #62 fix; 30 pose-memory rollouts that could not fire, traced below); every merged proposal is a dark flag, and none has decision-tier evidence; review threads were answered in comments but left unresolved; status PRs piled up.

Credit for work outside this flow, as the slide line used to say: the owner's session ran the yaw servo study (#125, the yaw servo slide); teammate Hcoder10 opened #162 and #163.

STATE MAP (was a separate slide: "GitHub held most of the project's state: decisions in pull requests, the log and evidence on main, runs in Actions"). Where each kind of state lived: proposals, reviews, decisions in pull requests and their comments; plan of record and idea ledger in issues #9 and #24; instructions and status in AGENTS.md, via status PRs; experiment log in results/experiments.csv on main; per-run evidence in results/reports/ and Releases with clips; run state in Actions run titles and status commits; public view: the site reads main when viewed. Short cost list: sessions edited the same files at once; 30 rollouts ran before a flag could fire; 9 status PRs left open; one bot login for every agent. Off GitHub: raw rollouts (Modal volume, 14-day Actions artifacts); full review verdicts and agent briefs (session context).

Most project state had a place on GitHub, and sessions read it from there; the exceptions are listed after this list; the slide's strip says "Off GitHub: raw rollouts, full review notes". Sources are origin/main unless noted.

- Proposals, reviews and decisions: PR bodies, PR comment threads and closing comments ("Landed via #90 ... Closing as superseded. Unscored."; #114's closing reason). Hold notes listed fixes and a kill criterion (#132).
- Plan of record: issue #9, "the single plan" (AGENTS.md "Plan of record"). Idea ledger: issue #24, one line per idea with an AR id, hypothesis, PR and status, and the PAUSE line. Out-of-sight research threads: #48 with sub-issues #49 to #53 and #58, closed as research records.
- Instructions and status: AGENTS.md, which every agent session loads, rewritten by hourly "Docs: status at HH:MM" PRs. Longer reasoning lives in research/*.md. Shared skills (19, copied from jpoehnelt/skills under MIT) live in the repo too.
- Experiment log: results/experiments.csv on main, 105 rows, with branch, status and run_url columns. Rows from any branch land on main through .github/scripts/push_results.sh, which stages only results/, so branch code never reaches main.
- Per-run evidence: 83 files in results/reports/ (74 official, 9 screening), 73 Releases named run-EXP with 480p clips, and 73 scenes manifests in results/media/.
- Run state: the Actions run title carries the experiment, runner, tasks and action source, because GitHub does not show a running job's inputs (AGENTS.md "Remote runs"). Status markers are commits to main: as of #169, 340 of the 456 commits on main start "results:", 339 of them authored by github-actions[bot].
- Public view: the site fetches results/experiments.csv and results/media/ from main at view time (site/src/scripts/app.js), so a new row shows up without a redeploy.

Not everything is on GitHub: raw rollouts sit in the Modal volume pwa-runs and in Actions artifacts, which expire after 14 days; the review agents' full verdicts, the research agents' briefs and the owner's standing dispatch authority lived in session context and chat; the owner's servo study ran in a separate Modal workspace; secrets live in config/env.sh and repo secrets.

What it cost, with sources:
- Collisions: #143 rewrote much of site/src/scripts/app.js while others held site edits; #166 had to merge main and move #164's review link; #167 avoided app.js to stay clear of #166; batch PRs #90 and #112 resolved conflicts with parallel PRs.
- Unverified launches: pose memory (#123) ran in pm14-fx-v1 and v2, and all 30 pose-memory rollouts had 0 retrievals before #129 fixed it (trace below). Three sharded runs were launched before the #62 fix.
- Status PRs: 9 "Docs: status" PRs are open and unmerged (#149, #152 to #155, #158, #161, #167, #169); each new one says it replaces the earlier ones.
- One login: 143 of 150 PRs were opened under the same bot account, so authorship is visible only through session links, and #90 lists #81 to #85 with no session link.
- Also: none of the 33 proposals that reached main has decision-tier evidence for its flag, and issue #9 was not updated when the plan switched to fixed-action A/Bs (AGENTS.md).

POSE MEMORY TRACE (was a separate slide: "Pose memory went from proposal to dropped in 12 hours, and every step is a pull request or a run row"). Timeline, UTC Nov 15, run times are launches: 04:32 #123 merged (proposal: pose-indexed memory, off by default); 04:33 pm14-fx-v1, v2 (30 rollouts, 0 retrievals; 3 arms match control); 05:34 #129 merged (CPU replay finds the cause; new rule); 05:35 pm14-fx-v3 (arms with the fix; memory fires); 05:46 #134 closed (covered by #129; re-file one knob); 07:01 #144 merged (the re-filed knob); 16:27 #157 merged (dropped: +0.20 against a 0.34 bar). The last gap is 9 hours. pm14-fx-v3's +0.20 is from the proxy judge only.

One proposal traced end to end, every step with a PR number or a run row.

- 04:32 UTC: #123 merged, pose-indexed memory that re-inserts past views into the attention sink, behind --lingbot-pose-memory, off by default.
- 04:32 and 04:33: arms runs pm14-fx-v1 (run 43677202111) and pm14-fx-v2 (run 43677269975) launched (status commits on main; their rows were written about 04:55 and 05:01), 14B, fixed dataset actions, tasks GC031, GC033, GC036, OE039, OE047, OE048. Every task printed pose_mem=on, but all 30 pose-memory rollouts ended with pose_mem_retrievals=0, and three arms (v1-a2, v2-a1, v2-a2) were byte-identical to the control v1-a1; v2-a3 (yaw gain 0.85) and v2-a4 (cache size) differed only because they change the model's inputs or cache (#129 body; AGENTS.md says only the cache-size and yaw-gain arms differed).
- 05:34: #129 merged. The cause was reproduced on CPU with pwa.pose_mem_plan: a shadow rule blocked every smooth turn, the opening chunks were never candidates, and the leave threshold was out of reach. The new coverage rule gives 1 to 6 planned retrievals per task. A review-fix second commit landed in the same PR.
- 05:35: pm14-fx-v3 arms launched one minute after #129 merged ("results: pm14-fx-v3 arms running" on main): control, pose memory, and pose memory with yaw scale 1.19. Memory fired: retrievals 3, 3, 6, 1, 3, 3 on the six tasks (AGENTS.md). Its score-only runs failed at 06:14 and were relaunched; the rows were last written at 07:41.
- 05:46: #134 closed. Its close comment says #129 covers the bug and asks for only the rel mode to be re-filed as a small PR from main once a #129 arm shows retrievals above 0.
- 07:01: #144 merged, the re-filed proposal (proposal/pose-mem-rel), filed "after pm14-fx-v3 verified the #129 default arm" and citing the #134 comment.
- 16:27: #157 merged; it records pose memory as dropped on the site and in the findings: under the proxy judge pm14-fx-v3 scored +0.20, against a bar of 0.34, and showed no geometric gain.

The same pattern ran without a GPU run where measurements already answered the question: #114 was closed after the owner's session posted fixed-script replays in its thread (left turns rendered 1.19 to 1.30 times right turns, no transient after a reversal), pointing to #119's per-direction yaw gain.

The 30 rollouts before the fix are also the "Unverified launches" cost listed above: the flag was launched on GPUs before a CPU replay checked that it could fire.
-->

---

# A task is an image, a goal and actions, played out by LingBot-World v2 and scored 1 to 5

<div class="dg mt-3">
<div class="flex items-stretch gap-1">
  <div class="box flex-1"><b>Task</b>image, goal, actions</div>
  <div class="arr">→</div>
  <div class="box flex-1 fill"><b>Runner</b>LingBot-World v2, flags</div>
  <div class="arr">→</div>
  <div class="box flex-1"><b>Clip</b>up to about 70 s</div>
  <div class="arr">→</div>
  <div class="box flex-1 fill2"><b>Judge</b>1 to 5 per task</div>
  <div class="arr">→</div>
  <div class="box flex-1"><b>Report</b>results row, site</div>
</div>
<div class="mt-4">
<ClipRow :items="[
  { exp: 'lb14-session-agent-dev-v1', task: 'GC033', head: 'Geometry consistency', sub: 'Watch: is the room the same when the camera comes back?' },
  { exp: 'lb14-session-agent-dev-v1', task: 'IF002', head: 'Interaction fidelity', sub: 'Watch: does the subject do what each key asks?' },
  { exp: 'lb14-session-agent-dev-v1', task: 'OE001', head: 'Insight evolution', sub: 'Watch: does the process on screen keep going?' },
  { exp: 'lb14-session-agent-dev-v1', task: 'OE039', head: 'Out-of-sight evolution', sub: 'Watch: what changed while it was out of view?' },
]" />
</div>
</div>

<div class="text-sm mt-3">

35 of 101 logged runs had an AI player (closed loop). The rest replayed fixed actions, for A/B tests only.

</div>

<!--
The boxes are the path one task takes; the clips are one control task per family from lb14-session-agent-dev-v1 (closed loop, no flags; CC BY-NC-SA 4.0, generated with LingBot-World v2). Clip list: results/media/lb14-session-agent-dev-v1.json. Clips load from GitHub Releases (run-lb14-session-agent-dev-v1) and do not autoplay. The watch cues are the family questions (site/src/scripts/families.js), not descriptions of what these clips show.

Benchmark: PlayWorld (Ding et al.), 171 tasks: GC 48, IF 50, insight 30, out-of-sight 43. Splits: dev and dev2, 24 each with 6 per family; heldout 123, unscored. A task with a gate (for example, return to the start view) scores 1.0 if the gate fails. Insight and out-of-sight task IDs both start with OE; the family is in the task JSON.

Model: LingBot-World v2 (Robbyant Team). 9 of the 101 logged runs used the 1.3B; the rest used the 14B (results/experiments.csv). The model weights are not changed. Our use is not "unmodified": adapters/lingbot_world2/session.py re-implements LingBot's sampling loop as a persistent session that keeps the attention cache between the player's steps (AGENTS.md "Scenes and attribution").

Clip length: a closed-loop clip is up to 30 chunks, about 60 s ("Run speed"). Fixed-action clips follow the dataset's action length, up to 280 latents (1117 frames, about 70 s at 16 fps) on wait-only insight tasks (AGENTS.md "Long steps").

Judge: the official judge (Gemini 3.1 Pro) at upstream settings, 2 or 4 passes. 45 of the 101 runs have an official overall score (42 with status scored, plus 3 rows from before the status column: lb14-session-agent-dev-v1, lb13-stateless-gc005-v1 and lb14-session-agent-gc005-v1); 34 were generated but never scored officially, and later ones have proxy judge scores only, which are not comparable to the paper. When official scoring stopped is on the slide "No 171-task run was launched, so there is no leaderboard score".

Compute: one H100 per shard on Modal, launched from GitHub Actions (experiment and arms workflows). On lb14-session-agent-dev-v1, 142 min wall clock or about 18 min per task on an 8-task shard, including GPU queueing ("Run speed").

Actions. results/experiments.csv on main has 105 rows; 4 are fake_runner pipeline tests. Of the other 101, action_source is dataset on 62 and agent on 39. Four of the 39 are the sp14-gc-v1 arms, the scripted player (#102), which replays a fixed plan with no AI player, so 35 had an AI player. Status of the 101: 42 scored, 34 generated, 15 cancelled, 7 failed, 3 predate the status column.
-->

---

# In the PlayWorld paper Genie 3 scores 2.12; our only official closed-loop dev score is 1.64 on 24 tasks

<div class="dg mt-4" style="font-size: 15px;">
<div class="pchart">
  <div class="prow"><div class="pname">Genie 3</div><div class="ptrack"><span class="pdot" style="left: 74.7%"></span><span class="pval" style="left: 74.7%">2.12</span></div></div>
  <div class="prow"><div class="pname">LingBot-World v2, paper's web demo</div><div class="ptrack"><span class="pdot" style="left: 54.7%"></span><span class="pval" style="left: 54.7%">1.82</span></div></div>
  <div class="prow"><div class="pname">SANA-WM</div><div class="ptrack"><span class="pdot" style="left: 32%"></span><span class="pval" style="left: 32%">1.48</span></div></div>
  <div class="prow"><div class="pname">Matrix-Game 3.0</div><div class="ptrack"><span class="pdot" style="left: 9.3%"></span><span class="pval" style="left: 9.3%">1.14</span></div></div>
  <div class="paxis"><span style="left: 0%">1.0</span><span style="left: 33.3%">1.5</span><span style="left: 66.7%">2.0</span><span style="left: 100%">2.5</span></div>
  <div class="small muted" style="margin-left: 270px; margin-top: 4px;">Paper overall score, all 171 tasks (1 to 5)</div>
</div>
<div class="box dash mt-5" style="text-align: left; max-width: 700px;"><b style="display:inline">Ours, not on this axis:</b> 1.64 ± 0.13 on 24 dev tasks, closed loop, official judge. Not comparable.</div>
</div>

<div class="text-sm mt-4">

The 1.82 is the paper's run through LingBot's web demo, not our code.

</div>

<style>
.pchart { position: relative; }
.prow { display: grid; grid-template-columns: 270px 1fr; align-items: center; height: 38px; }
.pname { text-align: right; padding-right: 16px; }
.ptrack { position: relative; height: 100%; border-left: 1px solid currentColor; margin-right: 40px; }
.ptrack::before { content: ''; position: absolute; left: 0; right: 0; top: 50%; border-top: 1px dotted currentColor; opacity: 0.35; }
.pdot { position: absolute; top: 50%; width: 16px; height: 16px; border-radius: 50%; background: #8b8b8b; transform: translate(-50%, -50%); }
.pdot.hi { background: #2f6fd6; }
.pval { position: absolute; top: 50%; transform: translate(14px, -50%); font-variant-numeric: tabular-nums; font-weight: 600; }
.paxis { position: relative; margin-left: 270px; margin-right: 40px; height: 22px; border-top: 1px solid currentColor; }
.paxis span { position: absolute; top: 2px; transform: translateX(-50%); font-size: 14px; }
</style>

<!--
Reference scores: the PlayWorld paper (Ding et al., arXiv:2608.13552) on all 171 tasks, copied in AGENTS.md "Reference scores". Full table, GC, IF, insight, out-of-sight, overall:
Genie 3: 2.74, 2.40, 1.51, 1.81, 2.12.
LingBot-World v2 (web demo): 2.04, 2.13, 1.95, 1.16, 1.82.
SANA-WM: 1.72, 1.89, 1.13, 1.16, 1.48.
Matrix-Game 3.0: 1.30, 1.25, 1.00, 1.00, 1.14.

LingBot-World v2 is the open model we ran, but the paper scored it through its web demo, not through the released code we run.

Ours: LingBot-World v2 14B, no flags, closed loop, official judge, 2 passes; by family GC 1.83, IF 1.81, insight 1.58, out-of-sight 1.33. Source: results/experiments.csv row lb14-session-agent-dev-v1 (GC 1.8333, IF 1.8058, insight 1.5833, out-of-sight 1.3333, overall 1.6390, std 0.1258, 2 passes, 24 tasks, 0 missing) and AGENTS.md "Status against the timeline" ("Best official closed-loop score is unchanged"). It is the only closed-loop dev run scored by the official judge on all 24 tasks; other officially scored rows are fixed-action arms or six-task subsets. The AI player was gpt-4.1-mini, which the plan treats as a diagnostic baseline ("Settled" fixes gpt-6-luna for compared runs), so this is not the plan's starting-model number. 24 of 171 tasks: not comparable to the paper.

The heldout 123 tasks are unscored, as the repo rules require until code freeze.
-->

---

# The official judge scored the same video 1.3 apart, and the seed alone changes the video

<div class="dg grid gap-8 mt-4" style="grid-template-columns: 1fr 380px;">
<div>
  <b style="font-size:16px">One clip, GC036, byte-identical video</b>
  <div class="small muted">official judge (Gemini 3.1 Pro), task score</div>
  <div class="strip mt-8">
    <span class="sdot fail" style="left: 8.75%"></span><span class="slab" style="left: 8.75%">1.35<br>gate failed</span>
    <span class="sdot" style="left: 41.25%"></span><span class="slab" style="left: 41.25%">2.65<br>gate passed</span>
    <span class="sspan" style="left: 8.75%; width: 32.5%"></span><span class="sspanlab" style="left: 25%">1.3 apart</span>
  </div>
  <div class="saxis"><span style="left:0%">1</span><span style="left:25%">2</span><span style="left:50%">3</span><span style="left:75%">4</span><span style="left:100%">5</span></div>
  <div class="box fill mt-6" style="text-align:left"><b>Six-task family mean</b>moves about 0.5 on the same videos, so smaller differences are not visible</div>
</div>
<div>
  <b style="font-size:16px">IF002, same flags and actions</b>
  <div class="small muted mb-2">Watch: same task, seed alone changes the video</div>
  <ClipPair task="IF002" control="stk14-fx-dev-v1-a1" treatment="stk14-fx-dev-v1-a3" controlLabel="Seed 0" treatmentLabel="Seed 1" :width="180" />
</div>
</div>

<div class="cap">Seed pair: control arms of the stack run, fixed actions, not scored by the official judge. CC BY-NC-SA 4.0, generated with LingBot-World v2.</div>

<style>
.strip { position: relative; height: 96px; border-bottom: 1px solid currentColor; margin-right: 20px; margin-left: 20px; }
.saxis { position: relative; height: 22px; margin: 0 20px; font-size: 14px; }
.saxis span { position: absolute; top: 2px; transform: translateX(-50%); }
.sdot { position: absolute; bottom: 10px; width: 16px; height: 16px; border-radius: 50%; background: #2f6fd6; transform: translateX(-50%); }
.sdot.fail { background: #8b8b8b; }
.slab { position: absolute; bottom: 32px; transform: translateX(-50%); text-align: center; font-size: 14px; white-space: nowrap; }
.sspan { position: absolute; top: 18px; height: 8px; border: 1px solid currentColor; border-bottom: none; }
.sspanlab { position: absolute; top: 0; transform: translateX(-50%); font-size: 14px; font-weight: 600; white-space: nowrap; }
</style>

<!--
This is the central finding. Sources: AGENTS.md "Status against the timeline": the "What is measured and what is a lead" bullet, the "Same config scored three times" bullet and the proxy judge bullet.

Left: GC036 comes from pm14-fx-v1 arms 1 and 2, which were checked byte-identical. The official judge gave 2.65 when it passed the gate and 1.35 when it failed it. A six-task family mean moves about 0.5 on the same videos. Generation is deterministic (the same config gives a byte-identical video, AGENTS.md), so these spreads come from the judge.

Proxy judge (openai:gpt-6-luna): on byte-identical clips, per-task scores moved 0.50 on average and a five-task mean moved 0.62. It lets 97% of gated passes through, where the official judge failed a gate on 23% of tasks. Rank correlation with the official judge: 0.62 on 21 clips (0.41 on out-of-sight). Proxy scores are not reported numbers and are not comparable to the leaderboard.

The practical bar: about 0.5 for a six-task family mean under the official judge, about 0.6 under the proxy judge.

Right: both clips are the no-flag control arms of stk14-fx-dev-v1: arm 1 at the default seed 0, arm 3 with --seed 1, the same runner arguments otherwise (results/experiments.csv notes). Both replay the dataset's actions. Nothing but the seed differs. The size of the difference was not measured; the pair only shows that it exists, which is why the adoption rule asks for a gain that repeats on both seeds (the next slide). stk14-fx-dev-v1 was generated after the official judge's credits ran out and has proxy judge scores only. The pair is also in the site's Pairs section.
-->

---

# Each change is an opt-in flag on the model or the AI player; none met the adoption rule, so none is adopted

<div class="dg mt-4">
<div class="grid items-center gap-x-2 gap-y-3" style="grid-template-columns: 1.1fr 24px 1fr 24px 0.9fr 24px 1fr;">
  <div class="box" style="grid-row: span 2;"><b>Same inputs</b>same task image<br>same seed<br>same actions</div>
  <div class="arr" style="grid-row: span 2;">⇉</div>
  <div class="box"><b>Control</b>flags off</div>
  <div class="arr" style="grid-row: span 2;">⇉</div>
  <div class="box fill2" style="grid-row: span 2;"><b>Judge</b>same judge<br>2 or 4 passes</div>
  <div class="arr" style="grid-row: span 2;">→</div>
  <div class="box" style="grid-row: span 2;"><b>One comparison</b>treatment minus control,<br>per task and family</div>
  <div class="box fill"><b>Treatment</b>flags differ (one, or a stack)</div>
</div>
<div class="small muted mt-5">Adoption rule</div>
<div class="grid grid-cols-3 gap-3 mt-1">
  <div class="box dash"><b>A task moves a full point</b>no gate lost</div>
  <div class="box dash"><b>The gain repeats</b>on two seeds</div>
  <div class="box dash"><b>Decision tier</b>closed loop, 14B, full length, official judge</div>
</div>
</div>

<div class="text-sm mt-5">

More than 30 flags are on main, all off by default. No run reached the decision tier.

</div>

<!--
Flags, grouped by the first plan's workstreams:
- Insight: caption prompt, insight director, conditioning schedule.
- Control and gates: turn calibration, yaw gain, yaw servo, re-anchor, IF slow translation, IF fixed camera.
- Player prompts: return stop, player hint. Out-of-sight memory: sink size, attention window, sink key scale, pose memory.

Flag count: AGENTS.md "Status against the timeline" recorded 28 method flags at 22:25 ("Main now carries 28 method flags"), and #115, #116, #121, #132, #133, #139, #144 and #147 each added at least one more since; all are merged and unscored. None has decision-tier evidence.

The rule: AGENTS.md "Rules" and "Testing tiers and the adoption rule". Decision tier: closed loop, 14B, full length, all 6 dev tasks of a family, 2 seeds, official judge. Adoption: a task moves a full point, the gain repeats on both seeds, no gate is lost. A delta smaller than twice the pass spread is noise (pwa compare).

Practice, not a written rule: since about 18:35 model-side flags were compared with the same actions in both arms (dataset or scripted player). Most arm groups ran one seed. AGENTS.md calls these runs a change from the plan as written: they are open loop and cannot meet the decision tier. Some servo groups borrow controls from other groups. The stack differs from its control by six flags, not one.
-->

---

# The model keeps the opening view and the last 2 seconds; everything in between is dropped

<div class="dg mt-8">
<div class="flex gap-1 text-center items-stretch" style="height: 96px">
  <div class="box fill2 flex flex-col justify-center" style="flex: 6"><b>Opening view</b>kept for the whole clip</div>
  <div class="box dash flex flex-col justify-center" style="flex: 5"><b>Middle</b>dropped</div>
  <div class="box fill flex flex-col justify-center" style="flex: 8"><b>Last ~2 s</b>kept</div>
  <div class="box grey flex flex-col justify-center" style="flex: 4"><b>Next chunk</b>being made</div>
</div>
<div class="taxis">
  <span style="left: 0%">start</span>
  <span class="brk" style="left: 37.5%">not to scale</span>
  <span style="left: 82.6%">now</span>
</div>
<div class="grid grid-cols-2 gap-3 mt-6">
  <div class="box"><b>Return to the opening view</b>it is still in memory</div>
  <div class="box dash"><b>Return to any other view</b>seen over ~2 s ago: gone</div>
</div>
</div>

<div class="text-sm mt-5">

This is the configuration, not a measurement. The GPU probe that would measure it is unmerged (#37).

</div>

<style>
.taxis { position: relative; height: 28px; border-top: 1px solid currentColor; margin-top: 4px; font-size: 14px; }
.taxis span { position: absolute; top: 4px; transform: translateX(-50%); white-space: nowrap; }
.taxis span:first-child { transform: none; }
.taxis .brk { opacity: 0.7; font-style: italic; }
</style>

<!--
Out-of-sight tasks ask the model to show the scene correctly after the camera leaves it and comes back. With this cache, anything seen more than about two seconds ago, other than the opening view, has to be regenerated from nothing.

Detail behind the plain words: LingBot's attention (KV) cache is 18 latents including a 6-latent "sink" that holds the opening frames and is never evicted, so only 8 latents (2 chunks, about 2 s) of recent past are attended; a view seen earlier is gone by the time the camera comes back, and the start view stays in the sink. Source: AGENTS.md "Adapters", the pose memory bullet, and "Status against the timeline" ("The cache's reach (opening view plus about 2 s) is its configuration, not a measurement; the GPU probe is unmerged (#37)"). The loader sets local_attn_size and sink_size (adapters/lingbot_world2/run.py). Block widths are not to scale.

"It is still in memory" means the start view's frames are attended, not that the model uses them well; that has not been measured.

Two flags change this window: keep-first 10 (sink 10) and attention window 22. Both are part of the stack on the slide "A stack of six flags scored about a point higher on out-of-sight, under the proxy judge only".
-->

---

# A yaw servo cut the end-heading error on turning GC tasks; it has no official judge score

<div class="grid gap-6 mt-2" style="grid-template-columns: 1fr 400px;">
<div class="dg">
<HeadingChart />
</div>
<div class="dg">
  <b style="font-size:15px">GC036: control vs yaw servo</b>
  <div class="small muted mb-2">Watch the last second: the servo clip ends back at the start heading</div>
  <ClipPair task="GC036" control="svgc14-fx-v1-a1" treatment="svgc14-fx-v1-a2" controlLabel="Control" treatmentLabel="Yaw servo" :width="190" />
</div>
</div>

<div class="text-sm mt-3">

Each chunk it measures the rendered turn and corrects the next command. Chart runs: fixed actions, no official judge score.

</div>

<!--
The loop: rendered turns differ from commanded turns (rendered over commanded, 8 static first-person scenes, one seed: 0.88 to 1.99 left, 0.56 to 1.44 right; PR #125 and the camera-response study bullet in AGENTS.md), so the servo measures the rendered rotation of each chunk by phase correlation and corrects the next command. Design, code and GPU trials by benceruleanlu in PR #125, merged in #131.

Source for the chart: AGENTS.md "Status against the timeline", the yaw servo bullet under the proxy judge findings. End-heading error in degrees, control to servo: GC033 28 to 0.3, GC036 70 to 5.6, GC031 96 to 0, GC012 8 to 2, GC022 45 to 1 (from the stack run, not the servo-only group), GC038 96 to 49.

Which tasks have an independent check: heading is read with phase correlation, the same estimator the servo steers with. The independent check, the last frame's similarity to frame 0, exists for GC033 (control -0.09, servo 0.52) and GC036 (control 0.07, servo 0.63) only. The other four are the servo's own estimate.

The GC036 pair: svgc14-fx-v1 arm 1 (control) and arm 2 (yaw servo), fixed actions, so the only difference is the servo (results/media/svgc14-fx-v1-a1.json and -a2.json). The GC033 pair is in the site's Pairs section. svgc14-fx-v1 is missing some clips (GC035 in all arms; GC002 and GC022 in the servo arms).

The chart's runs replay fixed actions. Other servo runs: sv14-fx-v1 and sv14-fx-v2 ran at seeds 0 and 1 (generation only), and clstk14-dev-v1-a2 ran the servo with the stack in closed loop (8 of 24 tasks before the GPU workspace was disabled). No official judge score exists for any servo clip; under the proxy judge the same-run servo deltas are noise (-0.10 fixed actions, 6 turning tasks; +0.05 closed loop, 4 turning tasks). Walking-only GC tasks give byte-identical clips with and without the servo. The servo does not support out-of-sight tasks.
-->

---

# A stack of six flags scored about a point higher on out-of-sight, under the proxy judge only; other families were mixed

<div class="grid gap-6 mt-2" style="grid-template-columns: 1fr 440px;">
<div class="dg">
  <b style="font-size:15px">Out-of-sight, stack minus control</b>
  <div class="small muted">proxy judge, six tasks per pair</div>
  <div class="dbars mt-3">
    <div class="dline" style="left: 50%"><span>proxy noise bar 0.6</span></div>
    <div class="drow"><span class="dl">dev, seed 0</span><span class="db" style="width: 85%"></span><span class="dv" style="left: 85%">+1.02</span></div>
    <div class="drow"><span class="dl">dev, seed 1</span><span class="db" style="width: 76.7%"></span><span class="dv" style="left: 76.7%">+0.92</span></div>
    <div class="drow"><span class="dl">dev2, other tasks</span><span class="db" style="width: 81.7%"></span><span class="dv" style="left: 81.7%">+0.98</span></div>
  </div>
  <div class="daxis"><span style="left:0%">0</span><span style="left:25%">0.3</span><span style="left:50%">0.6</span><span style="left:75%">0.9</span><span style="left:100%">1.2</span></div>
  <div class="small mt-4">Stack: turn calibration, caption prompt, insight director, IF slow translation, sink 10, window 22</div>
</div>
<div class="dg flex flex-col gap-1">
  <div class="small muted">Watch: what the hidden part looks like on return. Clips not scored by the official judge.</div>
  <ClipPair task="OE039" control="stk14-fx-dev-v1-a1" treatment="stk14-fx-dev-v1-a2" controlLabel="Control" treatmentLabel="Stack" :width="200" />
  <ClipPair task="OE047" control="stk14-fx-dev-v1-a1" treatment="stk14-fx-dev-v1-a2" controlLabel="Control" treatmentLabel="Stack" :width="200" />
</div>
</div>

<div class="cap">Fixed actions, seed 0. CC BY-NC-SA 4.0, generated with LingBot-World v2.</div>

<style>
.dbars { position: relative; padding-top: 22px; margin-left: 130px; margin-right: 52px; }
.dline { position: absolute; top: 0; bottom: 0; border-left: 2px dashed currentColor; opacity: 0.8; }
.dline span { position: absolute; top: 0; left: 4px; font-size: 13px; white-space: nowrap; }
.drow { height: 30px; position: relative; border-left: 1px solid currentColor; }
.dl { position: absolute; right: 100%; padding-right: 8px; top: 50%; transform: translateY(-50%); font-size: 14px; white-space: nowrap; }
.drow .db { position: absolute; left: 0; top: 7px; height: 16px; background: #2f6fd6; }
.dv { position: absolute; top: 50%; transform: translate(6px, -50%); font-size: 14px; font-variant-numeric: tabular-nums; }
.daxis { position: relative; height: 22px; margin-left: 130px; margin-right: 52px; border-top: 1px solid currentColor; font-size: 13px; font-variant-numeric: tabular-nums; }
.daxis span { position: absolute; top: 6px; transform: translateX(-50%); }
.daxis span::before { content: ''; position: absolute; left: 50%; top: -6px; height: 5px; border-left: 1px solid currentColor; }
</style>

<!--
This is a lead from small samples, not a result. Source: AGENTS.md "Status against the timeline", the stack bullet under "Proxy judge findings"; the deltas are in that prose, not in results/experiments.csv (the stk14 rows carry no official score). The three pairs: stk14-fx-dev-v1 at seeds 0 and 1 (4 passes) and stk14-fx-dev2-v1 (2 passes). dev2 is a different set of 24 tasks, not a third seed.

Stack: turn calibration, caption prompt, insight director, IF slow translation, sink 10 (keep the first 10 latents, up from 6) and window 22 (up from 18). Against the control, fixed actions, six out-of-sight tasks per pair, proxy judge: +1.02, +0.92, +0.98. Out-of-sight is the only family above the proxy judge's 0.6 identical-clip bar in all three pairs.

Other families were mixed across the three pairs: GC +0.59, -0.16, +0.30; IF +0.40, -0.25, +0.45; insight +0.48, +0.58, +0.63; overall +0.62, +0.27, +0.59.

The proxy judge agrees weakly with the official judge on out-of-sight (rank correlation 0.41) and almost never fails a gate, so this may not hold under the official judge. None of the six parts passed the adoption rule alone, so a gain would not say which part caused it.

Clips: OE039 and OE047 at seed 0, results/media/stk14-fx-dev-v1-a1.json and -a2.json, marked not scored there. LingBot-World v2 14B.
-->

---

# No flag's gain has repeated cleanly; the largest single moves were mixed on a second look

<div class="dg grid grid-cols-4 gap-3 mt-6 tiers">
  <div class="box fill2"><b>Measured</b><div class="m">Yaw servo: end heading</div></div>
  <div class="box fill"><b>Lead, small sample</b><div class="m">Stack: out-of-sight about +1 (proxy judge), 2 seeds + dev2</div></div>
  <div class="box"><b>Mixed</b><div class="m">Turn calibration on GC031: +1.95, then +0.35</div><div class="m">Sink 10 + window 22, OE039: +2.44 at seed 1; seed 0 mixed</div><div class="m">Caption prompt: 2 tasks up, 2 down</div></div>
  <div class="box dash"><b>Dropped</b><div class="m">Sink key scale: −0.46 to −0.85</div><div class="m">Conditioning schedule: insight 3.00 → 1.50</div><div class="m">Pose memory: +0.20 (proxy), bar 0.34</div></div>
</div>

<div class="text-sm mt-6">

Official judge and one seed unless marked. Each comparison covers 15 tasks or fewer.

</div>

<style>
.tiers .box { text-align: left; display: flex; flex-direction: column; gap: 6px; }
.tiers .m { font-size: 14px; border-top: 1px solid rgba(128,128,128,0.4); padding-top: 5px; }
</style>

<!--
Sources: AGENTS.md "Status against the timeline": the yaw servo and stack bullets under the proxy judge findings, the sks14-fx-v1, dec14-ins-v1, win14-fx-v1 and pose memory bullets, and "What the fixed-action results say so far"; results/experiments.csv for the sink key scale rows.

Measured: the yaw servo's end heading, geometry with no official judge score (the slide "A yaw servo cut the end-heading error on turning GC tasks; it has no official judge score").

Lead: the stack, about +1 on out-of-sight under the proxy judge (the stack slide).

Mixed: turn calibration, the same comparison run twice on GC031, gave +1.95 and then +0.35 (the +0.35 is from fx14-model-dev-v2); generation is deterministic, so that spread is a config difference or judge spread. Sink 10 with window 22 (two flags) raised OE039 from 1.00 to 3.44 (+2.44) at seed 1 (win14-fx-v1). At seed 0 the same flags gave OE039 1.75 in win14-fx-v1, inside the 1.25 to 2.00 of the plain controls, but 3.12 in pm14-fx-v2-a4 (same flags, earlier commit); whether those two clips are the same video is not checked, so seed 0 is mixed. Caption prompt: 2 tasks up and 2 down by a full point, fx14-model-dev-v2 arm 2 to 3.

Dropped: sink key scale lowered out-of-sight (sks14-fx-v1, official judge, one seed, 6 tasks): control 2.10, arms 1.65, 1.33 and 1.25, so -0.46, -0.77 and -0.85 (CSV: 2.1042, 1.6458, 1.3333, 1.2500). The conditioning schedule halved insight, 3.00 to 1.50, on the two tasks it ran, OE001 and OE018 (dec14-ins-v1). Pose memory retrieves as planned after #129 with no geometric gain, +0.20 under the proxy judge against a bar of 0.34. These drops rest on one seed and six tasks or fewer, the same caution as the stack lead in the other direction.

Sample sizes: the sink key scale group is 6 tasks; mem14-fx-v1 and win14-fx-v1 are 9; dec14-ins-v1 is 2; the caption prompt comparison is 14 tasks and fx14-model-dev-v2 scored 15 tasks in both turn calibration arms; the turn calibration figure is one task, GC031. Nothing is adopted (the flags slide).
-->

---

# No 171-task run was launched, so there is no leaderboard score

<div class="dg mt-6">
<div class="tl">
  <div class="tlband" style="left: 51.9%; right: 0;"><span>proxy judge scores only</span></div>
  <div class="tlev" style="left: 32.6%"><b>03:55</b>official judge credits out<br>(topped up by 04:27)</div>
  <div class="tlev" style="left: 51.9%"><b>06:14</b>out for good</div>
  <div class="tlev" style="left: 75.1%"><b>09:01</b>GPU workspace disabled<br>during a closed-loop run</div>
  <div class="tlaxis"><span style="left:0%">00:00</span><span style="left:25%">03:00</span><span style="left:50%">06:00</span><span style="left:75%">09:00</span><span style="left:100%">12:00 UTC</span></div>
</div>
<div class="small muted" style="margin-top: 30px;">Nov 15, UTC. Before this, the 171-task control run waited on an AI player check that never completed (issue #9).</div>
<div class="grid grid-cols-3 gap-3 mt-5">
  <div class="box"><b>Results site</b>benceruleanlu.github.io/<br>playworld-advancement<br><span class="muted">runs, scores, Pairs;<br>73 of 101 runs have clips</span></div>
  <div class="box"><b>Blind review</b>…/playworld-advancement/review/<br><span class="muted">hides the arms until you finish</span></div>
  <div class="box"><b>Repo</b>github.com/benceruleanlu/<br>playworld-advancement<br><span class="muted">code, results log, reports</span></div>
</div>
</div>

<style>
.tl { position: relative; height: 104px; margin: 0 30px; }
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
What stopped a full run, from AGENTS.md "Status against the timeline" and "Plan of record". The plan put the starting-model 171-task run "After the player check", a 14B gpt-6-luna player check on the GC and out-of-sight dev tasks. AGENTS.md: "The starting-model 171 run has not been launched. It was waiting on a 14B gpt-6-luna player check, and the first-wave runs for that check (lb14-luna-gc-s42, lb14-luna-oos-s42, lb14-cap-ins-s42, cand1-smoke-gc-v1) ended in Modal generation with a bare RemoteError or incomplete rollouts; the cause was never identified (issue #9)." The plan table marks the player check "Not done". So the run was never started; the judge credit and GPU events on the timeline came after that and removed the means to run or score it later.

Timeline: the official judge's AI Studio prepaid credits ran out about 03:55 UTC Nov 15 (402 RESOURCE_EXHAUSTED), were topped up (scoring worked 04:27 to 05:43), and ran out for good about 06:14 UTC. Later runs have proxy judge scores only. Scoring through Google Cloud is wired (#148) but no live call has been made. At 09:01 UTC the GPU provider workspace was disabled during clstk14-dev-v1 (closed loop, 24 dev tasks: control | stack + servo | stack + servo without IF slow translation): control 23 of 24 tasks, stack + servo 8 of 24, third arm never started. No closed-loop comparison of stack plus servo exists.

What a trusted score needs (estimate): control and method each on all 171 tasks, closed loop, official judge, 2 or more passes. Scaling the 0.5 six-task spread by the square root of 6/171 gives noise of about 0.1 on the overall mean (an estimate, not a measurement). Generation for one 171-task arm on 8 GPUs: about 3.8 h without queueing, about 6.9 h at the dev baseline's queued 18 minutes per task, over the 350-minute job cap ("Run speed").

Where to look. Results site: benceruleanlu.github.io/playworld-advancement, with every logged run, its scores and a Pairs section that plays control and treatment side by side. Clips: github.com/benceruleanlu/playworld-advancement/releases/download/run-<EXP>/<TASK>.mp4, 480p with a .jpg poster. results/media/index.json lists 73 runs with published clips, all among the 101 real runs in results/experiments.csv; the other 28 have none: 15 cancelled, 7 failed, 4 capped smoke runs that ended generated (none of them scored), and 2 one-task scored runs from before the status column (lb13-stateless-gc005-v1, lb14-session-agent-gc005-v1). Per-run reports with the judge's reasons are in results/reports/ (83 files; not every run has one).

Blind review page: benceruleanlu.github.io/playworld-advancement/review/. It hides which clip is control and which is treatment until you finish; it records a preference by eye, not a score. Clips load from release URLs that name the run, so blinding holds only if reviewers do not open developer tools.

Pairs in this deck: GC033, IF002, OE001 and OE039 in lb14-session-agent-dev-v1 (the task slide); IF002 seed 0 against seed 1 in stk14-fx-dev-v1 a1 against a3 (the judge noise slide); GC036 in svgc14-fx-v1 a1 against a2 (the yaw servo slide); OE039 and OE047 in stk14-fx-dev-v1 a1 against a2 (the stack slide).
-->

---

# Credits and licences

<div class="mt-4 credits">

| | |
|---|---|
| **PlayWorld** | Benchmark, harness, verifier, task data: Ding et al., arXiv:2608.13552. Code kxding/PlayWorld (no licence; pinned submodule, not copied). Data jocelynd/playworld-bench. Task images from Pexels and web search keep their sources' terms. |
| **LingBot-World v2** | Robbyant Team, arXiv:2607.07534, CC BY-NC-SA 4.0. Weights and modules run unchanged; `session.py` re-implements its sampling loop. |
| **Reference scores** | Genie 3 (Google DeepMind), SANA-WM (NVIDIA), Matrix-Game 3.0 (Skywork AI), LingBot-World v2: PlayWorld paper. |
| **Judges and player** | Official judge: Gemini 3.1 Pro (Google). Proxy judge (not official) and AI player: OpenAI `gpt-6-luna`; dev control player `gpt-4.1-mini`. |
| **Scene videos** | Generated with LingBot-World v2, CC BY-NC-SA 4.0, non-commercial. Removal: open an issue titled "Scene removal request". |

</div>

<style>
.credits table { font-size: 16px; }
.credits thead { display: none; }
.credits td:first-child { white-space: nowrap; }
.credits code { white-space: nowrap; }
</style>

<!--
Wording follows README.md "Credits" and the attribution facts in AGENTS.md "Scenes and attribution". session.py is adapters/lingbot_world2/session.py. The deck is built with Slidev; source in slides/.
-->
