## win14-fx-v1-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 9 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 3.15 | 0.64 | 3 | 3/3 | 0 | 0 | 3.53, 3.40, 2.20, 3.47 |
| outsight | 1.81 | 0.29 | 6 | 6/6 | 0 | 0 | 1.50, 1.67, 2.17, 1.92 |
| **overall** | **2.48** | 0.21 | | | | | 2.52, 2.53, 2.18, 2.69 |

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
| GC031 | gc | 3.45 | 5/3.2/1.8/3.8 | ok | The camera rotated to the right, but failed to complete a full 360-degree rotation to return to the initial view, failing to meet the revisit requirement.<details><summary>judge's original</summary>镜头进行了向右旋转的动作，但未能完成完整的360度旋转以回到初始视角，未满足重访要求。</details> |
| GC033 | gc | 3.85 | 3.6/4/3.8/4 | ok | The camera successfully rotated left and back, and the key objects inside the initial display window remained consistent in structure and color upon reappearance, with only slight blurring on the sign text.<details><summary>judge's original</summary>相机成功完成向左旋转并转回的动作，初始橱窗内的关键物体在重现时结构和颜色保持一致，仅标志文字出现轻微模糊。</details> |
| GC036 | gc | 2.15 | 2/3/1/2.6 | gate_fail | The camera successfully executed the panning trajectory to the left, right, and back to the center, but failed to stop at the center position and continued panning left until the end of the video.<details><summary>judge's original</summary>镜头成功执行了向左、向右并回到中心的平移轨迹，但未能在中心位置停止，而是继续向左平移直至视频结束。</details><br>pass 3 gate_fail: The initial panning direction (to the right) is opposite to the instruction to pan left first, and the video remains static for most of the duration, failing to execute the full trajectory from left to right and back to the center.<details><summary>judge's original</summary>初始平移方向（向右）与指令要求的先向左平移相反，且视频大部分时间处于静止状态，未执行完整的从左到右再回到中心的轨迹。</details> |
| OE034 | outsight | 1.00 | 1/1/1/1 | score_1.0 | After the camera turned right and returned, the video failed to maintain consistency with the initial scene; the original zebra, ostrich, and lettuce completely disappeared, replaced by a giant zebra body with severely distorted proportions, resulting in a catastrophic scene replacement.<details><summary>judge's original</summary>视频在镜头向右转动并返回后，未能保持初始场景的一致性，最初的斑马、鸵鸟和生菜完全消失，取而代之的是比例严重失调的巨大斑马身体，发生了灾难性的场景替换。</details> |
| OE039 | outsight | 1.75 | 1/1/3/2 | ok | The camera trajectory became an orbit rather than rotating in place, and it did not return to the initial view.<details><summary>judge's original</summary>镜头轨迹变为环绕而非原地旋转，且未回到初始视角。</details> |
| OE047 | outsight | 2.12 | 2/2/2.5/2 | ok | Although the video executed the camera movement of turning right and back, the man erroneously teleported from the escalator to walking on flat ground while the camera moved, breaking physical coherence and the plausible evolution of hidden states.<details><summary>judge's original</summary>视频虽然执行了镜头的右转和转回动作，但男子在镜头移动时错误地从扶梯瞬移到平地上行走，破坏了物理连贯性和隐藏状态的合理演变。</details> |
| OE048 | outsight | 2.12 | 1/3/2/2.5 | ok | The video executed the required camera motion, but after the camera returned, the appearance of the scene background, coffee machine, and cup underwent severe sudden changes, and the previously accumulated coffee completely disappeared, causing a state reset.<details><summary>judge's original</summary>视频执行了要求的镜头运动，但在镜头返回后，场景背景、咖啡机和杯子的外观发生严重突变，且原本累积的咖啡完全消失，导致状态重置。</details> |
| OE058 | outsight | 1.25 | 1/2/1/1 | gate_fail | The camera did not execute the instruction to turn left back to the initial view.<details><summary>judge's original</summary>相机没有执行向左转回初始视角的指令。</details><br>pass 3 gate_fail: The camera failed to follow the instruction to rotate 180 degrees to the right and return to the original viewpoint; instead, a scene cut occurred.<details><summary>judge's original</summary>镜头未能按照指令完成向右180度旋转并返回原视角的轨迹，而是发生了场景切换。</details> |
| OE069 | outsight | 2.62 | 3/1/3.5/3 | ok | The video successfully executed the instruction for the camera to rotate left and back, and the escalator maintained plausible downward movement while out of view, but after the camera turned back, an orange backpack identical to her mother's appeared out of nowhere on the girl, indicating a severe feature duplication error.<details><summary>judge's original</summary>视频成功执行了镜头向左旋转并转回的指令，自动扶梯在视野外保持了合理的向下运行，但镜头转回后女孩身上凭空出现了与母亲相同的橙色背包，存在严重的特征复制错误。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 9 rollouts of `win14-fx-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 3.45 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a1/GC031.mp4) |
| GC033 | gc | 3.85 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a1/GC033.mp4) |
| GC036 | gc | 2.15 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a1/GC036.mp4) |
| OE034 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a1/OE034.mp4) |
| OE039 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a1/OE039.mp4) |
| OE047 | outsight | 2.12 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a1/OE047.mp4) |
| OE048 | outsight | 2.12 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a1/OE048.mp4) |
| OE058 | outsight | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a1/OE058.mp4) |
| OE069 | outsight | 2.62 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a1&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a1/OE069.mp4) |
