# Agent and contributor notes

Hackathon repo: raise an open world model's PlayWorld score above Genie 3 (2.12) with inference-time methods. Project docs live in this file (README.md is the public landing page); do not add a docs/ directory.

## Layout

- `third_party/PlayWorld/` upstream benchmark, pinned submodule. No license: import or subprocess it, never copy its code into this repo.
- `adapters/<name>/run.py` world-model runners. They reuse the upstream closed-loop harness and swap in our engine.
- `pwa/` iteration CLI (`pwa --help`).
- `splits/` dev (24) / heldout (147) / all (171) task lists. Regenerate with `splits/make_splits.py`; do not hand-edit.
- `runs/<exp>/` rollouts, verifier output, logs (git-ignored).
- `results/experiments.csv` shared experiment log (committed).

## Rules

- New experiment name for every run. Upstream `--skip-done` silently reuses old videos; `pwa gen` refuses existing dirs unless `--resume`.
- Iterate on `dev`. Do not score `heldout` before code freeze.
- Final numbers must be closed loop (`--action-source agent` or `refined`) and scored with Gemini 3.1 Pro at the upstream sampling settings. `--action-source dataset` is for fast A/B only.
- Do not change verifier FPS, resolution, or JPEG settings.
- A delta smaller than 2x the pass-to-pass std is noise.
- Secrets live in `config/env.sh` only. Never print or commit key values.

## CLI (`pwa`)

Setup: `./setup.sh`, fill `config/env.sh`, `source .venv/bin/activate`, `pwa doctor`.

- `pwa doctor [--for gen|score|all] [--runner R] [--json]` check env, data, keys, model roots, torch/cuda.
- `pwa tasks [--split dev|heldout|all|PATH] [--family ..] [--json]` list tasks.
- `pwa gen EXP --split dev --runner sana|NAME|PATH --action-source dataset|agent|refined [--shard i --num-shards n] [--resume] [--notes ..] [-- runner args]` rollouts to `runs/EXP/videos/`, plus `meta.json`, `gen.log`.
- `pwa score EXP [--passes 2] [--workers 4] [--dry-run] [--force]` verifier into `runs/EXP/eval/pass<k>/`; idempotent.
- `pwa report EXP [--split ..] [--strict] [--json]` per-family means, std, gate passes, missing; upserts `results/experiments.csv`.
- `pwa compare A B [--json]` deltas B minus A, flags noise (< 2x pass std).
- `pwa failures EXP [--json]` missing, gate-failed, or 1.0 tasks with the verifier's reason.
- `pwa ls [--json]` experiments and status.
- `pwa preview EXP TASK` export the contact sheets the judge sees.
- `pwa run EXP ...` gen + score + report.

Typical loop: `pwa run sana-base-dev --split dev --runner sana --action-source dataset --passes 2`, change code, rerun under a new name, `pwa compare sana-base-dev sana-anchor-v1`.

### Adapters

`adapters/<name>/run.py` imports upstream `run_agent`, applies `adapters/common/agent_api.patch` (sets auth by `PLAYER_API_PROVIDER`), swaps `SanaWMEngine` for our engine, and calls `main()`. Wrappers compose around `generate()`, e.g. `AnchorMemory(base_engine)`. `matrix_game3/run.py` is a stub to fill in.

### Upstream quirks (verified)

- IF third-person gate crashes upstream ("third person" vs "third-person"); `pwa` uses the embedded IF check instead.
- Rollouts with no usable score or gate review are dropped from the mean, not counted as 1.0. `pwa report --strict` counts them as 1.0.
- `run_agent.main()` always exits 0, and agent API errors silently fall back to dataset/WAIT actions. `pwa gen` checks mp4s and warns on agent fallback lines. A bad key gives an open-loop rollout, not an error.
- Wait-only insight tasks always regenerate, even with `--resume`.

## Plan (30 hours)

Submission due Sunday 14:30: repo link, 2-minute demo video, short description. No commits before the event starts.

### Reference scores (paper, full benchmark, 1-5)

| Model | GC | IF | Insight | Out-of-sight | Overall |
|---|---|---|---|---|---|
| Genie 3 | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |

Genie 3 is weak on insight and out-of-sight. That is where we win.

### Timeline

| Hours | Goal | Exit criterion |
|---|---|---|
| 0-2 | setup.sh, keys, one SANA-WM task generated and scored | one score JSON |
| 2-6 | MG3 adapter in parallel; dev baseline; measure min/task | baseline in results/experiments.csv; base-model go/no-go |
| 6-18 | workstreams A-D | each beats baseline on its family (dev) |
| 18-20 | integrate, closed-loop dev run, 2 passes | combined > baseline |
| **20** | **code freeze**, full 171 closed-loop run, sharded | |
| 20-26 | full run + 2-3 verifier passes | final score with std |
| 26-30 | horizon curve, failure gallery, writeup, demo | submission |

Full-run budget: `171 * min_per_task / n_gpus / 60` must fit in ~6 h. Check at hour 4.

### Workstreams

- **A. Insight progress scheduler.** LLM plans process stages, re-prompt per chunk, stall detector forces progress. WAIT-only tasks run with no agent calls.
- **B. Control / gate fixes.** Action magnitude calibration, pose-checked correction. Gate fail = 1.0 on GC, IF third-person, out-of-sight.
- **C. Out-of-sight state tracker.** Save target crop + description on exit, advance state with LLM, condition on edited anchor on return.
- **D. Eval infra (owner from hour 2).** `pwa`, proxy metrics, horizon curve, failure gallery.

Cut: fine-tuning, full pose-indexed spatial memory. If B finishes early: re-inject first frame when pose returns near start.


### Compute

- Generation (SANA-WM, Matrix-Game 3.0) needs CUDA GPUs: run it on Modal, sharded.
- Mac Studio (96 GB): `pwa`, scoring (Gemini), agent player and planner calls (OpenAI), proxy metrics on short clips, reviewing rollouts. The upstream SANA runner falls back to CPU off CUDA, so do not generate there.
- Agent player: OpenAI `gpt-4.1-mini` by default (`PLAYER_API_PROVIDER=openai`). Scorer stays Gemini 3.1 Pro so numbers compare to the leaderboard.
