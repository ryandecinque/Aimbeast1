# Rest times from PracticeLog's practice_log.csv, with the same rules as the Road to Master 3 site:
#   - a rest runs from one completed run's end to the next start
#   - a restart is an unfinished end at least 3 s after the start (unfinished ends in the same second as a start are
#     noise), repeat entries within 1 s count once
#   - a gap of 15 min or more, or a change of playlist, is a break, not a rest
# Also compares scores after short rests (under 20 s) with longer ones (20 s to 2 min), first attempts on a scenario
# left out (they're warm-up), scores taken from the game's statistics files and measured against that scenario's
# typical score.
import csv, datetime as dt, os, statistics as st
import config

BREAK_MIN = 15 * 60
SHORT, LONG = 20, 120
MIN_RUNS = 10                 # per group, before the comparison is shown


def t(s): return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def read(path=None):
    path = path or config.PRACTICE_LOG
    if not path or not os.path.exists(path): return None
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try: r["t"] = t(r["time"])
            except Exception: continue
            rows.append(r)
    return rows


def analyse(rows):
    """{"days": [...newest first], "starts": {start time: (kind, seconds)}, "runs": [completed runs]}.
    kind is "rest", "break", "first" (first of the day) or "restart"."""
    days, starts, runs = {}, {}, []
    pending = None; last_start = None; last_restart = None; seen_day = set()
    for r in rows:
        day = r["t"].date().isoformat()
        d = days.setdefault(day, {"runs": 0, "restarts": 0, "rests": [], "breaks": 0})
        routine = r.get("routine") or "(single scenario)"
        if r["event"] == "end" and r.get("completed") == "true":
            d["runs"] += 1
            runs.append(dict(day=day, scenario=r["scenario"], end=r["t"], rest=None, kind=None))
            pending = (r["t"], routine)
        elif r["event"] == "end":
            if last_start is None or (r["t"] - last_start).total_seconds() < 3: continue
            if not last_restart or (r["t"] - last_restart).total_seconds() > 1: d["restarts"] += 1
            last_restart = r["t"]
        if r["event"] == "start":
            last_start = r["t"]
            kind, secs = ("first", None) if day not in seen_day else ("restart", None)
            seen_day.add(day)
            if pending:
                gap = (r["t"] - pending[0]).total_seconds()
                if r["t"].date() == pending[0].date() and gap >= 0:
                    if routine != pending[1] or gap >= BREAK_MIN: kind, secs = "break", round(gap); d["breaks"] += 1
                    else: kind, secs = "rest", round(gap); d["rests"].append(round(gap))
                pending = None
            starts[r["t"]] = (kind, secs)
    # the rest before each completed run is the one at its last start
    si = sorted(starts)
    j = 0
    for x in runs:
        while j + 1 < len(si) and si[j + 1] <= x["end"]: j += 1
        if si and si[j] <= x["end"]: x["kind"], x["rest"] = starts[si[j]]
    out = []
    for day in sorted(days, reverse=True):
        d = days[day]
        if not d["runs"] and not d["restarts"]: continue
        out.append(dict(date=day, runs=d["runs"], restarts=d["restarts"], breaks=d["breaks"],
                        rest_typical_s=round(st.median(d["rests"])) if d["rests"] else None,
                        rest_longest_s=max(d["rests"]) if d["rests"] else None))
    return {"days": out, "starts": starts, "runs": runs}


def rest_before(info, when):
    """(kind, seconds) for the run that started at `when` (a recording's start time), matched within 2 s."""
    if not info: return None
    best = min(info["starts"], key=lambda s: abs((s - when).total_seconds()), default=None)
    return info["starts"][best] if best and abs((best - when).total_seconds()) <= 2 else None


def compare(info):
    """Scores after short rests vs 20 s to 2 min, as % of each scenario's typical score. None if too few runs."""
    import pb_events
    runs = info["runs"]
    groups = {}
    for x in runs: groups.setdefault((x["day"], x["scenario"]), []).append(x)
    hist = {}
    for (day, scen), xs in groups.items():                   # same day, same order: line up from the end
        if scen not in hist: hist[scen] = pb_events.history(scen)
        sc = [s for d, s in hist[scen] if d == day]
        k = min(len(xs), len(sc))
        for x, s in zip(xs[-k:] if k else [], sc[-k:]): x["score"] = s
    scored = [x for x in runs if "score" in x]
    med = {}
    for x in scored: med.setdefault(x["scenario"], []).append(x["score"])
    med = {k: st.median(v) for k, v in med.items()}
    prev = None; n = 0
    for x in scored:
        n = n + 1 if x["scenario"] == prev else 1; prev = x["scenario"]; x["attempt"] = n
        x["rel"] = 100 * x["score"] / med[x["scenario"]] if med[x["scenario"]] else None
    later = [x for x in scored if x["attempt"] >= 2 and x["kind"] == "rest" and x["rel"] is not None]
    short = [x["rel"] for x in later if x["rest"] < SHORT]
    long_ = [x["rel"] for x in later if SHORT <= x["rest"] < LONG]
    if len(short) < MIN_RUNS or len(long_) < MIN_RUNS:
        return dict(enough=False, short_runs=len(short), long_runs=len(long_), need=MIN_RUNS)
    a, b = st.median(short), st.median(long_)
    return dict(enough=True, short_runs=len(short), long_runs=len(long_), short_pct=round(a, 1), long_pct=round(b, 1),
                diff_pct=round(a - b, 1))


def summary():
    rows = read()
    if rows is None: return None, None
    info = analyse(rows)
    try: cmp_ = compare(info)
    except Exception: cmp_ = None
    return info, {"days": info["days"][:14], "compare": cmp_}
