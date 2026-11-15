## win14-fx-v1-a2

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 9 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.85 | 0.55 | 3 | 3/3 | 0 | 0 | 2.53, 2.60, 2.60, 3.67 |
| outsight | 2.12 | 0.35 | 6 | 5/6 | 0 | 0 | 1.92, 2.33, 2.50, 1.75 |
| **overall** | **2.49** | 0.20 | | | | | 2.23, 2.47, 2.55, 2.71 |

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
| GC031 | gc | 2.95 | 1.8/2.6/2.4/5 | ok | Although the camera panned to the right, it failed to complete a full 360-degree rotation and return to the initial viewpoint, failing to meet the revisit requirement.<details><summary>judge's original</summary>镜头虽然进行了向右的环视，但未能完成完整的360度旋转并回到初始视角，未满足重访要求。</details> |
| GC033 | gc | 3.55 | 3.8/3.2/3.2/4 | ok | The video successfully executes the requested camera motion, and the objects in the display window reappear with consistent identity, layout, and color, with only minor degradation of the sign text. |
| GC036 | gc | 2.05 | 2/2/2.2/2 | ok | The HATS sign morphed during the camera pan, shifting from a gray storefront to a magenta storefront, and then its spelling changed to HATTS, resulting in severe inconsistencies in identity, color, and relative position.<details><summary>judge's original</summary>HATS招牌在镜头平移过程中发生变异，从灰色店面转移到洋红色店面，随后拼写变为HATTS，导致身份、颜色和相对位置严重不一致。</details> |
| OE034 | outsight | 1.75 | 1/4/1/1 | ok | The video executed the required back-and-forth camera movement, but failed to maintain the state of off-screen objects. After the camera returned, the initial three zebras, ostrich, and lettuce completely disappeared and were replaced by brand-new zebras and a different background, causing severe scene resets and hallucinations.<details><summary>judge's original</summary>视频执行了要求的镜头往返运动，但未能保持视野外物体的状态，镜头返回后初始的三只斑马、鸵鸟和生菜完全消失，被全新的斑马和背景取代，发生了严重的场景重置和幻觉。</details> |
| OE039 | outsight | 3.25 | 3.5/2/4/3.5 | ok | The camera successfully completed a 360-degree rotation and pulled back, and the dog plausibly jumped from the chair to the floor while off-screen, but the shapes of the dog's harness and the red chair underwent severe mutations upon reappearing.<details><summary>judge's original</summary>相机成功完成了360度旋转并后退，狗在视野外合理地从椅子跳到了地板上，但狗的胸背带和红色椅子的形状在重新出现时发生了严重的突变。</details> |
| OE047 | outsight | 1.50 | 1/2/2/1 | gate_fail | The camera failed to execute the instruction to turn right and return.<details><summary>judge's original</summary>镜头未执行向右转动并返回的指令。</details> |
| OE048 | outsight | 3.25 | 3/3/4/3 | ok | The video successfully showed the camera turning right and returning, during which the off-screen coffee level rose plausibly. However, after returning to the initial viewpoint, the camera continued panning excessively to the left, causing multiple duplicate potted plant hallucinations to appear in the background.<details><summary>judge's original</summary>视频成功展示了镜头向右转动并返回的过程，期间画面外的咖啡液面合理上升，但在回到初始视角后镜头继续向左过度平移，导致背景中出现了多个重复的盆栽幻觉。</details> |
| OE058 | outsight | 1.25 | 1/1/2/1 | gate_fail | The camera failed to return to the initial viewpoint, and the subject moved along with the camera, failing to achieve the effect of leaving the field of view.<details><summary>judge's original</summary>镜头未返回初始视角，且主体随镜头移动，未实现离开视线的效果。</details> |
| OE069 | outsight | 1.75 | 2/2/2/1 | ok | The camera successfully completed the left-and-right rotation, but the off-screen person did not move down with the escalator, and upon reappearing, their backpack changed color and an extra scarf appeared, lacking plausible physical evolution.<details><summary>judge's original</summary>镜头成功完成左右旋转，但视线外的人物未随扶梯向下移动，且重新出现时背包颜色改变并多出围巾，缺乏合理的物理演变。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 9 rollouts of `win14-fx-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 2.95 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a2/GC031.mp4) |
| GC033 | gc | 3.55 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a2/GC033.mp4) |
| GC036 | gc | 2.05 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a2/GC036.mp4) |
| OE034 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a2/OE034.mp4) |
| OE039 | outsight | 3.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a2/OE039.mp4) |
| OE047 | outsight | 1.50 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a2/OE047.mp4) |
| OE048 | outsight | 3.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a2/OE048.mp4) |
| OE058 | outsight | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a2/OE058.mp4) |
| OE069 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a2&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a2/OE069.mp4) |
