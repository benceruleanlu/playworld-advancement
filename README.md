# playworld-advancement

How long can a generated world hold together while an agent plays in it?

We take an open world model and add inference-time memory, state tracking, and re-anchoring to raise its [PlayWorld](https://kxding.github.io/project/PlayWorld/) score past Genie 3 (2.12), without training from scratch. Iterate hackathon, Track 4: World Models.

## Results

Live leaderboard, charts and baseline comparison: https://benceruleanlu.github.io/playworld-advancement/

Scores on the PlayWorld rubric (1-5, higher is better). Reference rows are from the PlayWorld paper. Ours are filled in from `results/experiments.csv`.

| Model | Geometry | Interaction | Insight | Out-of-sight | Overall |
|---|---|---|---|---|---|
| Genie 3 (closed, record) | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| LingBot-World v2 (web demo) | 2.04 | 2.13 | 1.95 | 1.16 | 1.82 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |
| **Ours** | TBD | TBD | TBD | TBD | TBD |

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

Contributor rules, CLI reference, plan, and known upstream quirks: [AGENTS.md](AGENTS.md).

## Credits

- [PlayWorld](https://github.com/kxding/PlayWorld) benchmark, harness, and verifier (Kuaishou Technology, HKU), pinned as a submodule. Dataset: [jocelynd/playworld-bench](https://huggingface.co/datasets/jocelynd/playworld-bench).
- [SANA-WM](https://github.com/NVlabs/Sana), [LingBot-World v2](https://github.com/Robbyant/lingbot-world-v2) (CC BY-NC-SA 4.0, cloned at a pinned commit, not vendored) and [Matrix-Game 3.0](https://github.com/SkyworkAI/Matrix-Game) world models.
- Gemini 3.1 Pro (verifier), OpenAI `gpt-4.1-mini` (agent player).
