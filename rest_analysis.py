# Joins each completed run in practice_log.csv to its score (game statistics, same day, same order)
# and the rest before it. Prints a summary used for the rest-period QnA.
import csv, json, os, statistics as st, datetime as dt, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish as P

def load(path):
    try: return json.loads(open(path, "rb").read().decode("utf-16"))
    except Exception: return None

def scores_for(scenario, day):
    base = scenario[:-9] if scenario.endswith(" - RANKED") else scenario
    y, m, d = day.split("-"); want = f"{int(d)}/{int(m)}/{y}"
    for f in (["Ranked", "Normal", "Custom"] if base != scenario else ["Normal", "Custom", "Ranked"]):
        for name in (base, scenario):
            j = load(os.path.join(P.TRAINER_STATS, f, name + ".json"))
            if j:
                s = [x for x, dd in zip(j.get("Score", []), j.get("Date", [])) if dd == want]
                if s: return s
    return []

rows = list(csv.DictReader(open(P.LOG, encoding="utf-8")))
# rest = from the end of the previous completed run to the next start (restarts count as playing, not rest)
runs, last_end, last_start, first, rest = [], None, {}, {}, None
for r in rows:
    t = P.t(r["time"]); day = r["time"][:10]
    first.setdefault(day, t)
    if r["event"] == "start":
        last_start[r["scenario"]] = t
        if last_end is not None:
            rest = (t - last_end).total_seconds() if last_end.date() == t.date() else None
            last_end = None
    if r["event"] == "end" and r["completed"] == "true":
        runs.append(dict(day=day, scen=r["scenario"], start=last_start.get(r["scenario"]), end=t, rest=rest, playlist=r["routine"],
                         since_first=(t - first[day]).total_seconds() / 60))
        last_end, rest = t, None

# attach scores per (day, scenario) in order; align from the end if counts differ
from collections import defaultdict
groups = defaultdict(list)
for x in runs: groups[(x["day"], x["scen"])].append(x)
for (day, scen), xs in groups.items():
    sc = scores_for(scen, day)
    k = min(len(xs), len(sc))
    for x, s in zip(xs[-k:] if k else [], sc[-k:]): x["score"] = s
scored = [x for x in runs if "score" in x]
# normalise: score / that scenario's median across all scored runs
med = {s: st.median([x["score"] for x in scored if x["scen"] == s]) for s in {x["scen"] for x in scored}}
for x in scored: x["rel"] = 100 * x["score"] / med[x["scen"]]

prev, k = None, 0
for x in scored:
    k = k + 1 if (x["scen"] == prev) else 1; prev = x["scen"]; x["k"] = k

if __name__ == '__main__':
    def summ(label, xs):
        if not xs: print(f"{label:34s} n=0"); return
        r = [x["rel"] for x in xs]
        print(f"{label:34s} n={len(xs):3d}  median {st.median(r):5.1f}%  mean {st.mean(r):5.1f}%")

    print("completed runs", len(runs), "scored", len(scored))
    for day in sorted({x["day"] for x in runs}):
        d = [x for x in runs if x["day"] == day]
        print(day, "first run", min(x["start"] or x["end"] for x in d).strftime("%H:%M"), "last", max(x["end"] for x in d).strftime("%H:%M"),
              "runs", len(d), "median rest", st.median([x["rest"] for x in d if x["rest"] is not None]))
    print("\nrest before run (score as % of that scenario's median):")
    R = [x for x in scored if x["rest"] is not None]
    for lo, hi, lab in [(0, 10, "<10 s"), (10, 20, "10-20 s"), (20, 40, "20-40 s"), (40, 120, "40 s-2 min"), (120, 900, "2-15 min"), (900, 1e9, "15 min+ (break)")]:
        summ(lab, [x for x in R if lo <= x["rest"] < hi])
    summ("first run of day", [x for x in scored if x["rest"] is None])
    print("\nposition in the day (minutes since first run):")
    for lo, hi in [(0, 15), (15, 30), (30, 60), (60, 120), (120, 600)]:
        summ(f"{lo}-{hi} min", [x for x in scored if lo <= x["since_first"] < hi])
    print("\nby hour:")
    for h in sorted({x["end"].hour for x in scored}): summ(f"{h:02d}:00", [x for x in scored if x["end"].hour == h])
    print("\nper day:")
    for day in sorted({x["day"] for x in scored}): summ(day, [x for x in scored if x["day"] == day])
    # within-scenario repeats: second attempt in a row vs first
    print("\nrun number within a scenario block:")
    for k in (1, 2, 3, 4): summ(f"attempt {k}", [x for x in scored if x.get("k") == k])
    if len(R) > 5:
        xs = [min(x["rest"], 120) for x in R]; ys = [x["rel"] for x in R]
        print("\ncorrelation rest (capped 120 s) vs score:", round(st.correlation(xs, ys), 2))

    print("\nrest, split by attempt (separates warm-up from rest):")
    for lab, cond in [("attempt 1", lambda x: x.get("k") == 1), ("attempt 2+", lambda x: x.get("k", 0) >= 2)]:
        for lo, hi, b in [(0, 20, "<20 s"), (20, 120, "20 s-2 min"), (120, 900, "2-15 min"), (900, 1e9, "15 min+")]:
            summ(f"{lab}, rest {b}", [x for x in scored if cond(x) and x["rest"] is not None and lo <= x["rest"] < hi])


def rest_effect():
    """Score vs that scenario's median, grouped by warm-up and rest. Used by publish.py."""
    def g(label, xs):
        r = [x["rel"] for x in xs]
        return {"label": label, "runs": len(r), "pct": round(st.median(r), 1) if r else None}
    later = [x for x in scored if x.get("k", 0) >= 2 and x["rest"] is not None]
    return {"runs": len(scored), "days": len({x["day"] for x in scored}), "groups": [
        g("First attempt on a scenario", [x for x in scored if x.get("k") == 1]),
        g("Later attempts, rest under 20 s", [x for x in later if x["rest"] < 20]),
        g("Later attempts, rest 20 s to 2 min", [x for x in later if 20 <= x["rest"] < 120]),
        g("First run after a break of 15 min+", [x for x in scored if x["rest"] is not None and x["rest"] >= 900]),
    ]}
