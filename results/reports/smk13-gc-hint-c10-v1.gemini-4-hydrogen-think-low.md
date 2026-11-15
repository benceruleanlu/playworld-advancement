## smk13-gc-hint-c10-v1

> **screening judge: gemini-4-hydrogen, thinking low, not comparable to the leaderboard.** Dev screening only; not written to results/experiments.csv.

runner `lingbot_world2_1p3b` | action source `agent` | passes 1 | tasks 3 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 3.40 | - | 3 | 3/3 | 0 | 0 | 3.40 |
| **overall** | **3.40** | - | | | | | 3.40 |

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
| GC005 | gc | 3.00 | ok | 完成了大部分环绕动作，但未能返回初始相机位置和原始朝向。 |
| GC033 | gc | 3.20 | ok | 完成了向左转90度的前半段动作，但后续未向右转回以重新面向橱窗。 |
| GC036 | gc | 4.00 | ok | 仅完成了初始向左平移，未执行后续向右平移及回到中心。 |
