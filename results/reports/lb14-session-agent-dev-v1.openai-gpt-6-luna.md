## lb14-session-agent-dev-v1

> **screening judge: openai:gpt-6-luna, not comparable to the leaderboard.** Dev screening only; not written to results/experiments.csv.

runner `lingbot_world2` | action source `agent` | passes 2 | tasks 24 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 4.12 | 0.02 | 6 | 6/6 | 0 | 0 | 4.10, 4.13 |
| if | 3.33 | 0.11 | 6 | 6/6 | 0 | 0 | 3.40, 3.25 |
| insight | 2.60 | 0.05 | 6 | - | 0 | 0 | 2.63, 2.57 |
| outsight | 1.31 | 0.03 | 6 | 6/6 | 0 | 0 | 1.29, 1.33 |
| **overall** | **2.84** | 0.03 | | | | | 2.86, 2.82 |

**Reference (paper, full benchmark)**

| model | gc | if | insight | outsight | overall |
|---|---:|---:|---:|---:|---:|
| Genie 3 | 2.74 | 2.40 | 1.51 | 1.81 | 2.12 |
| SANA-WM | 1.72 | 1.89 | 1.13 | 1.16 | 1.48 |
| Matrix-Game-3.0 | 1.30 | 1.25 | 1.00 | 1.00 | 1.14 |

### Tasks

> **screening judge: openai:gpt-6-luna, not comparable to the leaderboard.**

| task | family | mean | status | reason |
|---|---|---:|---|---|
| GC005 | gc | 4.00 | ok | 已出现明显的环绕运动，但没有观察到回到原始相机位置和观看方向。 |
| GC016 | gc | 4.20 | ok | 有效阶段人物、塔与周围树木总体稳定且动作有进展，但首次完成后镜头持续大幅移动，故按规定扣除1分。 |
| GC031 | gc | 3.70 | ok | 已出现明显的原地转向进展，也曾中途经过接近起始方向，但结尾仍在继续转动，未完成并停回原始角度。 |
| GC033 | gc | 4.00 | ok | 镜头连续转向并回看橱窗，列出的展示物总体保持一致；完成相关视角变化后仍长时间进入其他区域，因此最终分数因过度延伸下调。 |
| GC036 | gc | 4.10 | ok | 已出现从左向右再回转的明显进展，但后续持续转动且结尾不在中心，因此目标轨迹未完整收束。 |
| GC038 | gc | 4.70 | ok | 已出现朝壁炉区域移动的相关进展，但没有完成左行返回并转回原始方向的轨迹，也未观察到回访起始视角。 |
| IF002 | if | 3.04 | ok | 人物持续沿通道向柜体方向前进且未见明显穿透，但人物服装和外观多次突变，显著损害整体一致性。 |
| IF010 | if | 3.00 | ok | 主体持续沿通路前进且支撑大致可信，但从机械机器人狗变成普通犬只的外观变化严重损害了整体质量。 |
| IF017 | if | 3.67 | ok | 人物沿岩石路径持续前行且支撑基本可信，场景连续稳定；未见坠落或穿岩，步态与外观漂移使整体质量略有折扣。 |
| IF031 | if | 3.00 | ok | 树旁出现可同时辨认的深色上衣人与蓝色牛仔夹克人，使后续主体连续性不确定。 |
| IF034 | if | 4.25 | ok | 机器人夹爪平稳夹持并抬起同一只金属碗，物体身份和接触关系稳定，整体交互物理连贯。 |
| IF052 | if | 3.00 | ok | 人物持续向前行走且未见明确穿过烤架或三脚架，但步态支撑略显僵硬，后段环境与外套外观出现明显不连贯变化。 |
| OE001 | insight | 3.10 | ok | 街景与行人保持连续且有可见行走进展，但近景女子和婴儿车推进有限，末段图形叠加伪影使整体演化质量为3分。 |
| OE005 | insight | 3.00 | ok | 固定镜头中一名孩子确实走向左侧离开，提供了有限但真实的演化；多数孩子及球、石堆长时间静止，且后段出现散点伪影，因此总体评为 3 分。 |
| OE018 | insight | 2.40 | ok | 茶叶和液体有少量真实演化，但长时间停滞、水流来源不连贯且后段蓝色噪点严重，整体质量偏低。 |
| OE035 | insight | 1.40 | ok | 工人和行人确有动作，但顶层木框全程未见明确移除或堆高减少，因此整体演化仅属极弱的部分进展。 |
| OE064 | insight | 2.70 | ok | 视频有连续烹饪动作和肉色变化，但肉堆未明显摊开翻炒，且中后段操作与器具变化削弱了连贯性。 |
| OE074 | insight | 3.00 | ok | 男子的用餐动作从咬包子转为反复饮用并继续取食，进展清楚但有限，且手持杯子的外观变化削弱了物理连贯性。 |
| OE034 | outsight | 1.00 | score_1.0 | 右转段有明显进展，但未观察到返回起始视角。 |
| OE039 | outsight | 1.00 | score_1.0 | 序列未清楚展示返回后后退两步，且相机随后仍继续旋转。 |
| OE047 | outsight | 2.50 | ok | 相机轨迹部分执行，但返回原视角的完成程度不确定。 |
| OE048 | outsight | 1.00 | score_1.0 | 已执行有意义的转向，但未完成回到原视角的轨迹。 |
| OE058 | outsight | 1.38 | ok | 未回到起始视角。 |
| OE069 | outsight | 1.00 | score_1.0 | 只完成了有意义的部分转向轨迹，最终没有稳定回到起始视角。 |

### Judge calibration: lb14-session-agent-dev-v1

> **Screening, not comparable to the leaderboard.** Each screening judge against the official judge's per-task means on the same videos. bias = screening minus official; self = agreement between the judge's own passes.

| judge | tasks | spearman | MAD | bias | >=1.0 off | passes | self MAD | self rho | self >=0.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| official (reference) | 24 | - | - | - | - | 2 | 0.56 | 0.34 | 10/24 |
| openai-gpt-6-luna | 24 | 0.55 | 1.24 | +1.20 | 15 | 2 | 0.30 | 0.90 | 9/24 |

openai-gpt-6-luna is 1.0 or more off official on: GC005, GC016, GC031, GC033, GC036, GC038, IF002, IF010, IF017, IF031, IF034, IF052, OE001, OE005, OE074

### Scenes

> **Not scored by the official judge; screened by openai:gpt-6-luna (screening scores are not shown here).**

[Watch all 24 rollouts of `lb14-session-agent-dev-v1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=GC005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/GC005.mp4) |
| GC016 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/GC016.mp4) |
| GC031 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/GC031.mp4) |
| GC033 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/GC033.mp4) |
| GC036 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/GC036.mp4) |
| GC038 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/GC038.mp4) |
| IF002 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=IF002#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/IF002.mp4) |
| IF010 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/IF010.mp4) |
| IF017 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=IF017#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/IF017.mp4) |
| IF031 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=IF031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/IF031.mp4) |
| IF034 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/IF034.mp4) |
| IF052 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=IF052#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/IF052.mp4) |
| OE001 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE001#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE001.mp4) |
| OE005 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE005.mp4) |
| OE018 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE018#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE018.mp4) |
| OE035 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE035#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE035.mp4) |
| OE064 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE064#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE064.mp4) |
| OE074 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE074#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE074.mp4) |
| OE034 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE034.mp4) |
| OE039 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE039.mp4) |
| OE047 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE047.mp4) |
| OE048 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE048#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE048.mp4) |
| OE058 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE058.mp4) |
| OE069 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=lb14-session-agent-dev-v1&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-lb14-session-agent-dev-v1/OE069.mp4) |
