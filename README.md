# playworld-advancement

How long can a generated world hold together while an agent plays in it?

We take an open world model, LingBot-World v2 14B, and change how it is run at inference time to raise its [PlayWorld](https://kxding.github.io/project/PlayWorld/) score toward Genie 3 (2.12). The track allows fine-tuning; we chose not to train for lack of time (reasons in [research/red-team-and-plan.md](research/red-team-and-plan.md)). Iterate hackathon, Track 4: World Models.

## Status

The plan of record is [issue #9](https://github.com/benceruleanlu/playworld-advancement/issues/9). The goal by Sunday 14:30 Pacific is a closed-loop 171-task score for the starting model (LingBot-World v2 14B, persistent session, every method flag off) and for our method on the same harness, plus evidence of where the world still breaks.

- **On `main`:** a persistent session that keeps the model's memory (its KV cache) across agent steps, and the `pwa` harness with a per-task decision readout (`pwa cells`). Thirty-five method flags are merged, each off by default with per-task counters. Some change what the AI player is told (where the camera is, when to stop), some change the world model's text prompt (scene caption, per-family cues), and some change the model's inputs or internals (turn calibration, re-anchoring, camera and text conditioning strength, attention window, sampling noise, a yaw servo that corrects each turn from the rendered frames). [AGENTS.md](AGENTS.md#adapters) describes each one.
- **Adopted so far: nothing.** A flag is adopted only if per-task scores move by a full point on both of two seeds, on the 14B model at full length with the AI player, and no gate that passed in the baseline fails. No run meets that bar yet.
- **Where the runs stand (Sunday 08:25 Pacific):** the starting-model run on all 171 tasks has not started. The official judge has been unavailable since about 03:40 UTC Sunday, when its API credits ran out; a second route to the same model through Google Cloud is merged and has not made a live call. Workflow runs now default to the `gpt-6-luna` proxy judge, whose scores are kept in a separate file and are not comparable to the leaderboard. So the best official closed-loop score is still the 24-task diagnostic below (1.64), and every run generated since has clips and no official score. Scored before the outage, all at one seed and mostly with fixed actions in place of the AI player (open loop, so they rank model-side flags and cannot produce a reported score): no flag moved a task by a full point in a way that repeated. Dropped as harmful or null: the conditioning schedule, sink key scale, the GC chunk director, GC turn easing and the GC completion hint. Pose-indexed memory never fired in its first two runs, and after a fix it fires and shows no gain, so it is dropped too. The judge limits how these read: three control runs with the same settings and seed gave task means up to 1.38 apart, and it moved one task by 1.30 on byte-identical clips. The candidate method is a stack (turn calibration, caption prompt, insight director, slow IF translation, a larger attention window) plus the yaw servo. Measured without any judge, the servo cut the end-of-turn heading error on five GC tasks from between 8 and 96 degrees to under 6, and on a sixth from 96 to 49. Under a proxy judge (`gpt-6-luna`, not comparable to the leaderboard or to any official score), the stack beat no flags on out-of-sight by about one point in all three fixed-action comparisons; the other families did not clear that judge's own noise. None of this is adopted. The first closed-loop run of the stack with the servo against no flags on the 24 dev tasks (`clstk14-dev-v1`) finished generating with most of the method's clips missing: 8 of 24 for the stack with the servo and none for a second variant, against 23 of 24 with no flags. The GPU workspace was disabled partway through generation (as reported in #157), so the candidate has no complete closed-loop run. No run has started since. On the 8 tasks both arms produced, the proxy judge moved one up and one down by a full point, which shows no effect either way. Per-task numbers and the run list: [AGENTS.md](AGENTS.md#status-against-the-timeline).
- **Player:** every compared run uses `gpt-6-luna` as the AI player. In one early run 22 of 110 player decisions were not the player's: its replies came back empty and the harness substituted a recorded action. A fix that retries empty replies and counts the substitutions is merged ([PR #89](https://github.com/benceruleanlu/playworld-advancement/pull/89)). One short check run since then (two tasks, 14 decisions) had no empty replies and no substitutions; no full-length run has confirmed it.
- **Screening judges:** `gemini-4-hydrogen` and `gpt-6-luna` were each checked against the official judge on the 24 baseline videos. Both are more lenient and neither agrees with it task by task, so neither is used to adopt or drop a flag. While the official judge is out, `gpt-6-luna` is used as a proxy judge to compare a control with a treatment scored the same way; it is more lenient than the official judge, so its numbers are never reported as scores. Its calibration against the official judge: [results/reports/lb14-session-agent-dev-v1.openai-gpt-6-luna.md](results/reports/lb14-session-agent-dev-v1.openai-gpt-6-luna.md).
- **Dropped for this event:** out-of-sight memory and state-tracking work, fine-tuning, SANA-WM, Matrix-Game 3.0 and the 1.3B model. Reasons: [research/red-team-and-plan.md](research/red-team-and-plan.md). Since that list was agreed, attention-window and sink flags for out-of-sight have been merged and run with fixed actions anyway; sink key scale lowered out-of-sight, the local-36 arms produced no clips, and the larger-sink arms are the OE039 result above.

## Results

Live leaderboard, charts and baseline comparison: https://benceruleanlu.github.io/playworld-advancement/

Scores on the PlayWorld rubric (1-5, higher is better). Reference rows are from the PlayWorld paper. We have no full-benchmark run yet. Our only scored run of all 24 dev tasks is `lb14-session-agent-dev-v1`: LingBot-World v2 14B with the persistent session, closed loop with the gpt-4.1-mini player, two verifier passes. It is a diagnostic, not the starting-model number: the reference rows cover all 171 tasks, the paper scored LingBot through its web demo, and compared runs now use a different player.

| Model | Geometry | Interaction | Insight | Out-of-sight | Overall |
|---|---|---|---|---|---|
| Genie 3 (closed, record) | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| LingBot-World v2 (web demo) | 2.04 | 2.13 | 1.95 | 1.16 | 1.82 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |
| **Ours, dev split (24 tasks), gpt-4.1-mini player, diagnostic** | 1.83 | 1.81 | 1.58 | 1.33 | 1.64 ± 0.13 |
| **Ours, full benchmark** | no run yet | | | | |

## Quickstart

```bash
git clone --recursive https://github.com/benceruleanlu/playworld-advancement
cd playworld-advancement
./setup.sh                      # venv, deps, dataset
$EDITOR config/env.sh           # Gemini (scorer), OpenAI (agent player), model paths
source .venv/bin/activate
pwa doctor
```

Generation needs a CUDA GPU and runs on Modal from the GitHub Actions `experiment` workflow (see [AGENTS.md](AGENTS.md)). Scoring, reports, and agent calls run anywhere.

## How it works

- `pwa` drives the loop: generate rollouts, score them with the official Gemini 3.1 Pro rubric verifier, report per-family means with pass-to-pass variance, and compare experiments.
- `adapters/` plug world models into the upstream closed-loop harness. LingBot-World v2 14B is the model we work on: a persistent session carries the KV cache across agent steps, and the method flags listed under Status are opt-in. A SANA-WM adapter (one smoke run), a LingBot 1.3B runner and a Matrix-Game 3.0 stub remain but are not used for decisions. Our methods wrap the engine's `generate()` call.
- Generation runs on Modal GPUs, launched from the GitHub Actions `experiment` workflow; every run's row lands in `results/experiments.csv` on `main` and on the results site.
- `splits/` fixes two 24-task dev sets for iteration (`dev`, and `dev2` drawn later from the held-out tasks before any of them was scored; `dev48` is both) and keeps the other 123 tasks held out until the final run.

In the dev baseline the player's actions decided most geometry and out-of-sight scores. It flipped between left and right for whole rollouts, and in 4 of 6 out-of-sight rollouts the camera never returned to the start view, so the judge graded no content. On insight, with no player involved, four of six rollouts were flagged static in at least one scoring. Two scorings of the same video differed by 0.5 or more on 10 of 24 tasks. The census, recomputed from the raw judge files: [research/baseline-census.md](research/baseline-census.md).

Research notes behind the plan (census, red-team rulings, autoresearch loop, out-of-sight analysis): [research/](research/). Contributor rules, CLI reference, plan, and known upstream quirks: [AGENTS.md](AGENTS.md).

## Credits

- **PlayWorld** benchmark, harness, verifier and task data: Ding et al., *PlayWorld: Benchmarking World Models with Agent Players over Long-Horizon Objectives*, [arXiv:2608.13552](https://arxiv.org/abs/2608.13552) (Kuaishou Technology, HKU). Code: [kxding/PlayWorld](https://github.com/kxding/PlayWorld), pinned as a submodule. Data: [jocelynd/playworld-bench](https://huggingface.co/datasets/jocelynd/playworld-bench). Task images come from Pexels and web image search and keep their sources' terms.
- **LingBot-World v2**: Robbyant Team, *Infinite Worlds with Versatile Interactions*, [arXiv:2607.07534](https://arxiv.org/abs/2607.07534), [Robbyant/lingbot-world-v2](https://github.com/Robbyant/lingbot-world-v2), CC BY-NC-SA 4.0. Cloned at a pinned commit, not vendored; its weights and modules run unchanged, and `adapters/lingbot_world2/session.py` re-implements its causal sampling loop.
- Reference scores for Genie 3 (Google DeepMind), [SANA-WM](https://github.com/NVlabs/Sana) (NVIDIA), [Matrix-Game 3.0](https://github.com/SkyworkAI/Matrix-Game) (Skywork AI) and LingBot-World v2 are as reported in the PlayWorld paper.
- Scoring: Gemini 3.1 Pro (Google) through the PlayWorld verifier. Since its credits ran out on Nov 15, later runs are scored by a proxy judge, OpenAI `gpt-6-luna`, and those scores are never reported as results. Agent player: OpenAI `gpt-6-luna` for compared runs; the first dev baseline used `gpt-4.1-mini`.

### Scene videos

Every run that generates videos publishes its rollouts to a GitHub Release named `run-<experiment>`, shown in the site's Scenes section; runs that are not official scores (not scored, capped smoke runs, screening-judge runs) are labelled there. Each release credits the world model that generated it (from the run's recorded runner) and the PlayWorld task images the rollouts start from. They are released under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) for non-commercial use, and re-encoded to 480p. Pipeline-test runs are never published. To request removal of a scene, [open an issue](https://github.com/benceruleanlu/playworld-advancement/issues/new?title=Scene+removal+request).
