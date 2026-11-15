# playworld-advancement

How long can a generated world hold together while an agent plays in it?

We take an open world model, LingBot-World v2, and change how it is run at inference time to raise its [PlayWorld](https://kxding.github.io/project/PlayWorld/) score past Genie 3 (2.12). No training. On `main` so far: a persistent session that keeps the model's memory across agent steps, and opt-in turn calibration. Re-anchoring, a player hint and out-of-sight state tracking are in open PRs and issues. Iterate hackathon, Track 4: World Models.

## Results

Live leaderboard, charts and baseline comparison: https://benceruleanlu.github.io/playworld-advancement/

Scores on the PlayWorld rubric (1-5, higher is better). Reference rows are from the PlayWorld paper. We have no full-benchmark run yet. Our best run so far, `lb14-session-agent-dev-v1`, covers the 24 dev tasks: LingBot-World v2 14B with the persistent session, closed loop, two verifier passes. The reference rows cover all 171 tasks, and the paper scored LingBot through its web demo, so the dev row is not directly comparable to them.

| Model | Geometry | Interaction | Insight | Out-of-sight | Overall |
|---|---|---|---|---|---|
| Genie 3 (closed, record) | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| LingBot-World v2 (web demo) | 2.04 | 2.13 | 1.95 | 1.16 | 1.82 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |
| **Ours, dev split (24 tasks)** | 1.83 | 1.81 | 1.58 | 1.33 | 1.64 ± 0.13 |
| **Ours, full benchmark** | no run yet | | | | |

## Quickstart

```bash
git clone --recursive https://github.com/benceruleanlu/playworld-advancement
cd playworld-advancement
./setup.sh                      # venv, deps, dataset
$EDITOR config/env.sh           # Gemini (scorer), OpenAI (agent player), model paths
source .venv/bin/activate
pwa doctor
pwa run sana-base-dev --split dev --runner sana --action-source dataset --passes 2
```

Generation needs a CUDA GPU. Scoring, reports, and agent calls run anywhere.

## How it works

- `pwa` drives the loop: generate rollouts, score them with the official Gemini 3.1 Pro rubric verifier, report per-family means with pass-to-pass variance, and compare experiments.
- `adapters/` plug world models into the upstream closed-loop harness: SANA-WM, LingBot-World v2 (14B and 1.3B, with a persistent session so the KV cache carries across agent steps, and opt-in turn calibration so key presses turn the angles the task prompts assume), and a Matrix-Game 3.0 stub. Our methods wrap the engine's `generate()` call.
- Generation runs on Modal GPUs, launched from the GitHub Actions `experiment` workflow; every run's row lands in `results/experiments.csv` on `main` and on the results site.
- `splits/` fixes a 24-task dev set for iteration and keeps the other 147 tasks held out until the final run.

In the dev baseline the player's actions decided most geometry and out-of-sight scores. It flipped between left and right for whole rollouts, and in 4 of 6 out-of-sight rollouts the camera never returned to the start view, so the judge graded no content. The census is in [issue #49](https://github.com/benceruleanlu/playworld-advancement/issues/49).

Contributor rules, CLI reference, plan, and known upstream quirks: [AGENTS.md](AGENTS.md).

## Credits

- **PlayWorld** benchmark, harness, verifier and task data: Ding et al., *PlayWorld: Benchmarking World Models with Agent Players over Long-Horizon Objectives*, [arXiv:2608.13552](https://arxiv.org/abs/2608.13552) (Kuaishou Technology, HKU). Code: [kxding/PlayWorld](https://github.com/kxding/PlayWorld), pinned as a submodule. Data: [jocelynd/playworld-bench](https://huggingface.co/datasets/jocelynd/playworld-bench). Task images come from Pexels and web image search and keep their sources' terms.
- **LingBot-World v2**: Robbyant Team, *Infinite Worlds with Versatile Interactions*, [arXiv:2607.07534](https://arxiv.org/abs/2607.07534), [Robbyant/lingbot-world-v2](https://github.com/Robbyant/lingbot-world-v2), CC BY-NC-SA 4.0. Cloned at a pinned commit, not vendored; its weights and modules run unchanged, and `adapters/lingbot_world2/session.py` re-implements its causal sampling loop.
- Reference scores for Genie 3 (Google DeepMind), [SANA-WM](https://github.com/NVlabs/Sana) (NVIDIA), [Matrix-Game 3.0](https://github.com/SkyworkAI/Matrix-Game) (Skywork AI) and LingBot-World v2 are as reported in the PlayWorld paper.
- Scoring: Gemini 3.1 Pro (Google) through the PlayWorld verifier. Agent player: OpenAI `gpt-4.1-mini`.

### Scene videos

Every run that generates videos publishes its rollouts to a GitHub Release named `run-<experiment>`, shown in the site's Scenes section; runs that are not official scores (not scored, capped smoke runs, screening-judge runs) are labelled there. Each release credits the world model that generated it (from the run's recorded runner) and the PlayWorld task images the rollouts start from. They are released under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) for non-commercial use, and re-encoded to 480p. Pipeline-test runs are never published. To request removal of a scene, [open an issue](https://github.com/benceruleanlu/playworld-advancement/issues/new?title=Scene+removal+request).
