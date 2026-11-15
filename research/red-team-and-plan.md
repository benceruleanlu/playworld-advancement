# Red-team review and the plan of record

Date: 2026-11-15. Question: with about 20 hours to the Sunday 14:30 Pacific deadline, which methods do we build and test, and how do we decide what ships?

Provenance: this note collects the coordinator session's working files. The rulings and the whole-plan review were produced on Saturday 2026-11-14 (Pacific evening) by an adversarial review: each proposal was attacked by two adversaries (can it be built in this code in the time left; will it move the score and is it legitimate), then ruled on by a judge that re-checked the objections against the code and data. A final adversary reviewed the plan as a whole. Three candidate plans were then written and scored by three judges, and the coordinator merged them. The owner agreed the result as the plan of record on issue #9 at 16:50 Pacific. Public records: issue #48 (rulings summary), its sub-issues #49 to #53 and #58, and issue #9. Effort and gain figures in this note are the reviewers' estimates, not measurements, unless marked measured.

## The 12 rulings

All twelve proposals targeted the out-of-sight family. The proposals themselves are listed in [out-of-sight-evolution.md](out-of-sight-evolution.md).

| # | Proposal | Ruling | Why | Estimated cost | Estimated gain |
|---|---|---|---|---|---|
| P0 | Failure census | Modify | Not free and not decisive alone: frozen and reverted are the same judge level, and all three hypothesised causes give the same symptom. Read the raw per-pass JSON for all 24 dev tasks, use three labels (trajectory fault; level 1 with a clean trajectory; level 2 or higher), use insight as the still-camera control. Never block building on it. | 0.75 to 1 h, no GPU | None directly; about a one in three chance it changes the build order |
| P1 | Still-camera check | Modify | The baseline's insight tasks answer most of it. Otherwise a matched still-versus-turn probe arm, read by eye, as a differential and not a go/no-go gate. | 0 h code, one probe run | None directly |
| P2 | Activity or return prompt | Modify | Ship candidate is a fixed activity sentence appended to the task prompt; the task prompt is never replaced. The return switch is a later add-on, gated on a probe. | 5 to 6 h plus two GPU round trips | +0.0 to +0.10 overall; insight is the better bet |
| P3 | Sink down-weight | Modify | No build until a no-sink probe arm shows a same-scene, advanced return. Step 1 alone is the wrong dose for this 4-step sampler. | Gate 0 h; build 3 to 4 h if the gate passes | Most likely zero; +0.05 to +0.08 overall if it works |
| P4, P14 | Cache flush, cache recompute | Withdrawn | Flush raises the sink's share of attention from 6 of 14 latents to 6 of 7. Recompute re-encodes the same second-0 latents. Only the text re-encode path, which a prompt switch needs, is kept. | P14 4 to 8 h | Flush alone zero or negative |
| P5 | Sink-preference diagnostic | Dropped | Folded into the P8 probe; the fused kernel does not expose attention scores and no proxy for progress exists. | | |
| P6 | Side rollout written into the sink | **Killed** | Slot 0 is re-conditioned from the original image through the `y` channel on every pass (`model_fast.py:548-549`, `session.py` `_encode_y`), slots 1 to 5 are not at the start pose in 38 of 43 tasks, and re-running the clean pass on the sink corrupts upstream cache indices. | 10 to 14 h for a corrected version | Ceiling about +0.2 overall |
| P7 | Edited anchor | Modify | No latent write, no entity ledger, no past.dev and no image editor before freeze. At most a donor-rollout K/V copy as a probe. | Stage 1 2 to 3 h; stage 2 8 to 12 h | Under 15% chance of shipping |
| P8 | Sink surgery | Modify | Only windows `13:1` and `12:0` change the sink size alone (at `18:0` the rolling window also grows). Replace-sink is a no-op on 41 of 43 tasks. One sink-size probe gates one judged arm. | 1 to 2.5 h | Most likely zero; +0.05 to +0.10 overall if it passes |
| P9 | Memory window and keyframe pinning (PR #37) | Modify | Not for this family: the returned view is already in the sink. A GC window A/B only if the baseline shows GC losing on identity at reappearance. | 0.25 h to read; 1.5 to 2 h if gated in | At most +0.05 overall |
| P11 | Best-of-N on the return | **Killed** | A similarity selector ranks the frozen return first; a "did it progress" selector restates the judge. Closed loop allows only greedy per-step selection, and the 14B cache (21.4 GiB on a 64.1 GiB peak) cannot be cloned on an 80 GB card. | 6 to 9 h | About zero with a deployable selector |
| P13 | Iteration setup | Modify | Select on 14B, not 1.3B: there is no evidence 1.3B fails the same way. One seed with two judge passes measures judge noise only, so use two seeds and count per-task cells. Fix the turn-calibration setting across arms. | 2 to 3 h of tooling | Protects against shipping a null method |
| P16 | Priority on out-of-sight | Modify | Out-of-sight alone cannot reach 2.12: every task at 2.0 there gives about 2.03 overall. Allocate by the measured gap once the baseline lands; two or three families must move. | 0.5 h plus a 2 h reliability reserve | 1.9 to 2.05 for a portfolio; 10 to 20% chance of passing 2.12 |

That is 14 proposals in 12 rulings: P4 and P14 share one, and P5 is folded into P8. The review also dropped P15 (global cache mode), which cannot run on 14B because `session.py` sizes the global cache to the `y` horizon.

## What the whole-plan review found that no proposal covered

- **The dataset caption is benchmark input.** Upstream's Genie 3 player (`Agent_player/genie3/player.py`, `build_genie3_prompt`) sends `Environment: <image_caption>` plus the task to Genie 3; the HappyOyster and HY-World2 players do the same. Our adapter sends only the camera instruction, or "wait and observe" on 29 of 30 insight tasks. The captions describe the activity as visible evidence, the format LingBot v2 was trained on. Four rulings had banned this field; the review called the ban stricter than the benchmark's own protocol and left the call to the owner, who allowed it with disclosure.
- **Insight is the cheapest family to move.** No gate, no player, no camera motion. One task point is worth 1/120 overall there, against 1/172 for out-of-sight, 1/192 for GC and 1/200 for IF.
- **The player is unexamined** although it drives 141 of 171 tasks. Ours was gpt-4.1-mini; upstream's default is Claude Haiku 4.5. It oscillated for 24 chunks on GC005.
- **The local baseline was unmeasured**, and every ruling assumed it equals the web demo's 1.82. It has since landed at 1.64 on dev ([baseline-census.md](baseline-census.md)).
- **The final 171-task run had never been tried** at the shard count it needs. A baseline generation started early tests shards, quota and wall clock and is also the fallback submission.
- **Time was not pinned down.** The rulings together approved about 18 to 22 hours of attention and ten or more one-hour GPU cycles, each "cheap" on its own.
- **Dev cannot predict the full-run number.** With 6 tasks per family, the dev overall has a task-sampling error of roughly 0.2 on top of seed and judge noise.
- **Little world time passes while the camera is away**: about 4 to 10 seconds on the out-of-sight tasks, against 60 seconds of still camera on insight. Elapsed time, not memory, may be the limit.
- **Shared risk of the prompt lever.** StEvo-Bench reports that when LingBot evolves a scene it stops obeying the camera. A richer prompt could cost trajectory gates on GC and out-of-sight; only a closed-loop run over all four families shows this.
- **No fallback claim and no time for the deliverables** had been set aside.

Biggest risk named: arriving at freeze with several half-tested probes, no complete closed-loop 171-task number, and no time left for the video and writeup.

## Three candidate plans and how the judges ranked them

| Plan | Thesis, short | Its own expected outcome |
|---|---|---|
| Score-first | Screen every lever in dataset mode, confirm winners closed loop on two seeds. Build the caption prompt and a plan-aware player that is given the dataset action sequence and returns END when the plan is done. Launch the full-171 baseline now. | 1.75 to 2.15, about 10 to 15% chance of passing 2.12 |
| Rigour-first | Launch the starting-model 171 run now, limit method work to what is already coded (session, turn calibration, caption prompt #32, GC re-anchor #46) plus at most one insight prompt arm, and make sure both 171-task numbers, the failure taxonomy, horizon curve and gallery exist by 10:30. | 1.6 to 2.05; starting model 1.5 to 1.9 |
| Fine-tune bet | A LoRA is not feasible before freeze (see below), so no GPU goes to training; spend the time on a faster loop over three built flags and on the rigour deliverables. | 1.7 to 2.0, about 10% chance of passing 2.12 |

Each judge scored each plan 1 to 5 on feasibility in time, expected score gain, method quality, rigour and completeness of the submission:

| Judge | Score-first | Rigour-first | Fine-tune bet | Ranking |
|---|---|---|---|---|
| Track (what the brief rewards) | 3 / 4 / 4 / 4 / 4 = 19 | 4 / 2 / 3 / 5 / 5 = 19 | 3 / 2 / 2 / 3 / 3 = 13 | score-first, rigour-first, fine-tune |
| Operations (can it run on our GPUs) | 2 / 4 / 4 / 3 / 3 = 16 | 4 / 2 / 3 / 5 / 5 = 19 | 3 / 2 / 3 / 3 / 3 = 14 | rigour-first, score-first, fine-tune |
| Statistics (can the data decide) | 2 / 3 / 3 / 3 / 4 = 15 | 3 / 2 / 3 / 4 / 4 = 16 | 3 / 2 / 2 / 3 / 3 = 13 | rigour-first, score-first, fine-tune |

Points the judges raised that changed the merged plan:

- The statistics judge read the landed baseline and found every plan's decision unit inside judge noise: 10 of 24 tasks differed by 0.5 or more between two passes of the same video, so "cells moving by 0.5 on two passes" would adopt null flags often (estimated 14 to 28% false adoptions).
- The same judge found the speed premise wrong: measured generation is about 11.4 s per 33-frame chunk, and the "23 min per task" figure came from GPU queueing, not from the model ([autoresearch-loop.md](autoresearch-loop.md)).
- A score-against-chunk-count horizon curve has no signal, because every baseline rollout is 28 to 30 chunks long.
- Several plans assumed 24 to 50 concurrent H100s. The quota is still unconfirmed; the merged plan sizes requests to about 10.

The coordinator took rigour-first as the base (ranked first by two of three judges), kept score-first's tiering, early freeze and second seed, and kept the fine-tune plan's dispatch tricks (one family per dispatch, staggered launches).

## Plan of record

Agreed with the owner Saturday 16:50 Pacific, issue #9. Goal by Sunday 14:30: a closed-loop 171-task score for the starting model and for our method on the same harness, a described method, and evidence of where the world still breaks.

Settled:

- Model: LingBot-World v2 14B, persistent session. The starting model is the same runner with every method flag off.
- Player: `gpt-6-luna` for every compared run (#61). The gpt-4.1-mini baseline `lb14-session-agent-dev-v1` (1.64) is a diagnostic only.
- Official judge: Gemini 3.1 Pro at upstream settings, for every reported number. A screening judge for the dev loop (`gemini-4-hydrogen`) is kept in a separate folder and never written to `results/experiments.csv`, and is used only if a calibration on the 24 baseline videos shows it agrees with the official judge.
- The dataset `image_caption` may be used as model input, disclosed. Upstream gives it to Genie 3.
- The coordinator session launches experiment runs, merges the integration branch when CI is green, and freezes and launches the final run.
- No fine-tuning and no out-of-sight memory work before submission.

Timeline (Pacific):

| When | What |
|---|---|
| Saturday 16:50 | Player check with `gpt-6-luna` on the 6 out-of-sight and 6 GC dev tasks, read from action logs: reversals, return to start, early END. Caption prompt on the 6 insight tasks (`lb14-cap-ins-s42`). |
| After the player check | Starting-model run on all 171 tasks, generation only, 8 shards. Scored at freeze. |
| To about 19:00 | Integration branch `method/candidate-v1`: caption prompt (#32), GC re-anchor (#46), player hint (#59), each behind an off-by-default flag with per-task counters. Screening-judge option and its calibration. |
| 19:00 to 22:30 | Second seeds for whatever moved; caption guard runs on the camera families; re-anchor. |
| 22:30 to Sunday 01:30 | All adopted flags together on the 24 dev tasks, two seeds, official judge. |
| Sunday 02:00, hard limit 03:30 | Code freeze. Method run on 171 tasks; score the starting-model run. |
| To 10:30 | Scoring, refills, second seeds if GPUs allow. Numbers freeze at 10:30. |
| Overnight | Rigour: failure taxonomy per family, horizon curve from scored rollout prefixes, judge-noise table, failure gallery. |
| 10:30 to 13:45 | Video, description, submit. |

### Adoption rule

A task cell (one task at one seed) moves only when the mean of its judge passes changes by a full point. A flag is adopted only if the gain repeats on both seeds and no gate that passed in the baseline fails. This replaces "a delta under 2x the pass std is noise" for dev decisions, because the baseline showed two passes on the same video disagreeing by 0.5 or more on 10 of 24 tasks. Final claims still need a closed-loop run scored by Gemini 3.1 Pro over 2 or more passes.

### Expected outcome

Estimates, nothing scored yet: starting model 1.5 to 1.8 on the full benchmark; method 1.6 to 2.0; chance of passing 2.12 about 5 to 10%. The coordinator's longer estimate: insight (1.58 locally against 1.95 for the web demo) is where the caption arm is most likely to gain; out-of-sight will probably stay near 1.2 to 1.4; the chance the method beats the starting model by a margin we can defend is about 35 to 45%.

## What was cut, and why

| Cut | Why |
|---|---|
| All out-of-sight memory work: sink changes (#52), state writer (#53), return prompt switch (#51), still-camera probe (#50), self-distillation LoRA (#58) | The baseline showed 4 of 6 out-of-sight rollouts never return to the start view, so content cannot be graded until control works. The rulings had already killed or gated most of it. |
| Best-of-N | Killed in review (above). |
| Fine-tuning of any kind | See below. |
| A plan-aware player fed the dataset action sequence | 3 h of new code, it changes what closed loop means, and the measured player cost is about 4 to 6 s per chunk, so the claimed speedup does not exist. PR #59's pose hint is tested in its place. |
| The 1.3B model for decisions, SANA-WM, Matrix-Game 3.0 | 1.3B is not shown to fail like 14B and is not the submission model. SANA-WM ran once as a smoke test and is stopped. The Matrix-Game adapter stayed a stub (issue #4 closed). |
| Dataset-mode screening of the camera families | Dataset and closed-loop rollouts differ about 3x in length and take different code paths; the difference sits inside judge noise. |
| Adoption on half-point cells, family-mean thresholds of 0.2, single-seed gate counts | All inside the measured judge noise. |
| Turn calibration as a separate decision | Evaluated only inside the hint and re-anchor arms, which need it. |
| 50-shard full runs and cross-family sharding | The quota does not support 50, and each extra shard pays up to four 5-minute model loads. |
| Staged per-chunk insight prompts, a Claude Haiku 4.5 player arm | No time after the harness freeze. |
| New autoresearch ideas, an A/B matrix workflow, a warm Modal class | The bottleneck was launching and reading, not ideas ([autoresearch-loop.md](autoresearch-loop.md)). |

### Fine-tuning: no-go for the event

The track brief allows fine-tuning and forbids only training from scratch, so this was a choice, not a rule. Fine-tuning was assessed and dropped:

- Upstream ships inference code only. The LingBot-World v2 clone at commit `1895d30` has `generate.py`, `wan/image2video.py`, `wan/modules` (fast and causal models, VAE, T5, attention), solvers and camera utilities. There is no training script, loss, optimizer or data loader. Every module is loaded with `eval().requires_grad_(False)` and sampling runs under `no_grad`. (Checked in the local clone.)
- The causal-fast weights we run are a distilled few-step student. The v2 tech report (arXiv 2607.07534, "Post-Training: Few-Step Distillation") describes consistency distillation plus distribution matching distillation (DMD) from the causal pre-trained model; our session samples 4 denoising steps. Fine-tuning that student correctly needs the DMD loop (a 14B teacher, a trainable critic, self-rollout), which is not released.
- A plain flow-matching LoRA on the student would likely break its few-step sampler, would be tractable only on 1.3B (not the submission model, and no 1.3B teacher is released), and needs pose-annotated video with ongoing activity that we do not have.
- There is no training workflow, so each debug cycle on Modal would take about an hour.

The LoRA design in #58 is kept as future work.
