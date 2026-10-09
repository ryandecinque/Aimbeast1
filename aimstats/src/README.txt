AimStats v1
===========

What it is
----------
AimStats records your Aimbeast tracking runs and shows you, after every session and without you doing
anything:
  - your best run per scenario as a short clip (the 8 seconds with the most hits, rebuilt from your aim)
  - a few clear numbers: time on target, how often you swing past the bot, points by distance
  - whether you're improving week to week
  - a "swing-past" moment from your session, next to a smooth version with your same reaction time
  - a banner and a share card when you set a new personal best or have your best week
  - on request: a target-score video. Pick a run, type a score (say 700), and you get a model run on the
    same bot movement that scores about that, on its own and side by side with yours.

Tracking scenarios only for now. Switching and clicking scenarios are recorded but not analysed yet.
No AI is involved anywhere: it's plain maths on your own recordings.

How to use it
-------------
1. Unzip this folder somewhere you'll keep it (for example Documents\AimStats). Not inside the game folder.
2. Close Aimbeast. Double-click Install.bat. It finds Aimbeast through Steam and tells you what it added.
3. Start Aimbeast and play a tracking scenario.
4. Double-click "Open AimStats.bat". Your stats page opens in your browser. A small window called
   "AimStats - close this window to stop" sits in your taskbar; the page keeps updating while it's open.
   Close that window when you're done.

It's read-only
--------------
The recorder only READS what the game already shows: where you aim, where the bot is, the hit counter, and
whether you're holding fire. It never writes scores, timers, bots or anything ranked, and it doesn't change
how the game plays. There is no aimbot. Ranked runs are recorded the same way, read-only.
Recordings are saved when a run ends, so there's no extra work while you play (about 0.1 ms per frame).
Press F7 in game to turn recording off or on.

Nothing is sent anywhere
------------------------
The stats page runs only on your own PC (http://127.0.0.1). Nothing is uploaded, there are no accounts,
and AimStats never connects to the internet. Your recordings and stats live in the "data" folder here.

What Install.bat puts in the game folder
----------------------------------------
In Aimbeast\Aimbeast\Binaries\Win64:
  - dwmapi.dll and the ue4ss folder: UE4SS, the free, open-source mod loader that lets the recorder run.
    The settings file turns its debug window and crash dumps off.
  - four small mods in ue4ss\Mods: AimRecorder (the recorder), PracticeLog (when you start and finish runs),
    and BPModLoaderMod and Keybinds (standard UE4SS parts), plus mods.txt, the list of mods to load.
If you already have UE4SS, Install.bat leaves it alone and only adds the mods that are missing.
Before it changes any file it makes a backup, and it writes a list of every file it added
(data\install_manifest.json).

Antivirus
---------
Some antivirus programs flag dwmapi.dll, because it's a file that loads mod code into a game. That's how
UE4SS works. It's open source, so anyone can check what it does: https://github.com/UE4SS-RE/RE-UE4SS
If your antivirus removes it, the game still starts, but nothing gets recorded.

If Aimbeast updates
-------------------
An Aimbeast update can stop the recorder working. If that happens the stats page says
"No recordings since ..., the recorder may need an update". If the game ever won't start, run
Uninstall.bat: it always puts the game back as it was.

How to uninstall
----------------
Close Aimbeast and double-click Uninstall.bat. It deletes exactly the files it added, puts back anything it
backed up, and copies your recordings into data\saved_from_game first. Then you can delete this folder.
(Steam's "Verify integrity of game files" won't remove the mod files, so use Uninstall.bat.)

Licences
--------
UE4SS is MIT-licensed (see app\game_files\ue4ss\LICENSE): https://github.com/UE4SS-RE/RE-UE4SS
Also included: Python (python.org, PSF licence), Pillow (MIT-CMU licence) and ffmpeg (GPL, build from
gyan.dev, source at https://ffmpeg.org). Their licence files are in the "licences" folder.
