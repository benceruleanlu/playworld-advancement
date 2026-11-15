# Demo video plan

The submission needs a 2-minute demo video. This is the plan for it. Nothing here is a result; every number below is read from the site at recording time.

## What the video has to show

The judging criteria are rigour, novelty, results, autonomy and reproducibility, at 20% each. The honest position today is that no change is adopted and no 171-task score exists, so the video leads with how we know that, not with a score.

1. The question and where we stand (results).
2. The bar and the verdict table (rigour).
3. The same video scored three times (rigour, and the reason for the bar).
4. One hypothesis that failed, with its clips (honest failures).
5. The one lead and its second seed (rigour).
6. Proposals as pull requests, experiments as GitHub Actions runs (autonomy, reproducibility).
7. What is still open.

## Shot list

The short tour on the site is this list. Open `?tour=1&auto=1` and it plays by itself: 7 seconds a step, 12 on steps that play clips, about 75 seconds in all. That leaves 45 seconds for an opening and a close.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Header: question, clip, score | We asked whether an open world model can pass Genie 3 on PlayWorld without retraining. Our best official score is 1.64 on 24 tasks. Genie 3 is at 2.12. So not yet. |
| 0:12 | Verdict table | Here is every change we tested and what happened. A task counts only if it moves a full point, on two seeds, with the AI player. Nothing has cleared that bar. |
| 0:26 | Finding: same video, three scorings | Why a full point. These three controls are the same video. The judge scored one task 1.25, 2.63 and 2.00. |
| 0:36 | The two identical clips playing | Same clip, left and right. Different scores. |
| 0:48 | Finding: sink key scale, then its clips | A hypothesis that failed. We thought the opening frames reset the scene. Turning them down made every arm worse. Dropped. |
| 1:07 | Finding: attention window, two seeds | Our best lead moved tasks on both seeds, but not the same tasks. Not repeated, so not adopted. |
| 1:18 | Still open | No 171-task score and nothing adopted. The stack's gain has only a proxy judge score. |
| 1:26 | Method: steps, counts, run chart | Every proposal is a pull request. Every experiment is a GitHub Actions run that generates on Modal, scores with the official judge and publishes the clips. Each dot is a run, each square a merged pull request. |
| 1:45 | Header again, or the 171-task table if it exists | What comes next, in one sentence. |

The numbers in the "Say" column are today's. Read them off the page when recording.

## How to record

- Browser window about 1280 by 720, light theme. The page is laid out to fit one step per screen at that size.
- `https://benceruleanlu.github.io/playworld-advancement/?tour=1&auto=1` starts the short tour on Auto. `A` toggles Auto, the arrow keys step by hand, `F` puts an open pair of clips full screen, `Esc` exits.
- Add `&full=1` for the 23-step tour. It is too long for the video and is meant for questions afterwards.
- Record the screen once on Auto to get the timing, then record narration over it. A silent draft made this way exists already (74 seconds).

## Before recording

- Merge the open site pull request so the live page has the short tour.
- If the 171-task runs have been scored, the header shows starting model against method on all 171 tasks by itself, and the verdict line changes from "Not yet" to "Yes" or "No". Rewrite the first and last rows of the shot list around that table.
- Update the hand-written parts in `site/src/scripts/app.js` if results changed: `STORY` (finding text and `verdict`), `ADOPTED`, and the "Still open" points.
- Check the clips play from GitHub release URLs in the browser used for recording. Only Chromium has been checked.

## Open decisions

- Who narrates, and whether the video shows a face or only the screen.
- Whether to lead with the identical-clips shot instead of the question. It is the strongest five seconds on the page, but it opens on a measurement problem.
