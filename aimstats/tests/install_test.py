# Install/uninstall test of the built AimStats zip against COPIES of the game's Binaries/Win64 (never the live one).
# Each case snapshots every file (size + sha256) before install and after uninstall and compares them.
# Usage: python -I install_test.py <empty temp folder> <dist/AimStats-v1.zip> [<live Binaries/Win64 to copy from>]
import hashlib, json, os, shutil, subprocess, sys, zipfile

T, ZIP = sys.argv[1], sys.argv[2]
LIVE = sys.argv[3] if len(sys.argv) > 3 else r"C:\Program Files (x86)\Steam\steamapps\common\Aimbeast\Aimbeast\Binaries\Win64"
shutil.rmtree(T, ignore_errors=True); os.makedirs(T)
ENV = {"SYSTEMROOT": r"C:\Windows", "PATH": r"C:\Windows\System32;C:\Windows\System32\WindowsPowerShell\v1.0"}   # nothing from this PC's Python


def snap(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = (os.path.getsize(p), hashlib.sha256(open(p, "rb").read()).hexdigest())
    return out


def diff(a, b):
    return dict(missing=sorted(set(a) - set(b)), extra=sorted(set(b) - set(a)), changed=sorted(k for k in set(a) & set(b) if a[k] != b[k]))


def same(a, b): return not any(diff(a, b).values())


def pkg(name):
    d = os.path.join(T, name)
    with zipfile.ZipFile(ZIP) as z: z.extractall(d)
    return os.path.join(d, "AimStats")


def run(p, *args):
    r = subprocess.run([os.path.join(p, "app", "python", "python.exe"), os.path.join(p, "app", "scripts", "installer.py"), *args, "--yes"],
                       capture_output=True, text=True, env=ENV)
    print("   > installer " + args[0]); print("     " + (r.stdout + r.stderr).strip().replace("\n", "\n     "))
    return r.returncode


def game_copy(root, with_ue4ss, drop_mods=()):
    w = os.path.join(root, "steamapps", "common", "Aimbeast", "Aimbeast", "Binaries", "Win64"); os.makedirs(w)
    for f in os.listdir(LIVE):
        p = os.path.join(LIVE, f)
        if os.path.isfile(p) and (with_ue4ss or f not in ("dwmapi.dll", "imgui.ini")): shutil.copy2(p, w)
    if with_ue4ss:
        def ign(d, names):
            out = {"UE4SS_ObjectDump.txt", "CXXHeaderDump", "runs"} & set(names)        # skip the 570 MB of dumps
            if os.path.basename(d) == "Mods": out |= set(drop_mods)
            return out
        shutil.copytree(os.path.join(LIVE, "ue4ss"), os.path.join(w, "ue4ss"), ignore=ign)
        mt = os.path.join(w, "ue4ss", "Mods", "mods.txt")
        s = open(mt, encoding="utf-8").read().splitlines()
        open(mt, "w", encoding="utf-8").write("\n".join(l for l in s if l.split(":")[0].strip() not in drop_mods) + "\n")
        mj = os.path.join(w, "ue4ss", "Mods", "mods.json")
        if os.path.exists(mj):
            j = [m for m in json.load(open(mj)) if m["mod_name"] not in drop_mods]; json.dump(j, open(mj, "w"), indent=4)
    return w


results = {}
print("A. Clean game (no UE4SS), found through a Steam libraryfolders.vdf with two libraries")
lib = os.path.join(T, "A_lib"); wA = game_copy(lib, False)
open(os.path.join(lib, "steamapps", "appmanifest_1100990.acf"), "w").write('"AppState"\n{\n\t"appid"\t\t"1100990"\n\t"installdir"\t\t"Aimbeast"\n}\n')
steam = os.path.join(T, "A_steam"); os.makedirs(os.path.join(steam, "steamapps"))
esc = lambda s: s.replace("\\", "\\\\")
open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), "w").write(
    '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t\t"apps"\n\t\t{\n\t\t\t"228980"\t\t"1"\n\t\t}\n\t}\n'
    '\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t\t"apps"\n\t\t{\n\t\t\t"1100990"\t\t"3316325640"\n\t\t}\n\t}\n}\n' % (esc(os.path.join(T, "A_other")), esc(lib)))
before = snap(wA); p = pkg("A_pkg")
run(p, "install", "--steam", steam)
mid = snap(wA); man = json.load(open(os.path.join(p, "data", "install_manifest.json")))
found = os.path.normcase(os.path.normpath(man["game"])) == os.path.normcase(os.path.normpath(wA))
d = diff(before, mid)
print(f"   found the copy through Steam: {found} | added {len(d['extra'])} files | changed existing: {d['changed'] or 'none'}")
ini = open(os.path.join(wA, "ue4ss", "UE4SS-settings.ini")).read()
print("   settings: GuiConsoleEnabled = 0:", "GuiConsoleEnabled = 0" in ini, "| GuiConsoleVisible = 0:", "GuiConsoleVisible = 0" in ini,
      "| EnableDumping = 0:", "EnableDumping = 0" in ini)
print("   mods.txt:", open(os.path.join(wA, "ue4ss", "Mods", "mods.txt")).read().strip().replace("\n", " | "))
rec = open(os.path.join(wA, "ue4ss", "Mods", "AimRecorder", "Scripts", "main.lua")).read()
import re as _re
phase = int((_re.search(r"phase (\d+)", rec) or [0, 0])[1])
print(f"   recorder: phase {phase} (6 or later: {phase >= 6})", "| 120/s clicking:", "CLICK_RATE = 1 / 120" in rec, "| RECORD_RANKED = true:", "local RECORD_RANKED = true" in rec)
listed = sorted(f["path"] for f in man["created_files"]) == d["extra"]
print("   manifest lists exactly the added files:", listed)
# pretend the game ran: a recording, the practice log and UE4SS's log
os.makedirs(os.path.join(wA, "ue4ss", "Mods", "AimRecorder", "runs"))
open(os.path.join(wA, "ue4ss", "Mods", "AimRecorder", "runs", "2026-10-09_120000_TEST.csv"), "w").write("t\n1\n")
open(os.path.join(wA, "ue4ss", "UE4SS.log"), "w").write("log")
open(os.path.join(wA, "ue4ss", "Mods", "PracticeLog", "practice_log.csv"), "w").write("time\n")
run(p, "uninstall")
after = snap(wA)
print(f"   after uninstall, {len(before)} files compared:", "IDENTICAL" if same(before, after) else diff(before, after))
saved = os.path.exists(os.path.join(p, "data", "saved_from_game", "ue4ss", "Mods", "AimRecorder", "runs", "2026-10-09_120000_TEST.csv"))
print("   recording copied to data\\saved_from_game:", saved)
results["A clean game"] = same(before, after) and listed and saved and found and phase >= 6

print("\nB. Existing UE4SS with other mods, AimRecorder and PracticeLog missing")
wB = game_copy(os.path.join(T, "B_lib"), True, drop_mods=("AimRecorder", "PracticeLog"))
before = snap(wB); p = pkg("B_pkg")
run(p, "install", "--game", wB)
mid = snap(wB); d = diff(before, mid)
untouched = all(before[k] == mid[k] for k in before if not k.endswith(("mods.txt", "mods.json")))
print(f"   added {len(d['extra'])} files | changed: {d['changed']} | everything else untouched: {untouched}")
print("   mods.txt:", open(os.path.join(wB, "ue4ss", "Mods", "mods.txt")).read().strip().replace("\n", " | ")[-170:])
run(p, "uninstall")
after = snap(wB)
print(f"   after uninstall, {len(before)} files compared:", "IDENTICAL" if same(before, after) else diff(before, after))
results["B existing UE4SS"] = same(before, after) and untouched

print("\nC. Same, but the player adds a mod to mods.txt after installing")
wC = game_copy(os.path.join(T, "C_lib"), True, drop_mods=("AimRecorder", "PracticeLog"))
before = snap(wC); p = pkg("C_pkg")
run(p, "install", "--game", wC)
mt = os.path.join(wC, "ue4ss", "Mods", "mods.txt"); open(mt, "a").write("MyOtherMod : 1\n")
run(p, "uninstall")
txt = open(mt).read(); d = diff(before, snap(wC))
ok = "MyOtherMod : 1" in txt and "AimRecorder" not in txt and "PracticeLog" not in txt and not d["missing"] and not d["extra"]
print("   their line kept, AimStats' lines gone, no other file changed:", ok, d["changed"])
results["C player edited mods.txt"] = ok

print("\nD. Existing setup that already has every AimStats mod (like Ryan's)")
wD = game_copy(os.path.join(T, "D_lib"), True)
before = snap(wD); p = pkg("D_pkg")
run(p, "install", "--game", wD)
mid = snap(wD); print("   changed by install:", "NOTHING" if same(before, mid) else diff(before, mid))
run(p, "uninstall"); after = snap(wD)
print("   after uninstall:", "IDENTICAL" if same(before, after) else diff(before, after))
results["D everything already there"] = same(before, mid) and same(before, after)

print("\nE. Second install without uninstalling first")
p = pkg("E_pkg"); wE = game_copy(os.path.join(T, "E_lib"), False)
before = snap(wE)
run(p, "install", "--game", wE); code = run(p, "install", "--game", wE); run(p, "uninstall")
results["E second install refused"] = code == 1 and same(before, snap(wE))

print("\nRESULTS")
for k, v in results.items(): print(f"  {'PASS' if v else 'FAIL'}  {k}")
sys.exit(0 if all(results.values()) else 1)
