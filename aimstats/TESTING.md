# AimStats v1: how it was built and tested (2026-10-09)

## Build
```
python build_zip.py --python python-3.11.9-embed-amd64.zip --ffmpeg imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl --ue4ss "<game>/Binaries/Win64"
```
- Output: `dist/AimStats-v1.zip`, 58 MB (UE4SS.dll is 20 MB of that).
- Python 3.11.9 embeddable from python.org. Pillow 12.3.0 copied from the local Python 3.11.
- ffmpeg 7.1 "essentials" (gyan.dev) taken from the imageio-ffmpeg 0.6.0 wheel on PyPI (sha256 matched PyPI).
  - It isn't a custom H.264-only build. A trimmed build would mean compiling ffmpeg; this ready-made one is 31 MB zipped.
- The UE4SS 3.0.1 files (dwmapi.dll, UE4SS.dll, LICENSE) are copied, read-only, from the working install.
- The build checks that the bundled Python imports everything with nothing from this PC on its path.

## Install and uninstall (copies only, never the live game folder)
`python -I tests/install_test.py <temp folder> dist/AimStats-v1.zip` copies Binaries/Win64 into a temp folder and compares every file (size and sha256) before install and after uninstall.

| Case | Result |
|---|---|
| A. Clean game, found through a fake Steam `libraryfolders.vdf` with two libraries | PASS: 11 files added, settings have the console and dumps off, all 58 files identical after uninstall, recording saved to `data/saved_from_game` |
| B. UE4SS already there (Ryan's setup without AimRecorder/PracticeLog) | PASS: only the 2 mods added, UE4SS untouched, mods.txt/mods.json backed up, all 115 files identical after uninstall |
| C. Same, and the player adds a mod line after installing | PASS: their line kept, only AimStats' lines removed |
| D. Every AimStats mod already there | PASS: install changes nothing |
| E. Second install without uninstalling | PASS: refused |

## The stats page, from Ryan's real recordings
- The packaged app was run with only Windows on PATH, pointed read-only at the live `AimRecorder/runs`.
- It produced 8 tracking scenarios, each with a best-run clip, numbers, a week-to-week line and a swing-past GIF.
- 7 switching or clicking scenarios were listed as "not analysed yet".
- The target-score video was made from the page.
  - Example: Air Control Sphere S, a run of 746 with a target of 900. The model reached 833, and the page says that was the closest it got.

## Added: rest times and aim numbers over time
- **Rest times** come from PracticeLog's practice_log.csv (`src/app/scripts/rests.py`). The rules are the same as `publish.py` sessions_by_day().
- Checked against `publish.py` on Ryan's log: runs, restarts, breaks, typical rest and longest rest are identical for 6 to 9 Oct. For example, 9 Oct: 34 runs, 29 restarts, typical rest 55 s.
- **The page shows:**
  - a "Practice and rests" box with the last 7 days
  - a rest-before column in each scenario's run table, matched to the recording's start within 2 s
  - the short-against-longer rest line, once there are 10+ runs in each group
- On Ryan's data the line reads: after rests under 20 s, scores are typically 3.2% lower than after rests of 20 s to 2 min (55 and 63 runs, first tries left out).
- Without practice_log.csv, the box and the rest column don't appear (checked).
- **Aim numbers over time:** per tracking scenario, small trend lines for on target, swing-past and points per second, one point per practice day (the typical run). Below 2 days the page says when they'll appear.
- Install tests re-run on the new zip: 5/5 PASS.

## Added: score fixes, ranked best, opt-in videos and the +20% side by side
- **Points per hit.** Each scenario's game scores are lined up with the recordings at a steady ratio.
  - Pennytracking now shows 545 and 630 (5 points a hit); Controlsphere OW shows 9 a hit.
  - If nothing lines up, the card says "hits". Zeus Track Evo (non-EZ) does this on Ryan's data.
- **Ranked best** comes from the game's own ranked record in `Trainer/rankedinfo.scns`.
  - Sphere S: 878. Smooth Thin: 555. Air Track: 548. These match RoutinePlanBanner's numbers.
  - That record can be out of date (Ryan's was last written in March), so the page shows the higher of it and the statistics file.
  - Without a record, it says "best X since <first date>".
- **Videos are opt-in.**
  - A Videos panel lists today's tracking scenarios with tick boxes and an Always option. The ticks and Always choices are saved in `data/settings.json`, and nothing is set to Always at first.
  - Each card has a "Make clip" button.
  - Tested: Make videos for 2 ticked scenarios, Make clip on another, Always on and off.
  - Clean-up per scenario keeps only the latest day's clip and the best run's clip. Unit-tested with 4 days: 2 kept, files deleted only in data/clips.
- **`model_clip.py <run csv> <real score> <first sample> <last sample> <out.mp4> [factor]`** makes the side-by-side clip, real run on the left, model on the right, tuned so the whole run scores factor × real (default 1.2).
  - The model lives in `model_run.py`, shared with `target_video.py`.
  - Pennytracking 630 to 757, Slow Accel 300 to 359, Smooth Thin 452 to 538 (target 542). About 4 s per clip.
- Target-score video re-checked after the change: Pennytracking 630 with a target of 700, the model reached 710.

## Added: "over-aim" wording and recorder phase 6
- **"Over-aim" wording.** "Swing-past", "swinging past the bot" and "overshoot" now read "over-aim" everywhere players see them: the page, the README, the checklist and the text in the GIFs ("No over-aiming.", "over-aim: past the bot"). Internal names are unchanged.
- **Recorder phase 6**, copied from Ryan's live file (the live file wasn't touched), still read-only (checked: no writes).
  - Body parts are read only for bots that moved more than 50 units this run.
  - Runs with 6 or more separate clicks are sampled 120 times a second.
- **`thin60()`** in aim_analysis thins such files back to 60 a second; the render scripts use it too.
  - On normal files it returns them untouched. The results are identical with and without it on Sphere S and Smooth Thin runs.
  - A test file at 120 a second (7345 rows) came back as 3669 rows; the original has 3673.

## Added: model videos only where the bot ignores hits
- **The check** is `model_check()` in `model_run.py`, used by `model_clip.py`, `target_video.py` and the server.
  - A model video is allowed only for a tracking run whose .bot file shows a bot that can't be destroyed, doesn't blink or leap on hit, doesn't change size on damage or health, and has no event triggered by a hit, damage or destroy.
  - Otherwise, the page shows "Not available for this scenario yet: the bot reacts to your hits, so a better run would change what the bot does." instead of the button and the clip.
  - Switching and clicking runs get none.
- **Ryan's 6 ranked tracking scenarios:**
  - PASS: Smooth Thin Track V2
  - PASS: Air Track Smooth V3 150%
  - PASS: Air Control Sphere - S
  - PASS: Zeus Track Evo - Noblink. Its bot has a lifetime, but it can't be destroyed, so its resets are time-based.
  - FAIL: PASU Track Evo (RCT) - 0.85X. Event 2 is "ON HIT: speed up/down", so each hit changes the bot's speed.
  - FAIL: PASU Track XYZ. The bot can be destroyed and comes back after a kill; Ryan's stats show 2 kills a run.
- **Every scenario Ryan has recorded passes.**
- **Tested:**
  - `model_clip.py` on a run named as PASU XYZ: refused (exit 3).
  - `target_video.py` on a clicking run: refused.
  - A normal run: still made.
  - The page with one card blocked: no form, no model clip, the plain line shown; the other cards unchanged.

## Added: red "No 20% better video" notice
- **Cards that can't get model videos** show a red notice where the +20% clip would be.
  - It has a red left border, a crossed-circle icon and the label "No 20% better video", so it doesn't rely on colour alone.
  - Under that, the plain reason from whichever bot-file check failed (`model_notice()` in model_run.py):
    - PASU RCT: "This bot reacts to your hits (it speeds up or slows down when hit), ..."
    - PASU XYZ: "This bot can die, so a better run would need bots that weren't in your recording." plus "A 'same bots, killed sooner' version is coming."
  - Cards without a clip show the notice in the target-score box instead.
- **Contrast:** the red is #ff7a7a on #2a1a1a, 6.5:1. The page is dark-only, so the light-theme value (#b91c1c on #fdf2f2, 5.9:1) is noted in the CSS for when a light theme exists.
- Checked in the browser with one card of each kind.

## Checked: no fixed-camera assumptions
- Every angle, on-target test, distance band, swing/over-aim check and 3D frame uses that snapshot's own cam_x/y/z.
- The drawn floor grid sits 350 units below the lowest camera height of the whole run and stays fixed in the world, so a player who drops after spawning (POPCORN - M: 425 to 362) is fine.
- Model videos keep the real camera path and change only the aim.
- When the player moves during the run (more than 100 units sideways, or a Dodge or Possession scenario), the model clip and the target-score video add "same movement as your run". Checked: a run under a Dodge name says moves = true; Zeus and Smooth Thin say moves = false.

## Added: switching and clicking cards, and "Same bots, 20% faster"
- **Files:** model_v2's `lives.py`, `scen_rules.py` and `fast_clip.py` are copied into the app's scripts.
  - They use AimStats' config: FOV from Config.cfg, the Workshop folder, AimStats' data folder, the bundled ffmpeg, and no console windows.
  - `kill_stats.py` gives each run's kills (checked against the game's kill counter), time per kill and missed shots.
  - `real_clip.py` makes the best 8 seconds with every bot drawn.
- **Which card a scenario gets:** it's a switching/clicking scenario when at least half its runs are. This stops TAMTARGETSWITCH from splitting across two cards: two of its runs were recorded before phase 7 and read as tracking.
- **"Same bots, 20% faster"** is offered only where `scen_rules` allows it.
  - The label shows the factor fast_clip actually reached.
  - fast_clip's hard checks are untouched. If it stops, the card says the run failed its safety checks.
  - Other refusals (kills not matching the game, too few kills, bots not only coming after kills, an old recording) each get a plain line.
- **Tested on Ryan's real runs from today**, with the packaged app on a scratch copy of the data:
  - POPCORN - M 11:21: card with 33 kills (matches the game) and 1.8 s per kill. Same bots, 22% faster: 48.3 s against 58.7 s.
  - PASU XYZ 11:38: 16 kills (matches the game). Same bots, 19% faster: 46.1 s against 55.0 s.
  - VOX TS BALANCED - 150% (8 Oct): 69 kills. Same bots, 19% faster: 49.8 s against 59.3 s.
  - TAMTARGETSWITCH 11:18: 30 kills, matching the game. Its card shows the clip and the red notice, because the scenario is scored on time on target and the bot heals.
  - The two runs from before phase 7 are marked "game: different".
  - PASU TRACK XYZ stays a tracking card with its red notice; the "coming" line is gone.
  - The "failed its safety checks" notice was checked in the browser.
- `aimstats/FOR-YOUR-FRIEND.txt`: the message for a friend, 227 words.

## Fixed: flying bots in older recordings (before phase 5)
- `model_run.py` already took a flying bot's visible height from the aim at each hit, joined up in between and lightly smoothed, whenever the root height was clearly wrong.
  - On the Air Track 526 and Sphere S 853 runs from 9 Oct this was active, and the drawn ball sat on the crosshair at hits.
- **Change:** the model's aim now also follows that estimated height. Before, it copied the player's pitch. Model clips and target-score videos now say "Bot height estimated from hits".
- **Re-made with best_run_gif's 8-second windows:**
  - **Air Track (window 2379–2859):** at its 85 hits the ball centre is a median 0.11° from the crosshair. The model's dot is 0.63° from the centre while on target, against a ball radius of about 2.8°. +20% reached: 634 against a target of 631.
  - **Sphere S (2776–3256):** 0.02° at its 154 hits. The model's dot is 0.19° from the centre, against a radius of about 0.8°. +20% wasn't reachable (943 against 1024), and the clip says so.

## Not tested yet (needs Ryan or a friend)
- The game starting and recording with the installed files. That needs a real install, and the decision says nothing installs until Ryan says go.
- A clean Windows account.
- A friend's PC: see `src/TEST-CHECKLIST.txt`.

## Real install on Ryan's PC (2026-10-09, passed)
Live game folder (953 files), with UE4SS and all AimStats mods already present. Website task paused during the test and turned back on afterwards.
- **Install:** found the game and left UE4SS and the 4 mods untouched ("Nothing needed adding"). Snapshot after install: IDENTICAL to before.
- **Play:**
  - The game started and loaded recorder phase 7 (12:14).
  - Normal Zeus EZ run recorded, at 0.06 ms per frame.
  - Ranked recording was already confirmed with the same files (PASU TRACK XYZ - RANKED, 11:34).
  - The only changes were the expected ones from playing: the new run, log.txt, practice_log.csv, session_done, rank_data.txt and UE4SS.log.
- **Uninstall:** "Removed 0 files". Snapshot after uninstall: IDENTICAL to after playing. Start vs end: only the play files above.

Still to do: a clean Windows account (no mods, no Python) and one friend's PC.
