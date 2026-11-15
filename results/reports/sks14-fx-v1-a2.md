## sks14-fx-v1-a2

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| outsight | 1.65 | 0.10 | 6 | 5/6 | 0 | 0 | 1.67, 1.50, 1.75, 1.67 |
| **overall** | **1.65** | 0.10 | | | | | 1.67, 1.50, 1.75, 1.67 |

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
| OE034 | outsight | 1.25 | 1/1/2/1 | ok | The camera panned right and then left, but upon returning, the original scene completely collapsed, replaced by an extremely oversized close-up of a zebra. The lettuce on the ground and the ostrich disappeared, constituting severe scene reset and hallucination.<details><summary>judge's original</summary>镜头执行了向右再向左的平移，但返回时原场景完全崩坏，取而代之的是比例极度放大的斑马特写，地面生菜和鸵鸟消失，构成了严重的场景重置和幻觉。</details> |
| OE039 | outsight | 1.50 | 1/2/2/1 | ok | Failed to return to the original viewpoint, and the scene reset.<details><summary>judge's original</summary>未能回到原始视角，场景发生了重置。</details> |
| OE047 | outsight | 1.50 | 2/1/1/2 | ok | The camera moved according to the prompt, but the man unreasonably teleported when the camera moved away, and his appearance severely mutated in the latter part.<details><summary>judge's original</summary>镜头按提示词移动，但男子在镜头移开时发生不合理的瞬移，且后段外观严重变异。</details> |
| OE048 | outsight | 3.12 | 3/3/3.5/3 | ok | The video successfully showed the camera turning right and turning back, and the coffee level in the cup rose reasonably. However, the potted plant in the background disappeared when turning back, the cup's structure changed, and the camera made many unnecessary extra movements after completing the instruction.<details><summary>judge's original</summary>视频成功展示了镜头右转并转回的过程，且杯中咖啡液面合理上升，但背景盆栽在转回时消失，杯子结构发生改变，且镜头在完成指令后有较多不必要的额外移动。</details> |
| OE058 | outsight | 1.00 | 1/1/1/1 | gate_fail | The camera failed to return to the initial viewpoint, and the scene completely changed.<details><summary>judge's original</summary>镜头未能回到初始视角，且场景完全改变。</details><br>pass 2 gate_fail: Did not perform the action of returning to the original viewpoint.<details><summary>judge's original</summary>未执行返回原视角的动作。</details> |
| OE069 | outsight | 1.50 | 2/1/1/2 | ok | The camera executes the requested pan, but the original escalator environment undergoes a hard reset, replacing the steps with a flat floor when the subjects reappear. |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `sks14-fx-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| OE034 | outsight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a2&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a2/OE034.mp4) |
| OE039 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a2&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a2/OE039.mp4) |
| OE047 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a2&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a2/OE047.mp4) |
| OE048 | outsight | 3.12 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a2&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a2/OE048.mp4) |
| OE058 | outsight | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a2&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a2/OE058.mp4) |
| OE069 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sks14-fx-v1-a2&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sks14-fx-v1-a2/OE069.mp4) |
