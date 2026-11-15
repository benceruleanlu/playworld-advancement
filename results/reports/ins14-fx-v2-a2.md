## ins14-fx-v2-a2

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| insight | 1.80 | 0.33 | 6 | - | 0 | 0 | 2.00, 2.17, 1.53, 1.50 |
| **overall** | **1.80** | 0.33 | | | | | 2.00, 2.17, 1.53, 1.50 |

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
| OE001 | insight | 2.00 | 2/2/2/2 | ok | The video failed to follow the "wait and observe" prompt, instead generating a first-person perspective of cycling, and the woman pushing a stroller in the initial frame completely disappeared after a few frames.<details><summary>judge's original</summary>视频未能遵循“等待并观察”的提示，而是生成了第一人称视角的自行车骑行画面，且初始画面中的推婴儿车女子在几帧后完全消失。</details> |
| OE005 | insight | 1.00 | 1/1/1/1 | score_1.0 | The first part of the video is completely static, followed by severe hard cuts and character distortion, failing to show any meaningful scene progression and resulting in extremely low scores across all dimensions.<details><summary>judge's original</summary>视频前段完全静止，随后发生严重的硬切和人物形变，未能展现任何有意义的场景演变，导致所有维度得分极低。</details> |
| OE018 | insight | 2.75 | 4/5/1/1 | ok | The video shows a continuous water-pouring process with the water level rising naturally, demonstrating good physical causality and subject consistency.<details><summary>judge's original</summary>视频展示了持续倒水的过程，水位自然上升，物理因果和主体一致性表现良好。</details> |
| OE035 | insight | 1.00 | 1/1/1/1 | score_1.0 | The video is completely static, with the two workers holding the pose of lifting a wooden frame without any movement, lacking meaningful temporal progression and receiving the lowest score.<details><summary>judge's original</summary>视频完全静止，两名工人保持抬起木架的姿势没有任何动作，缺乏有意义的时间演进，得分为最低分。</details> |
| OE064 | insight | 2.05 | 2/2/2.2/2 | ok | The cooking action in the video is ineffective; the meat did not cook and instead turned an unnatural bright pink, and a severe hard cut occurred at frame 500 where the chef's outfit abruptly changed into a blue down jacket.<details><summary>judge's original</summary>视频中烹饪动作无效，肉未变熟反而变成不自然的亮粉色，且在第500帧发生严重的硬切，厨师服装突变为蓝色羽绒服。</details> |
| OE074 | insight | 2.00 | 2/2/2/2 | ok | In the video, the man in yellow stays frozen in the pose of biting a steamed bun, the bun does not get smaller, and there is a lack of substantial eating progression, with only a hand moving into the foreground and the camera moving down.<details><summary>judge's original</summary>视频中黄衣男子一直停留在咬包子的姿势，包子未见缩小，缺乏实质性的进食演进，仅有前景手移入和镜头下移。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `ins14-fx-v2-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| OE001 | insight | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a2&scene=OE001#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a2/OE001.mp4) |
| OE005 | insight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a2&scene=OE005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a2/OE005.mp4) |
| OE018 | insight | 2.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a2&scene=OE018#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a2/OE018.mp4) |
| OE035 | insight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a2&scene=OE035#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a2/OE035.mp4) |
| OE064 | insight | 2.05 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a2&scene=OE064#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a2/OE064.mp4) |
| OE074 | insight | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a2&scene=OE074#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a2/OE074.mp4) |
