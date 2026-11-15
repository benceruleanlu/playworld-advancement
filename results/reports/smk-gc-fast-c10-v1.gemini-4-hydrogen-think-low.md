## smk-gc-fast-c10-v1

> **screening judge: gemini-4-hydrogen, thinking low, not comparable to the leaderboard.** Dev screening only; not written to results/experiments.csv.

runner `lingbot_world2` | action source `agent` | passes 1 | tasks 3 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.60 | - | 3 | 2/3 | 0 | 0 | 2.60 |
| **overall** | **2.60** | - | | | | | 2.60 |

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
| GC005 | gc | 2.80 | ok | 视频完成了围绕雕塑的环绕运动并回到初始视角，色彩与整体背景较稳定，但后段出现基座重复及表面裂缝伪影。 |
| GC033 | gc | 4.00 | ok | 镜头平滑左转至街道后转回橱窗，所有关键物体在重现后均保持一致的身份、材质、颜色与空间位置。 |
| GC036 | gc | 1.00 | gate_fail | 实际平移方向与指令完全相反（实际为右-左-右，指令要求为左-右-左）。 |
