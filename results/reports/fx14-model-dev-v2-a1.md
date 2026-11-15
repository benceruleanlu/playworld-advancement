## fx14-model-dev-v2-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 24 | missing 8

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.15 | 0.30 | 6 | 4/6 | 1 | 0 | 2.03, 2.57, 1.87, 2.13 |
| if | 1.86 | 0.27 | 6 | 3/6 | 0 | 0 | 2.17, 1.67, 2.00, 1.60 |
| insight | 1.00 | 0.00 | 6 | - | 6 | 0 | 1.00, 1.00, 1.00, 1.00 |
| outsight | 1.71 | 0.61 | 6 | 5/6 | 1 | 0 | 1.67, 1.00, 2.50, 1.67 |
| **overall** | **1.68** | 0.13 | | | | | 1.72, 1.56, 1.84, 1.60 |

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
| GC016 | gc | 3.90 | ok | 视频较好地展现了男子走向宝塔并抬头的过程，背景和主体颜色、纹理相对稳定，但男子手中的相机在走动过程中消失。 |
| GC031 | gc | 3.00 | ok | 相机完成了360度旋转并经过了初始视角，但由于持续向右旋转，未能停在并保持在初始视角，而是继续旋转了第二圈并最终停在其他视角。 |
| GC033 | gc | 2.25 | ok | 镜头在向右回转后没有停止在初始视角，而是继续向右平移，且画面内容完全改变，未能完整实现返回并面对展示窗的目标。 |
| GC036 | gc | 1.25 | gate_fail | 镜头仅持续向左平移，未能执行向右平移以及回到中心的指令。 |
| GC038 | gc | 1.50 | gate_fail | 视频虽然执行了先右后左的转向动作，但未能准确到达壁炉，且后半段场景完全崩坏，未能完成回到初始方向的完整轨迹。 |
| IF002 | if | 3.75 | ok | The video shows a highly coherent and stable walk forward with consistent identity, solid foot contact, and a stable environment. |
| IF010 | if | 2.00 | ok | 视频中机器狗在转向后突变为真狗，且工厂环境发生硬重置变为走廊，物理连贯性严重受损。 |
| IF017 | if | 1.15 | gate_fail | 男子向前行走越过悬崖边缘后，违背物理规律在半空中继续悬空行走而未下落，且手中的武器发生了无端的替换与增生。 |
| IF031 | if | 2.00 | gate_fail | 男子向前行走，接触到树干后被合理阻挡并停下，未发生穿模，整体物理交互连贯自然。 |
| IF034 | if | 1.00 | gate_fail | 场景在接触前发生硬重置，导致交互未能发生。 |
| IF052 | if | 1.25 | gate_fail | 主体未执行提示词要求的行走动作，仅为镜头运动。 |
| OE001 | insight | 1.00 | missing |  |
| OE005 | insight | 1.00 | missing |  |
| OE018 | insight | 1.00 | missing |  |
| OE035 | insight | 1.00 | missing |  |
| OE064 | insight | 1.00 | missing |  |
| OE074 | insight | 1.00 | missing |  |
| OE034 | outsight | 1.00 | missing |  |
| OE039 | outsight | 2.00 | ok | 视频完成了360度旋转和后退的相机运动，狗在重新出现时姿态发生了合理变化，但初始场景布局在旋转后发生了严重的复制和重置错误。 |
| OE047 | outsight | 2.25 | ok | 镜头转回后男子完全消失，随后在扶梯底部重置出现，且画面中凭空生成了巨大的镜头遮挡物，导致严重的连续性和物理逻辑失败。 |
| OE048 | outsight | 1.00 | score_1.0 | 未执行返回原视角的动作。 |
| OE058 | outsight | 1.25 | ok | 镜头未能按照指令要求转回初始视角。 |
| OE069 | outsight | 2.75 | ok | 视频成功展示了镜头旋转180度并返回的过程，期间人物随自动扶梯合理下降，身份保持一致。 |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 16 rollouts of `fx14-model-dev-v2-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | 1.00 | missing | no video |
| GC016 | gc | 3.90 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/GC016.mp4) |
| GC031 | gc | 3.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/GC031.mp4) |
| GC033 | gc | 2.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/GC033.mp4) |
| GC036 | gc | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/GC036.mp4) |
| GC038 | gc | 1.50 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/GC038.mp4) |
| IF002 | if | 3.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=IF002#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/IF002.mp4) |
| IF010 | if | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/IF010.mp4) |
| IF017 | if | 1.15 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=IF017#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/IF017.mp4) |
| IF031 | if | 2.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=IF031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/IF031.mp4) |
| IF034 | if | 1.00 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/IF034.mp4) |
| IF052 | if | 1.25 | gate_fail | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=IF052#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/IF052.mp4) |
| OE001 | insight | 1.00 | missing | no video |
| OE005 | insight | 1.00 | missing | no video |
| OE018 | insight | 1.00 | missing | no video |
| OE035 | insight | 1.00 | missing | no video |
| OE064 | insight | 1.00 | missing | no video |
| OE074 | insight | 1.00 | missing | no video |
| OE034 | outsight | 1.00 | missing | no video |
| OE039 | outsight | 2.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/OE039.mp4) |
| OE047 | outsight | 2.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/OE047.mp4) |
| OE048 | outsight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/OE048.mp4) |
| OE058 | outsight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/OE058.mp4) |
| OE069 | outsight | 2.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=fx14-model-dev-v2-a1&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-fx14-model-dev-v2-a1/OE069.mp4) |
