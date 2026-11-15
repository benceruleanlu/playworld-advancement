## pm14-fx-v1-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.82 | 0.32 | 3 | 3/3 | 0 | 0 | 2.67, 3.20, 2.93, 2.47 |
| outsight | 1.83 | 0.36 | 3 | 3/3 | 0 | 0 | 2.17, 1.33, 2.00, 1.83 |
| **overall** | **2.33** | 0.14 | | | | | 2.42, 2.27, 2.47, 2.15 |

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
| GC031 | gc | 1.80 | 1/2.8/1.4/2 | ok | The camera completed a 360-degree rotation, but upon returning to the initial anchor area, the original couple disappeared and was replaced, and the structure of the signpost changed, resulting in poor scene consistency.<details><summary>judge's original</summary>镜头完成了360度旋转，但在回到初始锚定区域时，原有的情侣消失并被替换，指示牌结构发生改变，场景一致性较差。</details> |
| GC033 | gc | 4.00 | 5/4/4/3 | ok | The camera successfully completed the left pan and return movement, and all key items in the initial display window maintained high consistency when they reappeared.<details><summary>judge's original</summary>镜头成功完成向左平移并返回的动作，初始橱窗内的所有关键物品在重现时均保持了高度的一致性。</details> |
| GC036 | gc | 2.65 | 2/2.8/3.4/2.4 | ok | The camera failed to maintain the initial spatial layout during the pan; the right wall erroneously evolved into a duplicate 'HATS' storefront, causing severe object duplication and structural replacement.<details><summary>judge's original</summary>镜头在平移过程中未能保持初始的空间布局，右侧墙壁错误地演变成重复的'HATS'店面，导致严重的物体复制和结构替换。</details> |
| OE039 | outsight | 1.25 | 1/1/2/1 | ok | The camera failed to return to its initial viewpoint position, and the scene drifted.<details><summary>judge's original</summary>相机未能回到初始的视角位置，场景发生了漂移。</details> |
| OE047 | outsight | 1.25 | 2/1/1/1 | gate_fail | The video failed to maintain scene consistency when the camera turned right; the escalator severely distorted into a flat corridor, causing the man's motion trajectory and hidden state progression to completely break down, representing a catastrophic failure of physical causality and scene reset.<details><summary>judge's original</summary>视频在镜头向右转时未能保持场景一致性，自动扶梯严重扭曲变为平坦走廊，导致男子的运动轨迹和隐藏状态演进完全断裂，属于灾难性的物理因果和场景重置失败。</details><br>pass 3 gate_fail: The camera did not perform any of the requested rotation movements.<details><summary>judge's original</summary>相机未执行任何要求的旋转动作。</details> |
| OE048 | outsight | 3.00 | 3.5/2/3/3.5 | ok | Although the return trajectory was executed, the scene content reset upon return, failing to truly return to the "original view".<details><summary>judge's original</summary>虽然执行了返回的轨迹，但返回后的场景内容发生了重置，未能真正回到“原始视图”。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `pm14-fx-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 1.80 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a1/GC031.mp4) |
| GC033 | gc | 4.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a1/GC033.mp4) |
| GC036 | gc | 2.65 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a1/GC036.mp4) |
| OE039 | outsight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a1&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a1/OE039.mp4) |
| OE047 | outsight | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a1&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a1/OE047.mp4) |
| OE048 | outsight | 3.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a1&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a1/OE048.mp4) |
