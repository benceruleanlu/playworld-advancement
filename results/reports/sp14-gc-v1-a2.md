## sp14-gc-v1-a2

> **Scripted dataset moves (no ai player), a/b only.** Moves replayed by the scripted player; never a closed-loop score or the site headline.

runner `lingbot_world2` | action source `agent` | passes 2 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.05 | 0.16 | 6 | 4/6 | 0 | 0 | 2.17, 1.93 |
| **overall** | **2.05** | 0.16 | | | | | 2.17, 1.93 |

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
| GC005 | gc | 1.00 | 1/1 | gate_fail | The camera did not execute a 360-degree orbit trajectory around the sculpture, nor did it return to the initial camera position and viewing direction; it only moved forward, panned, and moved backward.<details><summary>judge's original</summary>相机并未执行360度环绕雕塑的轨迹，也未返回初始的相机位置和观看方向，仅进行了简单的前进、平移和后退。</details> |
| GC016 | gc | 2.00 | 2/2 | ok | In the first half of the video, the man walks toward the pagoda, but after the camera tilts up, the man suddenly changes into a different person facing the camera, and then turns into a huge camera structure, showing severe consistency and spatial positioning errors.<details><summary>judge's original</summary>视频前半段男子走向佛塔，但镜头上移后男子突变为面向镜头的不同人物，随后变成巨大的相机结构，存在严重的一致性和空间位置错误。</details> |
| GC031 | gc | 2.00 | 2/2 | ok | The camera rotated partially to the right, showing a rotational action, but failed to complete a 360-degree rotation or return to the initial viewpoint, failing to meet the task requirement of returning to the original viewpoint.<details><summary>judge's original</summary>镜头向右旋转了部分角度，有执行旋转的动作，但未能完成360度旋转，也没有回到初始的视角，未满足回到原视角的任务要求。</details> |
| GC033 | gc | 3.80 | 4/3.6 | ok | The camera successfully completed the action of rotating left and returning, and most objects inside the display window remained consistent, but the text on the sign changed noticeably after returning.<details><summary>judge's original</summary>镜头成功完成了向左旋转并返回的动作，橱窗内大部分物体保持了一致性，但标志上的文本在返回后发生了明显的改变。</details> |
| GC036 | gc | 1.50 | 2/1 | gate_fail | The video failed to maintain scene consistency during the camera pan, as the HATS sign and storefront structure experienced severe distortion, duplication, and position shifting.<details><summary>judge's original</summary>视频在镜头平移过程中未能保持场景一致性，HATS招牌和店面结构发生了严重的变形、复制和位置转移。</details><br>pass 2 gate_fail: The actual camera movement trajectory in the video (right-left-right) is completely opposite to the requested basic motion sequence (left-right-left).<details><summary>judge's original</summary>视频中的镜头实际运动轨迹（右-左-右）与请求的基础动作序列（左-右-左）完全相反。</details> |
| GC038 | gc | 2.00 | 2/2 | ok | Although the required round-trip trajectory was completed in the first 12 seconds, the second half of the video contains a lot of unrequested continuous forward movement, resulting in the trajectory not fully staying in the target state.<details><summary>judge's original</summary>虽然前12秒完成了要求的往返轨迹，但视频后半段包含了大量未要求的持续向前移动，导致轨迹未完全停留在目标状态。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Scripted dataset moves (no AI player), A/B only.**

[Watch all 6 rollouts of `sp14-gc-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a2&scene=GC005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a2/GC005.mp4) |
| GC016 | gc | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a2&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a2/GC016.mp4) |
| GC031 | gc | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a2&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a2/GC031.mp4) |
| GC033 | gc | 3.80 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a2/GC033.mp4) |
| GC036 | gc | 1.50 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a2/GC036.mp4) |
| GC038 | gc | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a2&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a2/GC038.mp4) |
