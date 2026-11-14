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

## Skills

`.claude/skills/` holds skills copied from [jpoehnelt/skills](https://github.com/jpoehnelt/skills) at commit `0eefeee` (MIT, see `.claude/skills/LICENSE`). The set is `eng-*` (change checklist, blast radius, benchmark checklist, testing, TDD, agent CLI scale), `gh-*` (CI triage, PR feedback loop, PR commit review), `comms-*` (technical writing, unslop, impact, how, why, interrogate, slides) and `agents-*` (correct, reflect, swarm). To update a skill, copy its folder again from upstream. The skills read these repo facts:

- Tests run with `python -m pytest -q` from the repo root. Run one file with `python -m pytest -q tests/test_cli.py`. Build the site with `cd site && npm ci && mkdir -p public && cp ../results/experiments.csv public/ && npm run build`.
- `.github/workflows/ci.yml` has two jobs. `test` runs pytest and needs the PlayWorld submodule and the dataset JSON from Hugging Face. `site` builds the Astro site. `experiment.yml` runs only when started by hand and needs the repo secrets and Modal. `pages.yml` deploys the site on pushes to main.
- `tests/fake_runner.py` stands in for a GPU runner in tests. CI does not test GPU generation, Gemini scoring or agent API calls. Those need a person with keys.
- `pwa` is the benchmark harness (see below). A score claim needs a closed-loop run scored by Gemini 3.1 Pro over 2 or more passes, and a delta of at least 2x the pass std (`pwa compare` checks this).
- The repo has no PR template or changeset. PR and commit titles use `Area: what changed`, for example `Site: ...` or `lingbot: ...`. Squash merges append the PR number.

## CLI (`pwa`)

Setup: `./setup.sh`, fill `config/env.sh`, `source .venv/bin/activate`, `pwa doctor`.

- `pwa doctor [--for gen|score|all] [--runner R] [--json]` check env, data, keys, model roots, torch/cuda.
- `pwa tasks [--split dev|heldout|all|PATH] [--family ..] [--json]` list tasks.
- `pwa gen EXP --split dev --runner sana|NAME|PATH --action-source dataset|agent|refined [--shard i --num-shards n] [--resume] [--notes ..] [-- runner args]` rollouts to `runs/EXP/videos/`, plus `meta.json`, `gen.log`.
- `pwa score EXP [--passes 2] [--workers 4] [--dry-run] [--force]` verifier into `runs/EXP/eval/pass<k>/`; idempotent.
- `pwa report EXP [--split ..] [--strict] [--json] [--md [--site-url U]]` per-family means, std, gate passes, missing; upserts `results/experiments.csv`.
- `pwa compare A B [--json]` deltas B minus A, flags noise (< 2x pass std).
- `pwa media EXP --out DIR [--base-url URL] [--release-url URL] [--index PATH]` web copies of a run's rollouts and the Scenes manifest (used by the workflow; see "Scenes and attribution").
- `pwa failures EXP [--all] [--json] [--md]` missing, gate-failed, or 1.0 tasks with the verifier's reason; `--all` lists every task.
- `pwa upsert-row EXP --into PATH` copy EXP's row from this checkout's `results/experiments.csv` into another CSV by column name (adds missing columns, fails on malformed files); used by the workflow.
- `pwa mark EXP --into PATH --status running|generated|failed|cancelled [--split ..] [--runner ..] [--action-source ..] [--notes ..]` live status row for a run (score-less); used by the workflow. `running` never overwrites a row that has a score, and the other statuses only update a row that still says `running`.
- `pwa ls [--json]` experiments and status.
- `pwa preview EXP TASK` export the contact sheets the judge sees.
- `pwa run EXP ...` gen + score + report.

Typical loop: `pwa run sana-base-dev --split dev --runner sana --action-source dataset --passes 2`, change code, rerun under a new name, `pwa compare sana-base-dev sana-anchor-v1`.

### Adapters

`adapters/<name>/run.py` imports upstream `run_agent`, applies `adapters/common/agent_api.patch` (sets auth by `PLAYER_API_PROVIDER`), swaps `SanaWMEngine` for our engine, and calls `main()`. Wrappers compose around `generate()`, e.g. `AnchorMemory(base_engine)`. `matrix_game3/run.py` is a stub to fill in.

`lingbot_world2` (14B) and `lingbot_world2_1p3b` (1.3B) run LingBot-World v2 causal-fast (PlayWorld paper: 1.82 overall via its web demo). Notes:

- The released code is conditioned on camera poses only; its WASD/IJKL files are never read. `adapters/lingbot_world2/poses.py` turns each key into per-frame camera deltas (signs checked against upstream examples; rotation rates via `LINGBOT_YAW_RAD` / `LINGBOT_PITCH_RAD`).
- Turn calibration, off by default: `-- --lingbot-turn-cal` (Actions input `extra`) or `LINGBOT_TURN_CAL=1`. Dataset tokens are fixed angles in the task prompts ("→*4" = 90 degrees, "u*2" = 40 degrees) but the default 0.03 / 0.01 rad per frame turns 34 / 11 degrees per 20-frame token. The flag sets the rates per call so a token is 22.5 degrees of yaw and 20 of pitch in dataset mode, and a closed-loop chunk is 2 tokens (45 / 40 degrees). Not corrected for tasks whose dataset actions exceed the frame budget and are rescaled by the harness. Unscored until the tier 1 run in its PR.
- Default is a persistent session (`adapters/lingbot_world2/session.py`, `reset/step`): the KV cache (LingBot's only memory), noise generator, camera track and VAE decoder cache survive across agent steps. `<task>_chunk_<NN>` following chunk NN-1 of the same task continues; chunk 01, another task or `<task>_full` (dataset mode: reset plus one long step) resets. A/B baseline: `-- --lingbot-stateless` (Actions input `extra`) or `LINGBOT_SESSION=0`, a fresh upstream rollout per call. `LINGBOT_STREAM_DECODE=0` re-decodes all latents per step instead of streaming.
- Session frame accounting: a request of F frames runs n = round((F-1)/16) latent chunks; the first step returns 16n-3 frames (input frame first), later steps the previous last frame plus 16n new ones, so the harness stitch is seamless (default 33 -> 29, then 33). The stateless path rounds up to 4n+1 frames with latent length a multiple of 4 (33 -> 45; `-- --chunk-frames 29` for exact chunks).
- Translation normalisation: upstream divides by the max per-latent translation of the whole sequence, unknown in closed loop. The session divides by a fixed 4 (one latent of straight single-key motion) and clips norms above 1, which equals upstream whenever the fastest latent is straight single-key motion.
- Weights live in the `pwa-weights` Volume under `/weights/lingbot` (`modal run prefetch_lingbot.py --variant 14b|1.3b`; the workflow does this). Outside the workflow set `PWA_RUNNER=<runner>` when calling `modal run modal_app.py` so the LingBot image is selected.
- License: CC BY-NC-SA 4.0 (non-commercial, share-alike). Code is cloned into the image at a pinned commit, not vendored.

### Upstream quirks (verified)

- IF third-person gate crashes upstream ("third person" vs "third-person"); `pwa` uses the embedded IF check instead.
- Rollouts with no usable score or gate review are dropped from the mean, not counted as 1.0. `pwa report --strict` counts them as 1.0.
- `run_agent.main()` always exits 0, and agent API errors silently fall back to dataset/WAIT actions. `pwa gen` checks mp4s and warns on agent fallback lines. A bad key gives an open-loop rollout, not an error.
- Wait-only insight tasks always regenerate, even with `--resume`.

### Remote runs (GitHub Actions + Modal)

Actions tab -> `experiment` -> Run workflow. Inputs: exp, split or tasks, runner, action_source, backend (modal|local), gpu, num_shards, stage (full|gen-only|score-only), passes, notes, extra (runner args, e.g. `--lingbot-stateless`).

- `backend=modal`: `modal_app.py` runs `pwa gen` shards on Modal GPUs into the `pwa-runs` Volume, then the runner fetches them, scores with Gemini, reports, records the `results/experiments.csv` row on main (from any branch; see below), and uploads `runs/EXP` as an artifact (14 days). The step summary shows the report and failures.
- `backend=local` with `runner=tests/fake_runner.py`: full pipeline test with no GPU.
- Finding and reading runs:
  - The run title in the Actions list and API is `EXP · runner · split or tasks · action_source [· extra] [· stage]`. GitHub does not expose a running job's logs or its inputs, so the title is how to tell runs apart.
  - At launch the workflow adds a `status=running` row for EXP to `results/experiments.csv` on main, with `run_url` linking to the Actions run. The final row (`status=scored`) replaces it. A gen-only run ends as `generated`, and a failed or cancelled job as `failed` / `cancelled`. Rows from before these columns have them blank. These marker steps never fail the job.
  - Every scored run commits `results/reports/EXP.md` to main: the report plus a table of every task with its mean, status and the verifier's reason. Read that instead of downloading the artifact.
  - Each marker is one more commit to main touching `results/experiments.csv`, so it also triggers a Pages deploy.
- LingBot memory probe: Actions tab -> `probe` -> Run workflow, on a ref that contains `probe_lingbot.py` (the #37 branch until it merges). Inputs: exp, variant (1.3b|14b), tasks, angles, holds, windows (e.g. `18:6,-1:0`), dino, gpu. One Modal GPU, no scoring and no results row; the step summary shows `summary.tsv` and `runs/EXP/probe` is uploaded as an artifact.
- Full 171-task runs: `stage=gen-only` first, then `stage=score-only` (jobs cap at ~6 h).
- Repo secrets: `GEMINI_API_KEY`, `PLAYER_API_KEY`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, optional `HF_TOKEN`. Optional repo variables: `PLAYER_API_PROVIDER`, `PLAYER_API_URL`, `PLAYER_MODEL`.
- From a laptop: `modal run modal_app.py --exp NAME --split dev --num-shards 4`, then `modal volume get pwa-runs /NAME runs/`, then `pwa score NAME`.
- The SANA image install in `modal_app.py` is unverified until the first real run.

### Run speed

Update this as runs land: add measured rows, and move a claim from unverified to verified with the run that showed it.

Sharding is per family: `pwa/gen.py::shard_tasks()` (mirroring upstream `run_agent`) assigns task `i` of each family to shard `i % num_shards`, and a shard runs its families one after another. So generation wall clock is roughly `sum over families of ceil(n_family / num_shards) * min_per_task + load_per_shard`, and shards beyond the largest family get no work. `modal_app.py` maps each shard to its own GPU container (`gen_shard.starmap`) with no cap in code.

- dev (6 per family): 4 shards -> busiest shard runs 8 tasks; 6 shards -> 4 tasks, the floor. More than 6 shards adds nothing.
- all (gc 48, if 50, insight 30, outsight 43): 4 -> 44 tasks per shard, 8 -> 23, 24 -> 9, 50 -> 4.

Verified:
- Launching several `experiment` runs at once can fail with Modal `App create rate limit exceeded` (`RESOURCE_EXHAUSTED`) in the prefetch step, before any GPU starts. Stagger dispatches by 1-2 min; rerun under the same name is fine if nothing was generated.
- Scoring runs on the Actions runner with `pwa score --workers 6`; it is serial after generation.
- The single-task GC005 time (~15 min) underestimates dev tasks: at 23:40 UTC on 2026-11-14, `lb14-turncal-dev-v1` (busiest shard 4 tasks) was still generating after 94 min and `lb14-session-dev-v1` (8 tasks) after 126 min, so a closed-loop 14B dev task takes over ~23 min on average unless a shard is stuck. Budgets below assume 15 min and are optimistic.

Unverified (check and update):
- Concurrent H100 containers available on our quota (`lb14-turncal-dev-v1` asked for 24, but only 6 have dev work).
- Whether a shard with no tasks exits before loading the model.
- Split of per-task time between model load, denoising and agent API calls (read from `gen.log`).

Levers, biggest first: raise `num_shards` up to the largest family size (dev: 6); one task per GPU would need cross-family sharding in `pwa gen`; 1.3B for A/B, 14B to confirm; `--action-source dataset` for A/B only (no agent calls, not for final numbers); `tasks` input to run only the family a method targets; start the next A/B while the last one runs.

| Exp | Runner | Tasks | Shards | GPU | Gen wall clock | Min/task | Notes |
|---|---|---|---|---|---|---|---|
| lb14-session-agent-gc005-v1 | lingbot_world2 | 1 | 1 | H100 | <=16 min | <=16 (incl. load) | closed loop; upper bound, gen start to job end incl. scoring |

Full 171-task budget at ~15 min/task: 4 shards ~11 h (over the 6 h job cap), 8 shards ~5.8 h, 24 shards ~2.3 h, 50 shards ~1 h.

### Results site

Live at https://benceruleanlu.github.io/playworld-advancement/. `site/` is an Astro project (static output, base `/playworld-advancement`): `src/pages/index.astro` composes section components from `src/components/`, styles live in `src/styles/global.css`, and all data rendering is client-side in `src/scripts/app.js`. Local: `cd site && npm ci && mkdir -p public && cp ../results/experiments.csv public/ && npm run dev` (or `npm run build` to `site/dist/`). Astro is pinned to an exact version at least two weeks old; CI's `site` job builds it on every PR. It fetches `results/experiments.csv` from `main` at view time, so new rows appear without a redeploy; the `experiments.csv` bundled by the workflow is only a fallback. Rows from runs on any branch land on main's CSV: the Commit step upserts just that row (`pwa upsert-row EXP --into <main checkout>`) into a separate checkout of main and pushes one commit touching only `results/experiments.csv`, so branch code never reaches main (`.github/scripts/push_results.sh` stages only `results/`). The `branch` column records the launch ref (`GITHUB_REF_NAME`, else `git rev-parse --abbrev-ref HEAD`); the site shows it, filters on it, and badges any non-`main` branch as "unmerged code". Rows without the column show a dash. `.github/workflows/pages.yml` builds `site/` and deploys `site/dist` with the official Pages actions on pushes to `main` touching `site/**`, `results/experiments.csv` or the workflow, and on manual `workflow_dispatch`. One-time admin setting: Settings -> Pages -> Source: "GitHub Actions". If it is ever set to "Deploy from a branch", GitHub's own "pages build and deployment" runs on every push to main and overwrites the site with the raw repo. Honesty badges follow the rules above: `dataset` is "open loop, A/B only", non-`all` splits are "partial", `fake_runner` rows are "pipeline test" (hidden by default). Real rows with fewer than 24 tasks or under 2 verifier passes are "smoke test": listed and plotted, but never the headline, ruler marker, family bars or best-so-far line. Preview locally with `?csv=name.csv` (same-origin file). Page story content (task-family blurbs, the "What we changed" method cards with status shipped|testing|planned, a one-line `what` stating what exists, a longer `body` shown under Details, evidence experiment names and PR links) lives in the `FAMINFO` and `METHODS` arrays in `src/scripts/app.js`; update a card when its work lands. Copy is observational: say what is built and what was measured, not goals; every card is one row in a single list (name, status badge, measured result) that opens on click; `planned` cards show "open PR" and "not merged". The headline, ruler, family bars, protocol checks (closed loop, full 171, 2+ passes, every task scored: `n_missing` and `n_dropped` both 0, unknown for rows without `n_dropped`, code on main) and the Progress table are derived from the CSV. Sections are separated by a hairline and moderate padding; do not force full-screen sections (tried, it left large empty bands). Tables must not scroll horizontally at 360-1280 px: secondary columns use `hide-sm`, headers can carry a short phone label. The Actions step summary uses `pwa report EXP --md` and `pwa failures EXP --md`.

#### Scenes and attribution

Every scored `experiment` run publishes its rollouts. The "Publish scenes" step runs `pwa media EXP --out DIR --base-url URL --release-url URL`, which re-encodes each rollout to 480p H.264 (`TASK.mp4`, no audio, faststart) with a poster frame (`TASK.jpg`) and writes `EXP.json`: per task the family, mean, status, the verifier's reason (the judge's own text, often Chinese) and the asset URLs. `pwa media` also writes `RELEASE_NOTES.md`, crediting the model from the run's `meta.json` runner (`MODELS` in `pwa/media.py`; add an entry for a new runner), and publishes nothing for `fake_runner` pipeline tests. The step uploads the clips to a GitHub Release `run-EXP` (created at the run's commit, never marked latest; a rerun clobbers the assets) whose notes carry the attribution and license. The commit step copies `EXP.json` to `results/media/` on main and adds the run to `results/media/index.json`. The site's Scenes section reads both like the CSV, and `pages.yml` bundles `results/media` as a fallback. The step is `continue-on-error`, so a media failure never loses the scored row.

Attribution must stay correct everywhere it appears: the site's footer credits and Scenes line, README "Credits", and the release notes in `experiment.yml`. Facts: PlayWorld is Ding et al., arXiv:2608.13552 (code kxding/PlayWorld, no license; data jocelynd/playworld-bench). Its task images come from Pexels and web image search with source-specific terms, and the task JSON does not record each image's source. LingBot-World v2 is the Robbyant Team, arXiv:2607.07534, CC BY-NC-SA 4.0. Its weights and modules run unchanged, but `adapters/lingbot_world2/session.py` re-implements its sampling loop, so never call our use "unmodified". Credit the model that actually generated a run, never LingBot by default. Scene videos are released under CC BY-NC-SA 4.0, non-commercial, and removal requests go to an issue titled "Scene removal request". Reference scores for Genie 3 (Google DeepMind), SANA-WM (NVIDIA), Matrix-Game 3.0 (Skywork AI) and LingBot come from the PlayWorld paper.

## Plan (30 hours)

Submission due Sunday 14:30: repo link, 2-minute demo video, short description. No commits before the event starts.

### Reference scores (paper, full benchmark, 1-5)

| Model | GC | IF | Insight | Out-of-sight | Overall |
|---|---|---|---|---|---|
| Genie 3 | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| LingBot-World v2 (web demo) | 2.04 | 2.13 | 1.95 | 1.16 | 1.82 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |

Genie 3 is weak on insight and out-of-sight. That is where we win. LingBot already beats Genie 3 on insight (1.95 vs 1.51); its gap is out-of-sight (1.16) and GC.

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

Cut: fine-tuning, full pose-indexed spatial memory. Re-injecting the first frame when the pose returns near the start is in PR #46 (GC only, opt-in, unscored). Out-of-sight hypotheses and test plan: issue #48.


### Compute

- Generation (SANA-WM, Matrix-Game 3.0) needs CUDA GPUs: run it on Modal, sharded.
- Mac Studio (96 GB): `pwa`, scoring (Gemini), agent player and planner calls (OpenAI), proxy metrics on short clips, reviewing rollouts. The upstream SANA runner falls back to CPU off CUDA, so do not generate there.
- Agent player: OpenAI `gpt-4.1-mini` by default (`PLAYER_API_PROVIDER=openai`). Scorer stays Gemini 3.1 Pro so numbers compare to the leaderboard.

## Judging

This is a hackathon challenge, you will be scored on 5 criteria, equal weight (20% each):

Research rigour: clear question, sound experiment design, baselines or ablations, claims backed by results
Novelty: a new idea, method or use case, beyond existing papers and open-source baselines
Results: a measurable result on a real problem or benchmark, ideally against a baseline; a working live demo
Autonomy & self-improvement: how much of the research loop runs without a human; extra credit if it gets better from its own results
Interpretability & reproducibility: decisions can be followed (logs, traces, sources), code runs, failures reported honestly