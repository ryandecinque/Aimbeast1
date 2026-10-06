"""Builds data.json for the public Aimbeast progress site from the local mod logs, then pushes it.

Usage:
  python publish.py            # build data.json; commit + push if it changed
  python publish.py --dry-run  # build and print a summary, no git
  python publish.py --if-marker  # only run when the PracticeLog mod left a session_done marker (for the scheduled task)

Only scenario names, times, run counts and scores are published. No Steam name, no file paths.
"""
import csv, datetime as dt, json, os, statistics as st, subprocess, sys

MODS = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods"
LOG = MODS + "/PracticeLog/practice_log.csv"
MARKER = MODS + "/PracticeLog/session_done"
BANNER = MODS + "/RoutinePlanBanner"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data.json")

INT = [("2793300284", "SMOOTH THIN TRACK V2"), ("2793819845", "AIR TRACK SMOOTH V3 150%"),
       ("2795101783", "AIR CONTROL SPHERE - S"), ("2795104443", "PASU TRACK EVO (RCT) - 0.85X"),
       ("2795099562", "PASU TRACK XYZ"), ("2795094492", "ZEUS TRACK EVO - NOBLINK")]
MASTER3 = 18          # rank index: 1 = Bronze 1 ... 18 = Master 3
RECENT_DAYS = 14
BREAK_MIN = 15 * 60   # a gap this long inside the same playlist counts as a break, not a rest


def t(s): return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def read_log():
    rows = []
    with open(LOG, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try: r["t"] = t(r["time"])
            except Exception: continue
            rows.append(r)
    return rows


def sessions_by_day(rows):
    """Completed runs, restarts (repeat entries within 1 s count once), rests and playlist breaks per day."""
    days = {}
    last_end = None        # (time, routine) of the last completed run
    pending_rest = None    # rest waiting for the next start
    last_restart = None
    for r in rows:
        day = r["t"].date().isoformat()
        d = days.setdefault(day, {"runs": 0, "restarts": 0, "rests": [], "breaks": [], "playlists": {}})
        routine = r["routine"] or "(single scenario)"
        if r["event"] == "end" and r["completed"] == "true":
            d["runs"] += 1
            p = d["playlists"].setdefault(routine, {"runs": 0, "first": r["time"][11:16], "last": r["time"][11:16]})
            p["runs"] += 1; p["last"] = r["time"][11:16]
            last_end = (r["t"], routine); pending_rest = last_end
        elif r["event"] == "end":
            if not last_restart or (r["t"] - last_restart).total_seconds() > 1:
                d["restarts"] += 1
            last_restart = r["t"]
        elif r["event"] == "start" and pending_rest:
            gap = (r["t"] - pending_rest[0]).total_seconds()
            same_day = r["t"].date() == pending_rest[0].date()
            if same_day and gap >= 0:
                if routine != pending_rest[1] or gap >= BREAK_MIN:
                    d["breaks"].append({"after": pending_rest[1], "before": routine,
                                        "at": pending_rest[0].strftime("%H:%M"), "minutes": round(gap / 60, 1)})
                else:
                    d["rests"].append(round(gap))
            pending_rest = None
    out = []
    for day in sorted(days, reverse=True):
        d = days[day]
        if d["runs"] == 0 and d["restarts"] == 0: continue
        rs = d["rests"]
        out.append({"date": day, "runs": d["runs"], "restarts": d["restarts"],
                    "rest_median_s": round(st.median(rs)) if rs else None,
                    "rest_longest_s": max(rs) if rs else None,
                    "breaks": d["breaks"],
                    "playlists": [{"name": k, **v} for k, v in d["playlists"].items()]})
    return out


def read_rank_data():
    best, ranges = {}, {}
    p = BANNER + "/rank_data.txt"
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if parts[0] == "best": best[parts[1]] = float(parts[2])
            elif parts[0] == "ranges":
                ranges[parts[1]] = (int(parts[2] or 0), [float(x) for x in parts[3].split(",") if x])
    return best, ranges


def read_recent():
    rec = {}
    p = BANNER + "/recent_scores.txt"
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3: rec.setdefault(parts[1], []).append((parts[0], float(parts[2])))
    return rec


def ranks():
    best, ranges = read_rank_data(); rec = read_recent()
    cutoff = (dt.date.today() - dt.timedelta(days=RECENT_DAYS)).isoformat()
    out = []
    for ws, name in INT:
        disabled, vals = ranges.get(ws, (0, []))
        i = MASTER3 - disabled - 1
        m3 = vals[i] if 0 <= i < len(vals) else (vals[-1] if vals else None)
        recent = [s for d, s in rec.get(ws, []) if d >= cutoff]
        out.append({"name": name, "master3": m3, "official_best": best.get(ws),
                    "best_14d": max(recent) if recent else None,
                    "median_14d": round(st.median(recent)) if recent else None,
                    "runs_14d": len(recent), "steps": vals})
    return out


PLAN_START = "2026-10-07"   # first session of the Master 3 plan
BASELINE_DAYS = 14          # baseline = ranked runs in the 14 days before the plan started
STATS = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Trainer/Statistics/Ranked"


def history():
    """Daily median, best and run count per scenario, from the game's own ranked statistics."""
    out = []
    for ws, name in INT:
        p = os.path.join(STATS, name + ".json")
        days = {}
        if os.path.exists(p):
            j = json.loads(open(p, "rb").read().decode("utf-16"))
            for s, d in zip(j["Score"], j["Date"]):
                dd, mm, yy = map(int, d.split("/"))
                days.setdefault(dt.date(yy, mm, dd).isoformat(), []).append(s)
        start = dt.date.fromisoformat(PLAN_START)
        before = [s for k, v in days.items() for s in v
                  if start - dt.timedelta(days=BASELINE_DAYS) <= dt.date.fromisoformat(k) < start]
        base = {"median": round(st.median(before)), "best": round(max(before)), "runs": len(before)} if before else None
        out.append({"name": name, "baseline": base,
                    "days": [{"date": k, "median": round(st.median(v)), "best": round(max(v)), "runs": len(v)}
                             for k, v in sorted(days.items())]})
    return out


def today_progress():
    p = BANNER + "/progress.txt"; today = dt.date.today().isoformat(); out = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3 and parts[0] == today: out[parts[1]] = int(parts[2])
    return out


def build():
    rows = read_log()
    return {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "today": {"date": dt.date.today().isoformat(), "progress": today_progress()},
            "plan_start": PLAN_START, "ranks": ranks(), "history": history(), "days": sessions_by_day(rows)}


def git(*args):
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True)


def main():
    if "--if-marker" in sys.argv and not os.path.exists(MARKER): return
    data = build()
    new = json.dumps(data, indent=1, ensure_ascii=False)
    old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    strip = lambda s: "\n".join(l for l in s.splitlines() if '"updated"' not in l)
    if "--dry-run" in sys.argv:
        for d in data["days"][:3]:
            print(d["date"], "runs", d["runs"], "restarts", d["restarts"], "median rest", d["rest_median_s"], "s, breaks", len(d["breaks"]))
        for r in data["ranks"]: print(f'  {r["name"]}: 14d best {r["best_14d"]} / M3 {r["master3"]}')
        return
    if strip(new) != strip(old):
        open(OUT, "w", encoding="utf-8").write(new)
        git("add", "data.json")
        c = git("commit", "-m", "Update practice data " + data["updated"])
        p = git("push")
        print(c.stdout.strip() or c.stderr.strip()); print(p.stderr.strip())
    if os.path.exists(MARKER): os.remove(MARKER)


if __name__ == "__main__":
    main()
