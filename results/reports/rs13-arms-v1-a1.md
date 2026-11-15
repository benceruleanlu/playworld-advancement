## rs13-arms-v1-a1

runner `lingbot_world2_1p3b` | action source `agent` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.22 | 0.32 | 3 | 2/3 | 0 | 0 | 2.47, 1.80, 2.47, 2.13 |
| outsight | 1.17 | 0.19 | 3 | 2/3 | 0 | 0 | 1.00, 1.33, 1.00, 1.33 |
| **overall** | **1.69** | 0.08 | | | | | 1.73, 1.57, 1.73, 1.73 |

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
| GC031 | gc | 3.55 | ok | 镜头旋转角度过小，未能完成360度旋转，也未能回到初始视角。 |
| GC033 | gc | 2.10 | ok | 镜头执行了向左和向右的运动轨迹，但在返回过程中场景内容发生了严重突变，未能真实呈现原始的展示窗，因此仅算作部分完成。 |
| GC036 | gc | 1.00 | gate_fail | 视频仅展示了持续向左平移的动作，未能执行向右平移以及回到中心的指令。 |
| OE034 | outsight | 1.25 | ok | 视频在镜头移动过程中发生了灾难性的变形和场景替换，斑马完全失去了原有形态，鸵鸟和生菜消失，未能展现任何合理的隐藏状态演进或场景一致性。 |
| OE047 | outsight | 1.00 | score_1.0 | 视频在镜头转回后发生了灾难性的场景重置，自动扶梯完全消失，男子的服装也发生了改变，没有任何有意义的隐藏状态进展。 |
| OE058 | outsight | 1.25 | gate_fail | 未执行向左转回的指令。 |

### Scenes

[Watch all 6 rollouts of `rs13-arms-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 3.55 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a1/GC031.mp4) |
| GC033 | gc | 2.10 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a1/GC033.mp4) |
| GC036 | gc | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a1/GC036.mp4) |
| OE034 | outsight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a1&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a1/OE034.mp4) |
| OE047 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a1&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a1/OE047.mp4) |
| OE058 | outsight | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=rs13-arms-v1-a1&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-rs13-arms-v1-a1/OE058.mp4) |
