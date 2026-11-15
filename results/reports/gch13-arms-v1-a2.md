## gch13-arms-v1-a2

runner `lingbot_world2_1p3b` | action source `agent` | passes 4 | tasks 3 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 1.48 | 0.35 | 3 | 2/3 | 0 | 0 | 1.73, 1.00, 1.73, 1.47 |
| **overall** | **1.48** | 0.35 | | | | | 1.73, 1.00, 1.73, 1.47 |

**Reference (paper, full benchmark)**

| model | gc | if | insight | outsight | overall |
|---|---:|---:|---:|---:|---:|
| Genie 3 | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |

[All experiments on the results site](https://benceruleanlu.github.io/playworld-advancement/)

### Tasks

| task | family | mean | status | reason |
|---|---|---:|---|---|
| GC031 | gc | 1.65 | ok | 相机完成了360度旋转，但在返回初始视角时，场景受到严重的黄绿色噪点破坏，导致物体形状、纹理和颜色出现严重的一致性失败。 |
| GC033 | gc | 1.80 | ok | 镜头仅执行了向左旋转的动作，且一直持续，未能按照指令要求向右转回初始视角。 |
| GC036 | gc | 1.00 | gate_fail | 视频仅完成了向左和向右的平移，缺失了最后向左平移回到中心的动作，轨迹未完全按照指令执行。 |

### Scenes

[Watch all 3 rollouts of `gch13-arms-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=gch13-arms-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 1.65 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=gch13-arms-v1-a2&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-gch13-arms-v1-a2/GC031.mp4) |
| GC033 | gc | 1.80 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=gch13-arms-v1-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-gch13-arms-v1-a2/GC033.mp4) |
| GC036 | gc | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=gch13-arms-v1-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-gch13-arms-v1-a2/GC036.mp4) |
