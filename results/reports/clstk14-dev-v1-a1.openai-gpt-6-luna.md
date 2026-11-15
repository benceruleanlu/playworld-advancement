**PROXY JUDGE (openai:gpt-6-luna), not comparable to the leaderboard.** A/B between runs scored by this same judge only; uncalibrated against Gemini 3.1 Pro. Written to results/proxy_experiments.csv, never results/experiments.csv.

## clstk14-dev-v1-a1

> **Temperature rejected by the judge model: sampled at the provider default, not upstream's setting.**

runner `lingbot_world2` | action source `agent` | passes 4 | tasks 24 | missing 1 | judge backend `aistudio`

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 4.14 | 0.07 | 6 | 6/6 | 0 | 0 | 4.23, 4.17, 4.07, 4.10 |
| if | 2.70 | 0.07 | 6 | 4/6 | 0 | 0 | 2.70, 2.60, 2.73, 2.76 |
| insight | 2.56 | 0.08 | 6 | - | 0 | 0 | 2.57, 2.53, 2.67, 2.48 |
| outsight | 1.32 | 0.18 | 6 | 5/6 | 1 | 0 | 1.33, 1.42, 1.46, 1.05 |
| **overall** | **2.68** | 0.06 | | | | | 2.71, 2.68, 2.73, 2.60 |

### Tasks

> **PROXY JUDGE (openai:gpt-6-luna), not comparable to the leaderboard.**

| task | family | mean | passes | status | reason |
|---|---|---:|---|---|---|
| GC005 | gc | 4.10 | 4.4/4/4/4 | ok | 未完整返回原始相机位置及观看方向。 |
| GC016 | gc | 4.20 | 4.2/4.4/4.2/4 | ok | 已观察到仰望塔的进展，但没有明显证据表明人物先走到塔基，因此完整轨迹未完成。 |
| GC031 | gc | 3.85 | 3.6/4/3.6/4.2 | ok | 已出现明显的环绕转动并中途经过起始方向，但转动没有在回到原始角度后结束，因此整体轨迹未完整收束。 |
| GC033 | gc | 4.95 | 5/5/5/4.8 | ok | 相机完成了连贯的转向与回望，展示窗陈列在稳定锚点下保持一致，未见可验证的身份、材质、颜色或相对位置缺陷。 |
| GC036 | gc | 4.20 | 4.2/4.2/4.2/4.2 | ok | 相机连续转向并重访喷泉走廊，主要锚定物体及表面保持稳定，未见明确场景重置或外观漂移。 |
| GC038 | gc | 3.55 | 4/3.4/3.4/3.4 | ok | 已出现接近壁炉的移动和折返进展，但最终没有转回原始方向，因此轨迹未完整完成。 |
| IF002 | if | 3.68 | 3.71/3.57/3.57/3.86 | ok | 老人持续沿通道向前行走且未见明显穿透，但步态略僵硬、衣着外观在长序列中明显漂移。 |
| IF010 | if | 3.00 | 3/3/3/3 | ok | 主体持续向前行走且总体接地自然，但机器人狗明显变成生物犬，严重拉低身份一致性与整体物理连贯性。 |
| IF017 | if | 1.00 | 1/1/1/1 | gate_fail | 未观察到提示所要求的向前行走进展。 |
| IF031 | if | 3.25 | 3/3/3.83/3.17 | ok | 男子持续向前接近并经过大树，身份和边界大致稳定，但草地响应及树旁交互证据有限，整体为有明显缺陷的部分互动。 |
| IF034 | if | 4.25 | 4.5/4/4/4.5 | ok | 机器人夹爪连贯地夹住并提起金属碗，物体身份与支撑稳定，整体物理交互质量良好。 |
| IF052 | if | 1.00 | 1/1/1/1 | gate_fail | 未观察到提示要求的向前行走进展。 |
| OE001 | insight | 2.93 | 3.2/3/2.6/2.9 | ok | 视频呈现了连贯的人群运动和镜头推进，但女子与推车的进展有限，末段蓝色物件及界面图形不自然，整体为部分可信的场景演化。 |
| OE005 | insight | 3.00 | 3/3/3/3 | ok | 场景中有少年步行及成人举手机等有限但真实的连续变化，背景与主要物体总体稳定，后段天空散点伪影和多数人物静止使整体质量评为3分。 |
| OE018 | insight | 2.50 | 2.4/2.4/2.8/2.4 | ok | 注水后段确有累积变化，但过程断续、浸泡表现较弱，且中后段蓝色颗粒伪影显著，因此整体质量偏低。 |
| OE035 | insight | 1.25 | 1/1/2/1 | ok | 工人与框堆外观大致稳定，但工人动作反复而顶部木框始终未见明确移除，故OE演化质量与最终分为1分。 |
| OE064 | insight | 2.70 | 2.8/2.8/2.6/2.6 | ok | 画面连续且人物和摊位基本稳定，食材确有变色与形态变化，但未有效持续摊炒，后段搬动大块肉的因果表现较弱。 |
| OE074 | insight | 3.00 | 3/3/3/3 | ok | 男子从咬包子转为长时间饮用并在末段再次取食，动作连续但进食结果不清且重复拖沓，整体进化质量为3。 |
| OE034 | outsight | 1.12 | 1/1.5/1/1 | ok | 右转后没有观察到回到起始相机姿态的轨迹。 |
| OE039 | outsight | 1.00 | 1/1/1/1 | score_1.0 | 相机连续转动并后退，场景锚点保持连贯，但狗重现时几乎维持原姿势，缺乏可验证的累积演化，因此最终评分受限为1分。 |
| OE047 | outsight | 2.77 | 3/3/3.75/1.33 | ok | 未能从可见镜头轨迹确认回到起始姿态。 |
| OE048 | outsight | 1.00 | 1/1/1/1 | missing |  |
| OE058 | outsight | 1.00 | 1/1/1/1 | score_1.0 | 右转有部分进展，但返回原视角未完成。 |
| OE069 | outsight | 1.00 | 1/1/1/1 | score_1.0 | 相机完成了转向侧墙再转回的视角轨迹，但母女与扶梯未显示可验证的向下累积进展，因此OE演化门槛将最终分数限制为1。 |

### Judge calibration: clstk14-dev-v1-a1

> **Screening, not comparable to the leaderboard.** Each screening judge against the official judge's per-task means on the same videos. bias = screening minus official; self = agreement between the judge's own passes.

| judge | tasks | spearman | MAD | bias | >=1.0 off | passes | self MAD | self rho | self >=0.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| official (reference) | 1 | - | - | - | - | 2 | 0.00 | - | 0/1 |
| openai-gpt-6-luna | 1 | - | 0.00 | +0.00 | 0 | 4 | 0.20 | 0.97 | 8/24 |

### Scenes

> **Not scored by the official judge; screened by openai:gpt-6-luna (screening scores are not shown here).**

[Watch all 23 rollouts of `clstk14-dev-v1-a1` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=GC005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/GC005.mp4) |
| GC016 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/GC016.mp4) |
| GC031 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/GC031.mp4) |
| GC033 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=GC033#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/GC033.mp4) |
| GC036 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/GC036.mp4) |
| GC038 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/GC038.mp4) |
| IF002 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=IF002#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/IF002.mp4) |
| IF010 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/IF010.mp4) |
| IF017 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=IF017#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/IF017.mp4) |
| IF031 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=IF031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/IF031.mp4) |
| IF034 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/IF034.mp4) |
| IF052 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=IF052#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/IF052.mp4) |
| OE001 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE001#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE001.mp4) |
| OE005 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE005.mp4) |
| OE018 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE018#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE018.mp4) |
| OE035 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE035#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE035.mp4) |
| OE064 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE064#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE064.mp4) |
| OE074 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE074#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE074.mp4) |
| OE034 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE034.mp4) |
| OE039 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE039#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE039.mp4) |
| OE047 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE047#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE047.mp4) |
| OE048 | outsight | - | missing | no video |
| OE058 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE058#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE058.mp4) |
| OE069 | outsight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a1&scene=OE069#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a1/OE069.mp4) |
