## gch13-arms-v1-a1

runner `lingbot_world2_1p3b` | action source `agent` | passes 4 | tasks 3 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.53 | 0.32 | 3 | 2/3 | 0 | 0 | 2.27, 3.00, 2.40, 2.47 |
| **overall** | **2.53** | 0.32 | | | | | 2.27, 3.00, 2.40, 2.47 |

**Reference (paper, full benchmark)**

| model | gc | if | insight | outsight | overall |
|---|---:|---:|---:|---:|---:|
| Genie 3 | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |

[All experiments on the results site](https://benceruleanlu.github.io/playworld-advancement/)

### Tasks

| task | family | mean | status | reason |
|---|---|---:|---|---|
| GC031 | gc | 3.30 | ok | 镜头向右旋转的速度较慢，未能在视频结束前完成360度旋转并回到初始视角。 |
| GC033 | gc | 3.30 | ok | 镜头没有在向左转90度后停止，也没有向右转回以重新看到初始的展示窗。 |
| GC036 | gc | 1.00 | gate_fail | 视频中镜头始终向右平移，完全没有执行指令中要求的向左平移动作，轨迹与指令要求完全不符。 |

### Scenes

[Watch all 3 rollouts of `gch13-arms-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=gch13-arms-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 3.30 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=gch13-arms-v1-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-gch13-arms-v1-a1/GC031.mp4) |
| GC033 | gc | 3.30 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=gch13-arms-v1-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-gch13-arms-v1-a1/GC033.mp4) |
| GC036 | gc | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=gch13-arms-v1-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-gch13-arms-v1-a1/GC036.mp4) |
