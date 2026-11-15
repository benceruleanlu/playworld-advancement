## orc14-gc-v1-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.17 | 0.22 | 6 | 5/6 | 0 | 0 | 2.07, 2.03, 2.50, 2.10 |
| **overall** | **2.17** | 0.22 | | | | | 2.07, 2.03, 2.50, 2.10 |

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
| GC005 | gc | 1.85 | gate_fail | 镜头完全没有执行要求的360度环绕雕塑运动，视角始终保持不变。 |
| GC016 | gc | 3.80 | ok | 视频中男子走向宝塔并仰视的动作连贯，人物、宝塔及周围环境的身份、材质和颜色均保持了良好的一致性。 |
| GC031 | gc | 2.05 | ok | 视频未能完成连贯的360度环视，而是通过多次硬切在公路和初始公园场景之间切换，且初始场景重新出现时两人和白色长椅完全消失，指示牌结构也发生了改变。 |
| GC033 | gc | 2.35 | ok | 镜头执行了先左后右的旋转轨迹，但画面中途出现巨大的不明物体遮挡，且最终未能完全对准初始的橱窗视角，因此判定为部分成功。 |
| GC036 | gc | 1.25 | gate_fail | 视频仅表现出单一的持续向左平移，未能执行提示词要求的“从左向右平移”以及“回到中心”的轨迹序列。 |
| GC038 | gc | 1.75 | gate_fail | 视频仅完成了向右转和向前移动的初始部分，未能执行后续的向左转、向后走以及转回原方向的指令。 |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `orc14-gc-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.85 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a1&scene=GC005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a1/GC005.mp4) |
| GC016 | gc | 3.80 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a1&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a1/GC016.mp4) |
| GC031 | gc | 2.05 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a1/GC031.mp4) |
| GC033 | gc | 2.35 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a1/GC033.mp4) |
| GC036 | gc | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a1/GC036.mp4) |
| GC038 | gc | 1.75 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a1&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a1/GC038.mp4) |
