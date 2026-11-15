**PROXY JUDGE (openai:gpt-6-luna), not comparable to the leaderboard.** A/B between runs scored by this same judge only; uncalibrated against Gemini 3.1 Pro. Written to results/proxy_experiments.csv, never results/experiments.csv.

## clstk14-dev-v1-a2

> **Temperature rejected by the judge model: sampled at the provider default, not upstream's setting.**

runner `lingbot_world2` | action source `agent` | passes 4 | tasks 24 | missing 16 | judge backend `aistudio`

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 2.61 | 0.18 | 6 | 3/6 | 2 | 0 | 2.47, 2.53, 2.87, 2.57 |
| if | 1.93 | 0.13 | 6 | 2/6 | 4 | 0 | 1.95, 2.04, 1.73, 1.98 |
| insight | 1.70 | 0.11 | 6 | - | 4 | 0 | 1.67, 1.87, 1.67, 1.62 |
| outsight | 1.00 | 0.00 | 6 | 0/6 | 6 | 0 | 1.00, 1.00, 1.00, 1.00 |
| **overall** | **1.81** | 0.04 | | | | | 1.77, 1.86, 1.82, 1.79 |

### Tasks

> **PROXY JUDGE (openai:gpt-6-luna), not comparable to the leaderboard.**

| task | family | mean | passes | status | reason |
|---|---|---:|---|---|---|
| GC005 | gc | 1.00 | 1/1/1/1 | missing |  |
| GC016 | gc | 1.50 | 1/1/3/1 | gate_fail | 没有观察到朝目标推进的运动证据，无法确认请求的轨迹已发生。 |
| GC031 | gc | 3.55 | 3.4/3.4/4/3.4 | ok | 镜头持续环绕且场景外观总体稳定；主要不确定性在于末段人物与开场人物的对应及其相对位置。 |
| GC033 | gc | 1.00 | 1/1/1/1 | missing |  |
| GC036 | gc | 3.60 | 3.4/3.8/3.2/4 | ok | 摄像机运动连贯且场景主体大致稳定，但招牌文字表现不稳，并在首次回到走廊宽视图后继续大幅转动。 |
| GC038 | gc | 5.00 | 5/5/5/5 | ok | 相机视点有连贯移动并重见初始家具区域，床、蚊帐、椅、壁炉、地毯及木质表面整体保持稳定，未见经确认的场景一致性缺陷。 |
| IF002 | if | 1.00 | 1/1/1/1 | missing |  |
| IF010 | if | 3.43 | 3.71/3.57/2.57/3.86 | ok | 前进进展清楚，但左转步骤是否完整执行无法从采样视角确定。 |
| IF017 | if | 1.00 | 1/1/1/1 | missing |  |
| IF031 | if | 1.00 | 1/1/1/1 | missing |  |
| IF034 | if | 4.12 | 4/4.67/3.83/4 | ok | 机械夹爪连贯地夹起并稳定托持金属碗，物体外观与柜台结构基本稳定，只有轻微的视角和运动突变。 |
| IF052 | if | 1.00 | 1/1/1/1 | missing |  |
| OE001 | insight | 1.00 | 1/1/1/1 | missing |  |
| OE005 | insight | 3.00 | 3/3/3/3 | ok | 行人持续经过并形成可见轨迹，背景与物体保持稳定，但部分孩子长时间静止，因此整体演化明确但不完整，评分为3分。 |
| OE018 | insight | 1.00 | 1/1/1/1 | missing |  |
| OE035 | insight | 1.00 | 1/1/1/1 | missing |  |
| OE064 | insight | 3.22 | 3/4.2/3/2.7 | ok | 固定视角下厨师持续翻动肉块且场景连贯，但食材累积变化有限、部分动作重复，因此整体属于有进展但不充分的演变。 |
| OE074 | insight | 1.00 | 1/1/1/1 | missing |  |
| OE034 | outsight | 1.00 | 1/1/1/1 | missing |  |
| OE039 | outsight | 1.00 | 1/1/1/1 | missing |  |
| OE047 | outsight | 1.00 | 1/1/1/1 | missing |  |
| OE048 | outsight | 1.00 | 1/1/1/1 | missing |  |
| OE058 | outsight | 1.00 | 1/1/1/1 | missing |  |
| OE069 | outsight | 1.00 | 1/1/1/1 | missing |  |

### Judge calibration: clstk14-dev-v1-a2

> **Screening, not comparable to the leaderboard.** Each screening judge against the official judge's per-task means on the same videos. bias = screening minus official; self = agreement between the judge's own passes.

| judge | tasks | spearman | MAD | bias | >=1.0 off | passes | self MAD | self rho | self >=0.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| official (reference) | 16 | - | - | - | - | 2 | 0.00 | - | 0/16 |
| openai-gpt-6-luna | 16 | - | 0.00 | +0.00 | 0 | 4 | 0.15 | 0.99 | 6/24 |

### Scenes

> **Not scored by the official judge; screened by openai:gpt-6-luna (screening scores are not shown here).**

[Watch all 8 rollouts of `clstk14-dev-v1-a2` on the results site](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a2#scenes). Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.

| task | family | score | status | watch |
|---|---|---:|---|---|
| GC005 | gc | - | missing | no video |
| GC016 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a2&scene=GC016#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a2/GC016.mp4) |
| GC031 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a2&scene=GC031#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a2/GC031.mp4) |
| GC033 | gc | - | missing | no video |
| GC036 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a2&scene=GC036#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a2/GC036.mp4) |
| GC038 | gc | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a2&scene=GC038#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a2/GC038.mp4) |
| IF002 | if | - | missing | no video |
| IF010 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a2&scene=IF010#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a2/IF010.mp4) |
| IF017 | if | - | missing | no video |
| IF031 | if | - | missing | no video |
| IF034 | if | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a2&scene=IF034#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a2/IF034.mp4) |
| IF052 | if | - | missing | no video |
| OE001 | insight | - | missing | no video |
| OE005 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a2&scene=OE005#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a2/OE005.mp4) |
| OE018 | insight | - | missing | no video |
| OE035 | insight | - | missing | no video |
| OE064 | insight | - | not scored | [play](https://benceruleanlu.github.io/playworld-advancement/?scenes=clstk14-dev-v1-a2&scene=OE064#scenes) · [mp4](https://github.com/benceruleanlu/playworld-advancement/releases/download/run-clstk14-dev-v1-a2/OE064.mp4) |
| OE074 | insight | - | missing | no video |
| OE034 | outsight | - | missing | no video |
| OE039 | outsight | - | missing | no video |
| OE047 | outsight | - | missing | no video |
| OE048 | outsight | - | missing | no video |
| OE058 | outsight | - | missing | no video |
| OE069 | outsight | - | missing | no video |
