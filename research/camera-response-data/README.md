# Data behind research/camera-response.md

One JSON object per line, one line per scripted trial on the 14B (see the note for the setup).

- `open-loop.jsonl`: gain 1, no feedback. The GC033 mechanism scripts and the two mirrored 90-degree scripts on 11 scenes.
- `servo.jsonl`: the same scripts through `yaw_servo.step` (`--lingbot-yaw-servo`), plus the longer task-shaped scripts in both arms.
- `fixed-gain-and-mirror.jsonl`: the fixed pair left 0.8 / right 1.0 on the GC scenes, and the mirrored-start-image control.
- `judged-clips.json`: for 86 officially scored clips already on main, the official mean and whether the start view is back at the end.

Fields of a trial: `task`, `name` (script), `script`, `tag` (arm), `segments` (per leg: `commanded`, `rendered`, `gain`, `peak`, `trusted`), `tokens` (rendered yaw per 20-frame token), `commanded_net`, `rendered_net`, `closure` (end of the last turn against frame 0: `yaw`, `ncc`, `match`), `best_return`, `rigid` (share of frame pairs whose motion is one rigid shift), `servo` (estimates, heading against intended, one line per chunk), `seconds`.

`python -m adapters.lingbot_world2.camera_probe research/camera-response-data/*.jsonl` prints the gain table and the end-error table.

The clips themselves are not in the repo. They are derivatives of LingBot-World v2 (CC BY-NC-SA 4.0) generated from PlayWorld start images.
