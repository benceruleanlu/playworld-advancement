## win14-fx-v1-a4

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 9 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.57 | 0.09 | 3 | 3/3 | 0 | 0 | 2.53, 2.47, 2.60, 2.67 |
| outsight | 2.04 | 0.23 | 6 | 6/6 | 0 | 0 | 1.88, 2.38, 1.92, 2.00 |
| **overall** | **2.30** | 0.09 | | | | | 2.20, 2.42, 2.26, 2.33 |

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
| GC031 | gc | 1.65 | 1/1/1.4/3.2 | ok | Although the camera rotated to the right, it failed to complete a 360-degree rotation and return to the initial perspective and frame.<details><summary>judge's original</summary>镜头虽然进行了向右旋转，但未能完成360度旋转并回到初始的视角和画面。</details> |
| GC033 | gc | 3.80 | 3.6/3.8/4/3.8 | ok | The camera successfully turned left and turned back, and key items in the display window maintained good consistency upon reappearing, with only slight degradation in the sign text and some hallucinated generation on the left background wall.<details><summary>judge's original</summary>相机成功完成了向左转动并转回的动作，橱窗内的关键物品在重新出现时保持了良好的一致性，仅标牌文本有轻微退化，且左侧背景墙面出现了一定程度的幻觉生成。</details> |
| GC036 | gc | 2.25 | 3/2.6/2.4/1 | gate_fail | The video experienced a scene layout reset, with the sign position teleporting and ground textures lost.<details><summary>judge's original</summary>视频发生场景布局重置，招牌位置瞬移且地面纹理丢失。</details><br>pass 4 gate_fail: The camera initially pans right instead of left, completely failing to show the left side of the scene, and the direction of movement is opposite to the requested "pan from left to right".<details><summary>judge's original</summary>镜头初始向右平移而非向左，完全没有展示场景的左侧，且运动方向与要求的“从左向右平移”相反。</details> |
| OE034 | outsight | 1.00 | 1/1/1/1 | score_1.0 | Although the camera returned to the left, it failed to accurately restore the spatial position of the initial perspective, and the content changed completely.<details><summary>judge's original</summary>镜头虽然向左返回，但未能准确还原初始视角的空间位置，且内容完全改变。</details> |
| OE039 | outsight | 3.44 | 3.75/4/2/4 | ok | The video successfully executed the 360-degree rotation and pullback instructions, and the dog plausibly changed posture while the camera moved away, but the dog's harness had a sudden color change early on, and the transparency of the background window changed after the camera turned back.<details><summary>judge's original</summary>视频成功执行了360度旋转和后退的指令，狗在镜头移开期间合理地改变了姿势，但狗的胸背带在初期发生了颜色突变，且背景窗户的透明度在镜头转回后发生了改变。</details> |
| OE047 | outsight | 1.00 | 1/1/1/1 | score_1.0 | The video failed completely: the man walked down the escalator and entered a door while the camera moved away, yet contradictorily reappeared at the bottom of the escalator when the camera turned back, failing to show the expected hidden progression and completely breaking the trajectory.<details><summary>judge's original</summary>视频完全失败，男子在镜头移开时走下扶梯进入一扇门，当镜头转回时却矛盾地在扶梯底部重新出现，没有展示预期的隐藏进展，且轨迹完全断裂。</details> |
| OE048 | outsight | 2.31 | 3.5/2.75/2/1 | ok | After the camera returned, the cup style and background underwent severe replacement, and the coffee level failed to accumulate plausibly while out of sight.<details><summary>judge's original</summary>镜头返回后，杯子款式和背景发生了严重的替换，且视线外期间咖啡液面未能合理积累。</details> |
| OE058 | outsight | 1.50 | 1/2/2/1 | ok | After the camera turned back, the initial decorator, cookies, and tabletop items were completely replaced with a different scene, causing severe identity and progression failures.<details><summary>judge's original</summary>镜头转回后，初始的装饰者、饼干和桌面物品被完全替换为不同的场景，导致严重的身份和演变失败。</details> |
| OE069 | outsight | 3.00 | 1/3.5/3.5/4 | ok | The video successfully executed the camera pan-around instruction and the elevator's downward motion accumulated plausibly, but a severe replacement error occurred with the person's backpack upon reappearing.<details><summary>judge's original</summary>视频成功执行镜头环视指令，电梯下行运动合理累积，但人物重新出现时背包发生严重替换错误。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 9 rollouts of `win14-fx-v1-a4` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 1.65 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a4/GC031.mp4) |
| GC033 | gc | 3.80 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a4/GC033.mp4) |
| GC036 | gc | 2.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a4/GC036.mp4) |
| OE034 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a4/OE034.mp4) |
| OE039 | outsight | 3.44 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a4/OE039.mp4) |
| OE047 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a4/OE047.mp4) |
| OE048 | outsight | 2.31 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a4/OE048.mp4) |
| OE058 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a4/OE058.mp4) |
| OE069 | outsight | 3.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a4&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a4/OE069.mp4) |
