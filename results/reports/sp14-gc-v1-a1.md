## sp14-gc-v1-a1

> **Scripted dataset moves (no ai player), a/b only.** Moves replayed by the scripted player; never a closed-loop score or the site headline.

runner `lingbot_world2` | action source `agent` | passes 2 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.48 | 0.16 | 6 | 6/6 | 0 | 0 | 2.37, 2.60 |
| **overall** | **2.48** | 0.16 | | | | | 2.37, 2.60 |

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
| GC005 | gc | 2.00 | 2/2 | ok | The camera performs a partial orbiting motion, but fails to complete a full 360-degree orbit and does not return to the initial camera position and perspective.<details><summary>judge's original</summary>相机进行了部分环绕运动，但未能完成完整的360度环绕，且未能返回初始的相机位置和视角。</details> |
| GC016 | gc | 3.40 | 4/2.8 | ok | The video successfully shows the man walking toward the pagoda and looking up, with the consistency, texture, color, and relative positions of all objects well maintained.<details><summary>judge's original</summary>视频成功展示了男子走向宝塔并仰视的过程，各物体的一致性、纹理、颜色和相对位置均保持良好。</details> |
| GC031 | gc | 2.30 | 2/2.6 | ok | Although a rightward rotation is executed, due to a loss of scene consistency, it fails to fully present a 360-degree rotation trajectory back to the initial perspective.<details><summary>judge's original</summary>虽然执行了向右旋转的动作，但由于场景一致性丢失，未能完整呈现360度旋转并回到初始视角的轨迹。</details> |
| GC033 | gc | 3.00 | 2/4 | ok | The video completes a camera pan to the left and then to the right, but during the panning, the amethyst and other items inside the fixed display window severely morph into a glowing purple blob, causing a severe failure in identity, texture, and color consistency.<details><summary>judge's original</summary>视频完成了向左再向右的镜头平移，但在平移期间，固定橱窗内的紫水晶及其他物品严重变形为一个发光的紫色斑块，导致严重的身份、纹理和颜色一致性失败。</details> |
| GC036 | gc | 2.20 | 2.2/2.2 | ok | The video fails to maintain scene consistency when the camera pans back; the small glowing 'HATS' sign disappears, the text shifts onto the adjacent pink panel, and subsequently the panel changes color to black with the text turning into 'HATSS'.<details><summary>judge's original</summary>视频在镜头回摇时未能保持场景一致性，发光的'HATS'小招牌消失，文字转移至旁边的粉色面板上，随后该面板又变色为黑色且文字变为'HATSS'。</details> |
| GC038 | gc | 2.00 | 2/2 | ok | The video exhibits severe scene resets and abrupt object mutations during continuous camera movement, with the initial bed, chair, and fireplace all failing to maintain consistency.<details><summary>judge's original</summary>视频在连续的镜头运动中出现了严重的场景重置和物体突变，初始的床、椅子和壁炉均未能保持一致性。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Scripted dataset moves (no AI player), A/B only.**

[Watch all 6 rollouts of `sp14-gc-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a1&scene=GC005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a1/GC005.mp4) |
| GC016 | gc | 3.40 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a1&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a1/GC016.mp4) |
| GC031 | gc | 2.30 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a1/GC031.mp4) |
| GC033 | gc | 3.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a1/GC033.mp4) |
| GC036 | gc | 2.20 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a1/GC036.mp4) |
| GC038 | gc | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a1&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a1/GC038.mp4) |
