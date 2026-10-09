# Install and uninstall the AimStats recorder mods. Called by Install.bat and Uninstall.bat.
#   install:   finds Aimbeast through Steam's library list (app 1100990), then
#              - no UE4SS in the game yet: copies dwmapi.dll, ue4ss/UE4SS.dll, a UE4SS-settings.ini with the debug
#                console and dumps off, and the mods AimRecorder, PracticeLog, BPModLoaderMod and Keybinds + mods.txt
#              - UE4SS already there: never replaces it; only adds the AimStats mods that are missing and lists them
#                in mods.txt (and mods.json if there is one)
#              Anything it would overwrite is backed up first. Every file it adds goes in data/install_manifest.json.
#   uninstall: deletes exactly the files in that list, takes out the mods.txt lines it added (or restores the
#              backup), puts back the backups, and copies your recordings into data/saved_from_game first.
# Usage: python installer.py install [--game <Binaries/Win64 folder>] [--steam <Steam folder>] [--yes]
#        python installer.py uninstall [--yes]
import datetime as dt, hashlib, json, os, shutil, subprocess, sys
import config

GAME_FILES = os.path.join(config.APP, "game_files")
MANIFEST = os.path.join(config.DATA, "install_manifest.json")
BACKUP = os.path.join(config.DATA, "backup")
SAVED = os.path.join(config.DATA, "saved_from_game")
OUR_MODS = ["AimRecorder", "PracticeLog"]                  # the AimStats mods
HELPER_MODS = ["BPModLoaderMod", "Keybinds"]               # stock UE4SS mods, only added when missing
LOADER = ["dwmapi.dll", "ue4ss/UE4SS.dll", "ue4ss/UE4SS-settings.ini", "ue4ss/LICENSE"]
EXE = "Aimbeast-Win64-Shipping.exe"
YES = "--yes" in sys.argv


def say(msg=""): print(msg, flush=True)


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else None


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def game_running(game):
    """Is this copy of the game running? (Matched by the exe's full path; by name if the path can't be read.)"""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              f"(Get-Process '{EXE[:-4]}' -ErrorAction SilentlyContinue).Path"],
                             capture_output=True, text=True, timeout=30, creationflags=config.NO_WINDOW).stdout
        want = os.path.normcase(os.path.normpath(os.path.join(game, EXE)))
        return any(os.path.normcase(os.path.normpath(l.strip())) == want for l in out.splitlines() if l.strip())
    except Exception:
        try:
            out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE}"], capture_output=True, text=True,
                                 creationflags=config.NO_WINDOW).stdout
            return EXE.lower() in out.lower()
        except Exception: return False


def wait_for_game_closed(game):
    while game_running(game):
        if YES: say("Aimbeast is running. Close it and try again."); sys.exit(1)
        input("Aimbeast is running. Close the game, then press Enter here... ")


def resolve_game(folder):
    """A folder the player typed: the game's root, its Aimbeast folder or Binaries/Win64 itself."""
    folder = folder.strip().strip('"')
    for c in (folder, os.path.join(folder, "Binaries", "Win64"), os.path.join(folder, "Aimbeast", "Binaries", "Win64")):
        if os.path.exists(os.path.join(c, EXE)): return os.path.normpath(c)
    return None


def find_game():
    if arg("--game"): return resolve_game(arg("--game"))
    g = config.find_game([arg("--steam")] if arg("--steam") else None)
    if g: return g
    say("I couldn't find Aimbeast through Steam.")
    if YES: return None
    return resolve_game(input("Paste the Aimbeast game folder (for example D:\\SteamLibrary\\steamapps\\common\\Aimbeast) and press Enter: "))


def mod_lines_add(text, names):
    """mods.txt with 'Name : 1' added for each name not listed yet, above the built-in Keybinds line."""
    lines = text.splitlines()
    listed = {l.split(":")[0].strip().lower() for l in lines if ":" in l and not l.strip().startswith(";")}
    add = [f"{n} : 1" for n in names if n.lower() not in listed]
    if not add: return text, []
    at = next((i for i, l in enumerate(lines) if l.strip().lower().startswith("; built-in keybinds")), None)
    if at is None: at = next((i for i, l in enumerate(lines) if l.split(":")[0].strip().lower() == "keybinds"), len(lines))
    lines[at:at] = add
    return "\n".join(lines) + "\n", add


def mods_json_add(text, names):
    data = json.loads(text)
    have = {m.get("mod_name", "").lower() for m in data}
    add = [n for n in names if n.lower() not in have]
    keyb = next((i for i, m in enumerate(data) if m.get("mod_name") == "Keybinds"), len(data))
    for n in add: data.insert(keyb, {"mod_name": n, "mod_enabled": True})
    return json.dumps(data, indent=4) + "\n", add


def install():
    if os.path.exists(MANIFEST):
        say("AimStats is already installed. Run Uninstall.bat first if you want to install it again."); return 1
    game = find_game()
    if not game: say("Aimbeast wasn't found, so nothing was installed."); return 1
    say(f"Found Aimbeast: {game}")
    wait_for_game_closed(game)
    existing = os.path.exists(os.path.join(game, "dwmapi.dll")) or os.path.isdir(os.path.join(game, "ue4ss")) \
        or os.path.exists(os.path.join(game, "UE4SS.dll"))
    mods_dir = os.path.join(game, "ue4ss", "Mods") if (not existing or os.path.isdir(os.path.join(game, "ue4ss"))) else os.path.join(game, "Mods")
    mods_rel = os.path.relpath(mods_dir, game)
    src_mods = os.path.join(GAME_FILES, "ue4ss", "Mods")

    plan = []                                   # (source, path relative to the game folder)
    def add_tree(name, dest_name=None):
        root = os.path.join(src_mods, name)
        for d, _, fs in os.walk(root):
            for f in fs:
                s = os.path.join(d, f)
                plan.append((s, os.path.join(mods_rel, dest_name or name, os.path.relpath(s, root))))
    added_mods, skipped_mods = [], []
    if not existing:
        for f in LOADER: plan.append((os.path.join(GAME_FILES, *f.split("/")), os.path.normpath(f)))
        for m in OUR_MODS + HELPER_MODS + ["shared"]: add_tree(m)
        plan.append((os.path.join(src_mods, "mods.txt"), os.path.join(mods_rel, "mods.txt")))
        added_mods = OUR_MODS + HELPER_MODS
    else:
        for m in OUR_MODS + HELPER_MODS:
            if os.path.isdir(os.path.join(mods_dir, m)): skipped_mods.append(m); continue
            add_tree(m); added_mods.append(m)
        if "BPModLoaderMod" in added_mods and not os.path.exists(os.path.join(mods_dir, "shared", "UEHelpers", "UEHelpers.lua")):
            add_tree("shared")

    man = dict(version=1, installed=dt.datetime.now().isoformat(timespec="seconds"), game=game, mods=mods_dir,
               mode="added mods to an existing UE4SS" if existing else "fresh", created_files=[], created_dirs=[],
               backups=[], edited=[], top_files_before=sorted(os.listdir(game)))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(config.DATA, exist_ok=True)
    try:
        for src, rel in plan:
            dest = os.path.join(game, rel)
            parts = os.path.normpath(os.path.dirname(rel)).split(os.sep)
            for i in range(1, len(parts) + 1):                     # remember every folder this creates
                d = os.path.join(*parts[:i])
                if d and d != "." and not os.path.isdir(os.path.join(game, d)):
                    os.makedirs(os.path.join(game, d)); man["created_dirs"].append(d)
            if os.path.exists(dest):                               # never lose a file: back it up first
                b = os.path.join(BACKUP, stamp, rel); os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copy2(dest, b); man["backups"].append(dict(path=rel, backup=os.path.relpath(b, config.DATA)))
                shutil.copy2(src, dest); man["edited"].append(dict(path=rel, how="replaced", sha256=sha(dest)))
            else:
                shutil.copy2(src, dest); man["created_files"].append(dict(path=rel, sha256=sha(dest)))
        if existing and added_mods:                                # list the new mods in mods.txt / mods.json
            for name, fn in (("mods.txt", mod_lines_add), ("mods.json", mods_json_add)):
                rel = os.path.join(mods_rel, name); p = os.path.join(game, rel)
                existed = os.path.exists(p)
                if not existed:
                    if name == "mods.json": continue
                    open(p, "w", encoding="utf-8").write("")
                    man["created_files"].append(dict(path=rel, sha256=None))
                    text = ""
                else:
                    text = open(p, encoding="utf-8-sig").read()
                    b = os.path.join(BACKUP, stamp, rel); os.makedirs(os.path.dirname(b), exist_ok=True)
                    shutil.copy2(p, b)
                    man["backups"].append(dict(path=rel, backup=os.path.relpath(b, config.DATA)))
                new, added = fn(text, added_mods)
                if added:
                    open(p, "w", encoding="utf-8", newline="\n").write(new)
                    if existed: man["edited"].append(dict(path=rel, how="added lines", added=added, sha256=sha(p)))
                elif existed:
                    man["backups"].pop()                          # nothing changed: no need to restore it later
                    os.remove(b)
                for f in man["created_files"]:
                    if f["path"] == rel and f["sha256"] is None: f["sha256"] = sha(p)
    except Exception as e:
        json.dump(man, open(MANIFEST, "w", encoding="utf-8"), indent=1)
        say(f"Something went wrong while copying ({e}). Undoing what was done so far...")
        uninstall(quiet=True)
        return 1
    json.dump(man, open(MANIFEST, "w", encoding="utf-8"), indent=1)
    cfg = json.load(open(config.CONFIG, encoding="utf-8")) if os.path.exists(config.CONFIG) else {}
    cfg.update(game=game, mods=mods_dir)
    json.dump(cfg, open(config.CONFIG, "w", encoding="utf-8"), indent=1)

    say()
    if existing:
        say("You already had UE4SS (the mod loader). It was left exactly as it was.")
        if added_mods: say("Added these mods: " + ", ".join(added_mods) + ", and listed them in mods.txt.")
        if skipped_mods: say("Already there, so not touched: " + ", ".join(skipped_mods) + ".")
    else:
        say("Installed UE4SS (the mod loader, with its debug window off) and the mods: " + ", ".join(added_mods) + ".")
    if man["created_files"]: say(f"Added {len(man['created_files'])} files. A list of them is in data\\install_manifest.json.")
    else: say("Nothing needed adding: AimStats can already read your recordings.")
    if man["backups"]: say(f"Backed up {len(man['backups'])} file(s) it changed, in data\\backup.")
    say()
    say("Next: start Aimbeast and play a tracking scenario, then double-click 'Open AimStats.bat'.")
    return 0


RUNTIME = ("aimrecorder" + os.sep + "runs" + os.sep, "aimrecorder" + os.sep + "log.txt", "practicelog" + os.sep + "practice_log.csv")


def uninstall(quiet=False):
    if not os.path.exists(MANIFEST):
        say("AimStats isn't installed (there's no install list in the data folder). Nothing to do."); return 1
    man = json.load(open(MANIFEST, encoding="utf-8"))
    game = man["game"]
    if not quiet: say(f"Removing AimStats from {game}"); wait_for_game_closed(game)
    created = {os.path.normcase(f["path"]) for f in man["created_files"]}
    removed, kept = 0, []
    # 1. files it added
    for f in man["created_files"]:
        p = os.path.join(game, f["path"])
        if os.path.exists(p): os.remove(p); removed += 1
    # 2. files it changed: take out only its own mods.txt lines if the file changed since, else restore the backup
    backups = {os.path.normcase(b["path"]): b for b in man["backups"]}
    restored = set()
    for e in man["edited"]:
        p = os.path.join(game, e["path"]); b = backups.get(os.path.normcase(e["path"]))
        if e["how"] == "added lines" and os.path.exists(p) and sha(p) != e["sha256"]:
            if p.lower().endswith(".json"):
                data = [m for m in json.load(open(p, encoding="utf-8-sig")) if m.get("mod_name") not in e["added"]]
                open(p, "w", encoding="utf-8", newline="\n").write(json.dumps(data, indent=4) + "\n")
            else:
                lines = [l for l in open(p, encoding="utf-8-sig").read().splitlines() if l.strip() not in e["added"]]
                open(p, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
            restored.add(os.path.normcase(e["path"]))
    for k, b in backups.items():
        if k in restored: continue
        src = os.path.join(config.DATA, b["backup"])
        if os.path.exists(src): shutil.copy2(src, os.path.join(game, b["path"]))
    # 3. folders it created: save recordings, clear what the mods wrote, keep anything else
    for d in sorted(man["created_dirs"], key=lambda x: -x.count(os.sep)):
        full = os.path.join(game, d)
        if not os.path.isdir(full): continue
        for root, _, files in os.walk(full):
            for f in files:
                p = os.path.join(root, f); rel = os.path.relpath(p, game)
                low = os.path.normcase(rel).lower()
                if any(r in low for r in RUNTIME):
                    dest = os.path.join(SAVED, rel); os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(p, dest); os.remove(p)
                elif low.startswith("ue4ss" + os.sep) and (low.endswith((".log", ".dmp")) or os.path.basename(low) == "imgui.ini"
                                                           or (os.sep + "cache" + os.sep) in low):
                    os.remove(p)                                   # UE4SS's own log, crash dumps and cache
                elif os.path.normcase(rel) not in created:
                    kept.append(rel)
        for root, dirs, _ in os.walk(full, topdown=False):
            for x in dirs:
                try: os.rmdir(os.path.join(root, x))
                except OSError: pass
        try: os.rmdir(full)
        except OSError: pass
    # 4. UE4SS's window settings file next to the game, if it appeared after the install
    if "imgui.ini" not in man.get("top_files_before", []) and man["mode"] == "fresh":
        p = os.path.join(game, "imgui.ini")
        if os.path.exists(p): os.remove(p)
    os.replace(MANIFEST, MANIFEST.replace(".json", f".uninstalled-{dt.datetime.now():%Y%m%d-%H%M%S}.json"))
    if not quiet:
        say(f"Removed {removed} files and put back {len(backups)} backed-up file(s). The game is as it was before AimStats.")
        if os.path.isdir(SAVED): say("Your recordings were copied to data\\saved_from_game. Your stats stay in the data folder until you delete it.")
        if kept: say("These files weren't added by AimStats, so they were left alone: " + ", ".join(kept[:10]))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    code = install() if cmd == "install" else uninstall() if cmd == "uninstall" else (say(__doc__ or "install | uninstall") or 2)
    sys.exit(code)
