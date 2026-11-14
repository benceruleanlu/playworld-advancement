# Memory for world models: 2026 research notes

Date: 2026-11-14. Question: how can memory raise an open world model's PlayWorld score?

Follow-up: [out-of-sight-evolution.md](out-of-sight-evolution.md) covers the out-of-sight family on LingBot-World v2 (open weights, the model we now run) and finds that family is graded on scene progress, not recall.

Provenance: compiled from three web-research passes over arXiv and project pages. Most GitHub repos could not be opened, so "code public" claims are as stated on paper or project pages. Confirm before committing time. Items marked (unverified) were not confirmed.

## Bottom line

Matrix-Game 3.0 (MG3) already ships pose-retrieved frame memory, so "add a memory bank" is not the gap. On PlayWorld it sits at the floor (1.00) on out-of-sight and insight evolution. The cheapest wins are likely memory of state plus anchoring, not more frame recall. This matches workstreams A to C in AGENTS.md; the items below are candidates for B's stretch goal and for the cut "pose-indexed spatial memory".

## What PlayWorld measures

- A 1 to 5 rubric judged by Gemini 3.1 Pro, averaged over geometry consistency, interaction fidelity, out-of-sight evolution, insight evolution.
- Validity gate: a rollout failing trajectory validity or subject reachability gets 1. MG3 passes 68.2% of the time, Genie 3 87.1%.
- MG3: 1.14 overall, exactly 1.00 on out-of-sight and insight. Whether that is the gate or a true memory failure is unknown (unverified). Check with `pwa failures`.
- Protocol: Claude Haiku 4.5 agent, WASD, arrows, WAIT, up to 40 steps (10 to 60 s), 171 cases.
- Other paper scores: HappyOyster 1.92, LingBot-World2 1.82, LingBot-World 1.78, HY-World2 1.61, Hunyuan-GameCraft 1.42, HY-WorldPlay 1.21.
- Reported failure modes (all models): landmarks regenerated as inconsistent copies on revisit; out-of-sight targets return unchanged, misplaced, or replaced; processes stall or reset; clipping through solids.

## Base model memory, as shipped

| Model | Memory | Notes |
|---|---|---|
| Matrix-Game 3.0 | Past frames retrieved by camera pose and FOV overlap, shared self-attention with recent and noisy latents, relative Plucker encoding, optional first-frame sink latent, error buffer trained on own residuals | Wan2.2-TI2V-5B finetune. Trained with 5 memory + 4 past + 10 noisy latents. Single-GPU VRAM not documented |
| ABot-World-0 | Bounded local KV cache with rolling eviction, reference-character identity tokens. No persistent scene memory (listed as future work) | Wan2.2-TI2V-5B finetune, about 19 GiB on one RTX 5090, about 16 FPS, Apache-2.0 |
| Genie 3 | Closed. DeepMind describes consistency as emergent, about one minute of visual memory, no explicit 3D | Context length undisclosed |

## Candidate methods, ranked by gain per hour

| # | Idea | Training | Effort | Targets |
|---|---|---|---|---|
| 1 | Diagnose: run PlayWorld on the base model, log which gate or rubric question fails | None | 4-6 h | Everything |
| 2 | Anchor or sink frame plus compressed distant history in the cache (WorldTrace, Deep Forcing, FreqForcing) | None | 6-12 h | Geometry, drift |
| 3 | Loop closure: re-insert evicted clean latents when the camera returns near an old pose (WorldKV, Closing the Loop) | None | 8-16 h | Geometry, revisits |
| 4 | VLM state tracker: ledger of objects and off-screen processes, fed back as conditioning on return | None | 6-10 h | Out-of-sight, insight |
| 5 | Pathwise test-time correction against a reference frame (TTC) | None | 4-8 h | Drift |
| 6 | Clean Forcing LoRA that learns the model's own drift | Light LoRA, about 1 GPU-day on a 1.3B model | 12-20 h | Drift |
| 7 | Online point cloud (VGGT or Depth Anything 3) as a consistency check | None | 12-24 h | Rigour, revisits |

Details and risks:

- **2.** WorldTrace (NVIDIA) is training-free, tested on Matrix-Game 2.0, reports +15.5% temporal consistency and +19.5% ABA-loop recall. Deep Forcing and FreqForcing were tested on Self-Forcing (Wan2.1). FreqForcing lists public code. Porting to MG3's cache layout and RoPE is the cost.
- **3.** WorldKV (KAIST) keeps evicted KV chunks and re-inserts those matching the current camera or action without re-encoding, about 2x throughput vs full KV, tested on Matrix-Game 2.0 and LingBot-World-Fast. Closing the Loop adds a geometric attention bias that needs pose and metric depth, which MG3 does not provide.
- **4.** The only idea aimed at the two floored dimensions. No verified paper found. MG3 is image-to-video with weak text control, so the injection path is unproven. Workstream C's edited-anchor approach sidesteps this.
- **5.** No code found. May fight a few-step distilled sampler, and the first frame goes stale once the view moves far.
- **6.** Code and checkpoints public. Reports transfer to HY-WorldPlay. May conflict with MG3's built-in error buffer.
- **7.** Most useful for the rigour criterion (showing where the world breaks).

## 2026 trends

- Pose-keyed memory is replacing raw frame recall: Matrix-Game 3.5 (3D patch retrieval, no new parameters), World-T3 (fixed-size fast-weight memory, revisit PSNR 13.52 to 18.31 dB), WorldCrafter, RELIC. All need training; no code found.
- Memory is moving into the KV cache and test-time state, which is why training-free options exist.
- Drift is treated as a memory problem, since stored frames are corrupted by accumulated error (residual modelling, LongForcing, self-forcing).
- Memory is trained jointly with few-step distillation; 16 to 40 FPS is the baseline.
- Evaluation is catching up: PlayWorld, R2M-Bench (revisit memory), WorldRoamBench.

## Avoid

- WorldMem or Context-as-Memory style retraining: too heavy for 30 hours and MG3 already does it.
- Training a new memory from scratch (DecMem, GIM-World).
- Echo-Memory variants: its own finding is that raw context K=20 is a strong baseline.
- Over-engineering Gaussian splatting.

## Open questions

- Are MG3's 1.00 scores caused by the gate or by real memory failure?
- Is LingBot-World2 (1.82) open-weight? If so it is a much closer starting point than MG3 (unverified).
- MG3 single-GPU VRAM and min per task on Modal.

## Sources

- PlayWorld: https://arxiv.org/html/2608.13552, https://github.com/kxding/PlayWorld, https://huggingface.co/spaces/jocelynd/PlayWorld-Leaderboard
- Matrix-Game 3.0: https://arxiv.org/abs/2604.08995, https://huggingface.co/Skywork/Matrix-Game-3.0
- Matrix-Game 3.5: https://arxiv.org/abs/2608.29910
- ABot-World-0: https://arxiv.org/abs/2607.19191, https://huggingface.co/acvlab/ABot-World-0-5B-LF
- Genie 3: https://deepmind.google/blog/genie-3-a-new-frontier-for-world-models/
- WorldKV: https://arxiv.org/abs/2605.22718
- World-T3: https://arxiv.org/abs/2610.17434
- WorldCrafter: https://arxiv.org/abs/2609.24984
- WorldTrace: https://arxiv.org/pdf/2608.07408
- Deep Forcing: https://arxiv.org/html/2512.05081v1
- FreqForcing: https://arxiv.org/html/2607.27110, https://github.com/jiatongli2024/FreqForcing
- Closing the Loop: https://arxiv.org/html/2607.21848
- Clean Forcing: https://clean-forcing.github.io/
- TTC: https://arxiv.org/abs/2602.05871v1
- HY-WorldPlay: https://arxiv.org/abs/2512.14614
- RELIC: https://arxiv.org/abs/2512.04040
- Spatia: https://arxiv.org/abs/2512.15716
- Memory Forcing: https://arxiv.org/abs/2510.03198
- VMem: https://arxiv.org/abs/2506.18903
- Context-as-Memory: https://arxiv.org/abs/2506.03141
- WorldMem: https://arxiv.org/abs/2504.12369
- Echo-Memory: https://arxiv.org/pdf/2606.09803
- R2M-Bench: https://arxiv.org/abs/2608.27328
- Survey, "The Past Frames the Future": https://arxiv.org/abs/2609.28466
- Reading list: https://github.com/HaroldChen19/Awesome-AR-Video-Memory
