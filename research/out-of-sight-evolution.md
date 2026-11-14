# Out-of-sight evolution on LingBot-World v2: hypothesis, literature, proposals

Date: 2026-11-14. Question: why does LingBot-World v2 score 1.16 on PlayWorld's out-of-sight family, and what inference-time change could raise it?

Provenance: the task analysis and cache analysis were run in this repo. The literature section comes from two research passes; the second read the primary papers in full (and public code where it exists). Claims not read from a primary source are marked (unverified). Nothing here has been tested on a GPU yet, and we have no judge output for our own out-of-sight rollouts. Companion note: [memory-for-world-models.md](memory-for-world-models.md).

## Bottom line

- The family is graded on whether the scene **progressed** while unseen. A return that looks the same as before scores the minimum. Remembering the scene is not the task.
- LingBot's failure is a content failure, not a camera failure: PlayWorld reports a 93% trajectory-gate pass rate for LingBot-World2 on this family, the highest of nine models.
- The literature agrees on the symptom ("frozen, not forgotten") across this model class. The cause on LingBot v2 causal-fast is ours to prove.
- The best-supported cheap levers are text that states the progressed state, and weakening or rewriting the pinned first frames at the moment the camera returns. More memory is not supported.

## What the task measures

From `data/outsight/data.json` and `third_party/PlayWorld/metrics/vqa/rubric.py`:

- 43 tasks, all first person. Typical prompt: "Turn the camera right 90 degrees, then return to the starting view", over an image of an ongoing activity (painting, pouring, an escalator).
- Every task carries the same policy: a static or near-static result is capped at 1.0; a reset or revert is a severe failure; any verified persistent change earns at least 2; identity starts to matter at level 3.
- The comparison is the last stable view before leaving against the first stable view after returning, not against the first frame.
- A separate trajectory gate (camera leaves and returns) scores 1.0 on fail.

## What the cache does on these tasks

From `python -m adapters.lingbot_world2.cache_model --split all --family outsight`:

- LingBot keeps the first 6 latents forever (the "sink": the input image plus about 20 frames) and the previous 8 latents (about 32 frames, 2 s).
- In 43 of 43 tasks the dataset trajectory ends at the starting view, which is in the sink and never evicted.
- Evictions only hit views passed in transit: 36 of 43 tasks with default turn rates, 18 of 43 with turn calibration.
- So on return, the model's only memory of the target view is the scene at second 0.

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

## Proposals

Status key: **census** = waits for the baseline's judge reasons; **untested** = no evidence on LingBot v2 yet. A red-team review of every proposal is in progress; rulings will be added below.

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

P9 is deprioritised for this family: the cache analysis shows the returned view is always retained.

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
