## win14-fx-v1-a3

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 9 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.62 | 0.58 | 3 | 3/3 | 0 | 0 | 1.93, 2.40, 3.27, 2.87 |
| outsight | 1.42 | 0.10 | 6 | 6/6 | 0 | 0 | 1.50, 1.50, 1.33, 1.33 |
| **overall** | **2.02** | 0.25 | | | | | 1.72, 1.95, 2.30, 2.10 |

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
| GC031 | gc | 1.40 | 1.4/1/2.2/1 | ok | Although the camera executed a panning rotation to the right, due to severe hallucinations and changes in the scene, it failed to visually return to the initial intersection perspective, only partially meeting the trajectory requirement.<details><summary>judge's original</summary>镜头虽然执行了向右的环视旋转动作，但由于场景发生严重幻觉和变化，未能真正在视觉上回到初始的十字路口视角，仅满足部分轨迹要求。</details> |
| GC033 | gc | 3.40 | 2.2/3.8/4/3.6 | ok | The video successfully completed the required left-and-right camera pan and returned to the initial perspective, keeping the identity, color, and relative positions of key objects in the display window consistent, but the text on the hanging sign appeared as gibberish, failing to meet the exact text requirement.<details><summary>judge's original</summary>视频成功完成了要求的镜头左右平移并返回初始视角，橱窗内关键物体的身份、颜色和相对位置保持一致，但悬挂标志上的文字呈现乱码，未能满足精确文本要求。</details> |
| GC036 | gc | 3.05 | 2.2/2.4/3.6/4 | ok | The video successfully executed the camera pan, and most scene elements remained stable, but the pink panel on the right wall erroneously generated the word 'HATS' when re-entering the view and then disappeared, resulting in an obvious texture consistency failure.<details><summary>judge's original</summary>视频成功执行了平移镜头，大部分场景元素保持稳定，但右侧墙壁的粉色面板在重新进入视野时错误地生成了'HATS'字样随后又消失，导致了明显的纹理一致性失败。</details> |
| OE034 | outsight | 1.00 | 1/1/1/1 | score_1.0 | Although the video executed a camera pan trajectory to the right and then back to the left, when the camera returned, the initial three zebras, ostrich, concrete ground, and lettuce completely disappeared and were replaced by an entirely new scene and zebras, resulting in a severe scene reset and loss of identity.<details><summary>judge's original</summary>视频虽然执行了向右再向左的镜头平移轨迹，但在镜头返回时，初始的三只斑马、鸵鸟、水泥地和生菜完全消失，被全新的场景和斑马取代，发生了严重的场景重置和身份丢失。</details> |
| OE039 | outsight | 1.00 | 1/1/1/1 | score_1.0 | After the camera completed its rotation, the initial fluffy white dog, red chair, and green wall were completely replaced by a different dog, an orange chair, and a glass window, failing to maintain scene and subject consistency.<details><summary>judge's original</summary>镜头完成旋转后，初始的毛茸茸白狗、红色椅子和绿墙被完全替换为不同的狗、橙色椅子和玻璃窗，未能保持场景和主体的一致性。</details> |
| OE047 | outsight | 1.25 | 2/1/1/1 | ok | Although the video fulfilled the camera rotation instruction, after the original man walked through the door, a duplicate of him appeared on the escalator and eventually walked on the ceiling, causing a complete failure in identity, state, and trajectory continuity.<details><summary>judge's original</summary>视频虽然完成了相机的转动指令，但原男子走入门内后，扶梯上出现了他的分身，且该分身最终在天花板上行走，导致身份、状态和轨迹连续性彻底失败。</details> |
| OE048 | outsight | 1.75 | 2/2/1/2 | ok | The camera successfully executed the action of rotating right and returning, but the coffee cup in the original perspective remained completely frozen in state while the camera was away, with no plausible accumulation of coffee liquid level, leading to an evolution failure.<details><summary>judge's original</summary>摄像机成功执行了向右旋转并返回的动作，但原视角的咖啡杯在镜头移开期间状态完全冻结，咖啡液面没有任何合理的积累，导致演变失败。</details> |
| OE058 | outsight | 1.50 | 2/2/1/1 | gate_fail | The video executed the required camera pan, but the cookies and background in the initial scene were completely replaced during the pan, resulting in no coherent decorating progress on the target cookie.<details><summary>judge's original</summary>视频执行了要求的镜头平移，但初始场景中的饼干和背景在平移过程中被完全替换，导致目标饼干上没有连贯的装饰进度。</details><br>pass 3 gate_fail: The camera completely failed to execute the prompt's requested trajectory of rotating 180 degrees to the right and then returning.<details><summary>judge's original</summary>相机完全没有执行提示要求的向右旋转180度然后返回的轨迹动作。</details> |
| OE069 | outsight | 2.00 | 1/2/3/2 | ok | The camera successfully completed the required left-and-right rotation, but while the camera was away, the mother and daughter on the escalator underwent severe identity replacement, with the mother's orange backpack disappearing and her coat changing, leading to low scores in process coherence and identity consistency.<details><summary>judge's original</summary>镜头成功完成了要求的左右旋转，但在镜头移开期间，扶梯上的母女发生了严重的身份替换，母亲的橙色背包消失且外套改变，导致过程连贯性和身份一致性得分较低。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 9 rollouts of `win14-fx-v1-a3` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 1.40 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a3/GC031.mp4) |
| GC033 | gc | 3.40 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a3/GC033.mp4) |
| GC036 | gc | 3.05 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a3/GC036.mp4) |
| OE034 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a3/OE034.mp4) |
| OE039 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a3/OE039.mp4) |
| OE047 | outsight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a3/OE047.mp4) |
| OE048 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a3/OE048.mp4) |
| OE058 | outsight | 1.50 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a3/OE058.mp4) |
| OE069 | outsight | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=win14-fx-v1-a3&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-win14-fx-v1-a3/OE069.mp4) |
