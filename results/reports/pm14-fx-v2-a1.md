## pm14-fx-v2-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.88 | 0.64 | 3 | 3/3 | 0 | 0 | 3.00, 2.13, 2.73, 3.67 |
| outsight | 2.12 | 0.42 | 3 | 3/3 | 0 | 0 | 2.00, 1.67, 2.67, 2.17 |
| **overall** | **2.50** | 0.44 | | | | | 2.50, 1.90, 2.70, 2.92 |

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
| GC031 | gc | 2.20 | 2.6/1.8/2.2/2.2 | ok | The camera completed a 360-degree rotation, but failed to maintain scene consistency upon returning to the initial viewpoint; the large tree trunk disappeared, the characters were replaced, and the bench position changed, resulting in a severe layout reset.<details><summary>judge's original</summary>相机完成了360度旋转，但回到初始视角时未能保持场景的一致性，大树干消失，人物被替换，长椅位置改变，发生了严重的布局重置。</details> |
| GC033 | gc | 3.55 | 3.2/2.4/3.6/5 | ok | The camera successfully panned left and right and returned to the initial view, but upon reappearing, the text on the sign became distorted and a chandelier's position teleported.<details><summary>judge's original</summary>相机成功完成了向左和向右的平移并返回初始视图，但重新出现时标志牌文本变形，且一个吊灯的位置发生了瞬间移动。</details> |
| GC036 | gc | 2.90 | 3.2/2.2/2.4/3.8 | ok | The video successfully executed the requested camera pan and kept the 'HATS' text and overall spatial layout stable, but failed to preserve the original colors of the HATS sign and the pink ceiling when revisiting the initial right-hand area.<details><summary>judge's original</summary>视频成功执行了要求的镜头平移，并保持了'HATS'文本和整体空间布局的稳定，但在重新观察初始右侧区域时，未能保持HATS招牌和粉色天花板的原始颜色。</details> |
| OE039 | outsight | 1.75 | 2/2/1/2 | ok | The content in the returning viewpoint is incorrect.<details><summary>judge's original</summary>返回视角内容错误。</details> |
| OE047 | outsight | 1.75 | 1/2/3/1 | ok | The video failed to properly handle the relationship between the camera rotation and the subject's position, causing the man to teleport to the hallway and back to the escalator during the camera movement, severely breaking the motion trajectory and physical continuity.<details><summary>judge's original</summary>视频未能正确处理镜头旋转与主体位置的关系，导致男子在镜头移动时瞬间转移到走廊又转移回扶梯，运动轨迹和物理连续性严重断裂。</details> |
| OE048 | outsight | 2.88 | 3/1/4/3.5 | ok | The camera did not perform the action of turning back to the left.<details><summary>judge's original</summary>镜头未执行向左转回的动作。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `pm14-fx-v2-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 2.20 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a1/GC031.mp4) |
| GC033 | gc | 3.55 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a1/GC033.mp4) |
| GC036 | gc | 2.90 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a1/GC036.mp4) |
| OE039 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a1&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a1/OE039.mp4) |
| OE047 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a1&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a1/OE047.mp4) |
| OE048 | outsight | 2.88 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a1&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a1/OE048.mp4) |
