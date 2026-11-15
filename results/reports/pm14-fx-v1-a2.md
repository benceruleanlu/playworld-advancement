## pm14-fx-v1-a2

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.37 | 0.28 | 3 | 2/3 | 0 | 0 | 2.00, 2.33, 2.67, 2.47 |
| outsight | 2.00 | 0.47 | 3 | 2/3 | 0 | 0 | 2.67, 2.00, 1.67, 1.67 |
| **overall** | **2.18** | 0.11 | | | | | 2.33, 2.17, 2.17, 2.07 |

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
| GC031 | gc | 2.00 | 1.6/2.2/1.8/2.4 | ok | The video completed the 360-degree panning motion, but upon returning to the initial forked path, the scene underwent a severe reset: the large tree trunk disappeared, the couple was replaced, and the bench changed position, failing to maintain consistency with the initial environment.<details><summary>judge's original</summary>视频完成了360度环视动作，但回到初始分叉路口时场景发生了严重重置，大树干消失，情侣被替换，长椅位置改变，未能保持初始环境的一致性。</details> |
| GC033 | gc | 3.75 | 3.4/3.8/3.8/4 | ok | The video successfully completed the pan-left and return motion. The items originally in the display window maintained good identity and position consistency when reappearing, with only slight blurring degradation on the text of the sign.<details><summary>judge's original</summary>视频成功完成了向左平移并返回的动作，原橱窗内的物品在重新出现时保持了较好的身份和位置一致性，仅标志牌上的文字出现了轻微的模糊退化。</details> |
| GC036 | gc | 1.35 | 1/1/2.4/1 | gate_fail | The camera movement direction executed in the video (right-left-right) is completely opposite to the prompt's requirement to 'pan from left to right, then return to the center' (which should be left-right-left).<details><summary>judge's original</summary>视频执行的镜头运动方向（右-左-右）与提示词要求的‘从左向右平移，然后回到中心’（应为左-右-左）完全相反。</details> |
| OE039 | outsight | 1.75 | 2/1/2/2 | ok | After the camera completed the 360-degree rotation, the original dog and green wall background were replaced by a completely different prick-eared dog and an orange wall, resulting in severe identity and scene mutation without reasonable hidden state evolution or process accumulation.<details><summary>judge's original</summary>镜头完成360度旋转后，原本的狗和绿色墙壁背景被完全不同的立耳狗和橙色墙壁替换，发生了严重的身份和场景突变，缺乏合理的隐藏状态演变和过程积累。</details> |
| OE047 | outsight | 1.75 | 3/2/1/1 | gate_fail | Although the video fulfilled the camera movement instruction, the man erroneously teleported to the hallway while out of frame and then contradictorily reset back to the escalator, causing severe trajectory discontinuity and physical logic failure.<details><summary>judge's original</summary>视频虽然完成了镜头运动指令，但男子在镜头移开时错误地瞬移至走廊，随后又矛盾地重置回扶梯，导致严重的轨迹断裂和物理逻辑失败。</details><br>pass 3 gate_fail: The camera does not turn right as requested. |
| OE048 | outsight | 2.50 | 3/3/2/2 | ok | The video successfully demonstrated the process of the camera turning right and returning, and the coffee liquid level rose reasonably while out of frame; however, a second coffee machine set was erroneously duplicated when the camera turned right, and after turning back, the background potted plant was replaced and an extra window appeared, resulting in poor subject consistency.<details><summary>judge's original</summary>视频成功展示了镜头右转并返回的过程，且隐藏期间咖啡液面合理上升，但镜头右转时错误地复制了第二套咖啡机，且转回后背景盆栽发生替换并多出窗户，主体一致性较差。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `pm14-fx-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a2&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a2/GC031.mp4) |
| GC033 | gc | 3.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a2/GC033.mp4) |
| GC036 | gc | 1.35 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a2/GC036.mp4) |
| OE039 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a2&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a2/OE039.mp4) |
| OE047 | outsight | 1.75 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a2&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a2/OE047.mp4) |
| OE048 | outsight | 2.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=pm14-fx-v1-a2&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-pm14-fx-v1-a2/OE048.mp4) |
