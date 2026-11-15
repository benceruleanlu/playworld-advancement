# playworld-advancement

How long can a generated world hold together while an agent plays in it?

We take an open world model, LingBot-World v2 14B, and change how it is run at inference time to raise its [PlayWorld](https://kxding.github.io/project/PlayWorld/) score toward Genie 3 (2.12). The track allows fine-tuning; we chose not to train for lack of time (reasons in [research/red-team-and-plan.md](research/red-team-and-plan.md)). Iterate hackathon, Track 4: World Models.

## Status

The plan of record is [issue #9](https://github.com/benceruleanlu/playworld-advancement/issues/9). The goal by Sunday 14:30 Pacific is a closed-loop 171-task score for the starting model (LingBot-World v2 14B, persistent session, every method flag off) and for our method on the same harness, plus evidence of where the world still breaks.

- **On `main`:** a persistent session that keeps the model's memory (its KV cache) across agent steps; opt-in turn calibration (unscored); the `pwa` harness with a screening-judge option for dev loops and a per-task decision readout (`pwa cells`).
- **Being tested:** a caption prompt for the world model, re-anchoring on geometry tasks and a hint for the AI player, each behind an off-by-default flag with per-task counters. They are merged from the integration branch ([PR #63](https://github.com/benceruleanlu/playworld-advancement/pull/63)) and unscored. A flag is adopted only if per-task scores move by a full point on both of two seeds and no gate that passed in the baseline fails.
- **Player:** every compared run uses `gpt-6-luna` as the AI player. The first baseline used gpt-4.1-mini, and its census showed that player decided most geometry and out-of-sight outcomes.
- **Where the runs stand (Saturday 17:20 Pacific):** the first `gpt-6-luna` runs on the dev tasks failed during generation on Modal, cause not yet found, so the starting-model run on all 171 tasks has not started. Since then only capped smoke runs have finished: rollouts cut to 10 of 30 chunks on three geometry tasks, to see how the player and the flags behave. They carry no official score.
- **Screening judge:** `gemini-4-hydrogen` was checked against the official judge on the 24 baseline videos and is more lenient (it passed every geometry and out-of-sight gate, where the official judge failed 2 of 6 in each). It is not used to adopt or drop a flag.
- **Dropped for this event:** out-of-sight memory and state-tracking work, fine-tuning, SANA-WM, Matrix-Game 3.0 and the 1.3B model. Reasons: [research/red-team-and-plan.md](research/red-team-and-plan.md).

## Results

Live leaderboard, charts and baseline comparison: https://benceruleanlu.github.io/playworld-advancement/

Scores on the PlayWorld rubric (1-5, higher is better). Reference rows are from the PlayWorld paper. We have no full-benchmark run yet. Our only scored dev run, `lb14-session-agent-dev-v1`, covers the 24 dev tasks: LingBot-World v2 14B with the persistent session, closed loop with the gpt-4.1-mini player, two verifier passes. It is a diagnostic, not the starting-model number: the reference rows cover all 171 tasks, the paper scored LingBot through its web demo, and compared runs now use a different player.

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
- `adapters/` plug world models into the upstream closed-loop harness. LingBot-World v2 14B is the model we work on: a persistent session carries the KV cache across agent steps, and opt-in turn calibration makes key presses turn the angles the task prompts assume. A SANA-WM adapter (one smoke run), a LingBot 1.3B runner and a Matrix-Game 3.0 stub remain but are not used for decisions. Our methods wrap the engine's `generate()` call.
- Generation runs on Modal GPUs, launched from the GitHub Actions `experiment` workflow; every run's row lands in `results/experiments.csv` on `main` and on the results site.
- `splits/` fixes a 24-task dev set for iteration and keeps the other 147 tasks held out until the final run.

In the dev baseline the player's actions decided most geometry and out-of-sight scores. It flipped between left and right for whole rollouts, and in 4 of 6 out-of-sight rollouts the camera never returned to the start view, so the judge graded no content. On insight, with no player involved, four of six rollouts were flagged static in at least one scoring. Two scorings of the same video differed by 0.5 or more on 10 of 24 tasks. The census, recomputed from the raw judge files: [research/baseline-census.md](research/baseline-census.md).

Research notes behind the plan (census, red-team rulings, autoresearch loop, out-of-sight analysis): [research/](research/). Contributor rules, CLI reference, plan, and known upstream quirks: [AGENTS.md](AGENTS.md).

## Credits

- **PlayWorld** benchmark, harness, verifier and task data: Ding et al., *PlayWorld: Benchmarking World Models with Agent Players over Long-Horizon Objectives*, [arXiv:2608.13552](https://arxiv.org/abs/2608.13552) (Kuaishou Technology, HKU). Code: [kxding/PlayWorld](https://github.com/kxding/PlayWorld), pinned as a submodule. Data: [jocelynd/playworld-bench](https://huggingface.co/datasets/jocelynd/playworld-bench). Task images come from Pexels and web image search and keep their sources' terms.
- **LingBot-World v2**: Robbyant Team, *Infinite Worlds with Versatile Interactions*, [arXiv:2607.07534](https://arxiv.org/abs/2607.07534), [Robbyant/lingbot-world-v2](https://github.com/Robbyant/lingbot-world-v2), CC BY-NC-SA 4.0. Cloned at a pinned commit, not vendored; its weights and modules run unchanged, and `adapters/lingbot_world2/session.py` re-implements its causal sampling loop.
- Reference scores for Genie 3 (Google DeepMind), [SANA-WM](https://github.com/NVlabs/Sana) (NVIDIA), [Matrix-Game 3.0](https://github.com/SkyworkAI/Matrix-Game) (Skywork AI) and LingBot-World v2 are as reported in the PlayWorld paper.
- Scoring: Gemini 3.1 Pro (Google) through the PlayWorld verifier. Agent player: OpenAI `gpt-6-luna` for compared runs; the first dev baseline used `gpt-4.1-mini`.

### Scene videos

Every run that generates videos publishes its rollouts to a GitHub Release named `run-<experiment>`, shown in the site's Scenes section; runs that are not official scores (not scored, capped smoke runs, screening-judge runs) are labelled there. Each release credits the world model that generated it (from the run's recorded runner) and the PlayWorld task images the rollouts start from. They are released under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) for non-commercial use, and re-encoded to 480p. Pipeline-test runs are never published. To request removal of a scene, [open an issue](https://github.com/benceruleanlu/playworld-advancement/issues/new?title=Scene+removal+request).
