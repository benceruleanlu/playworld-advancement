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

The slides follow that order. Setup first: how the work was organised, one coordinating agent session with research agents sending proposals as pull requests (slide 2), GitHub as the state store and what the pattern cost (slide 3), and one proposal traced end to end (slide 4); then the system and what a task looks like (slide 5) and our approach (slide 6). Then the benchmark's published scores for context, our best official score, the judge noise and a seed-repeat pair, what the model remembers and what our flags changed, what stopped a full run, and where to look at the clips.

Every number in this deck comes from AGENTS.md, README.md, results/experiments.csv or results/reports/ on main; the counts on slides 2 to 4 also come from the pull request and issue record and the commit history of main, as of PR #169. Each slide's notes name the source.
-->

---

# One coordinating agent session ran the proposal flow: research agents sent each idea as a proposal pull request

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
  <div><span class="n">150</span>pull requests in 24 hours</div>
  <div><span class="n">36</span>proposal pull requests</div>
  <div><span class="n">33</span>proposals reached main, off by default</div>
  <div><span class="n">105</span>rows in the experiment log</div>
</div>
</div>

<div class="text-sm mt-2 muted">Outside this flow: the owner's session ran the yaw servo study (#125, slides 12 and 13); teammate Hcoder10 opened #162 and #163.</div>

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
.nums .n { display: block; font-size: 34px; font-weight: 700; line-height: 1.05; font-variant-numeric: tabular-nums; color: #2f6fd6; }
html.dark .nums .n { color: #7fa8ee; }
</style>

<!--
This is how the proposal work was organised. It was not all of the project: the owner's own agent session ran the yaw servo study (#125, the lead on slides 12 and 13) in a separate Modal workspace and posted the replays that closed #114; #129 opens with "The project owner asked to 'fix pose memory'"; teammate Hcoder10 opened #162 (SANA-WM in the infra) and #163 (a loop-closure wrapper); jpoehnelt opened #1, #12 and #21. One coordinating agent session (a Claude Code session) ran the proposal flow: it gave each proposal to review agents, folded accepted proposals into main, closed or held the rest with a written reason, dispatched the experiment and arms workflow runs, and kept AGENTS.md and issue #9 current. AGENTS.md "Settled" gives it that role: "The coordinator session launches experiment runs, merges the integration branch when CI is green ... and freezes and launches the final run." The owner gave it standing authority to dispatch.

The loop on the slide, as the pull request record shows it:
- A research agent (a subagent of the coordinating session in most cases; the 36 proposal branches carry commit trailers from only two sessions, the coordinator's and one other) writes one idea as an off-by-default runner flag with unit tests, on a proposal/<idea> branch, and opens a PR whose body is the proposal: hypothesis, how it works, how it differs from earlier work, smoke recipe, kill criterion, risks, an Unverified list, tests (template from #80). Proposals state that flag-off output is byte-identical to main and refuse flag combinations it cannot support.
- Review agents return merge, merge_with_fixes or reject. Their verdicts are recorded only in the coordinator's PR text ("Every review came back merge or merge_with_fixes", #90); they leave no GitHub reviews of their own. An automated code-review app also posted findings on proposal PRs, which the coordinator answered in comments and fix commits.
- The coordinator merged a proposal directly, or folded several into a batch PR (#63, #90, #100, #104, #112) that merges each proposal branch with --no-ff, applies the review fixes, and closes the originals with "Landed via #N". Some it held and later merged ("On hold, no GPU slot", #132 and #133, merged at 07:05 and 07:07) or closed with measured reasons (#114, #117, #126).
- Experiments are Actions runs of experiment.yml or arms.yml on Modal GPUs; arm 1 of each group is the control. The workflow writes the results row, the report and the clips back to GitHub (next slide).
- Findings go into AGENTS.md status and PR comments, and the next proposals cite them by commit-pinned link (#147 has a "Duplicate check" against earlier PRs).

The first version was an hourly "autoresearch loop" in a fresh session, whose only memory was the ledger in issue #24. It could not dispatch GPU runs, so in its first hours its 4 ideas got 0 evaluations; AR-002 to AR-004 were later folded into the integration branch (#63), and the caption prompt and re-anchor ran in sp14-gc-v1. It was paused with a PAUSE line in #24 at 00:50 UTC Nov 15 "at the owner's direction", and the proposal PRs took over (research/autoresearch-loop.md).

Counts. 150 pull requests: #1 to #169 minus 19 issue numbers, first opened 19:22 UTC Nov 14, last (#169) opened 19:21 UTC Nov 15; 110 merged, 27 closed unmerged, 13 open. 36 proposal PRs (proposal/* branches, #75 to #147): 15 merged directly, 18 closed and landed through batch PRs #90, #100, #104 and #112, and 3 closed without landing (#114, #117, #126), so 33 reached main as off-by-default flags. 105 rows in results/experiments.csv on main: 101 real runs and 4 pipeline tests.

Who is who. 143 of the 150 PRs were opened under one shared bot login. Session links do not tell research agents apart: most proposal PR bodies carry none, and those that do (#103, #105, #108, #119, #123) carry the coordinator's. Main's commit messages carry 24 distinct session links, 35 across all branches, both lower bounds because squash merges drop branch trailers. #125 is the owner's servo PR; #131 carried its result to main.

What the pattern cost (the next slide has the short list): sessions collided on the same files (#143 rewrote site/src/scripts/app.js and AGENTS.md asked others to hold site edits; #166 had to absorb #164); runs were launched before the path was checked (three sharded runs before the #62 fix; 30 pose-memory rollouts that could not fire, slide 4); every merged proposal is a dark flag, and none has decision-tier evidence; review threads were answered in comments but left unresolved; status PRs piled up.
-->

---

# GitHub held most of the project's state: decisions in pull requests, the log and evidence on main, runs in Actions

<div class="grid gap-6 mt-4" style="grid-template-columns: 1fr 250px;">
<div class="dg smap">
  <div class="k">Proposals, reviews, decisions</div><div class="arr">→</div><div class="v">pull requests and their comments</div>
  <div class="k">Plan of record, idea ledger</div><div class="arr">→</div><div class="v">issues #9 and #24</div>
  <div class="k">Instructions and status</div><div class="arr">→</div><div class="v"><code>AGENTS.md</code>, via status PRs</div>
  <div class="k">Experiment log</div><div class="arr">→</div><div class="v"><code>results/experiments.csv</code> on main</div>
  <div class="k">Per-run evidence</div><div class="arr">→</div><div class="v"><code>results/reports/</code>, Releases with clips</div>
  <div class="k">Run state</div><div class="arr">→</div><div class="v">Actions run titles, status commits</div>
  <div class="k">Public view</div><div class="arr">→</div><div class="v">the site reads main when viewed</div>
</div>
<div class="dg cost">
  <b>What it cost</b>
  <div>Sessions edited the same files at once</div>
  <div>30 rollouts ran before a flag could fire</div>
  <div>9 status PRs left open</div>
  <div>One bot login for every agent</div>
</div>
</div>

<div class="text-sm mt-3 muted">Off GitHub: raw rollouts (Modal volume, 14-day Actions artifacts); full review verdicts and agent briefs (session context).</div>

<style>
.smap { display: grid; grid-template-columns: 240px 24px 1fr; gap: 10px 6px; align-items: stretch; font-size: 16px; }
.smap .k { border: 1px solid currentColor; border-radius: 4px; padding: 8px 10px; font-weight: 600; background: rgba(47, 111, 214, 0.16); }
.smap .v { border: 1px solid currentColor; border-radius: 4px; padding: 8px 10px; }
.smap code { font-size: 14px; }
.cost { align-self: start; display: flex; flex-direction: column; gap: 14px; font-size: 15px; padding: 12px 14px; border: 1px dashed currentColor; border-radius: 4px; }
.cost b { font-size: 16px; }
.cost div { padding-left: 10px; border-left: 2px solid currentColor; }
</style>

<!--
Most project state had a place on GitHub, and sessions read it from there; the exceptions are listed after this list and on the slide. Sources are origin/main unless noted.

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
- Unverified launches: pose memory (#123) ran in pm14-fx-v1 and v2, and all 30 pose-memory rollouts had 0 retrievals before #129 fixed it (slide 4). Three sharded runs were launched before the #62 fix.
- Status PRs: 9 "Docs: status" PRs are open and unmerged (#149, #152 to #155, #158, #161, #167, #169); each new one says it replaces the earlier ones.
- One login: 143 of 150 PRs were opened under the same bot account, so authorship is visible only through session links, and #90 lists #81 to #85 with no session link.
- Also: none of the 33 proposals that reached main has decision-tier evidence for its flag, and issue #9 was not updated when the plan switched to fixed-action A/Bs (AGENTS.md).
-->

---

# Pose memory went from proposal to dropped in 12 hours, and every step is a pull request or a run row

<div class="dg mt-6">
<div class="ptl">
  <div class="st fill"><span class="t">04:32</span><b>#123 merged</b>proposal: pose-indexed memory, off by default</div>
  <div class="st"><span class="t">04:33</span><b>pm14-fx-v1, v2</b>30 rollouts, 0 retrievals; 3 arms match control</div>
  <div class="st fill"><span class="t">05:34</span><b>#129 merged</b>CPU replay finds the cause; new rule</div>
  <div class="st"><span class="t">05:35</span><b>pm14-fx-v3</b>arms with the fix; memory fires</div>
  <div class="st dash"><span class="t">05:46</span><b>#134 closed</b>covered by #129; re-file one knob</div>
  <div class="st fill"><span class="t">07:01</span><b>#144 merged</b>the re-filed knob</div>
  <div class="st grey"><span class="t">16:27</span><b>#157 merged</b>dropped: +0.20 against a 0.34 bar</div>
</div>
<div class="small muted mt-3">Times in UTC, Nov 15; run times are launches. The last gap is 9 hours. pm14-fx-v3's +0.20 is from the proxy judge only.</div>
</div>

<style>
.ptl { display: grid; grid-template-columns: repeat(7, 1fr); gap: 0; position: relative; }
.ptl { font-size: 15px; }
.ptl::before { content: ''; position: absolute; left: 0; right: 0; top: 12px; border-top: 2px solid currentColor; opacity: 0.6; }
.ptl .st { position: relative; margin: 34px 4px 0; padding: 14px 6px 10px; border: 1px solid currentColor; border-radius: 4px; text-align: center; min-height: 150px; background-clip: padding-box; }
.ptl .st.fill { background: rgba(47, 111, 214, 0.16); }
.ptl .st.grey { background: rgba(139, 139, 139, 0.2); }
.ptl .st.dash { border-style: dashed; }
.ptl .t { position: absolute; top: -22px; left: 50%; transform: translate(-50%, -50%); padding: 0 6px; font-weight: 700; font-variant-numeric: tabular-nums; background: var(--slidev-theme-background, #fff); }
html.dark .ptl .t { background: #121212; }
.ptl .st b { display: block; font-size: 16px; margin-bottom: 6px; }
</style>

<!--
One proposal traced end to end, every step with a PR number or a run row.

- 04:32 UTC: #123 merged, pose-indexed memory that re-inserts past views into the attention sink, behind --lingbot-pose-memory, off by default.
- 04:32 and 04:33: arms runs pm14-fx-v1 (run 43677202111) and pm14-fx-v2 (run 43677269975) launched (status commits on main; their rows were written about 04:55 and 05:01), 14B, fixed dataset actions, tasks GC031, GC033, GC036, OE039, OE047, OE048. Every task printed pose_mem=on, but all 30 pose-memory rollouts ended with pose_mem_retrievals=0, and three arms (v1-a2, v2-a1, v2-a2) were byte-identical to the control v1-a1; v2-a3 (yaw gain 0.85) and v2-a4 (cache size) differed only because they change the model's inputs or cache (#129 body; AGENTS.md says only the cache-size and yaw-gain arms differed).
- 05:34: #129 merged. The cause was reproduced on CPU with pwa.pose_mem_plan: a shadow rule blocked every smooth turn, the opening chunks were never candidates, and the leave threshold was out of reach. The new coverage rule gives 1 to 6 planned retrievals per task. A review-fix second commit landed in the same PR.
- 05:35: pm14-fx-v3 arms launched one minute after #129 merged ("results: pm14-fx-v3 arms running" on main): control, pose memory, and pose memory with yaw scale 1.19. Memory fired: retrievals 3, 3, 6, 1, 3, 3 on the six tasks (AGENTS.md). Its score-only runs failed at 06:14 and were relaunched; the rows were last written at 07:41.
- 05:46: #134 closed. Its close comment says #129 covers the bug and asks for only the rel mode to be re-filed as a small PR from main once a #129 arm shows retrievals above 0.
- 07:01: #144 merged, the re-filed proposal (proposal/pose-mem-rel), filed "after pm14-fx-v3 verified the #129 default arm" and citing the #134 comment.
- 16:27: #157 merged; it records pose memory as dropped on the site and in the findings: under the proxy judge Luna pm14-fx-v3 scored +0.20, against a bar of 0.34, and showed no geometric gain.

The same pattern ran without a GPU run where measurements already answered the question: #114 was closed after the owner's session posted fixed-script replays in its thread (left turns rendered 1.19 to 1.30 times right turns, no transient after a reversal), pointing to #119's per-direction yaw gain.

The 30 rollouts before the fix are also the cost listed on the previous slide: the flag was launched on GPUs before a CPU replay checked that it could fire.
-->

---

# Each task ran on LingBot-World v2 through our harness on Modal GPUs, and Gemini 3.1 Pro scored the clip

<div class="dg mt-4">
<div class="flex items-stretch gap-1">
  <div class="box flex-1"><b>Task</b>image, goal, actions</div>
  <div class="arr">→</div>
  <div class="box flex-1 fill"><b>Runner</b>LingBot 14B, flags</div>
  <div class="arr">→</div>
  <div class="box flex-1"><b>Clip</b>about 60 s</div>
  <div class="arr">→</div>
  <div class="box flex-1 fill2"><b>Judge</b>1 to 5 per task</div>
  <div class="arr">→</div>
  <div class="box flex-1"><b>Report</b>CSV row, site</div>
</div>
<div class="mt-4">
<ClipRow :items="[
  { exp: 'lb14-session-agent-dev-v1', task: 'GC033', head: 'Geometry consistency', sub: 'layout holds as the camera moves' },
  { exp: 'lb14-session-agent-dev-v1', task: 'IF002', head: 'Interaction fidelity', sub: 'each action does what was asked' },
  { exp: 'lb14-session-agent-dev-v1', task: 'OE001', head: 'Insight evolution', sub: 'an on-screen process keeps going' },
  { exp: 'lb14-session-agent-dev-v1', task: 'OE039', head: 'Out-of-sight evolution', sub: 'hidden things change sensibly' },
]" />
</div>
</div>

<div class="text-sm mt-3">

35 of 101 logged runs had an AI player (closed loop). The rest replayed fixed actions, for A/B tests only.

</div>

<!--
This slide compresses the system and protocol. The boxes are the path one task takes; the clips are one baseline task per family from lb14-session-agent-dev-v1 (closed loop, no flags; CC BY-NC-SA 4.0, generated with LingBot-World v2). Clip list: results/media/lb14-session-agent-dev-v1.json. Clips load from GitHub Releases (run-lb14-session-agent-dev-v1) and do not autoplay.

Benchmark: PlayWorld (Ding et al.), 171 tasks: GC 48, IF 50, insight 30, out-of-sight 43 (AGENTS.md "Run speed", the sharding bullet). Splits: dev and dev2, 24 each with 6 per family; heldout 123, unscored (AGENTS.md "Layout"). A task with a gate (for example, return to the start view) scores 1.0 if the gate fails ("Workstreams" in the first AGENTS.md, commit 2d8b8c4, and the PlayWorld harness). Insight and out-of-sight task IDs both start with OE; the family is in the task JSON.

The family questions are the site's one-line questions (site/src/scripts/families.js):
- Geometry consistency: move the camera away and back. Is the place still the same place?
- Interaction fidelity: press a key. Does the subject do what was asked, with real contact?
- Insight evolution: wait and watch. Does a process on screen keep going sensibly?
- Out-of-sight evolution: look away, then back. Did the hidden part of the world move on sensibly?

Model: LingBot-World v2 (Robbyant Team). 9 of the 101 logged runs used lingbot_world2_1p3b, including 4 scored rows (rs13-arms-v1, gch13-arms-v1); the rest used the 14B (results/experiments.csv). The plan of record cut the 1.3B for decisions. The runner is adapters/lingbot_world2/run.py, which reuses the upstream PlayWorld harness and swaps in our engine (AGENTS.md "Layout" and "Adapters"). The model weights are not changed. Our use is not "unmodified": adapters/lingbot_world2/session.py re-implements LingBot's sampling loop as a persistent session that keeps the attention cache between the player's steps (AGENTS.md "Scenes and attribution").

Clip length: up to 30 chunks, mean 29.7, about 60 s of video ("Run speed", Verified). A closed-loop step adds about 2 s (16n frames at 16 fps, 2 latent chunks by default; AGENTS.md "Adapters", session frame accounting).

Judge: Gemini 3.1 Pro, the official judge, at upstream settings (frame rate, resolution and JPEG unchanged), 2 or 4 passes. 42 runs were Gemini-scored; 34 were generated but never Gemini-scored, and later ones have proxy scores from Luna (openai:gpt-6-luna), which are not comparable to the paper. Luna's noise and its agreement with Gemini are on slide 9; when Gemini scoring stopped is on slide 16.

Compute: one H100 per shard on Modal, launched from GitHub Actions (experiment and arms workflows). Timings from "Run speed", measured on lb14-session-agent-dev-v1: model load 267 to 357 s once per family per shard, agent rollouts 522 to 610 s with the first chunk (insight 367 to 443 s), 142 min wall clock or about 18 min per task on an 8-task shard, including GPU queueing. A later flag (--lingbot-fast-dit, #79) cuts the 14B load to about 31 s.

Actions. Sources: AGENTS.md "Rules" (dataset mode for A/B only), "Status against the timeline" ("Dataset actions and a scripted player are open loop"; since about 18:35 both arms of a pair see the same actions) and "Settled" (player gpt-6-luna for compared runs, the gpt-4.1-mini baseline is a diagnostic). results/experiments.csv on main has 105 rows; 4 are fake_runner pipeline tests. Of the other 101, action_source is dataset on 62 and agent on 39. Four of the 39 are the sp14-gc-v1 arms, the scripted player (#102), which replays a fixed plan with no AI player, so 35 had an AI player. Status: 42 scored, 34 generated, 15 cancelled, 7 failed, 3 predate the status column.

Players: gpt-4.1-mini on the dev baseline (slide 8), gpt-6-luna in later closed-loop arms. The only Luna closed-loop arms with a Gemini score are on the 1.3B or capped at 10 chunks (rs13, gch13, smk14-arms-gc-v2); in gch13, 22 of 110 player decisions fell back. The full-length 14B closed-loop runs (clstk14-dev-v1, stksv14-cl-gc-v1) were generated only. Pass counts: the dev baseline was scored at 2 passes, the arm groups at 4.
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

The four groups follow the workstreams of the first plan (AGENTS.md as scaffolded, commit 2d8b8c4); the plan of record in #66 replaced that section and later cut out-of-sight memory and sink work for the event ("Cut for this event"), but fixed-action runs on the sink and window went ahead anyway. The flags under each are documented in AGENTS.md "Adapters". Return stop and player hint change what the AI player is told, not the model (README.md), and were scored only on the 1.3B. The eval infrastructure (pwa CLI, experiment and arms workflows, per-run reports, results site, blind review page) is on slides 3, 5 and 17.

Flag count: AGENTS.md "Status against the timeline" recorded 28 method flags at 22:25, and #115, #116, #121, #132, #133, #139, #144 and #147 added more since; those eight are merged and unscored. None has decision-tier evidence.

What would count. The strip at the bottom is the rule set. Decision tier: closed loop, 14B, full length, all 6 dev tasks of a family, 2 seeds, official judge. Adoption: a task moves a full point, the gain repeats on both seeds, no gate is lost. Rules: AGENTS.md "Rules" and "Testing tiers and the adoption rule". Also in "Rules": a new experiment name for every run (pwa gen refuses an existing run directory because upstream --skip-done silently reuses old videos), heldout unscored until code freeze, and final numbers closed loop with Gemini 3.1 Pro over 2 or more passes.

Practice, not a written rule: since about 18:35 model-side flags were compared with the same actions in both arms (dataset or scripted player) at the same seed. Generation is deterministic, so any difference between such arms is the flag or the judge. AGENTS.md calls these runs a change from the plan as written: they are open loop and cannot meet the decision tier. Some servo groups borrow controls from other groups (sks14, mem14, win14). The stack on slide 14 differs by six flags, not one.

The rest of the deck reads results against these rules. Slide 9 shows why the judge spread sets the bar.
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
The reference scores are the PlayWorld paper's numbers on all 171 tasks, copied in AGENTS.md "Reference scores". None of our runs is on that footing, so our 1.64 is drawn apart from the axis (slide 8 has the run).

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
Source: results/experiments.csv row lb14-session-agent-dev-v1 (overall 1.6390, std 0.1258, 2 passes, 24 tasks, 0 missing) and the "Ours" row in AGENTS.md "Reference scores". Other Gemini-scored rows exist (the arm groups on slide 15), but they are fixed-action or six-task subsets, so this is the best closed-loop dev number.

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

Right: a six-task family mean moves about 0.5 on the same videos, drawn as the band from -0.5 to +0.5. The dots are the sink key scale arms on out-of-sight (sks14-fx-v1, Gemini, one seed): control 2.10, arms 1.65, 1.33 and 1.25. Scale 0.7 (-0.45) is inside the band; the two arms that start at chunk 4 are below it (slide 15).

Luna (openai:gpt-6-luna, proxy judge): byte-identical clips give 0.50 per task on average and 0.62 on a five-task mean. It lets 97% of gate checks pass, where Gemini failed a gate on 23% of tasks. Rank correlation with Gemini: 0.62 on 21 clips (0.41 on out-of-sight). Luna's identical-clip numbers come from walking-only GC tasks, where the servo arm and the control are the same file.

We used Luna after Gemini scoring stopped working on Nov 15 (the credits ran out about 03:55 UTC, were topped up, and ran out for good about 06:14; the last Gemini-scored row in results/experiments.csv is at 05:43). Luna's scores are not reported numbers and are not comparable to the leaderboard.

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

Use "Play both from start" to run them together. Nothing but the seed differs, so the difference between the clips is what a second seed adds on top of the judge noise on the previous slide. This is why the adoption rule asks for a gain that repeats on both seeds (slide 6).

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

Two flags change this window: keep-first 10 and attention window 22. They are part of the stack on slide 14.
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

GC038 improved least, 96 to 49 degrees. Walking-only GC tasks give byte-identical clips with and without the servo, which is where Luna's identical-clip noise numbers on the judge slide (slide 9) came from.

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
  <div class="daxis"><span style="left:0%">0</span><span style="left:25%">0.3</span><span style="left:50%">0.6</span><span style="left:75%">0.9</span><span style="left:100%">1.2</span></div>
  <div class="small muted dtitle">Change in out-of-sight family mean (Luna, treatment minus control)</div>
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
.daxis { position: relative; height: 22px; margin-left: 92px; margin-right: 52px; border-top: 1px solid currentColor; font-size: 13px; font-variant-numeric: tabular-nums; }
.daxis span { position: absolute; top: 6px; transform: translateX(-50%); }
.daxis span::before { content: ''; position: absolute; left: 50%; top: -6px; height: 5px; border-left: 1px solid currentColor; }
.dtitle { margin-left: 92px; margin-top: 2px; }
</style>

<!--
This is a lead from small samples, not a result. The three pairs are stk14-fx-dev-v1 at seeds 0 and 1 (4 passes) and stk14-fx-dev2-v1 (2 passes). Source: AGENTS.md, the stack bullet under "Proxy judge findings". The bars are drawn on a 0 to 1.2 scale, shown by the axis; the dashed line is Luna's 0.6 bar from the judge slide (slide 9).

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

Measured: the yaw servo's end heading (slides 12 and 13); no judge score change.

Leads from small samples: the stack, about +1 on out-of-sight under Luna (slide 14). Dropped as harmful or null (AGENTS.md, each on one seed and six tasks or fewer): sink key scale lowered out-of-sight: control 2.10; scaled arms 1.65, 1.33 and 1.25 (sks14-fx-v1, Gemini, one seed). Scale 0.7 (-0.45) is inside the six-task noise from the judge slide (slide 9); scale 0.4 and 0.7 from chunk 4 are below it. The conditioning schedule halved insight, 3.00 to 1.50, on the two tasks it ran, OE001 and OE018 (dec14-ins-v1). Both sit in the "Dropped" tier with their numbers; they are drops on small samples, the same caution as the stack lead in the other direction.

Did not repeat or inside the noise: turn calibration, the same comparison run twice on GC031, gave +1.95 and +0.35. Generation is deterministic, so that spread is a config difference or judge spread, not rollout noise. Caption prompt: 2 tasks up and 2 down by a full point in one run. Sink 10 with window 22 raised OE039 1.00 to 3.44 at seed 1, but 1.75 at seed 0, inside the controls (win14-fx-v1).

Dropped: pose memory retrieves as planned after #129, with no geometric gain, +0.20 under Luna against a bar of 0.34.
-->

---

# No full-benchmark run was launched before judge credits and GPU access ran out

<div class="dg mt-8">
<div class="tl">
  <div class="tlband" style="left: 51.9%; right: 0;"><span>Luna proxy scores only</span></div>
  <div class="tlev" style="left: 32.6%"><b>03:55</b>Gemini credits out<br>(topped up by 04:27)</div>
  <div class="tlev" style="left: 51.9%"><b>06:14</b>out for good<br>(last Gemini row 05:43)</div>
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

The Gemini AI Studio prepaid credits ran out twice, both times with 402 RESOURCE_EXHAUSTED "prepayment credits are depleted" in the score .err files. First: the first failed judge call is at 03:55 (mem14-fx-v1-a1, run 43673784900), and every score-only run from 04:00 to 04:08 failed (sks14-fx-v1-a1, run 43674792081: failed=24). After a top-up, the reruns from 04:27 scored, and results/experiments.csv has Gemini-scored rows (dec14, sks14, pm14-fx-v1/v2, ins14-fx-v2, win14-fx-v1) up to 05:43. Second: from 06:13 every score-only run failed (pm14-fx-v3-a1, run 43684466681: failed=24, first failed call 06:14). The band starts at 06:14. Later runs have Luna scores only.

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

Pairs in this deck: GC033, IF002, OE001 and OE039 in lb14-session-agent-dev-v1 (slide 5); IF002 seed 0 against seed 1 in stk14-fx-dev-v1 a1 against a3 (slide 10); GC033 and GC036 in svgc14-fx-v1 a1 against a2 (slide 13); OE039 and OE047 in stk14-fx-dev-v1 a1 against a2 (slide 14).

Blind review page: benceruleanlu.github.io/playworld-advancement/review/. It hides which clip is control and which is treatment until you finish; it records a preference by eye, not a score. Given the judge noise on slide 9, looking at the clips is a fair check on any claim here. The review page (#164, site/src/pages/review.astro) shuffles sides per reviewer and reveals arms and a sign test only after "Finish and reveal". Clips load from release URLs that name the run, so blinding holds only if reviewers do not open developer tools.

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
