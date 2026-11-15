## pm14-fx-v1-a3

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.73 | 0.64 | 3 | 2/3 | 0 | 0 | 2.40, 3.53, 2.07, 2.93 |
| outsight | 2.25 | 0.29 | 3 | 3/3 | 0 | 0 | 2.00, 2.00, 2.50, 2.50 |
| **overall** | **2.49** | 0.29 | | | | | 2.20, 2.77, 2.28, 2.72 |

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
| GC031 | gc | 2.35 | 2.6/4.2/1.2/1.4 | ok | Although the camera rotated, it did not complete a 360-degree turn and return to the initial viewpoint.<details><summary>judge's original</summary>镜头虽然进行了旋转，但没有完成360度旋转并回到初始视角。</details> |
| GC033 | gc | 3.75 | 3.6/3.4/4/4 | ok | The camera successfully moved left and returned. The main items and sign text inside the initial display window remained highly consistent upon re-entering the frame, with only one fewer pendant light on the right.<details><summary>judge's original</summary>镜头成功完成了向左平移并返回的动作，初始橱窗内的主要物品及标牌文字在重新进入视野后保持了高度一致，仅右侧吊灯数量减少了一个。</details> |
| GC036 | gc | 2.10 | 1/3/1/3.4 | gate_fail | The video completed the panning motion, with the yellow sign and pool remaining consistent, but the anchor area on the right underwent severe abrupt changes when panning back—the black trash can disappeared and the dark wall turned into a new glass storefront.<details><summary>judge's original</summary>视频完成了摇摄动作，黄色标志和水池保持一致，但右侧锚定区域在回摇时发生严重突变，黑色垃圾桶消失且深色墙面变成了新的玻璃店面。</details><br>pass 1 gate_fail: The camera only keeps panning left and fails to follow the instructions to pan right and return to the center.<details><summary>judge's original</summary>镜头仅持续向左平移，未能执行向右平移以及回到中心的指令。</details> |
| OE039 | outsight | 3.12 | 3/3/3.5/3 | ok | The camera completed looking around and pulling back, and the dog's pose changed reasonably, but the scene background suffered a severe reset upon returning.<details><summary>judge's original</summary>相机完成了环视和后退，狗的姿态有合理变化，但返回时场景背景发生了严重的重置。</details> |
| OE047 | outsight | 2.12 | 1/2/3/2.5 | ok | In the video, the man instantly teleported from the escalator to flat ground as the camera began turning, completely breaking the off-screen state progression and trajectory continuity of riding the escalator.<details><summary>judge's original</summary>视频中男子在镜头开始转动时瞬间从扶梯瞬移到平地，完全破坏了视线外乘坐扶梯的状态演进和轨迹连续性。</details> |
| OE048 | outsight | 1.50 | 2/1/1/2 | gate_fail | The camera successfully turned right and returned, but the coffee that had accumulated in the cup completely vanished when it reappeared, resulting in a severe state reset.<details><summary>judge's original</summary>镜头成功完成右转并返回，但杯中原本积累的咖啡在重新出现时完全消失，导致状态严重重置。</details><br>pass 3 gate_fail: Did not return to the original perspective as requested.<details><summary>judge's original</summary>未按要求返回原视角。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `pm14-fx-v1-a3` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a3#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 2.35 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a3&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a3/GC031.mp4) |
| GC033 | gc | 3.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a3&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a3/GC033.mp4) |
| GC036 | gc | 2.10 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a3&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a3/GC036.mp4) |
| OE039 | outsight | 3.12 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a3&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a3/OE039.mp4) |
| OE047 | outsight | 2.12 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a3&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a3/OE047.mp4) |
| OE048 | outsight | 1.50 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a3&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a3/OE048.mp4) |
