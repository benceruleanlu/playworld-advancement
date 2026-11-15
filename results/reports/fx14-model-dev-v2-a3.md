## fx14-model-dev-v2-a3

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 24 | missing 10

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.21 | 0.28 | 6 | 5/6 | 1 | 0 | 2.33, 2.53, 2.07, 1.90 |
| if | 1.22 | 0.23 | 6 | 2/6 | 1 | 0 | 1.50, 1.07, 1.00, 1.33 |
| insight | 1.00 | 0.00 | 6 | - | 6 | 0 | 1.00, 1.00, 1.00, 1.00 |
| outsight | 1.81 | 0.36 | 6 | 4/6 | 2 | 0 | 1.75, 2.08, 2.08, 1.33 |
| **overall** | **1.56** | 0.13 | | | | | 1.65, 1.67, 1.54, 1.39 |

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
| GC016 | gc | 3.50 | ok | 视频整体非特定任务质量较好，材质、颜色和空间位置保持稳定，但男子背包上凭空生成了一根自拍杆，导致身份一致性受损。 |
| GC031 | gc | 1.35 | ok | 视频完成了360度环视，但当镜头回到初始的岔路口时，原本的大树干、人物和长椅均未一致重现，场景布局和物体身份发生了严重的重置失败。 |
| GC033 | gc | 3.40 | ok | 视频成功执行了向左旋转并返回的相机运动，初始橱窗内的所有关键物体在重新进入视野后均保持了高度的身份、材质、颜色和相对位置一致性。 |
| GC036 | gc | 2.25 | ok | 视频在镜头平移过程中出现了严重的物体复制和属性变异，原本唯一的黄色HATS招牌变成了整排颜色各异的招牌，场景布局完全崩溃。 |
| GC038 | gc | 1.75 | gate_fail | 视频在镜头移动过程中发生了严重的场景重置和物体替换，初始的壁炉、椅子和地毯均未能保持一致。 |
| IF002 | if | 1.00 | missing |  |
| IF010 | if | 1.75 | gate_fail | 视频成功展示了主体向左转并向前行走的轨迹，但机器狗在移动过程中严重变形为真实的狗，导致身份和运动学评分较低。 |
| IF017 | if | 1.10 | gate_fail | 男子仅执行了与提示无关的转身和挥剑动作，完全没有向前走动。 |
| IF031 | if | 1.00 | gate_fail | 人物完全没有移动。 |
| IF034 | if | 1.00 | gate_fail | 场景硬重置导致动作中断。 |
| IF052 | if | 1.50 | gate_fail | 男孩向前走，但直接穿过了实体的篝火和金属烤架，发生了严重的穿模失败。 |
| OE001 | insight | 1.00 | missing |  |
| OE005 | insight | 1.00 | missing |  |
| OE018 | insight | 1.00 | missing |  |
| OE035 | insight | 1.00 | missing |  |
| OE064 | insight | 1.00 | missing |  |
| OE074 | insight | 1.00 | missing |  |
| OE034 | outsight | 1.00 | missing |  |
| OE039 | outsight | 2.00 | gate_fail | 镜头完成了360度旋转，但返回初始视角时，狗的品种和背景墙颜色发生了严重的替换，未能保持身份和场景的一致性。 |
| OE047 | outsight | 2.00 | ok | 视频虽然完成了镜头的转动，但主体男子在镜头移开时发生了不合理的空间平移，脱离了扶梯，导致隐藏状态演进和轨迹连续性完全失败。 |
| OE048 | outsight | 3.12 | ok | 视频成功展示了镜头移开期间咖啡继续倒入杯中的累积过程，但镜头转回后背景发生了严重改变（出现了原本没有的窗户和新植物）。 |
| OE058 | outsight | 1.00 | missing |  |
| OE069 | outsight | 1.75 | ok | 镜头返回后人物未随扶梯向下移动且背包发生突变，缺乏有效演进。 |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 14 rollouts of `fx14-model-dev-v2-a3` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.00 | missing | no video |
| GC016 | gc | 3.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/GC016.mp4) |
| GC031 | gc | 1.35 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/GC031.mp4) |
| GC033 | gc | 3.40 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/GC033.mp4) |
| GC036 | gc | 2.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/GC036.mp4) |
| GC038 | gc | 1.75 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/GC038.mp4) |
| IF002 | if | 1.00 | missing | no video |
| IF010 | if | 1.75 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/IF010.mp4) |
| IF017 | if | 1.10 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=IF017#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/IF017.mp4) |
| IF031 | if | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=IF031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/IF031.mp4) |
| IF034 | if | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/IF034.mp4) |
| IF052 | if | 1.50 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=IF052#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/IF052.mp4) |
| OE001 | insight | 1.00 | missing | no video |
| OE005 | insight | 1.00 | missing | no video |
| OE018 | insight | 1.00 | missing | no video |
| OE035 | insight | 1.00 | missing | no video |
| OE064 | insight | 1.00 | missing | no video |
| OE074 | insight | 1.00 | missing | no video |
| OE034 | outsight | 1.00 | missing | no video |
| OE039 | outsight | 2.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/OE039.mp4) |
| OE047 | outsight | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/OE047.mp4) |
| OE048 | outsight | 3.12 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/OE048.mp4) |
| OE058 | outsight | 1.00 | missing | no video |
| OE069 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a3&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a3/OE069.mp4) |
