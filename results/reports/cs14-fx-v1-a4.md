## cs14-fx-v1-a4

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 7 | missing 4

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.55 | 0.72 | 1 | 1/1 | 0 | 0 | 2.40, 2.00, 2.20, 3.60 |
| if | 1.82 | 0.13 | 2 | 2/2 | 0 | 0 | 1.80, 1.80, 2.00, 1.70 |
| insight | 1.00 | 0.00 | 4 | - | 4 | 0 | 1.00, 1.00, 1.00, 1.00 |
| **overall** | **1.79** | 0.21 | | | | | 1.73, 1.60, 1.73, 2.10 |

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
| GC033 | gc | 2.55 | ok | 镜头成功执行了左转并转回的动作，但重新面对原橱窗时，内部的所有关键物品均被替换，布局彻底改变，一致性极差。 |
| IF010 | if | 2.00 | ok | 主体形态发生严重突变，未能保持机器狗的身份。 |
| IF034 | if | 1.65 | ok | 虽然执行了抓取和提起的动作轨迹，但交互主体（机械臂和碗）发生了严重的身份突变，且环境消失。 |
| OE001 | insight | 1.00 | missing |  |
| OE005 | insight | 1.00 | missing |  |
| OE018 | insight | 1.00 | missing |  |
| OE035 | insight | 1.00 | missing |  |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 3 rollouts of `cs14-fx-v1-a4` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a4#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC033 | gc | 2.55 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a4&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a4/GC033.mp4) |
| IF010 | if | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a4&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a4/IF010.mp4) |
| IF034 | if | 1.65 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a4&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a4/IF034.mp4) |
| OE001 | insight | 1.00 | missing | no video |
| OE005 | insight | 1.00 | missing | no video |
| OE018 | insight | 1.00 | missing | no video |
| OE035 | insight | 1.00 | missing | no video |
