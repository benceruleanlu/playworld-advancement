## ins14-fx-v2-a3

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| insight | 2.09 | 0.25 | 6 | - | 0 | 0 | 1.83, 2.00, 2.10, 2.43 |
| **overall** | **2.09** | 0.25 | | | | | 1.83, 2.00, 2.10, 2.43 |

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
| OE001 | insight | 1.25 | 1/1/1/2 | ok | The video fails to maintain coherent progression, suffering from multiple severe hard cuts after a brief initial movement, which results in a complete loss of subject identity, scene, and physical causality.<details><summary>judge's original</summary>视频未能保持连贯的演进，在短暂的初始移动后发生了多次严重的硬切，导致主体身份、场景和物理因果关系完全丧失。</details> |
| OE005 | insight | 2.75 | 3/3/2/3 | ok | The video shows smooth camera movement and children walking forward naturally with a coherent scene, but the expected ball-kicking action does not occur and clothing details change slightly after turning around.<details><summary>judge's original</summary>视频展示了镜头平滑移动和孩子们自然向前走动的过程，场景连贯，但未发生预期的踢球动作且转身后衣服细节有轻微变化。</details> |
| OE018 | insight | 2.25 | 2/2/2/3 | ok | The video shows water being poured into a teapot and the water level rises, but the tea leaves at the bottom completely disappear during the process, showing severe flaws in physical causality and identity consistency.<details><summary>judge's original</summary>视频展示了向茶壶注水的过程，水位有上升，但壶底的茶叶在过程中完全消失，存在严重的物理因果和身份一致性缺陷。</details> |
| OE035 | insight | 1.25 | 1/2/1/1 | ok | The two workers in the video remain completely frozen in a posture of lifting a wooden frame, failing to perform the carrying action, while severe object distortion hallucinations appear in the foreground with no valid progression.<details><summary>judge's original</summary>视频中两名工人保持抬起木框的姿势完全冻结，未能执行搬运动作，且前景出现严重的物体变形幻觉，无任何有效演进。</details> |
| OE064 | insight | 2.25 | 2/2/3/2 | ok | In the video, the chef waves a spatula, but the meat lump is not spread out continuously; instead, it undergoes a physically implausible sudden shape change at frame 350, lacking a realistic evolution process.<details><summary>judge's original</summary>视频中厨师挥动锅铲，但肉团并未被连续摊开，而是在第350帧发生了不符合物理规律的形态突变，缺乏真实的演变过程。</details> |
| OE074 | insight | 2.80 | 2/2/3.6/3.6 | ok | In the video, a man repeatedly bites a steamed bun without the bun getting smaller, making the eating process ineffective and physically implausible, while the food on the table develops severe color noise artifacts, resulting in poor overall progression quality.<details><summary>judge's original</summary>视频中男子反复咬包子但包子并未减小，进食过程无效且不符合物理规律，同时桌上的食物演变出严重的彩色噪点伪影，整体演变质量差。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `ins14-fx-v2-a3` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a3#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| OE001 | insight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a3&scene=OE001#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a3/OE001.mp4) |
| OE005 | insight | 2.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a3&scene=OE005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a3/OE005.mp4) |
| OE018 | insight | 2.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a3&scene=OE018#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a3/OE018.mp4) |
| OE035 | insight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a3&scene=OE035#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a3/OE035.mp4) |
| OE064 | insight | 2.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a3&scene=OE064#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a3/OE064.mp4) |
| OE074 | insight | 2.80 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a3&scene=OE074#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a3/OE074.mp4) |
