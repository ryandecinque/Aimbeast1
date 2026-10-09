# "Same run, 20% better" clips for the site's best runs: the best run's 8 best seconds, real aim on the left and a model
# on the same bot movement on the right, tuned so the whole run would score 20% more. Uses AimStats' model_clip.py
# (same rules: only bots whose path ignores the player's hits; real camera path; bot shape from the .bot file).
# Usage: python model_best.py            (makes any missing clips for best_runs.json)
import glob, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "aimstats", "src", "app", "scripts")
RUNS = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods/AimRecorder/runs"
BEST = os.path.join(HERE, "best_runs.json")
WIN = 8 * 60


def run_file(date, hhmm, scen_key):
    """The recording for a best run, from its date, start time (HH:MM) and scenario."""
    import re
    key = lambda s: re.sub(r"[^A-Z0-9]", "", s.upper().replace(" - RANKED", "").replace("RANKED", ""))
    for p in sorted(glob.glob(f"{RUNS}/{date}_{hhmm.replace(':', '')}*")):
        if key(os.path.basename(p)[18:].replace(".gz", "").replace(".csv", "")) == key(scen_key): return p
    return None


def window(path):
    """Sample range of the 8 seconds with the most hits (same choice as the best-run clip)."""
    import csv
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    hits = [int(r["hits"]) for r in rows]
    resets = [i for i in range(1, len(hits)) if hits[i] < hits[i - 1]]
    first = resets[-1] if resets else 0
    best, a = -1, first
    for i in range(first, len(hits) - WIN, 6):
        if hits[i + WIN] - hits[i] > best: best, a = hits[i + WIN] - hits[i], i
    return a, a + WIN


def make(path, score, out, factor=1.2):
    """Returns {"file", "label"} or {"none": reason}."""
    a, b = window(path)
    env = dict(os.environ, AIMSTATS_DATA=os.path.join(tempfile.gettempdir(), "aimstats_site"),
               AIMSTATS_GAME=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(RUNS)))))
    r = subprocess.run([sys.executable, "model_clip.py", path, str(score), str(a), str(b), out, str(factor)], cwd=SCRIPTS, env=env,
                       capture_output=True, text=True, creationflags=0x08000000, timeout=1800)
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    if r.returncode == 3 or not os.path.exists(out):
        return {"none": (lines[-1] if lines else "Not available for this scenario.")}
    info = json.loads(lines[-1]) if lines and lines[-1].startswith("{") else {}
    tgt = info.get("target") or round(factor * score)
    lab = f"Model: {info.get('model_score', tgt)}" + ("" if info.get("reached", True) else f" (the closest it could get to {tgt})")
    return {"file": os.path.basename(out)[:-4], "label": lab}


def update():
    best = json.load(open(BEST, encoding="utf-8"))
    changed = False
    for date, entries in best.items():
        for e in entries:
            if "model" in e: continue
            p = run_file(date, e["time"], e["scenario"])
            if not p: continue
            out = os.path.join(HERE, "assets", "aim", e["gif"].replace("best-", "model-") + ".mp4")
            e["model"] = make(p, e["score"], out); changed = True
            print(date, e["scenario"], e["model"])
    if changed: json.dump(best, open(BEST, "w", encoding="utf-8"), indent=1)
    return changed


if __name__ == "__main__":
    update()
