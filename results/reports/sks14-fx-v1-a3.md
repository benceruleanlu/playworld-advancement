## sks14-fx-v1-a3

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| outsight | 1.33 | 0.14 | 6 | 5/6 | 0 | 0 | 1.33, 1.33, 1.50, 1.17 |
| **overall** | **1.33** | 0.14 | | | | | 1.33, 1.33, 1.50, 1.17 |

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
| OE034 | outsight | 1.00 | 1/1/1/1 | score_1.0 | The camera failed to return to the initial viewpoint.<details><summary>judge's original</summary>相机未能返回初始视角。</details> |
| OE039 | outsight | 1.25 | 1/1/2/1 | gate_fail | It did not perform a 360-degree rotation in place; the trajectory does not match at all.<details><summary>judge's original</summary>未执行原地360度旋转，轨迹完全不符。</details> |
| OE047 | outsight | 1.00 | 1/1/1/1 | gate_fail | The camera trajectory generally matches, but the scene content failed to remain consistent.<details><summary>judge's original</summary>镜头轨迹基本符合，但场景内容未能保持一致。</details><br>pass 3 gate_fail: The camera did not perform the requested rotation.<details><summary>judge's original</summary>相机未执行要求的旋转动作。</details> |
| OE048 | outsight | 1.75 | 3/2/1/1 | ok | The camera completed the trajectory of turning right and then back left, but after returning, the original double-walled glass, coffee machine, and background potted plant were completely replaced by new objects, resulting in severe identity and state continuity failure.<details><summary>judge's original</summary>摄像机完成了向右再向左转回的轨迹，但转回后原有的双层玻璃杯、咖啡机和背景盆栽被完全替换为新物体，导致严重的身份和状态连续性失败。</details> |
| OE058 | outsight | 1.25 | 1/1/2/1 | gate_fail | Although the right and left turning movements were executed, it failed to return to the original viewpoint due to a scene reset.<details><summary>judge's original</summary>虽然执行了右转和左转的动作，但由于场景重置，未能返回到原始视角。</details><br>pass 2 gate_fail: Did not return to the initial viewpoint.<details><summary>judge's original</summary>未返回初始视角。</details> |
| OE069 | outsight | 1.75 | 1/2/2/2 | ok | The video completed the left and right camera rotation, but after turning back, the person's backpack was replaced, and the video developed a severe blue color cast, failing to demonstrate reasonable accumulation of physical displacement.<details><summary>judge's original</summary>视频完成了镜头的左右旋转，但转回后人物背包被替换，且画面出现严重的蓝色色偏，未能展现合理的物理位移积累。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `sks14-fx-v1-a3` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a3#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| OE034 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a3&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a3/OE034.mp4) |
| OE039 | outsight | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a3&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a3/OE039.mp4) |
| OE047 | outsight | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a3&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a3/OE047.mp4) |
| OE048 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a3&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a3/OE048.mp4) |
| OE058 | outsight | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a3&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a3/OE058.mp4) |
| OE069 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a3&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a3/OE069.mp4) |
