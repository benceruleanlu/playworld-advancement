## sks14-fx-v1-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| outsight | 2.10 | 0.28 | 6 | 6/6 | 0 | 0 | 2.08, 2.17, 2.42, 1.75 |
| **overall** | **2.10** | 0.28 | | | | | 2.08, 2.17, 2.42, 1.75 |

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
| OE034 | outsight | 1.00 | 1/1/1/1 | score_1.0 | The camera failed to return to the initial viewpoint as instructed by the prompt.<details><summary>judge's original</summary>镜头未能按照提示要求返回初始视角。</details> |
| OE039 | outsight | 2.00 | 1/2/3/2 | gate_fail | The camera completed a 360-degree pan and pulled back, but when the white dog reappeared, it had changed into a different breed (floppy ears became upright ears) and lacked meaningful motion progression.<details><summary>judge's original</summary>镜头完成了360度环视和后退，但重新出现时的白狗变成了不同的品种（垂耳变立耳），且缺乏有意义的动作演变。</details><br>pass 1 gate_fail: Failed to return to the initial viewpoint and did not perform the backward action.<details><summary>judge's original</summary>未能回到初始视角，且未执行后退动作。</details> |
| OE047 | outsight | 2.62 | 3/2/3.5/2 | ok | The video successfully executed the camera's pan right, pan back, and tilt up, and the man reasonably moved higher up the escalator, but a duplicate of the man appeared in the hallway while the camera was turned away, resulting in a serious logical and identity error.<details><summary>judge's original</summary>视频成功执行了镜头的右转、转回和上仰动作，且男子在扶梯上的位置合理上升，但在镜头移开期间走廊中出现了男子的复制体，存在严重的逻辑和身份错误。</details> |
| OE048 | outsight | 3.38 | 3.5/4/4/2 | ok | The video successfully showed a reasonable rise in the coffee level while the camera was turned away, but after the camera returned, the background plants suffered from severe hallucinated replacement.<details><summary>judge's original</summary>视频成功展示了镜头移开期间咖啡液面的合理累积，但镜头返回后背景植物发生了严重的幻觉替换。</details> |
| OE058 | outsight | 1.25 | 1/1/2/1 | ok | Although the camera panned left and right, it failed to return to the initial viewpoint.<details><summary>judge's original</summary>镜头虽然执行了左右转动，但未能成功返回初始视角。</details> |
| OE069 | outsight | 2.38 | 3/3/1/2.5 | ok | Instead of turning back to the right as instructed, it continued rotating to the left.<details><summary>judge's original</summary>未按指令向右转回，而是持续向左旋转。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `sks14-fx-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| OE034 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a1&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a1/OE034.mp4) |
| OE039 | outsight | 2.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a1&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a1/OE039.mp4) |
| OE047 | outsight | 2.62 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a1&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a1/OE047.mp4) |
| OE048 | outsight | 3.38 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a1&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a1/OE048.mp4) |
| OE058 | outsight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a1&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a1/OE058.mp4) |
| OE069 | outsight | 2.38 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a1&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a1/OE069.mp4) |
