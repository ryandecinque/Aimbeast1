# Where everything lives. The game folder comes from data/config.json (written by Install.bat), or from Steam's
# library list if that file is missing. AIMSTATS_GAME (the game's Binaries/Win64 folder) overrides both, for testing.
# AimStats only READS from the game folder: recordings are copied out to data/runs, statistics are read in place.
import gzip, json, os, re, subprocess, sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(SCRIPTS)
ROOT = os.path.dirname(APP)
DATA = os.environ.get("AIMSTATS_DATA") or os.path.join(ROOT, "data")
RUNS = os.path.join(DATA, "runs")            # AimStats' own copies of the recordings
CONFIG = os.path.join(DATA, "config.json")
APP_ID = "1100990"
NO_WINDOW = 0x08000000                        # child processes never flash a console window


def steam_dirs():
    """Steam install folders to look in: the registry first, then the usual places."""
    out = []
    try:
        import winreg
        for hive, key, val in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                               (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, key) as k: out.append(os.path.normpath(winreg.QueryValueEx(k, val)[0]))
            except OSError: pass
    except ImportError: pass
    out += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    seen = []
    for d in out:
        if d and d.lower() not in [s.lower() for s in seen]: seen.append(d)
    return seen


def libraries(steam):
    """Library folders listed in steamapps/libraryfolders.vdf, each with the app ids it holds."""
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(vdf): return []
    text = open(vdf, encoding="utf-8", errors="replace").read()
    out = []
    for block in re.finditer(r'"\d+"\s*\{(.*?)\n\t\}', text, re.S):
        b = block.group(1)
        m = re.search(r'"path"\s*"([^"]+)"', b)
        if not m: continue
        apps = set(re.findall(r'"(\d+)"\s*"\d+"', b.split('"apps"', 1)[1])) if '"apps"' in b else set()
        out.append((m.group(1).replace("\\\\", "\\"), apps))
    return out


def find_game(steam_dirs_=None):
    """The game's Binaries/Win64 folder, found through Steam's library list (app 1100990). None if not found."""
    for steam in steam_dirs_ or steam_dirs():
        for lib, apps in libraries(steam):
            if apps and APP_ID not in apps: continue
            acf = os.path.join(lib, "steamapps", f"appmanifest_{APP_ID}.acf")
            name = "Aimbeast"
            if os.path.exists(acf):
                m = re.search(r'"installdir"\s*"([^"]+)"', open(acf, encoding="utf-8", errors="replace").read())
                if m: name = m.group(1)
            win64 = os.path.join(lib, "steamapps", "common", name, "Aimbeast", "Binaries", "Win64")
            if os.path.exists(os.path.join(win64, "Aimbeast-Win64-Shipping.exe")): return os.path.normpath(win64)
    return None


def load():
    cfg = json.load(open(CONFIG, encoding="utf-8")) if os.path.exists(CONFIG) else {}
    if os.environ.get("AIMSTATS_GAME"): cfg["game"] = os.environ["AIMSTATS_GAME"]; cfg.pop("mods", None)
    if not cfg.get("game"): cfg["game"] = find_game()
    g = cfg.get("game")
    if g and not cfg.get("mods"):
        cfg["mods"] = os.path.join(g, "ue4ss", "Mods") if os.path.isdir(os.path.join(g, "ue4ss")) else os.path.join(g, "Mods")
    return cfg


CFG = load()
GAME = CFG.get("game")                                                    # .../Aimbeast/Binaries/Win64
MODS = CFG.get("mods")
GAME_RUNS = os.path.join(MODS, "AimRecorder", "runs") if MODS else None   # where the recorder writes
PRACTICE_LOG = os.path.join(MODS, "PracticeLog", "practice_log.csv") if MODS else None
TRAINER = os.path.join(os.path.dirname(os.path.dirname(GAME)), "Trainer") if GAME else None
STATS = os.path.join(TRAINER, "Statistics") if TRAINER else None
STEAMAPPS = os.path.abspath(os.path.join(GAME, *[".."] * 5)) if GAME else None
WORKSHOP = os.path.join(STEAMAPPS, "workshop", "content", APP_ID) if STEAMAPPS else None


def fov():
    """The player's horizontal field of view from the game's own settings (103 if it can't be read)."""
    try:
        import scenario_profile
        v = float(scenario_profile.read(os.path.join(TRAINER, "Config.cfg")).get("FOV", 103))
        return v if 60 <= v <= 150 else 103.0
    except Exception: return 103.0


def open_run(path):
    """A recording as text, plain or gzipped."""
    return gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8")


def ffmpeg():
    exe = os.path.join(APP, "ffmpeg", "ffmpeg.exe")
    return exe if os.path.exists(exe) else "ffmpeg"


def run_script(name, *args, env=None, timeout=900):
    """Run one of the render scripts with this same Python, no console window. Returns (ok, output)."""
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, name), *map(str, args)], capture_output=True, text=True,
                       cwd=SCRIPTS, env=dict(os.environ, **(env or {})), creationflags=NO_WINDOW, timeout=timeout)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def key(s):
    """Scenario names compared without spaces, case or punctuation (the recorder turns '%' into '_')."""
    return re.sub(r"[^A-Z0-9]", "", s.upper())
