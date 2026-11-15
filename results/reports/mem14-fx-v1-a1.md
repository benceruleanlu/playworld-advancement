## mem14-fx-v1-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 9 | missing 1

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.77 | 0.49 | 3 | 3/3 | 0 | 0 | 2.73, 2.53, 2.33, 3.47 |
| outsight | 1.93 | 0.16 | 6 | 5/6 | 1 | 0 | 2.08, 1.83, 2.04, 1.75 |
| **overall** | **2.35** | 0.20 | | | | | 2.41, 2.18, 2.19, 2.61 |

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
| GC031 | gc | 1.80 | 1.6/1.4/1.4/2.8 | ok | The camera successfully completed a 360-degree rotation, but upon returning to the initial viewpoint, the large tree trunk originally behind the signpost completely disappeared, the signpost's structure changed, and the initial two people merged into one during the camera pan, showing severe failures in identity, color, and relative position consistency.<details><summary>judge's original</summary>镜头成功完成了360度旋转，但在回到初始视角时，原本位于指示牌后方的大树干完全消失，指示牌结构改变，且初始的两人在镜头平移时融合成了一人，存在严重的身份、颜色和相对位置一致性失败。</details> |
| GC033 | gc | 3.75 | 3.6/4/3.4/4 | ok | The video successfully showed the camera turning left and returning to the initial shop window. The objects inside the window maintained good structural and positional consistency upon reappearing, but the text on the 'Gift Vouchers' sign changed noticeably.<details><summary>judge's original</summary>视频成功展示了相机向左转动并返回初始橱窗的过程，橱窗内的物体在重新出现时保持了良好的结构和位置一致性，但'Gift Vouchers'标志上的文字发生了明显的改变。</details> |
| GC036 | gc | 2.75 | 3/2.2/2.2/3.6 | ok | The video showed a coherent camera pan, but the 'HATS' sign on the right underwent an obvious abrupt change in color (from yellow to magenta) and structure when re-entering the frame.<details><summary>judge's original</summary>视频展示了连贯的镜头平移，但右侧的'HATS'招牌在重新进入视野时发生了明显的颜色（黄变紫红）和结构突变。</details> |
| OE034 | outsight | 1.00 | 1/1/1/1 | score_1.0 | The camera failed to return to the initial viewpoint.<details><summary>judge's original</summary>镜头未能返回初始视角。</details> |
| OE039 | outsight | 1.50 | 2/1/2/1 | ok | After the camera completed a 360-degree rotation, the original puppy and background wall were completely replaced, resulting in a severe scene reset and loss of identity.<details><summary>judge's original</summary>镜头完成360度旋转后，原本的小狗和背景墙壁被完全替换，发生了严重的场景重置和身份丢失。</details> |
| OE047 | outsight | 2.00 | 2/2/2/2 | ok | The video successfully executed the camera turning instruction, but the main male subject experienced severe teleportation and trajectory breaks during the camera movement, teleporting from the escalator to the hallway and then resetting back to the escalator, breaking physical continuity.<details><summary>judge's original</summary>视频成功执行了镜头的转向指令，但主体男子在镜头移动期间发生了严重的瞬移和轨迹断裂，从扶梯瞬移至走廊又重置回扶梯，破坏了物理连续性。</details> |
| OE048 | outsight | 3.19 | 3/3/3.25/3.5 | ok | The camera successfully turned right and turned back. The coffee liquid level rose reasonably while out of frame, but the cup and background plants were severely replaced upon reappearing.<details><summary>judge's original</summary>镜头成功完成右转并转回，咖啡液面在移开期间合理上升，但重新出现时杯子和背景植物发生了严重的替换。</details> |
| OE058 | outsight | 1.00 | 1/1/1/1 | missing |  |
| OE069 | outsight | 2.88 | 3.5/3/3/2 | ok | The camera successfully rotated left and turned back, and the escalator maintained its downward operation. However, after the camera turned back, the pattern on the mother's backpack changed noticeably, and the relative distance between the characters and the camera shortened unreasonably.<details><summary>judge's original</summary>镜头成功完成了向左旋转并转回的动作，扶梯也保持了向下的运行状态，但镜头转回后母亲的背包图案发生了明显改变，且人物与镜头的相对距离出现了不合理的缩短。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 8 rollouts of `mem14-fx-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 1.80 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a1/GC031.mp4) |
| GC033 | gc | 3.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a1/GC033.mp4) |
| GC036 | gc | 2.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a1/GC036.mp4) |
| OE034 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a1&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a1/OE034.mp4) |
| OE039 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a1&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a1/OE039.mp4) |
| OE047 | outsight | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a1&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a1/OE047.mp4) |
| OE048 | outsight | 3.19 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a1&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a1/OE048.mp4) |
| OE058 | outsight | 1.00 | missing | no video |
| OE069 | outsight | 2.88 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a1&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a1/OE069.mp4) |
