## dec14-ins-v1-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 2 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| insight | 3.00 | 0.00 | 2 | - | 0 | 0 | 3.00, 3.00, 3.00, 3.00 |
| **overall** | **3.00** | 0.00 | | | | | 3.00, 3.00, 3.00, 3.00 |

**Reference (paper, full benchmark)**

| model | gc | if | insight | outsight | overall |
|---|---:|---:|---:|---:|---:|
| Genie 3 | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |

[All experiments on the results site](https://benceruleanlu.github.io/playworld-advancement/)

### Tasks

| task | family | mean | passes | status | reason |
|---|---|---:|---|---|---|
| OE001 | insight | 2.00 | 2/2/2/2 | ok | After a brief initial movement, the video undergoes a severe hard cut; the initial subject completely disappears and is replaced by other constantly morphing figures, failing to achieve coherent scene progression.<details><summary>judge's original</summary>视频在短暂的初始运动后发生了严重的硬切，初始主体完全消失并被不断形变的其他人物取代，未能实现连贯的场景演进。</details> |
| OE018 | insight | 4.00 | 4/4/4/4 | ok | The video successfully shows the continuous water-pouring process, with the water level rising naturally, tea leaves tumbling, and physical laws and object appearances well maintained.<details><summary>judge's original</summary>视频成功展示了持续倒水的过程，水位自然上升，茶叶翻滚，物理规律和物体外观保持良好。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 2 rollouts of `dec14-ins-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=dec14-ins-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| OE001 | insight | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=dec14-ins-v1-a1&scene=OE001#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-dec14-ins-v1-a1/OE001.mp4) |
| OE018 | insight | 4.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=dec14-ins-v1-a1&scene=OE018#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-dec14-ins-v1-a1/OE018.mp4) |
