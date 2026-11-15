## fx14-model-dev-v2-a4

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 24 | missing 13

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.26 | 0.33 | 6 | 4/6 | 2 | 0 | 1.93, 2.70, 2.10, 2.30 |
| if | 1.65 | 0.24 | 6 | 3/6 | 2 | 0 | 1.50, 2.00, 1.59, 1.50 |
| insight | 1.00 | 0.00 | 6 | - | 6 | 0 | 1.00, 1.00, 1.00, 1.00 |
| outsight | 1.50 | 0.20 | 6 | 2/6 | 3 | 0 | 1.75, 1.33, 1.58, 1.33 |
| **overall** | **1.60** | 0.11 | | | | | 1.55, 1.76, 1.57, 1.53 |

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
| GC016 | gc | 3.30 | ok | 视频较好地展现了男子走向佛塔并仰视的过程，颜色和纹理保持稳定，但在视角上移时男子背部凭空出现了一根长自拍杆，存在局部结构突变。 |
| GC031 | gc | 2.70 | ok | 视频在相机360度旋转过程中未能保持场景一致性，发生了硬切导致布局重置，初始的两人融合成一人，且最终画面中白色路标变为绿色，树干和长椅等关键物体消失。 |
| GC033 | gc | 3.70 | ok | 镜头成功向左旋转并转回，初始橱窗内的所有关键物品在重现时保持了良好的身份、外观和位置一致性。 |
| GC036 | gc | 1.00 | missing |  |
| GC038 | gc | 1.85 | ok | 视频中发生了多次硬切，导致房间布局和物体被完全替换，且初始的白色壁炉在镜头移动时严重变形并变色为黑色火炉，完全未能保持世界的一致性。 |
| IF002 | if | 1.00 | missing |  |
| IF010 | if | 2.39 | ok | 视频中主体成功完成了左转和向前行走的轨迹，但机器狗在移动中发生了严重的形变，变成了一个带有真实狗头的立柱并僵硬滑行，导致身份和运动学评分极低。 |
| IF017 | if | 2.00 | ok | 男子未能持续向前行走并走下悬崖，而是在边缘停止并执行了与指令无关的挥剑动作。 |
| IF031 | if | 1.50 | gate_fail | 主体完全静止，未执行提示词要求的动作。 |
| IF034 | if | 1.00 | missing |  |
| IF052 | if | 2.00 | ok | 发生了严重的穿模现象。 |
| OE001 | insight | 1.00 | missing |  |
| OE005 | insight | 1.00 | missing |  |
| OE018 | insight | 1.00 | missing |  |
| OE035 | insight | 1.00 | missing |  |
| OE064 | insight | 1.00 | missing |  |
| OE074 | insight | 1.00 | missing |  |
| OE034 | outsight | 1.00 | missing |  |
| OE039 | outsight | 1.75 | gate_fail | 未执行后退2步的指令。 |
| OE047 | outsight | 1.88 | gate_fail | 视频成功执行了镜头的右转、转回和仰视动作，但男子在镜头移开时走下扶梯，转回时却违背物理规律瞬移回扶梯上，导致轨迹和状态演进严重断裂。 |
| OE048 | outsight | 2.38 | gate_fail | 视频成功展示了镜头向右转动并返回的过程，且视线外咖啡持续注入杯中的物理累积合理，但镜头返回后背景中的盆栽被完全替换并凭空出现了窗户，存在严重的场景一致性失败。 |
| OE058 | outsight | 1.00 | missing |  |
| OE069 | outsight | 1.00 | missing |  |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 11 rollouts of `fx14-model-dev-v2-a4` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.00 | missing | no video |
| GC016 | gc | 3.30 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/GC016.mp4) |
| GC031 | gc | 2.70 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/GC031.mp4) |
| GC033 | gc | 3.70 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/GC033.mp4) |
| GC036 | gc | 1.00 | missing | no video |
| GC038 | gc | 1.85 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/GC038.mp4) |
| IF002 | if | 1.00 | missing | no video |
| IF010 | if | 2.39 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/IF010.mp4) |
| IF017 | if | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=IF017#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/IF017.mp4) |
| IF031 | if | 1.50 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=IF031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/IF031.mp4) |
| IF034 | if | 1.00 | missing | no video |
| IF052 | if | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=IF052#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/IF052.mp4) |
| OE001 | insight | 1.00 | missing | no video |
| OE005 | insight | 1.00 | missing | no video |
| OE018 | insight | 1.00 | missing | no video |
| OE035 | insight | 1.00 | missing | no video |
| OE064 | insight | 1.00 | missing | no video |
| OE074 | insight | 1.00 | missing | no video |
| OE034 | outsight | 1.00 | missing | no video |
| OE039 | outsight | 1.75 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/OE039.mp4) |
| OE047 | outsight | 1.88 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/OE047.mp4) |
| OE048 | outsight | 2.38 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a4&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a4/OE048.mp4) |
| OE058 | outsight | 1.00 | missing | no video |
| OE069 | outsight | 1.00 | missing | no video |
