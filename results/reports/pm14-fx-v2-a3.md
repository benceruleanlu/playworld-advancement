## pm14-fx-v2-a3

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.33 | 0.80 | 3 | 2/3 | 0 | 0 | 2.27, 2.20, 1.47, 3.40 |
| outsight | 1.50 | 0.19 | 3 | 3/3 | 0 | 0 | 1.67, 1.33, 1.67, 1.33 |
| **overall** | **1.92** | 0.34 | | | | | 1.97, 1.77, 1.57, 2.37 |

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
| GC031 | gc | 2.20 | 1.8/1.6/1.2/4.2 | ok | The video completes a 360-degree pan, but a severe scene reset occurs upon returning to the initial viewpoint: the sign structure changes, the huge tree trunk disappears, and the people are completely replaced.<details><summary>judge's original</summary>视频完成了360度环视，但回到初始视角时发生了严重的场景重置，指示牌结构改变，巨大的树干消失，人物被完全替换。</details> |
| GC033 | gc | 3.25 | 4/4/1/4 | gate_fail | The video successfully demonstrates the camera panning left and returning, with all key items in the initial shop window maintaining high consistency when they reappear.<details><summary>judge's original</summary>视频成功展示了镜头向左平移并返回的过程，初始橱窗内的所有关键物品在重新出现时均保持了高度的一致性。</details><br>pass 3 gate_fail: The camera first turns right, which is completely opposite to the left turn required by the instruction.<details><summary>judge's original</summary>相机首先向右转动，与指令要求的向左转动方向完全相反。</details> |
| GC036 | gc | 1.55 | 1/1/2.2/2 | gate_fail | During the camera pan, the background storefronts undergo multiple severe hard resets and sudden color shifts, causing identity and spatial layout to fail completely.<details><summary>judge's original</summary>视频在镜头平移过程中，背景店面发生了多次严重的硬重置和颜色突变，导致身份和空间布局完全失效。</details><br>pass 1 gate_fail: The video only shows a continuous pan to the left, failing to execute the instructed movement of panning right and returning to the center.<details><summary>judge's original</summary>视频仅显示持续向左平移，未能执行指令要求的向右平移并返回中心的动作。</details> |
| OE039 | outsight | 1.00 | 1/1/1/1 | score_1.0 | Failed to return to the initial viewpoint.<details><summary>judge's original</summary>未能回到初始视角。</details> |
| OE047 | outsight | 2.00 | 2/2/2/2 | ok | The video executes the camera movement, but the man duplicates and teleports across the corridor and walls, severely breaking physical coherence.<details><summary>judge's original</summary>视频执行了相机运动，但男子在走廊和墙壁上出现分身和瞬移，严重破坏了物理连贯性。</details> |
| OE048 | outsight | 1.50 | 2/1/2/1 | ok | The camera completes panning right and returning, but the coffee pouring process freezes completely with no accumulation, and a brand-new container to catch the coffee is hallucinated on the right during the pan.<details><summary>judge's original</summary>镜头完成了向右平移并返回的动作，但咖啡注入过程完全冻结无积累，且平移时右侧幻觉出全新的接咖啡容器。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `pm14-fx-v2-a3` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a3#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 2.20 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a3&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a3/GC031.mp4) |
| GC033 | gc | 3.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a3&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a3/GC033.mp4) |
| GC036 | gc | 1.55 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a3&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a3/GC036.mp4) |
| OE039 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a3&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a3/OE039.mp4) |
| OE047 | outsight | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a3&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a3/OE047.mp4) |
| OE048 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a3&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a3/OE048.mp4) |
