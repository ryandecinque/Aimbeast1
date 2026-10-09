# Builds the AimStats zip for friends: src/ + embeddable Python + Pillow + ffmpeg + the UE4SS loader files.
# Nothing is downloaded here; pass the files you already have:
#   --python  python-3.11.9-embed-amd64.zip     (python.org)
#   --ffmpeg  imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl  (PyPI; holds a static ffmpeg 7.1 with H.264)
#   --pillow  a Python 3.11 site-packages folder with PIL in it (default: this Python's)
#   --ue4ss   the game's Binaries/Win64 folder with UE4SS 3.0.1 (dwmapi.dll, ue4ss/UE4SS.dll, ue4ss/LICENSE); read only
# Output: dist/AimStats-v1.zip
import argparse, glob, os, shutil, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--python", required=True); ap.add_argument("--ffmpeg", required=True)
ap.add_argument("--pillow"); ap.add_argument("--ue4ss", required=True)
ap.add_argument("--stage", default=os.path.join(HERE, "build"), help="folder to assemble in (emptied first)")
a = ap.parse_args()

OUT = os.path.join(a.stage, "AimStats")
shutil.rmtree(a.stage, ignore_errors=True)
shutil.copytree(os.path.join(HERE, "src"), OUT, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
APP = os.path.join(OUT, "app")
LIC = os.path.join(OUT, "licences"); os.makedirs(LIC)

# Python (embeddable) with our scripts and site-packages on its path
py = os.path.join(APP, "python")
with zipfile.ZipFile(a.python) as z: z.extractall(py)
pth = glob.glob(os.path.join(py, "python3*._pth"))[0]
open(pth, "w").write("python311.zip\n.\nLib\\site-packages\n..\\scripts\n")
shutil.copy2(os.path.join(py, "LICENSE.txt"), os.path.join(LIC, "Python-LICENSE.txt"))

# Pillow
site = a.pillow
if not site:
    import PIL; site = os.path.dirname(os.path.dirname(PIL.__file__))
sp = os.path.join(py, "Lib", "site-packages"); os.makedirs(sp)
shutil.copytree(os.path.join(site, "PIL"), os.path.join(sp, "PIL"), ignore=shutil.ignore_patterns("__pycache__"))
dist = glob.glob(os.path.join(site, "pillow-*.dist-info"))[0]
shutil.copytree(dist, os.path.join(sp, os.path.basename(dist)))
for f in [f for f in glob.glob(os.path.join(dist, "**", "LICENSE*"), recursive=True) if os.path.isfile(f)]: shutil.copy2(f, os.path.join(LIC, "Pillow-" + os.path.basename(f)))

# ffmpeg (just the exe from the wheel)
ff = os.path.join(APP, "ffmpeg"); os.makedirs(ff)
with zipfile.ZipFile(a.ffmpeg) as z:
    exe = next(n for n in z.namelist() if n.endswith(".exe") and "ffmpeg" in n)
    with z.open(exe) as s, open(os.path.join(ff, "ffmpeg.exe"), "wb") as d: shutil.copyfileobj(s, d)
open(os.path.join(LIC, "ffmpeg-README.txt"), "w").write(
    "ffmpeg 7.1 'essentials' static build by gyan.dev (https://www.gyan.dev/ffmpeg/builds/), as shipped in the\n"
    "imageio-ffmpeg 0.6.0 package. ffmpeg is licensed under the GNU GPL v3 because this build includes libx264.\n"
    "Source code: https://ffmpeg.org/download.html  Licence text: https://www.gnu.org/licenses/gpl-3.0.txt\n"
    "AimStats only uses it to turn its own pictures into MP4 videos.\n")

# UE4SS loader files, copied from a working install (read only)
gf = os.path.join(APP, "game_files")
shutil.copy2(os.path.join(a.ue4ss, "dwmapi.dll"), os.path.join(gf, "dwmapi.dll"))
for f in ("UE4SS.dll", "LICENSE"): shutil.copy2(os.path.join(a.ue4ss, "ue4ss", f), os.path.join(gf, "ue4ss", f))
shutil.copy2(os.path.join(gf, "ue4ss", "LICENSE"), os.path.join(LIC, "UE4SS-LICENSE.txt"))
os.makedirs(os.path.join(OUT, "data"))

# check the bundled Python can import everything, with nothing from this PC on its path
r = subprocess.run([os.path.join(py, "python.exe"), "-c", "import PIL.Image, winreg, http.server, gzip, csv, statistics, webbrowser;"
                    "import config, aim_analysis, scenario_profile, pb_events, installer, rests, model_run, lives, scen_rules, fast_clip, kill_stats; print('imports ok', PIL.__version__)"],
                   capture_output=True, text=True, env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")}, cwd=OUT)
print(r.stdout.strip(), r.stderr.strip()[-500:])
if r.returncode: sys.exit("bundled Python check failed")

os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
zp = os.path.join(HERE, "dist", "AimStats-v1.zip")
if os.path.exists(zp): os.remove(zp)
with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for d, _, fs in os.walk(OUT):
        for f in fs:
            p = os.path.join(d, f); z.write(p, os.path.relpath(p, os.path.dirname(OUT)))
        if not fs and d != OUT: z.write(d, os.path.relpath(d, os.path.dirname(OUT)) + "/")
print("wrote", zp, round(os.path.getsize(zp) / 1e6, 1), "MB")
