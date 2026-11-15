## sks14-fx-v1-a4

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| outsight | 1.25 | 0.22 | 6 | 4/6 | 0 | 0 | 1.50, 1.33, 1.00, 1.17 |
| **overall** | **1.25** | 0.22 | | | | | 1.50, 1.33, 1.00, 1.17 |

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
| OE034 | outsight | 1.00 | 1/1/1/1 | gate_fail | The camera failed to return to the initial viewpoint and ended up pointing at the sky.<details><summary>judge's original</summary>镜头未能返回初始视角，最终指向了天空。</details><br>pass 3 gate_fail: The camera only pans to the right and does not execute the instruction to return to the initial viewpoint.<details><summary>judge's original</summary>镜头仅向右平移，未执行返回初始视角的指令。</details> |
| OE039 | outsight | 1.00 | 1/1/1/1 | gate_fail | Although it executed the rotation and pullback, it failed to return to the scene of the original viewpoint.<details><summary>judge's original</summary>虽然执行了旋转和后退，但未能回到原始视角的场景。</details><br>pass 2 gate_fail: The trajectory completely deviates from the instruction requirements.<details><summary>judge's original</summary>轨迹完全偏离指令要求。</details> |
| OE047 | outsight | 1.75 | 2/2/1/2 | ok | Although the video completed the camera turning prompt, it completely failed in off-screen evolution; the man reset to the bottom of the escalator and the environment underwent a hard reset.<details><summary>judge's original</summary>视频虽然完成了镜头的转向提示，但在视线外演变中完全失败，男子重置回扶梯底部且环境发生了硬重置。</details> |
| OE048 | outsight | 1.25 | 2/1/1/1 | gate_fail | Failed to execute the instruction to turn back to the initial viewpoint.<details><summary>judge's original</summary>未能执行转回初始视角的指令。</details><br>pass 4 gate_fail: The camera fails to rotate back to the initial viewpoint.<details><summary>judge's original</summary>相机未能转回初始视角。</details> |
| OE058 | outsight | 1.00 | 1/1/1/1 | gate_fail | The camera completely failed to execute the rotation movement requested by the prompt.<details><summary>judge's original</summary>相机完全没有执行提示要求的旋转动作。</details> |
| OE069 | outsight | 1.50 | 2/2/1/1 | ok | The video executed the left-and-right camera pan, but when the camera turned back to the original viewpoint, the ambient lighting turned blue, the poster changed, and the appearances of the mother and daughter mutated severely, failing to maintain scene and character consistency as well as reasonable motion accumulation.<details><summary>judge's original</summary>视频执行了镜头的左右转动，但当镜头转回原视角时，环境光线变为蓝色，海报改变，且母亲和女儿的外观发生严重变异，未能保持场景和人物的一致性及合理的运动积累。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `sks14-fx-v1-a4` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a4#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| OE034 | outsight | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a4&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a4/OE034.mp4) |
| OE039 | outsight | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a4&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a4/OE039.mp4) |
| OE047 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a4&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a4/OE047.mp4) |
| OE048 | outsight | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a4&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a4/OE048.mp4) |
| OE058 | outsight | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a4&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a4/OE058.mp4) |
| OE069 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a4&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a4/OE069.mp4) |
