## sp14-gc-v1-a4

> **Scripted dataset moves (no ai player), a/b only.** Moves replayed by the scripted player; never a closed-loop score or the site headline.

runner `lingbot_world2` | action source `agent` | passes 2 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.77 | 0.05 | 6 | 6/6 | 0 | 0 | 2.73, 2.80 |
| **overall** | **2.77** | 0.05 | | | | | 2.73, 2.80 |

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
| GC005 | gc | 1.50 | 1/2 | ok | The video experiences severe scene resets and object deformation during camera movement, with the initial statue, pedestal, and background buildings completely lost and replaced by unrelated objects.<details><summary>judge's original</summary>视频在摄像机移动过程中发生了严重的场景重置和物体形变，初始雕像、底座和背景建筑完全丢失并被替换为不相关的物体。</details> |
| GC016 | gc | 4.00 | 4/4 | ok | As the man walks toward the pagoda and looks up, the video maintains good consistency in object identity, texture, color, and spatial relationships.<details><summary>judge's original</summary>视频在男子走向宝塔并仰视的过程中，较好地保持了物体身份、纹理、颜色和空间关系的连贯性。</details> |
| GC031 | gc | 2.50 | 2.6/2.4 | ok | The camera completes a 360-degree pan, but upon returning to the initial area, the signpost's structure changes, and the original two people and bench fail to reappear.<details><summary>judge's original</summary>镜头完成了360度环视，但回到初始区域时指示牌结构改变，且原本的两人和长椅未能重现。</details> |
| GC033 | gc | 4.00 | 4/4 | ok | The camera successfully pans left and returns, with all key objects inside the initial shop window reappearing consistently.<details><summary>judge's original</summary>镜头成功完成向左平移并返回，初始橱窗内的所有关键物体均一致重现。</details> |
| GC036 | gc | 2.20 | 2/2.4 | ok | The camera performs noticeable panning movement in the video, but the scene undergoes a severe hard reset, causing the 'HATS' sign to appear repeatedly, the text to change to 'HASTS', and the relative positions of the store's interior structure and ceiling panels to change impossibly.<details><summary>judge's original</summary>视频中相机进行了明显的平移运动，但场景出现了严重的硬重置，导致'HATS'招牌重复出现、文本变为'HASTS'，且店铺内部结构和天花板面板的相对位置发生了不可能的改变。</details> |
| GC038 | gc | 2.40 | 2.8/2 | ok | The video experiences multiple severe hard resets during camera panning, resulting in discontinuities in spatial layout and object identity, although the initial scene reappears at the end with consistent appearance.<details><summary>judge's original</summary>视频在相机平移过程中发生了多次严重的硬重置，导致空间布局和物体身份不连续，尽管初始场景在末尾重新出现且外观保持一致。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Scripted dataset moves (no AI player), A/B only.**

[Watch all 6 rollouts of `sp14-gc-v1-a4` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a4#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a4&scene=GC005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a4/GC005.mp4) |
| GC016 | gc | 4.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a4&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a4/GC016.mp4) |
| GC031 | gc | 2.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a4&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a4/GC031.mp4) |
| GC033 | gc | 4.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a4&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a4/GC033.mp4) |
| GC036 | gc | 2.20 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a4&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a4/GC036.mp4) |
| GC038 | gc | 2.40 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=sp14-gc-v1-a4&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-sp14-gc-v1-a4/GC038.mp4) |
