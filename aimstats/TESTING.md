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

## Not tested yet (needs Ryan or a friend)
- The game starting and recording with the installed files. That needs a real install, and the decision says nothing installs until Ryan says go.
- A clean Windows account.
- A friend's PC: see `src/TEST-CHECKLIST.txt`.
