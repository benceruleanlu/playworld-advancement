## cs14-fx-v1-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 7 | missing 4

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 3.90 | 0.20 | 1 | 1/1 | 0 | 0 | 4.00, 3.60, 4.00, 4.00 |
| if | 1.25 | 0.29 | 2 | 1/2 | 0 | 0 | 1.50, 1.50, 1.00, 1.00 |
| insight | 1.00 | 0.00 | 4 | - | 4 | 0 | 1.00, 1.00, 1.00, 1.00 |
| **overall** | **2.05** | 0.08 | | | | | 2.17, 2.03, 2.00, 2.00 |

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
| GC033 | gc | 3.90 | ok | 视频执行了摄像机旋转并返回，初始橱窗内的关键物体在重现时保持了良好的身份、外观和位置一致性。 |
| IF010 | if | 1.50 | gate_fail | 视频中机器狗成功执行了左转并直行的轨迹，但在行走过程中完全变形为一只真实的狗，导致严重的物理不合理性。 |
| IF034 | if | 1.00 | gate_fail | 场景在接触前发生硬重置，导致动作未完成。 |
| OE001 | insight | 1.00 | missing |  |
| OE005 | insight | 1.00 | missing |  |
| OE018 | insight | 1.00 | missing |  |
| OE035 | insight | 1.00 | missing |  |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 3 rollouts of `cs14-fx-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC033 | gc | 3.90 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a1/GC033.mp4) |
| IF010 | if | 1.50 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a1&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a1/IF010.mp4) |
| IF034 | if | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=cs14-fx-v1-a1&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-cs14-fx-v1-a1/IF034.mp4) |
| OE001 | insight | 1.00 | missing | no video |
| OE005 | insight | 1.00 | missing | no video |
| OE018 | insight | 1.00 | missing | no video |
| OE035 | insight | 1.00 | missing | no video |
