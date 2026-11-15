## dec14-ins-v1-a2

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 2 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| insight | 1.50 | 0.00 | 2 | - | 0 | 0 | 1.50, 1.50, 1.50, 1.50 |
| **overall** | **1.50** | 0.00 | | | | | 1.50, 1.50, 1.50, 1.50 |

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
| OE001 | insight | 1.00 | 1/1/1/1 | score_1.0 | The video fails to maintain the coherence of the initial scene; the woman pushing a stroller quickly disappears and is replaced by a series of unrelated clips of cyclists, resulting in severe failures across all dimensions.<details><summary>judge's original</summary>视频未能保持初始场景的连贯性，推婴儿车的女子迅速消失，被一系列毫无关联的骑车人片段取代，导致所有维度的严重失败。</details> |
| OE018 | insight | 2.00 | 2/2/2/2 | ok | The first half of the video shows the process of pouring water and tea leaves tumbling, but a hard cut occurs at frame 525, completely replacing the kettle, container, and background in the scene, which disrupts temporal coherence and subject consistency.<details><summary>judge's original</summary>视频前半段展示了倒水和茶叶翻滚的过程，但在第525帧发生硬切，场景中的水壶、容器和背景被完全替换，破坏了时间连贯性和主体一致性。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 2 rollouts of `dec14-ins-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=dec14-ins-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| OE001 | insight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=dec14-ins-v1-a2&scene=OE001#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-dec14-ins-v1-a2/OE001.mp4) |
| OE018 | insight | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=dec14-ins-v1-a2&scene=OE018#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-dec14-ins-v1-a2/OE018.mp4) |
