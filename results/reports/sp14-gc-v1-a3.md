## sp14-gc-v1-a3

> **Scripted dataset moves (no ai player), a/b only.** Moves replayed by the scripted player; never a closed-loop score or the site headline.

runner `lingbot_world2` | action source `agent` | passes 2 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.23 | 0.24 | 6 | 6/6 | 0 | 0 | 2.40, 2.07 |
| **overall** | **2.23** | 0.24 | | | | | 2.40, 2.07 |

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
| GC005 | gc | 1.50 | 2/1 | gate_fail | The camera completed a 360-degree orbit and returned to the initial viewing direction, but it stopped closer than the starting position and failed to fully return to the original camera position.<details><summary>judge's original</summary>相机完成了360度环绕并回到了初始的观察方向，但最终停留的位置比初始位置更近，未能完全回到原始的相机位置。</details><br>pass 2 gate_fail: The camera failed to perform a 360-degree orbit around the sculpture and did not return to its initial position and perspective at all; the motion trajectory does not match the instructions.<details><summary>judge's original</summary>相机未能执行360度环绕雕塑的轨迹，且完全没有回到初始的相机位置和视角，运动轨迹与指令要求不符。</details> |
| GC016 | gc | 3.00 | 2/4 | ok | The first 13 seconds of the video are completely static, followed by a hard cut that resets the scene and characters. There is a lack of substantial motion progression throughout, triggering the minimum score limit for the dynamics threshold.<details><summary>judge's original</summary>视频前13秒完全静止，随后发生硬切导致场景和人物重置，全程缺乏实质性动作进展，触发动态性门槛最低分限制。</details> |
| GC031 | gc | 2.10 | 2.2/2 | ok | The camera rotated to the right, but failed to complete a full 360-degree rotation and return to the initial viewpoint.<details><summary>judge's original</summary>相机进行了向右旋转，但未能完成完整的360度旋转并回到初始视角。</details> |
| GC033 | gc | 3.20 | 4/2.4 | ok | The video shows continuous camera translation motion, and objects from the initial scene, such as the amethyst geode and signs, maintain a high degree of consistency when re-entering the field of view.<details><summary>judge's original</summary>视频展示了连续的相机平移运动，初始场景中的紫水晶洞、标志牌等物体在重新进入视野时保持了高度的一致性。</details> |
| GC036 | gc | 2.10 | 2.2/2 | ok | The video failed to maintain scene consistency during camera translation; the sign text suffered severe distortion and duplication, and the spatial layout turned into infinitely extending repetitive shops.<details><summary>judge's original</summary>视频在镜头平移时未能保持场景的一致性，招牌文字发生严重变形和重复，空间布局也变成了无限延伸的重复店铺。</details> |
| GC038 | gc | 1.50 | 2/1 | ok | The video executed the actions of turning right, walking forward (reaching the stove), and turning left, but the left turn lasted too long and caused the direction to deviate. The subsequent walk forward did not return to the starting point, nor did it fulfill the requirement of finally turning toward the initial direction, failing to successfully revisit the starting point.<details><summary>judge's original</summary>视频执行了向右转、向前走（到达火炉）以及向左转的动作，但向左转的时间过长导致方向偏离，随后的向前走并未回到起点，也没有完成最后转向初始方向的要求，未能成功重访起点。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Scripted dataset moves (no AI player), A/B only.**

[Watch all 6 rollouts of `sp14-gc-v1-a3` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a3#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.50 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a3&scene=GC005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a3/GC005.mp4) |
| GC016 | gc | 3.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a3&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a3/GC016.mp4) |
| GC031 | gc | 2.10 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a3&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a3/GC031.mp4) |
| GC033 | gc | 3.20 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a3&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a3/GC033.mp4) |
| GC036 | gc | 2.10 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a3&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a3/GC036.mp4) |
| GC038 | gc | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a3&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a3/GC038.mp4) |
