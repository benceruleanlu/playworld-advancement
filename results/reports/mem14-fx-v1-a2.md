## mem14-fx-v1-a2

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 9 | missing 1

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.47 | 0.14 | 3 | 3/3 | 0 | 0 | 2.47, 2.40, 2.67, 2.33 |
| outsight | 1.86 | 0.35 | 6 | 5/6 | 1 | 0 | 1.67, 2.29, 2.00, 1.50 |
| **overall** | **2.17** | 0.21 | | | | | 2.07, 2.35, 2.33, 1.92 |

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
| GC031 | gc | 1.10 | ok | 镜头虽然进行了向右的环视，但未能完成360度旋转并回到初始视角。 |
| GC033 | gc | 3.85 | ok | The video successfully executes the requested camera pan and return, maintaining excellent consistency of the objects, textures, and layout in the display window. |
| GC036 | gc | 2.45 | ok | 视频在连续的镜头平移中出现了严重的物体复制和突变，包括凭空出现第二个喷泉以及粉色面板上生成第二个'HATS'招牌，同时原有招牌的文字细节也发生了改变。 |
| OE034 | outsight | 1.50 | ok | 镜头成功完成了向右平移并返回的动作，但转回后三只斑马的条纹图案完全改变，且初始画面中的鸵鸟和地上的生菜不合理地完全消失，存在严重的身份和物体一致性错误。 |
| OE039 | outsight | 3.00 | ok | 视频成功执行了360度环视和后退，狗在重新出现时展现了合理的姿态变化，但在后退阶段狗的品种和胸背带发生了严重的突变。 |
| OE047 | outsight | 1.75 | ok | 镜头按提示完成了旋转，但男子并未在视线外继续乘坐扶梯，而是离开后又返回，并在镜头仰视时荒谬地复制并出现在天花板上，物理逻辑和轨迹连续性严重崩坏。 |
| OE048 | outsight | 1.25 | ok | 镜头成功向右并返回，但返回后原背景中的盆栽被替换为银色电器，且经过长时间隐藏后杯中咖啡量未见合理增加，状态未能正确累积。 |
| OE058 | outsight | 1.00 | missing |  |
| OE069 | outsight | 2.69 | ok | 镜头成功完成了180度旋转并返回，但原本应在视线外向下移动的母亲和女孩在镜头旋转时矛盾地瞬移到了镜头前方，导致了严重的空间逻辑和物理累积错误。 |

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 8 rollouts of `mem14-fx-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC031 | gc | 1.10 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a2&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a2/GC031.mp4) |
| GC033 | gc | 3.85 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a2&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a2/GC033.mp4) |
| GC036 | gc | 2.45 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a2/GC036.mp4) |
| OE034 | outsight | 1.50 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a2&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a2/OE034.mp4) |
| OE039 | outsight | 3.00 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a2&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a2/OE039.mp4) |
| OE047 | outsight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a2&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a2/OE047.mp4) |
| OE048 | outsight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a2&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a2/OE048.mp4) |
| OE058 | outsight | 1.00 | missing | no video |
| OE069 | outsight | 2.69 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=mem14-fx-v1-a2&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-mem14-fx-v1-a2/OE069.mp4) |
