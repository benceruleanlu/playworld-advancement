## ins14-fx-v2-a1

runner `lingbot_world2` | action source `dataset` | passes 4 | tasks 6 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| insight | 1.76 | 0.21 | 6 | - | 0 | 0 | 1.73, 1.50, 1.80, 2.00 |
| **overall** | **1.76** | 0.21 | | | | | 1.73, 1.50, 1.80, 2.00 |

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
| OE001 | insight | 2.25 | 3/1/2/3 | ok | In the video, the stroller and the man on the left disappear in the very first frame. The woman and child stand stiffly throughout, and a blue object appears out of thin air in hand later on, showing poor progression and physical plausibility.<details><summary>judge's original</summary>视频中婴儿车和左侧男子在首帧即消失，女子和儿童全程僵立，且后期手中凭空生成蓝色物体，演变和物理合理性差。</details> |
| OE005 | insight | 1.25 | 1/1/1/2 | ok | The first 20 seconds of the video are completely static, followed by a severe hard reset where the children instantly vanish and are replaced by a man holding a phone, completely lacking plausible scene progression.<details><summary>judge's original</summary>视频前20秒完全静止，随后发生严重的硬重置，孩子们瞬间消失并被一个拿手机的男子替换，完全缺乏合理的场景演进。</details> |
| OE018 | insight | 2.20 | 2/2/2.8/2 | ok | The video initially shows water being poured, but quickly degrades into physically implausible hallucinations, including a disappearing wooden lid, floating blue particles, white liquid with no source, and green particles appearing suddenly.<details><summary>judge's original</summary>视频初期展示了倒水的过程，但随后迅速退化为物理上不合理的幻觉，包括木盖消失、漂浮的蓝色颗粒、无源的白色液体以及突然出现的绿色颗粒。</details> |
| OE035 | insight | 1.00 | 1/1/1/1 | score_1.0 | The video is completely static. The worker does not perform any action to lift the wooden frame, and severe color drift occurs in the second half, lacking meaningful temporal evolution.<details><summary>judge's original</summary>视频完全静止，工人没有执行任何抬起木框的动作，且后半段出现了严重的颜色漂移，缺乏有意义的时间演变。</details> |
| OE064 | insight | 1.75 | 1/2/2/2 | ok | The video fails to show the chef stir-frying meat with a spatula. The spatula disappears, the meat slices morph into a red solid block in a physically implausible way, and a green stick appears out of thin air.<details><summary>judge's original</summary>视频未能展示厨师使用锅铲炒肉的过程，锅铲消失，肉片不符合物理规律地变形为红色固体块，且凭空出现了绿色棍子。</details> |
| OE074 | insight | 2.10 | 2.4/2/2/2 | ok | The video fails to show a plausible eating process. The steamed bun in hand turns into a cup, and the scene lighting and food on the table undergo drastic, physically implausible changes.<details><summary>judge's original</summary>视频未能展示合理的进餐过程，手中的包子变成了杯子，且场景光线和桌上食物发生了不符合物理规律的剧烈变化。</details> |

> Reasons are machine-translated into English for display after scoring; the judge's original text (under each) is authoritative.

### Scenes

> **Replayed dataset moves (open loop), A/B only.**

[Watch all 6 rollouts of `ins14-fx-v2-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| OE001 | insight | 2.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a1&scene=OE001#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a1/OE001.mp4) |
| OE005 | insight | 1.25 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a1&scene=OE005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a1/OE005.mp4) |
| OE018 | insight | 2.20 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a1&scene=OE018#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a1/OE018.mp4) |
| OE035 | insight | 1.00 | score_1.0 | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a1&scene=OE035#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a1/OE035.mp4) |
| OE064 | insight | 1.75 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a1&scene=OE064#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a1/OE064.mp4) |
| OE074 | insight | 2.10 | ok | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=ins14-fx-v2-a1&scene=OE074#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-ins14-fx-v2-a1/OE074.mp4) |
