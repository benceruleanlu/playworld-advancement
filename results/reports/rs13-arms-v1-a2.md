## rs13-arms-v1-a2

runner `lingbot_world2_1p3b` | action source `agent` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 3.08 | 0.31 | 3 | 3/3 | 0 | 0 | 3.47, 2.80, 3.20, 2.87 |
| outsight | 1.25 | 0.32 | 3 | 3/3 | 0 | 0 | 1.33, 1.67, 1.00, 1.00 |
| **overall** | **2.17** | 0.20 | | | | | 2.40, 2.23, 2.10, 1.93 |

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
| GC031 | gc | 3.35 | ok | 视角执行了向右旋转的动作，但未能完成360度旋转并回到初始的十字路口视角。 |
| GC033 | gc | 3.60 | ok | 镜头执行了向左转动的指令，但未能向右转回以重新看到初始视角。 |
| GC036 | gc | 2.30 | ok | 视频未能执行向右平移和回中的指令，仅向左平移，且在第69-75帧期间商场背景完全突变为一个暗室，导致严重的纹理和颜色一致性失败。 |
| OE034 | outsight | 1.00 | score_1.0 | 视频在镜头旋转期间发生了灾难性的幻觉和形变，斑马融化成条纹团，场景完全改变，未能保持任何合理的物理演进或主体一致性。 |
| OE047 | outsight | 1.50 | ok | 视频初始扶梯静止，镜头转回后发生严重场景重置，扶梯消失，无合理演化。 |
| OE058 | outsight | 1.25 | gate_fail | 镜头未转回初始视角。 |

### Scenes

[Watch all 6 rollouts of `rs13-arms-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 3.35 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a2&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a2/GC031.mp4) |
| GC033 | gc | 3.60 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a2/GC033.mp4) |
| GC036 | gc | 2.30 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a2/GC036.mp4) |
| OE034 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a2&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a2/OE034.mp4) |
| OE047 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a2&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a2/OE047.mp4) |
| OE058 | outsight | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a2&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a2/OE058.mp4) |
