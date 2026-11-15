## cs14-fx-v1-a3

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 7 | missing 4

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 3.30 | 0.87 | 1 | 1/1 | 0 | 0 | 3.80, 2.00, 3.60, 3.80 |
| if | 1.43 | 0.30 | 2 | 2/2 | 0 | 0 | 1.50, 1.00, 1.50, 1.70 |
| insight | 1.00 | 0.00 | 4 | - | 4 | 0 | 1.00, 1.00, 1.00, 1.00 |
| **overall** | **1.91** | 0.39 | | | | | 2.10, 1.33, 2.03, 2.17 |

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
| GC033 | gc | 3.30 | ok | 镜头成功执行了向左旋转并转回的动作，初始橱窗内的关键物体在重新出现时基本保持了身份和位置的一致性，但招牌上的文本内容发生了退化。 |
| IF010 | if | 1.75 | gate_fail | 视频中机器狗严重变形为真狗，且工厂地面无端变为冰面，导致整体物理连贯性极差。 |
| IF034 | if | 1.10 | gate_fail | 由于硬重置，完整的抓取和抬起动作未能连贯展示。 |
| OE001 | insight | 1.00 | missing |  |
| OE005 | insight | 1.00 | missing |  |
| OE018 | insight | 1.00 | missing |  |
| OE035 | insight | 1.00 | missing |  |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 3 rollouts of `cs14-fx-v1-a3` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a3#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC033 | gc | 3.30 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a3&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a3/GC033.mp4) |
| IF010 | if | 1.75 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a3&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a3/IF010.mp4) |
| IF034 | if | 1.10 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a3&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a3/IF034.mp4) |
| OE001 | insight | 1.00 | missing | no video |
| OE005 | insight | 1.00 | missing | no video |
| OE018 | insight | 1.00 | missing | no video |
| OE035 | insight | 1.00 | missing | no video |
