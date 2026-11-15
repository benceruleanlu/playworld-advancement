## cs14-fx-v1-a2

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 7 | missing 4

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.30 | 0.20 | 1 | 1/1 | 0 | 0 | 2.60, 2.20, 2.20, 2.20 |
| if | 1.68 | 0.24 | 2 | 2/2 | 0 | 0 | 1.50, 1.50, 2.00, 1.70 |
| insight | 1.00 | 0.00 | 4 | - | 4 | 0 | 1.00, 1.00, 1.00, 1.00 |
| **overall** | **1.66** | 0.07 | | | | | 1.70, 1.57, 1.73, 1.63 |

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
| GC033 | gc | 2.30 | ok | 视频完成了向左再向右的镜头转动，但返回初始视角时，橱窗内的物体发生了明显的形状变形和纹理丢失（如标牌文字变成乱码）。 |
| IF010 | if | 2.00 | ok | 未执行左转动作，且主体完全变形。 |
| IF034 | if | 1.35 | gate_fail | 场景硬重置导致动作未能完成。 |
| OE001 | insight | 1.00 | missing |  |
| OE005 | insight | 1.00 | missing |  |
| OE018 | insight | 1.00 | missing |  |
| OE035 | insight | 1.00 | missing |  |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 3 rollouts of `cs14-fx-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC033 | gc | 2.30 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a2/GC033.mp4) |
| IF010 | if | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a2&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a2/IF010.mp4) |
| IF034 | if | 1.35 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a2&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a2/IF034.mp4) |
| OE001 | insight | 1.00 | missing | no video |
| OE005 | insight | 1.00 | missing | no video |
| OE018 | insight | 1.00 | missing | no video |
| OE035 | insight | 1.00 | missing | no video |
