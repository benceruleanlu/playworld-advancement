## smk14-arms-gc-v2-a1

> **Capped smoke run: 10 agent chunks per rollout (official 30), not comparable to official scores.** Smoke tier only; never the site headline.

runner `lingbot_world2` | action source `agent` | passes 4 | tasks 3 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.92 | 0.63 | 3 | 2/3 | 0 | 0 | 3.40, 3.00, 3.27, 2.00 |
| **overall** | **2.92** | 0.63 | | | | | 3.40, 3.00, 3.27, 2.00 |

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
| GC005 | gc | 1.55 | gate_fail | 相机仅在雕塑的前方和局部侧面进行了移动，没有执行完整的360度环绕轨迹。 |
| GC033 | gc | 3.95 | ok | 视频成功展示了相机向左平移后返回的动作，橱窗内的关键物体在重新出现时保持了高度的一致性。 |
| GC036 | gc | 3.25 | gate_fail | 视频中镜头连续左右平移，所有关键物体、纹理、颜色和相对位置均保持高度一致，无明显突变或噪点。 |

### Scenes

> **Capped smoke run: 10 agent chunks per rollout (official 30), not comparable to official scores.**

[Watch all 3 rollouts of `smk14-arms-gc-v2-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=smk14-arms-gc-v2-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.55 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=smk14-arms-gc-v2-a1&scene=GC005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-smk14-arms-gc-v2-a1/GC005.mp4) |
| GC033 | gc | 3.95 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=smk14-arms-gc-v2-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-smk14-arms-gc-v2-a1/GC033.mp4) |
| GC036 | gc | 3.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=smk14-arms-gc-v2-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-smk14-arms-gc-v2-a1/GC036.mp4) |
