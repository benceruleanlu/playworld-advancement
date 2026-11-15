## fx14-model-dev-v2-a2

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 24 | missing 9

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.35 | 0.60 | 6 | 4/6 | 1 | 0 | 2.33, 3.20, 2.03, 1.83 |
| if | 1.38 | 0.21 | 6 | 3/6 | 1 | 0 | 1.67, 1.17, 1.33, 1.33 |
| insight | 1.00 | 0.00 | 6 | - | 6 | 0 | 1.00, 1.00, 1.00, 1.00 |
| outsight | 1.57 | 0.33 | 6 | 5/6 | 1 | 0 | 1.50, 1.58, 2.00, 1.21 |
| **overall** | **1.57** | 0.17 | | | | | 1.62, 1.74, 1.59, 1.34 |

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
| GC016 | gc | 3.65 | ok | 视频连贯展示男子走向宝塔并仰视，各要素一致性良好。 |
| GC031 | gc | 3.35 | ok | 镜头未能完成360度旋转，且没有回到初始的视角。 |
| GC033 | gc | 2.05 | ok | The video completes the requested camera movements but completely hallucinates a large blue device and resets the contents of the shop window upon return, losing all required key objects. |
| GC036 | gc | 2.05 | gate_fail | 摄像机仅向左平移，未能执行向右平移并返回中心的指令。 |
| GC038 | gc | 2.00 | ok | 视频在镜头平移过程中发生了两次严重的硬重置，初始的木屋场景被石屋和蓝墙房间彻底替换，完全未能保持世界的一致性。 |
| IF002 | if | 1.00 | missing |  |
| IF010 | if | 2.00 | ok | 轨迹基本符合，但场景和主体严重崩坏。 |
| IF017 | if | 1.00 | gate_fail | 男子未能完成走下悬崖并下落的完整物理过程。 |
| IF031 | if | 2.25 | gate_fail | 男子成功向前行走并在接触大树时被合理阻挡停下，物理交互和身份保持良好。 |
| IF034 | if | 1.00 | gate_fail | 视频在机械臂接触碗之前发生了硬重置，未能完成抓取动作。 |
| IF052 | if | 1.00 | gate_fail | 主体完全没有执行要求的行走动作，仅是画面随镜头移动。 |
| OE001 | insight | 1.00 | missing |  |
| OE005 | insight | 1.00 | missing |  |
| OE018 | insight | 1.00 | missing |  |
| OE035 | insight | 1.00 | missing |  |
| OE064 | insight | 1.00 | missing |  |
| OE074 | insight | 1.00 | missing |  |
| OE034 | outsight | 1.00 | missing |  |
| OE039 | outsight | 1.50 | ok | 相机成功执行了360度旋转和后退，但狗在重新出现时呈现完全冻结的复制粘贴状态，缺乏任何合理的动作演变。 |
| OE047 | outsight | 2.06 | ok | 镜头按提示完成了转动，但男子在镜头转回时位置重置到了扶梯底部，未能保持向上的运动进展。 |
| OE048 | outsight | 1.88 | ok | 镜头执行了要求的左右转动，但返回后背景发生了严重的重置（瓷砖墙变为窗户），且杯中咖啡液位在隐藏期间没有任何累积上升，过程状态被不自然地冻结。 |
| OE058 | outsight | 1.25 | gate_fail | 未执行向左转回初始视角的动作。 |
| OE069 | outsight | 1.75 | ok | 视频成功执行了镜头的左右环顾动作，但整个场景（包括本应运行的自动扶梯）处于完全冻结状态，没有任何时间演进，导致演进质量得分为最低。 |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 15 rollouts of `fx14-model-dev-v2-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.00 | missing | no video |
| GC016 | gc | 3.65 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/GC016.mp4) |
| GC031 | gc | 3.35 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/GC031.mp4) |
| GC033 | gc | 2.05 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/GC033.mp4) |
| GC036 | gc | 2.05 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/GC036.mp4) |
| GC038 | gc | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/GC038.mp4) |
| IF002 | if | 1.00 | missing | no video |
| IF010 | if | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/IF010.mp4) |
| IF017 | if | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=IF017#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/IF017.mp4) |
| IF031 | if | 2.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=IF031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/IF031.mp4) |
| IF034 | if | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/IF034.mp4) |
| IF052 | if | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=IF052#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/IF052.mp4) |
| OE001 | insight | 1.00 | missing | no video |
| OE005 | insight | 1.00 | missing | no video |
| OE018 | insight | 1.00 | missing | no video |
| OE035 | insight | 1.00 | missing | no video |
| OE064 | insight | 1.00 | missing | no video |
| OE074 | insight | 1.00 | missing | no video |
| OE034 | outsight | 1.00 | missing | no video |
| OE039 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/OE039.mp4) |
| OE047 | outsight | 2.06 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/OE047.mp4) |
| OE048 | outsight | 1.88 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/OE048.mp4) |
| OE058 | outsight | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/OE058.mp4) |
| OE069 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a2&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a2/OE069.mp4) |
