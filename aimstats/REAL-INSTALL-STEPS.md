# Real install on Ryan's PC: step by step

**What this proves:** on Ryan's live game, where UE4SS and every AimStats mod are already installed:
- Install.bat changes nothing.
- The game still starts and records.
- Uninstall.bat changes nothing.

Every step is checked with a full file list (path, size, SHA-256) of `Aimbeast\Aimbeast\Binaries\Win64`.

Takes about 15 minutes. Run the commands in **PowerShell** (Start menu → type "PowerShell"). They only read the game folder; the only things that ever touch it are Install.bat, Uninstall.bat and the game itself.

## 0. Before you start
- Close Aimbeast.
- Optional: pause the website task so it can't touch the recordings folder during the test. Every 5 minutes it removes the `session_done` marker and compresses week-old recordings, which would show up in the checks below.
  ```
  schtasks /Change /TN "Aimbeast publish" /Disable
  ```
  If you skip this, those two kinds of change can appear in steps 6 and 9; they're harmless.

## 1. Unzip AimStats into a test folder (not the game folder)
```
New-Item -ItemType Directory -Force C:\AimStatsTest | Out-Null
Expand-Archive -Force "C:\Users\Ryan\aimbeast-progress\aimstats\dist\AimStats-v1.zip" C:\AimStatsTest
$T = "C:\Users\Ryan\aimbeast-progress\aimstats\tests"
```
If your main checkout doesn't have the zip (it isn't committed), use the worktree copy instead: `C:\Users\Ryan\aimbeast-progress\.claude\worktrees\busy-hypatia-d9c474\aimstats\dist\AimStats-v1.zip`, and the matching `...\aimstats\tests` folder for `$T`.

## 2. Snapshot 1: before
```
powershell -ExecutionPolicy Bypass -File "$T\snapshot.ps1" -Out C:\AimStatsTest\snap-1-before.csv
```
It takes about half a minute; the 590 MB object dump is part of the list.

## 3. Install
Double-click `C:\AimStatsTest\AimStats\Install.bat`. It should say:
- `Found Aimbeast: C:\Program Files (x86)\Steam\steamapps\common\Aimbeast\Aimbeast\Binaries\Win64`
- `You already had UE4SS (the mod loader). It was left exactly as it was.`
- `Already there, so not touched: AimRecorder, PracticeLog, BPModLoaderMod, Keybinds.`
- `Nothing needed adding: AimStats can already read your recordings.`

**Stop and tell Claude** if it says it added or backed up anything, or asks for the folder.

## 4. Snapshot 2: after install, and compare with 1
```
powershell -ExecutionPolicy Bypass -File "$T\snapshot.ps1" -Out C:\AimStatsTest\snap-2-installed.csv
powershell -ExecutionPolicy Bypass -File "$T\compare.ps1" -Before C:\AimStatsTest\snap-1-before.csv -After C:\AimStatsTest\snap-2-installed.csv
```
Expected: `IDENTICAL: no file was added, removed or changed.`

## 5. Play and check it records
1. Start Aimbeast. It should start normally.
2. Play one normal tracking run to the end, then one ranked tracking run.
3. Check that both runs were recorded:
   ```
   $R = "C:\Program Files (x86)\Steam\steamapps\common\Aimbeast\Aimbeast\Binaries\Win64\ue4ss\Mods\AimRecorder"
   Get-ChildItem "$R\runs" | Sort-Object LastWriteTime | Select-Object -Last 3 Name, Length, LastWriteTime
   Get-Content "$R\log.txt" -Tail 4
   ```
   Expected:
   - two new CSV files with today's time
   - in log.txt: `run ended: <scenario>, ... samples over 6x.x s, cost ... ms per frame` for each run
   - `loaded (phase 7 recorder, read-only, ranked on)` after the game started
   - the cost per frame should be about 0.1 ms
4. Optional: double-click `C:\AimStatsTest\AimStats\Open AimStats.bat`. Within about a minute the page shows both scenarios with numbers. The ranked one has a RANKED tag. Then close the small "AimStats - close this window to stop" window.
5. Close Aimbeast.

## 6. Snapshot 3: after playing, and compare with 2
```
powershell -ExecutionPolicy Bypass -File "$T\snapshot.ps1" -Out C:\AimStatsTest\snap-3-played.csv
powershell -ExecutionPolicy Bypass -File "$T\compare.ps1" -Before C:\AimStatsTest\snap-2-installed.csv -After C:\AimStatsTest\snap-3-played.csv
```
These changes come from playing and are expected:
- `ADDED    ue4ss\Mods\AimRecorder\runs\<today>_<time>_<scenario>.csv` (one per run)
- `CHANGED  ue4ss\Mods\AimRecorder\log.txt`
- `CHANGED  ue4ss\Mods\PracticeLog\practice_log.csv`
- `ADDED` or `REMOVED  ue4ss\Mods\PracticeLog\session_done` (the marker for the website task)
- `CHANGED  ue4ss\UE4SS.log`, `ue4ss\imgui.ini`, `imgui.ini` (UE4SS's own log and console window settings)
- files in `ue4ss\Mods\RoutinePlanBanner\` (your banner saves scores)
- if the website task wasn't paused: week-old `runs\*.csv` replaced by `*.csv.gz`

**Stop and tell Claude** if anything else is listed, above all `dwmapi.dll`, `ue4ss\UE4SS.dll`, `ue4ss\UE4SS-settings.ini`, `mods.txt`, `mods.json` or any `Scripts\*.lua`.

## 7. Uninstall
Double-click `C:\AimStatsTest\AimStats\Uninstall.bat`. It should say:
- `Removed 0 files and put back 0 backed-up file(s). The game is as it was before AimStats.`

## 8. Snapshot 4: after uninstall, and compare with 3 (the file-by-file check)
```
powershell -ExecutionPolicy Bypass -File "$T\snapshot.ps1" -Out C:\AimStatsTest\snap-4-uninstalled.csv
powershell -ExecutionPolicy Bypass -File "$T\compare.ps1" -Before C:\AimStatsTest\snap-3-played.csv -After C:\AimStatsTest\snap-4-uninstalled.csv
```
Expected: `IDENTICAL: no file was added, removed or changed.`

## 9. Overall check: before vs after uninstall
```
powershell -ExecutionPolicy Bypass -File "$T\compare.ps1" -Before C:\AimStatsTest\snap-1-before.csv -After C:\AimStatsTest\snap-4-uninstalled.csv
```
Expected: only the files from playing, the same list as step 6.

## 10. Afterwards
- If you paused the website task, turn it back on:
  ```
  schtasks /Change /TN "Aimbeast publish" /Enable
  ```
- `C:\AimStatsTest` can be deleted. Keep `C:\AimStatsTest\AimStats\data\install_manifest.uninstalled-*.json` if you want a record. AimStats' copies of the recordings are in `data\runs` there; the originals stay in the game folder.
- Send Claude the output of steps 3, 4, 6, 7 and 8, or a screenshot of each.
