## pm14-fx-v2-a4

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.65 | 0.26 | 3 | 2/3 | 0 | 0 | 2.53, 3.00, 2.67, 2.40 |
| outsight | 2.67 | 0.38 | 3 | 3/3 | 0 | 0 | 3.00, 3.00, 2.33, 2.33 |
| **overall** | **2.66** | 0.28 | | | | | 2.77, 3.00, 2.50, 2.37 |

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
| GC031 | gc | 2.00 | 1.4/1.4/3/2.2 | ok | Although the camera performs a rotation, it keeps turning right and fails to complete a full 360-degree rotation to return to the initial viewpoint.<details><summary>judge's original</summary>镜头虽然执行了旋转动作，但一直在向右转，未能完成完整的360度旋转并回到初始视角。</details> |
| GC033 | gc | 4.15 | 4/4.6/4/4 | ok | The video successfully executes the camera movement of rotating left and returning. The key objects in the revisited initial display window maintain extremely high consistency in identity, texture, color, and relative position.<details><summary>judge's original</summary>视频成功执行了向左旋转并返回的镜头动作，重新观察到的初始橱窗内各关键物体在身份、纹理、颜色及相对位置上均保持了极高的一致性。</details> |
| GC036 | gc | 1.80 | 2.2/3/1/1 | gate_fail | When the camera pans to revisit the right wall, the original yellow sign and dark wall are completely replaced by a pink storefront, resulting in a severe failure in identity and color consistency.<details><summary>judge's original</summary>相机平移重访右侧墙壁时，原黄色招牌和暗墙被粉色店面完全替换，导致严重的身份和颜色一致性失败。</details><br>pass 3 gate_fail: The camera only keeps panning left and fails to execute the instruction to pan right and return to the center.<details><summary>judge's original</summary>镜头仅持续向左平移，未能执行向右平移并返回中心的指令。</details> |
| OE039 | outsight | 3.12 | 3.5/4/3/2 | ok | The video shows plausible camera rotation, pulling back, and progression of the dog's posture, but mistakenly generates a duplicate of the subject midway through the rotation.<details><summary>judge's original</summary>视频展示了合理的相机旋转与后退及狗的姿态演进，但在旋转中途错误地生成了主体的复制品。</details> |
| OE047 | outsight | 2.00 | 2/3/1/2 | gate_fail | Although the video completes the camera movements of turning right, turning back, and looking up, after entering the elevator, the man defies the laws of physics by teleporting back to the bottom of the escalator when the camera turns back, leading to a severe failure in identity and trajectory continuity.<details><summary>judge's original</summary>视频虽然完成了镜头的右转、转回和仰视动作，但男子在进入电梯后于镜头转回时违背物理规律地瞬移回扶梯底部，导致严重的身份与轨迹连贯性失败。</details><br>pass 3 gate_fail: The camera fails to execute the requested right turn and return. |
| OE048 | outsight | 2.88 | 3.5/2/3/3 | ok | In the first half, the video successfully executes the requested camera turn to the right and return, with the coffee level in the cup rising plausibly. However, after completing the action, the camera makes several unnecessary side-to-side swings, and the coffee accumulated in the cup suddenly empties and resets in subsequent frames.<details><summary>judge's original</summary>视频在前半段成功执行了要求的镜头右转和转回，且杯中咖啡液面合理上升；但在完成动作后，镜头进行了多次多余的左右摆动，且杯中积累的咖啡在后续画面中突然清空重置。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `pm14-fx-v2-a4` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a4#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a4&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a4/GC031.mp4) |
| GC033 | gc | 4.15 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a4&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a4/GC033.mp4) |
| GC036 | gc | 1.80 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a4&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a4/GC036.mp4) |
| OE039 | outsight | 3.12 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a4&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a4/OE039.mp4) |
| OE047 | outsight | 2.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a4&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a4/OE047.mp4) |
| OE048 | outsight | 2.88 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v2-a4&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v2-a4/OE048.mp4) |
