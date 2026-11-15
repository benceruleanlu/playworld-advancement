## orc14-gc-v1-a2

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 1

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.58 | 0.37 | 6 | 5/6 | 1 | 0 | 2.10, 2.80, 2.47, 2.93 |
| **overall** | **2.58** | 0.37 | | | | | 2.10, 2.80, 2.47, 2.93 |

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
| GC005 | gc | 1.00 | missing |  |
| GC016 | gc | 3.40 | ok | 视频较好地展现了男子走向宝塔并抬头仰望的过程，各物体的一致性和相对位置保持稳定，仅在后半段出现了一次合理的视角切换。 |
| GC031 | gc | 4.00 | ok | 相机未能完成360度旋转，也没有回到初始的十字路口视角。 |
| GC033 | gc | 2.35 | ok | The camera executes the requested turns, but completely fails to maintain world consistency, as all initial window contents disappear upon return and a massive blue camera object hallucinates in the foreground. |
| GC036 | gc | 2.95 | gate_fail | 视频成功执行了平移操作，场景结构和颜色基本稳定，但招牌在重新进入视野时文字内容发生了明显改变。 |
| GC038 | gc | 1.75 | ok | 相机未能执行最后的向右转动以停在初始方向，而是持续向左平移并在最后向前移动，轨迹未完全完成。 |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 5 rollouts of `orc14-gc-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.00 | missing | no video |
| GC016 | gc | 3.40 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a2&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a2/GC016.mp4) |
| GC031 | gc | 4.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a2&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a2/GC031.mp4) |
| GC033 | gc | 2.35 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a2/GC033.mp4) |
| GC036 | gc | 2.95 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a2/GC036.mp4) |
| GC038 | gc | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=orc14-gc-v1-a2&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-orc14-gc-v1-a2/GC038.mp4) |
