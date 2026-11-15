# The autoresearch loop: how it worked, why it stalled, and what changed

Date: 2026-11-15. Question: why did the autoresearch loop produce four ideas and no evaluations in its first hours, and how fast can one idea be tested?

Provenance: a study by the coordinator session on Saturday evening (Pacific) of the loop's scheduled-task prompt, ledger issue #24, the open PRs and the `experiment` workflow runs, plus timings that this note recomputes from the logs of `lb14-session-agent-dev-v1` (`gen.shard*.log`, `meta.shard*.json`, `videos/*/*_result.json` in its run artifact). Where a figure comes only from the study and was not re-checked, it says so.

## How the loop works

- A scheduled task, "PlayWorld autoresearch loop", fires hourly at minute 57 in a fresh session. Its only memory is the ledger in issue #24.
- One iteration reads the ledger and `results/experiments.csv`, picks one idea, implements it as an off-by-default flag with unit tests, opens one draft PR on `autoresearch/<idea>` with a written evaluation ladder, and updates the ledger. An iteration takes about 8 minutes (22:57 to 23:05 UTC for AR-003).
- Its prompt says it never spends GPU or scoring money itself and never dispatches the `experiment` workflow with `backend=modal`. Humans decide which evaluations to pay for.
- Its stop rule was "4 or more open PRs with the autoresearch label and no evaluation result".
- The evaluation ladder in each PR: tier 1 (4 to 6 dev tasks, dataset actions, 1 judge pass, a baseline arm and a flag arm), tier 2 (24 dev tasks, dataset, 2 passes, both arms), tier 3 (closed loop on dev, 2 passes, both arms). Each tier is launched by a person.

## Why four ideas had zero evaluations

By Saturday 23:57 UTC the ledger held AR-001 (turn calibration, #23, merged with the flag off), AR-002 (caption prompt, #32), AR-003 (GC re-anchor, #46) and AR-004 (player hint, #59). None had been run: no experiment named `ar00x-*` existed among the 21 workflow runs. In the same window other bot sessions dispatched five dev-scale runs and one probe, so dispatch worked; only the loop's own prompt forbade it.

| Bottleneck | Effect |
|---|---|
| Nobody was allowed or assigned to launch tier 1. The loop may not dispatch, and the owner was not watching. | The whole delay: three hours for tests that need about 20 to 40 H100-minutes each. |
| The stop rule counted open labelled PRs. Merged-but-unscored #23 no longer counted, so the loop could keep adding ideas. | More unevaluated branches, some conflicting with each other (#32 and #46 both edit `run.py` and `AGENTS.md`). |
| Each idea paid for its own baseline arm on its own branch, although every flag is off by default and the baselines are the same code. | Half of all tier 1 GPU time and dispatches. |
| The decision rule (mean delta against 2x the pass std, one seed, 4 to 6 tasks) cannot decide. | An idea needed three human-launched rounds (six runs) before a verdict. |
| The model loads once per family per shard (`pwa/gen.py` starts one runner per family). | A fixed cost of about 5 minutes per family per shard, before the first chunk. |
| Results reached the ledger only through the hourly loop, and `pwa compare` needs both runs' eval folders, which live only in the run artifacts. | Up to an hour between a result and the ledger changing, plus a manual step. |

## Measured run speed

From `lb14-session-agent-dev-v1` (14B, closed loop, 24 dev tasks, 4 shards, H100):

| Step | Measured | Source |
|---|---|---|
| Model load, once per family per shard | 267 to 357 s over 16 loads; 10 of 16 between 273 and 290 s | `[lingbot] loaded 14b ... in Ns` |
| First chunk of a rollout (session reset, `y` encode, 29 frames) | 93.5 to 103.1 s on 23 of 24 tasks; 30.6 s on OE064 | `GC005_chunk_01: reset ... in Ns` |
| Each later chunk (33 frames) | 10.4 to 12.3 s, mostly 11.3 to 11.5 s | `continue latent chunks ... in Ns` |
| One rollout, first chunk included, model load excluded | insight (no player) 367 to 443 s; agent tasks 522 to 610 s | `elapsed` in `_result.json` |
| Player calls | about 4 s per chunk on average (agent tasks minus insight, over about 30 chunks); 3 timeouts, retried, 0 fallbacks | as above, and `[agent] error attempt` lines |
| Scoring, 24 tasks x 2 passes, 6 workers | about 10 min (generation finished 23:57:23 UTC, report written 00:07:55 UTC, fetch included) | `meta.shard2of4.json`, `report.json` |

The "over 23 min per task" figure in AGENTS.md was GPU queueing, not generation. Shards 0 and 1 started at 21:35 and 21:36 UTC. Shard 3 started at 22:31, and shard 2 at 23:03:08, two seconds after shard 0 finished at 23:03:06. So fewer H100s were usable than requested: other runs were in flight at the same time, and the quota itself is unconfirmed. Each shard's own time matches the components above: shard 0 ran 8 tasks with 4 model loads in 87 minutes.

From the study, not re-checked here: a one-task dispatch takes about 14.5 minutes end to end; run 43641966866 (GC005 alone) loaded the model in 374 s.

## Accelerations adopted

These are in the plan of record (issue #9) or in effect now:

- **The coordinator session launches runs.** The owner gave it standing authority to dispatch, so evaluations no longer wait for a person. The loop is paused: the ledger has a `PAUSE` line, set on 2026-11-15 00:50 UTC at the owner's direction, and no new ideas are proposed before submission.
- **One integration branch.** AR-002, AR-003 and AR-004 go into `method/candidate-v1`, each behind an off-by-default flag with per-task counters in `meta.json`, so arms differ only by the `extra` input and a flag that did nothing shows in the counters. AR-001 (turn calibration) is evaluated together with AR-004.
- **Shared baselines.** Every arm compares with the same main baselines at two seeds, instead of each idea paying for its own.
- **A decision rule that can decide.** Per-task cells over two seeds, a cell moves only at a full point on the mean of its judge passes, and no gate that passed in the baseline may fail ([red-team-and-plan.md](red-team-and-plan.md)). This replaces the three-tier ladder.
- **One family per dispatch.** Using the `tasks` input with `num_shards=6` gives each GPU one task and one model load: an estimated 15 minutes of generation per arm (load plus one rollout, from the timings above) instead of 142 minutes for the 4-shard baseline. No code change.
- **Requests sized to the real quota.** Until the owner reads the H100 concurrency, plan on about 10; the starting-model 171 run uses 8 shards so it cannot starve dev arms.
- **A screening judge for dev only**, if it agrees with Gemini 3.1 Pro on the 24 baseline videos. Screening scores never go to `results/experiments.csv`.

Not adopted: cross-family sharding in `pwa gen`, an A/B matrix workflow, a warm Modal class that keeps the model loaded, and 1.3B for decisions. Each costs more build time than it saves before freeze, or the quota does not support it.
