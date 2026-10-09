# Keeps best_runs.json up to date on its own: for every day and ranked Intermediate scenario with recorder data,
# the best recorded run gets a card and a GIF of its 8 seconds with the most hits. Called by publish.py.
# Hand-written entries are kept unless a better run of the same scenario on the same day shows up.
import glob, json, os, re, statistics as st, subprocess, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BEST = os.path.join(HERE, "best_runs.json")
SUMMARY = os.path.join(HERE, "aim_summary.json")
RUNS = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods/AimRecorder/runs"
SCORES = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods/RoutinePlanBanner/recent_scores.txt"
# (workshop id, ranked name, card title, gif slug)
INT = [("2793300284", "SMOOTH THIN TRACK V2", "Smooth Thin Track V2", "smooththin"),
       ("2793819845", "AIR TRACK SMOOTH V3 150%", "Air Track Smooth V3 150%", "airtrack"),
       ("2795101783", "AIR CONTROL SPHERE - S", "Air Control Sphere - S", "spheres"),
       ("2795104443", "PASU TRACK EVO (RCT) - 0.85X", "PASU Track Evo (RCT) - 0.85X", "pasu085"),
       ("2795099562", "PASU TRACK XYZ", "PASU Track XYZ", "pasuxyz"),
       ("2795094492", "ZEUS TRACK EVO - NOBLINK", "Zeus Track Evo - Noblink", "zeus")]
key = lambda s: re.sub(r"[^A-Z0-9]", "", s.upper())


def scores():
    """{(date, id): [scores in play order]} from the banner's ranked score log."""
    out = {}
    if os.path.exists(SCORES):
        for line in open(SCORES, encoding="utf-8", errors="replace"):
            p = line.split()
            if len(p) == 3 and p[2].isdigit(): out.setdefault((p[0], p[1]), []).append(int(p[2]))
    return out


def update(master3=None, best_14d=None):
    if not os.path.exists(SUMMARY): return
    summ = json.load(open(SUMMARY, encoding="utf-8"))
    best = json.load(open(BEST, encoding="utf-8")) if os.path.exists(BEST) else {}
    sc = scores()
    changed = False
    for wid, rname, title, slug in INT:
        ks = {key(rname + " - RANKED"), key(rname)}          # recorded under either name
        by_day = {}
        for f, v in summ.items():
            if v.get("hits") is None or key(v.get("scenario", "")) not in ks: continue
            by_day.setdefault(v["date"], []).append((f, v))
        for date, runs in by_day.items():
            f, v = max(runs, key=lambda x: x[1]["hits"])
            day_scores = sc.get((date, wid), [])
            # the game's score for this run: the day's best if the recorder agrees within 3, else the recorded hits
            score = max(day_scores) if day_scores and abs(max(day_scores) - v["hits"]) <= 3 else v["hits"]
            entries = best.setdefault(date, [])
            old = next((e for e in entries if key(e["scenario"]) == key(title)), None)
            if old and old["score"] >= score: continue
            gif = f"best-{slug}-{date}"
            path = next(iter(glob.glob(os.path.join(RUNS, f)) + glob.glob(os.path.join(RUNS, f + ".gz"))), None)
            if not path or path.endswith(".gz"): continue
            r = subprocess.run([sys.executable, os.path.join(HERE, "best_run_gif.py"), path, str(score), f"{title}, best run ({score})",
                                os.path.join(HERE, "assets", "aim", gif + ".gif")], cwd=HERE, capture_output=True, text=True,
                               creationflags=0x08000000)
            if r.returncode != 0: print("best-run gif failed:", r.stderr[-300:]); continue
            im = Image.open(os.path.join(HERE, "assets", "aim", gif + ".gif")); im.seek(min(120, im.n_frames - 1))
            im.convert("RGB").save(os.path.join(HERE, "assets", "aim", gif + ".png"))
            before = [s for (d, i), L in sc.items() if i == wid and d < date for s in L]
            note = f"Best of {len(runs)} recorded today (median {round(st.median(x[1]['hits'] for x in runs))})."
            if before and score > max(before): note += f" A new best, above my old {max(before)}."
            new = dict(scenario=title, score=score, time=v["time"][:5], gif=gif, on_target=round(v["on_target"]),
                       reaction_ms=v.get("reaction_ms"), overshoot_pct=v.get("overshoot_pct"),
                       best_14d=(best_14d or {}).get(rname), master3=(master3 or {}).get(rname),
                       note=note + " The clip is its 8 seconds with the most hits.")
            if old: entries.remove(old)
            entries.append(new); changed = True
            print("best run:", date, title, score)
    if changed: json.dump(best, open(BEST, "w", encoding="utf-8"), indent=1)
    return changed
