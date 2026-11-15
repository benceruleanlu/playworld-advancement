## smk14-arms-gc-v2-a2

> **Capped smoke run: 10 agent chunks per rollout (official 30), not comparable to official scores.** Smoke tier only; never the site headline.

runner `lingbot_world2` | action source `agent` | passes 4 | tasks 3 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.35 | 0.41 | 3 | 2/3 | 0 | 0 | 2.20, 2.27, 2.93, 2.00 |
| **overall** | **2.35** | 0.41 | | | | | 2.20, 2.27, 2.93, 2.00 |

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
| GC005 | gc | 3.00 | ok | 视频在复杂的相机环绕和返回初始视角的过程中，成功保持了雕像及其周围环境的身份、外观和空间布局的一致性。 |
| GC033 | gc | 2.30 | ok | 镜头返回初始锚定区域时，橱窗内的主要物体消失，标志文字变为乱码，空间布局完全重置，表现出严重的对象持久性失败。 |
| GC036 | gc | 1.75 | gate_fail | 视频仅展示了持续向右平移，完全未执行基础动作序列中要求的先向左平移以及最后的向左平移，轨迹与指令严重不符。 |

### Scenes

> **Capped smoke run: 10 agent chunks per rollout (official 30), not comparable to official scores.**

[Watch all 3 rollouts of `smk14-arms-gc-v2-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=smk14-arms-gc-v2-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 3.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=smk14-arms-gc-v2-a2&scene=GC005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-smk14-arms-gc-v2-a2/GC005.mp4) |
| GC033 | gc | 2.30 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=smk14-arms-gc-v2-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-smk14-arms-gc-v2-a2/GC033.mp4) |
| GC036 | gc | 1.75 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=smk14-arms-gc-v2-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-smk14-arms-gc-v2-a2/GC036.mp4) |
