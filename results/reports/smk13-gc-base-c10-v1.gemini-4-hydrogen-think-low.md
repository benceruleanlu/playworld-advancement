## smk13-gc-base-c10-v1

> **screening judge: gemini-4-hydrogen, thinking low, not comparable to the leaderboard.** Dev screening only; not written to results/experiments.csv.

runner `lingbot_world2_1p3b` | action source `agent` | passes 1 | tasks 3 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 1.47 | - | 3 | 1/3 | 0 | 0 | 1.47 |
| **overall** | **1.47** | - | | | | | 1.47 |

**Reference (paper, full benchmark)**

| model | gc | if | insight | outsight | overall |
|---|---:|---:|---:|---:|---:|
| Genie 3 | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |

### Tasks

> **screening judge: gemini-4-hydrogen, thinking low, not comparable to the leaderboard.**

| task | family | mean | status | reason |
|---|---|---:|---|---|
| GC005 | gc | 1.00 | gate_fail | 未完成围绕雕塑的360度环绕，也未返回初始位置和视角。 |
| GC033 | gc | 2.40 | ok | 视频完成了先左转再转回橱窗的相机运动，但“Gift Vouchers”标牌在转动过程中变形为机械物体并跨表面漂移，且动作完成后继续大幅超程左转。 |
| GC036 | gc | 1.00 | gate_fail | 仅执行了初始向左平移，随后持续向左而非向右平移并回到中心。 |
