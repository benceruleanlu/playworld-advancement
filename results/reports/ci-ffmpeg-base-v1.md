## ci-ffmpeg-base-v1

runner `tests/fake_runner.py` | action source `dataset` | passes 1 | tasks 2 | missing 0

| family | mean | std | n | gate pass | missing | dropped | per pass |
|---|---:|---:|---:|---:|---:|---:|---|
| gc | 1.00 | - | 2 | 0/2 | 0 | 0 | 1.00 |
| **overall** | **1.00** | - | | | | | 1.00 |

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
| GC005 | gc | 1.00 | gate_fail | 画面静止，未执行任何环绕或移动指令。 |
| GC016 | gc | 1.00 | gate_fail | 视频内容为静态测试图案，完全没有执行所要求的“走向宝塔并抬头”的动作轨迹。 |
