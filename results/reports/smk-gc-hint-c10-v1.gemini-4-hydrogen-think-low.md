## smk-gc-hint-c10-v1

> **screening judge: gemini-4-hydrogen, thinking low, not comparable to the leaderboard.** Dev screening only; not written to results/experiments.csv.

runner `lingbot_world2` | action source `agent` | passes 1 | tasks 3 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 4.00 | - | 3 | 3/3 | 0 | 0 | 4.00 |
| **overall** | **4.00** | - | | | | | 4.00 |

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
| GC005 | gc | 4.00 | ok | 视频中相机连续环绕并成功返回初始广场视角，骑马雕像、底座及周围建筑的身份、纹理、色彩和空间关系整体保持稳定。 |
| GC033 | gc | 4.00 | ok | 相机平滑左转90度并成功转回正对橱窗，所有关键物体在重现后保持高度一致。 |
| GC036 | gc | 4.00 | ok | 视频整体空间结构、物体身份与色彩一致性良好，仅HATS招牌文字在重现时略有模糊，且回中后存在额外平移。 |
