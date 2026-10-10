# Zeus teacher video

A 2:24 lesson showing Ryan's three Zeus Track weaknesses. Each one is drawn onto his own runs and set next to a smooth version of the same moment.

## Files
- **Outputs**
  - `zeus_teacher_1080p.mp4` is the full video.
  - `zeus_teacher_chat.mp4` is the copy under 30 MB.
- **Planning**
  - `QnA - Zeus teacher video.md`: the 50 questions, the evidence and the decision.
  - `SCRIPT.md`: every on-screen note with its time. These become the voice lines if a narrated version is wanted.
- **Evidence scripts** (read-only on the game folder)
  - `zeus_data.py`: loads a Zeus recording, resamples it to 60 a second and splits it into rounds.
  - `evidence.py`: per-second scoring through a round. Writes `evidence.json`.
  - `kinds.py`: what kind of miss each off-target moment is. Writes `kinds.json`.
  - `checks.py`: links with score, offset at hits, reaction. Writes `per_run.json`.
- **Video**
  - `moments.py` picks one typical moment per weakness from tonight's runs and builds the smooth version. Writes `motion/src/data.json` and `moments_chosen.json`.
  - `motion/` is the Remotion project. Its `node_modules` is a junction to `Videos\Positioning Rebuild\motion\node_modules`.

## Rebuild
```
python moments.py
cd motion
npx remotion render Zeus out/zeus_teacher_1080p.mp4 --concurrency=6 --crf=18
```
To render storyboard stills: `node stills.mjs <seconds...>`, then `python tools/sheet.py main`.

## Notes
- **Bot size**: a capsule of half-width 31.5 and half-height 49.5. The game uses the bot file's Min fields: radius 0.75 × 42 = 31.5, which matches his hits. The 1.57 height-to-width ratio comes from the stream footage (56 × 88 px). See the revision in the QnA.
- **The smooth version** follows `weak_moment_auto.py`: the same 133 ms reaction, it eases in and aims where the bot will be. It's a model, and the video says so.
