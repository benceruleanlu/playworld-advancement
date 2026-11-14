# Out-of-sight evolution on LingBot-World v2: hypothesis, literature, proposals

Date: 2026-11-14. Question: why does LingBot-World v2 score 1.16 on PlayWorld's out-of-sight family, and what inference-time change could raise it?

Provenance: the task analysis and cache analysis were run in this repo. The literature section comes from two research passes; the second read the primary papers in full (and public code where it exists). Claims not read from a primary source are marked (unverified). Nothing here has been tested on a GPU yet, and we have no judge output for our own out-of-sight rollouts. Companion note: [memory-for-world-models.md](memory-for-world-models.md).

## Bottom line

- The family is graded on whether the scene **progressed** while unseen. A return that looks the same as before scores the minimum. Remembering the scene is not the task.
- LingBot's failure is a content failure, not a camera failure: PlayWorld reports a 93% trajectory-gate pass rate for LingBot-World2 on this family, the highest of nine models.
- The literature agrees on the symptom ("frozen, not forgotten") across this model class. The cause on LingBot v2 causal-fast is ours to prove.
- After a red-team review, the first lever to test is the scene caption as prompt (which upstream gives Genie 3 and we do not give LingBot), starting on insight. Sink changes are gated behind a probe, and writing a new state into the sink as first proposed is not buildable. More memory is not supported.
- Out-of-sight alone cannot reach 2.12; two or three families must move.

## What the task measures

From `data/outsight/data.json` and `third_party/PlayWorld/metrics/vqa/rubric.py`:

- 43 tasks, all first person. Typical prompt: "Turn the camera right 90 degrees, then return to the starting view", over an image of an ongoing activity (painting, pouring, an escalator).
- Every task carries the same policy: a static or near-static result is capped at 1.0; a reset or revert is a severe failure; any verified persistent change earns at least 2; identity starts to matter at level 3.
- The comparison is the last stable view before leaving against the first stable view after returning, not against the first frame.
- A separate trajectory gate (camera leaves and returns) scores 1.0 on fail.

## What the cache does on these tasks

From `python -m adapters.lingbot_world2.cache_model --split all --family outsight`:

- LingBot keeps the first 6 latents forever (the "sink": the input image plus about 20 frames) and the previous 8 latents (about 32 frames, 2 s).
- 31 of 43 dataset trajectories end at the starting view (33 with turn calibration), which is in the sink and never evicted. Four more return to it and then make a final move (OE026, OE037, OE039, OE047); two return after walking (OE019, OE050); four never return (OE021, OE028, OE029, OE032). An earlier version of this note said 43 of 43; that came from a check that also counted a still tail as a revisit.
- Evictions hit views passed in transit: 36 of 43 tasks with default turn rates, 18 of 43 with turn calibration.
- So on a clean return, the model's only memory of the target view is the scene at second 0.
- The sink is not six copies of the start view. Slot 0 is the input image, and it is re-conditioned from the original image on every pass through the `y` channel. In 38 of 43 tasks the camera starts moving at frame 1, so slots 1 to 5 hold the first part of the outbound sweep.
- Only about 4 to 10 seconds pass while the camera is away. Insight tasks get 60 seconds of still camera.

## Hypothesis

LingBot returns a frozen or reset scene for three reasons:

1. It stops evolving the scene while the camera moves.
2. On return, the pinned first frames are the only memory of that view and pull content back to the start.
3. Nothing in the text says the activity progressed. Our local harness passes only the camera instruction as the prompt.

Status: 1 and 2 are reported for LingBot v1 or for the model family in the literature below. None is shown on LingBot v2 causal-fast. Reading the judge's reasons for our own baseline run is the first check.

## Literature (primary sources read in full unless marked)

### Benchmarks: the symptom

| Source | Finding |
|---|---|
| PlayWorld (arXiv 2608.13552) | Out-of-sight gate pass: LingBot-World2 93.0%, Genie 3 90.7%, LingBot-World 83.7%. Scores: Genie 3 1.81, LingBot-World 1.43, LingBot-World2 1.16. Web-interface models, LingBot-World2 included, were run through their demos. No per-model failure analysis. |
| StEvo-Bench (arXiv 2603.13215) | Camera-controlled models "almost never evolve states". LingBot (original release): 0.0% success, 3.4% state progress, look-away achieved in 35.6% of videos. Lead example: a cup "resets" and becomes empty after LingBot looks away and back. When LingBot or Genie 3 does evolve the scene, it tends to ignore the camera command. Cause is hypothesised as training data (camera-motion clips of static scenes), not tested. |
| WRBench (arXiv 2606.20545) | Models resume "a returning target in the state at which it was abandoned". Camera-controlled Wan 1.3B to 14B lowers returned-state score 0.657 to 0.621. LingBot (original, Cam variant): camera precision 0.513, only 6.0% of clips gave a scoreable leave-and-return. No intervention tested. |
| LiveWorld (arXiv 2603.07145) | Names the problem "out-of-sight dynamics": unobserved regions are frozen in memory, KV cache included. |

### LingBot itself

- v2 tech report (arXiv 2607.07534): trained with a background prompt plus one event prompt per chunk; captions describe only visible evidence, with speculative or future-revealing text removed. The authors' main stated limitation is long-term memory: a region that leaves the context "tends to be regenerated rather than recalled". The deployed demo uses dynamic KV-cache scheduling and a prompt-writing "Director" model; neither is in the released code.
- Released code: one prompt encoded once per rollout; `--local_attn_size 18 --sink_size 6` is the recommended fast setting; cached keys are stored with RoPE already applied.
- Consequence: the 1.16 in the paper is not from the code we run. Our own baseline may differ in either direction.

### Pinned first frames suppress change

| Source | Finding | Training-free? |
|---|---|---|
| Reward Forcing (arXiv 2512.04678) | Static sink tokens cause "copied initial frames and diminished motion dynamics". Ablation dynamic score: static sink 35.15, no sink 51.56, EMA sink 43.75. | No (trained variants) |
| AdaState (arXiv 2605.30349) | The first-frame anchor "draws disproportionate attention, suppressing video dynamics, and locking scene composition to the initial viewpoint". A static sink kept beside an evolving one wins the attention. | No, no code |
| DySink (arXiv 2605.21028) | Content "regresses toward sink frames"; per-layer fraction of heads preferring the sink is a usable diagnostic and gate (threshold 0.8). | Gate is inference-time; full method trained |
| DyMoS (arXiv 2605.19398) | Image-to-video models over-attend to reference-frame keys. Subtracting a constant from those attention logits in the first denoising steps raises motion. | Yes. Not tested on few-step or causal models |
| Deep Forcing (arXiv 2512.05081) | Larger sink with re-timed positions improves long rollouts. No experiment shows re-timing alone raises motion; too large a sink over-preserves early frames. | Yes, code public |
| LoL (arXiv 2601.16914) | "Sink collapse" from position-encoding periodicity. First collapse at about 33 s. | Yes. Poor fit for our rollout lengths |

### Getting a new state to appear

| Source | Finding | Training-free? |
|---|---|---|
| StateAgent (arXiv 2609.03673) | Predict the post-state, render it as an edited end frame, generate toward it: 32.5 to 69.3. Writing the predicted state into the prompt alone reaches 55.8. | In effect yes (off-the-shelf models) |
| MIST / M3-Agent (arXiv 2610.23542) | Many apparent memory failures are the change never being executed. Six-case LingBot pilot with prompt expansion: establishing the event 0.008 to 0.79, reveal after return 0.04 to 0.19. Rewrites work only when they name the end state. | Yes |
| LiveWorld (arXiv 2603.07145) | Stationary "monitor" rollouts advance off-screen entities, prompted each round by a vision model. Plain Wan image-to-video is a better one-round monitor (71%) than their trained one (62%). Injection on return uses a trained adapter. Event progression 59% against 8-20% for baselines; 18.5% without the evolution step. | Monitor yes; injection no |
| LongLive (arXiv 2509.22622) | A cache written under the old prompt resists a new one ("prompt inertia"). Recomputing the cache fixes it, on a model trained with that step. | Unproven without training |
| Infinity-RoPE (arXiv 2511.20649) | Flushing the cache to the sink plus the last latent makes a new prompt take effect. This raises the sink's share of attention. | Yes |

### Dropped after checking

- "Best consistency means worst evolution" (MBench): not supported by the source.
- "Few-step distilled models lose motion" (Phased DMD): measured on a different distillation setup; does not transfer.

## Red-team rulings (2026-11-14)

Every proposal below was attacked by two adversaries (can it be built in this code; will it move the score) and ruled on by a judge that re-checked the objections against the code and data. A final adversary reviewed the plan as a whole. Summary:

| # | Ruling | Why |
|---|---|---|
| P0 census | Modify | Not free and not decisive alone: frozen and reverted are the same judge level, and all three causes give the same symptom. Read the raw per-pass JSONs for all 24 dev tasks, use three labels (trajectory fault, level 1 with clean trajectory, level 2+), use insight as the still-camera control. Never block building on it. |
| P1 still camera | Modify | The baseline's insight tasks already answer most of it. Otherwise a matched still-versus-turn probe arm, read by eye. |
| P2 return prompt | Modify | Ship candidate is a fixed activity sentence appended to the task prompt. The return switch is a later add-on. Replacing the task prompt would drop instruction-following content. |
| P3 sink down-weight | Modify | No build until a no-sink probe arm shows a same-scene, advanced return. Step 1 alone is the wrong dose for this sampler. |
| P4 flush, P14 recompute | Withdrawn | Flush raises the sink's share from 6 of 14 latents to 6 of 7. Recompute re-encodes the same second-0 latents. Keep only the text re-encode path, which the prompt switch needs. |
| P5 diagnostic | Dropped | Folded into the probe; no proxy for progress exists. |
| P6 side rollout | **Killed** | Slot 0 is re-conditioned from the original image through `y` on every pass, slots 1 to 5 are not at the start pose, and re-running the clean pass on the sink corrupts upstream cache indices. |
| P7 edited anchor | Modify | No latent write, no ledger, no past.dev, no image editor before freeze. At most a donor-rollout K/V copy as a probe. |
| P8 sink surgery | Modify | Only `13:1` and `12:0` change sink size alone (at `18:0` the rolling window also grows). Replace-sink is a no-op on 41 of 43 tasks. |
| P9 memory window | Modify | Not for this family. A GC window A/B only if the baseline shows GC loses on identity at reappearance. |
| P11 best-of-N | **Killed** | A similarity selector prefers the frozen return; a "did it progress" selector restates the judge. Closed loop allows only greedy per-step selection, and the 14B cache cannot be cloned on an 80 GB card. |
| P13 iteration setup | Modify | Select on 14B, not 1.3B. One seed with two judge passes measures judge noise only: use two seeds and count per-task cells. Fix the turn-calibration setting across arms. |
| P16 priority | Modify | Out-of-sight alone cannot reach 2.12: every task at 2.0 there gives about 2.03 overall. Two or three families must move. |

What the whole-plan review added:

- **The dataset caption is benchmark input.** Upstream's Genie 3, HappyOyster and HY-World2 players send `Environment: <image_caption>` plus the task. Our adapter sends only the camera instruction, or "wait and observe" on 29 of 30 insight tasks. The captions already describe the activity as visible evidence, which is the format LingBot v2 was trained on. This is AR-002 (#32).
- **Insight is the cheapest family to move.** It has no gate, no agent and no camera motion, so a judged A/B has no player noise. A task point there is worth 1/120 overall, against 1/172 for out-of-sight.
- **The player is unexamined.** Ours is gpt-4.1-mini; the paper used Claude Haiku 4.5. It oscillated for 24 chunks on GC005.
- **The local baseline is unmeasured**, and every estimate above assumes it equals the web demo's 1.82.
- **The final 171-task run has never been tried** at the shard count it needs.
- **Shared risk of the prompt lever:** StEvo-Bench reports that when LingBot evolves a scene it stops obeying the camera. A richer prompt could cost trajectory gates on GC and out-of-sight.

Order the review defends: fix the freeze time and the fallback; start a baseline full-171 generation without scoring; test the caption prompt on insight; read the baseline; run the caption arm on all 24 dev tasks; one merged probe only if out-of-sight is still at level 1; everything else after freeze.

## Proposals (as first written)

Kept for the record. See the rulings above for what survived.

| # | Proposal | What it tests or changes | Support | Main risk |
|---|---|---|---|---|
| P0 | Failure census | Label each baseline out-of-sight rollout: gate-failed, frozen, reverted, identity changed | Free; decides direction | Six dev tasks is a small sample |
| P1 | Still-camera check | Same images, camera held still, activity prompt, same duration. Does LingBot progress the activity at all? | LingBot insight score 1.95 | If no, return tricks cannot work |
| P2 | Return prompt | Background prompt for scene and activity; at the return chunk, a prompt stating the progressed state as visible; reset the text cache | LingBot's training design; StateAgent; MIST | Demo with a prompt harness still scored 1.16 |
| P3 | Sink down-weight | Subtract a constant from attention to the 6 sink latents at denoising step 1, return chunks only | DyMoS | Untested on few-step causal models; identity drift |
| P4 | Cache flush at return | Keep sink plus last latent so new text takes effect; pair with P3 or P6 | Infinity-RoPE | Alone it strengthens the sink |
| P5 | Sink-preference diagnostic | Log per-layer fraction of heads preferring sink keys during away and return chunks | DySink | Needs attention scores the fused kernel does not expose |
| P6 | Side rollout as state writer | Second session, still camera, activity prompt, while the camera is away; write its final latents into the sink slots on return | LiveWorld (monitor works untrained) | Injection untested without training |
| P7 | Edited anchor | Language model predicts the state, image editor renders it, write it into the sink. Optional entity ledger, with past.dev for the text side | StateAgent; workstream C | Seams; extra models; latency |
| P8 | Sink surgery | Shrink, replace with latest in-view latents, or re-time positions; against a no-sink control | Reward Forcing; AdaState | Sink was trained in; loses identity |
| P9 | Memory window and keyframe pinning (PR #37) | Bigger window, pinned keyframes, turn-back probe | LingBot authors name memory as their limit | Target view is never evicted on these tasks |
| P11 | Best-of-N on return | Sample 2-4 seeds for the return chunks, pick with a cheap check | Generic | Cannot create progress the model never samples; cost |
| P13 | Iteration setup | 1.3B, dataset mode, 6 dev tasks, 2 judge passes, then 14B closed loop and heldout | WRBench: scale does not help | Open loop may not predict closed loop |
| P14 | Cache recompute under new prompt | LongLive-style | LongLive | Shown only on a model trained with it |
| P16 | Priority on this family | Out-of-sight is a quarter of the mean; reaching Genie's 1.81 adds about 0.16 overall | Score arithmetic | Other families may be cheaper |

### Proposed test order (nothing launched)

1. P0 when `lb14-session-dev-v1` posts results.
2. P1.
3. P2 and P3, as a 2x2 on the dev out-of-sight tasks.
4. P6 or P7 if 3 shows the return can be moved.
5. P8 only with the no-sink control.

P9 is deprioritised for this family: on a clean return the cache analysis shows the returned view is retained. This order is superseded by the red-team order above.

## Honesty rules for these tests

- The model gets only what a player has: the first frame and the task prompt. Descriptions come from a vision model looking at the frame, never from the judge's `questions` field or rubric text.
- One method for all tasks. Tune on dev, confirm once on heldout.
- Report the other three families with every change; a sink change that helps here may cost consistency elsewhere.
- Watch the videos. A prompt that says "the activity continues" could produce motion that satisfies the judge without being physically sensible.

## Open questions

- What do our own out-of-sight rollouts look like: frozen, reverted, or different?
- Does our local gate pass rate match the 93% reported for the demo?
- Does LingBot causal-fast progress an activity under a still camera for 5 to 10 seconds with an activity prompt?
- Can a frame written into the sink slots be accepted without a seam?

## Sources

- PlayWorld: https://arxiv.org/abs/2608.13552, https://github.com/kxding/PlayWorld
- LingBot-World v2: https://arxiv.org/abs/2607.07534, https://github.com/Robbyant/lingbot-world-v2
- LingBot-World: https://arxiv.org/abs/2601.20540
- StEvo-Bench: https://arxiv.org/abs/2603.13215, https://ziqi-ma.github.io/blog/2026/outofsight/
- WRBench: https://arxiv.org/abs/2606.20545
- LiveWorld: https://arxiv.org/abs/2603.07145
- StateAgent: https://arxiv.org/abs/2609.03673
- MIST / M3-Agent: https://arxiv.org/abs/2610.23542
- LongLive: https://arxiv.org/abs/2509.22622
- Infinity-RoPE: https://arxiv.org/abs/2511.20649
- DyMoS: https://arxiv.org/abs/2605.19398
- Deep Forcing: https://arxiv.org/abs/2512.05081
- LoL: https://arxiv.org/abs/2601.16914
- Reward Forcing: https://arxiv.org/abs/2512.04678
- Rolling Sink: https://arxiv.org/abs/2602.07775
- AdaState: https://arxiv.org/abs/2605.30349
- DySink: https://arxiv.org/abs/2605.21028
- Phased DMD: https://arxiv.org/abs/2510.27684
