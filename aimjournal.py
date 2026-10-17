# AimJournal: rule-based journal reviews after each completed plan playlist. No AI calls, only templates.
#
# For every completed play of a plan playlist (RANK INT A / B, ZEUS BUILDER, ZEUS WEAKNESS) that hasn't been
# reviewed, it appends a "## YYYY-MM-DD AimJournal" entry to journal.md:
#   Playlist: <name>
#   <the answer: how the scores compared with his own last 14 days, or a best>
#   <the biggest gap against his own last 14 days: over-aim, far-away scoring, extra mouse movement or rests>
#   One thing to try: <cue for that gap: cause, then fix, then feel>
# At most 3 numbers per entry, each set against his own runs. A line that says the same thing as the previous
# AimJournal entry is replaced by the next candidate, or dropped.
#
# Where the numbers come from:
#   - ranked scores: the game's Ranked statistics files (via pb_events.history). recent_scores.txt also logs the
#     Normal-mode warm-up runs of the same scenario, so it is not used for the comparison.
#   - drill scores: the game's Normal/Custom statistics (rest_analysis.scores_for's folder order)
#   - official bests: RoutinePlanBanner/rank_data.txt. "New best" only when a score beats every earlier score and
#     reaches that official best; otherwise "best since the score log started".
#   - over-aim and far-away points a second: aim_summary.json (aim_analysis.py)
#   - aim travel vs bot travel: coach_metrics' input-economy measure, per run (cached in reviews/)
#   - rests: practice_log.csv via rest_analysis
# A play is counted in a run of the same playlist with no gap over 3 hours, so a play that crosses midnight still
# counts; its entry is dated by its first run. Playlist sizes come from the game's .rtn files.
#
# Usage: python aimjournal.py [--dry-run] [--day YYYY-MM-DD] [--explain]
import csv, datetime as dt, glob, gzip, hashlib, importlib, json, math, os, statistics as st, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import publish as P

REVIEWS = os.path.join(HERE, "reviews")
STATE = os.path.join(REVIEWS, "aimjournal_state.json")
LOG = os.path.join(REVIEWS, "aimjournal_log.txt")
TRAVEL = os.path.join(REVIEWS, "aimjournal_travel.json")
ROUTINES = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Trainer/Routines"
RUNS_DIR = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods/AimRecorder/runs"
AUTHOR = "AimJournal"
START = "2026-10-11"             # plays before this were reviewed by hand
PLAN = {"RANK INT A": 26, "RANK INT B": 32, "ZEUS BUILDER": 16, "ZEUS WEAKNESS": 15, "RANK INT B2": 24,
        "ZEUS DAILY": 29, "ZEUS FOCUS": 20, "ZEUS SECOND": 11, "OTHERS 1": 10, "OTHERS 2": 10, "OTHERS 3": 10}   # fallback sizes
WARMUP = {"RANK INT A": 2, "RANK INT B": 2}   # the first runs of each play are warm-ups (B's are Normal mode)
WINDOW = 14                      # "your usual" = the 14 days before the play's day
SESSION_GAP = 3 * 3600
MIN_BASE = 3                     # runs needed in the 14 days before a comparison is made
MAX_NUMBERS = 3
INT_NAMES = {n: ws for ws, n in P.INT}

SHORT = {"SMOOTH THIN TRACK V2": "Smooth Thin", "AIR TRACK SMOOTH V3 150%": "Air Track", "AIR CONTROL SPHERE - S": "Sphere S",
         "PASU TRACK EVO (RCT) - 0.85X": "PASU 0.85x", "PASU TRACK XYZ": "PASU XYZ", "ZEUS TRACK EVO - NOBLINK": "Zeus",
         "AIR CONTROL SPHERE": "Air Control Sphere", "SCX CLOSE STRAFES": "SCX Close Strafes", "CLOSELY STRAFING KYTAN": "Kytan",
         "PENNYTRACKING": "Pennytracking", "THIN FAST": "Thin Fast", "SLOW ACCEL 'STT' SHORT": "Slow Accel 'STT' Short",
         "ZEUS TRACK FAR BZN EDITION": "Far BZN", "ZEUS TRACK EVO - NOBLINK (EZ)": "Zeus EZ"}
WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()


def log(m):
    os.makedirs(REVIEWS, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(dt.datetime.now().strftime("%Y-%m-%d %H:%M ") + m + "\n")


def word(n): return WORDS[n] if 0 <= n < len(WORDS) else str(n)
def base_name(scen): return scen[:-9] if scen.endswith(" - RANKED") else scen
def short(scen): b = base_name(scen); return SHORT.get(b, b.title())
def norm(s): return "".join(c for c in s.upper() if c.isalnum())
def pick(variants, seed, avoid=None):
    """One wording, chosen by a hash of the seed (same input, same wording). Avoids the index `avoid` if possible."""
    i = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(variants)
    if avoid is not None and len(variants) > 1 and i == avoid: i = (i + 1) % len(variants)
    return i, variants[i]


# ---------- playlists and plays ----------

def playlist_size(name):
    """Total runs in a playlist: the sum of its Repetitions in the game's .rtn file (falls back to PLAN)."""
    try:
        f = next(p for p in glob.glob(ROUTINES + "/*.rtn") if os.path.basename(p)[:-4].strip().upper() == name.upper())
        b = open(f, "rb").read(); d = zlib.decompress(b[b.find(b"\x78\x9c"):])
        i = d.find(b"Repetitions\x00") + len(b"Repetitions\x00") + 8      # name, then a 64-bit size
        n = struct.unpack_from("<i", d, i)[0]
        reps = struct.unpack_from(f"<{n}i", d, i + 4)
        if 0 < n < 50 and all(0 < r < 100 for r in reps): return sum(reps)
    except Exception: pass
    return PLAN[name]


def plays(runs):
    """Completed plays of plan playlists: [(key, day, playlist, k, runs)], in time order. Also sets x['pos']
    (position inside its play) on every plan-playlist run, finished play or not."""
    sizes = {pl: playlist_size(pl) for pl in PLAN}
    cur, out, count = {}, [], {}
    for x in runs:
        pl = x["playlist"]
        if pl not in sizes: continue
        c = cur.get(pl)
        if c is None or (x["end"] - c["last"]).total_seconds() > SESSION_GAP:
            c = cur[pl] = {"runs": [], "last": x["end"]}
        x["pos"] = len(c["runs"]); c["runs"].append(x); c["last"] = x["end"]
        if len(c["runs"]) == sizes[pl]:
            xs = c["runs"]; day = xs[0]["day"]
            k = count[(day, pl)] = count.get((day, pl), 0) + 1
            out.append((f"{day}|{pl}|{k}", day, pl, k, xs))
            c["runs"] = []
    return out


# ---------- scores ----------

_hist = {}
def history(scen):
    """[(date, score)] in play order. Ranked scenarios: the game's Ranked file. Others: per day, the first of
    Normal/Custom/Ranked with scores that day (as rest_analysis does)."""
    if scen in _hist: return _hist[scen]
    b = base_name(scen)
    if b in INT_NAMES:
        import pb_events
        h = pb_events.history(b)
    else:
        import rest_analysis as R
        per = {}
        for f in (["Ranked", "Normal", "Custom"] if b != scen else ["Normal", "Custom", "Ranked"]):
            for name in (b, scen):
                j = R.load(os.path.join(P.TRAINER_STATS, f, name + ".json"))
                if not j: continue
                tmp = {}
                for s, d in zip(j.get("Score", []), j.get("Date", [])):
                    dd, mm, yy = d.split("/"); tmp.setdefault(f"{yy}-{int(mm):02d}-{int(dd):02d}", []).append(round(s))
                for d, v in tmp.items(): per.setdefault(d, v)
        h = [(d, s) for d in sorted(per) for s in per[d]]
    _hist[scen] = h
    return h


def attach_scores(runs):
    """x['score'] for every completed run: that day's scores for the scenario, matched in order from the end of the
    day. Warm-up runs in A and B are left out first (B's warm-ups are Normal mode and not in the Ranked file)."""
    by = {}
    for x in runs:
        if x.get("pos", 99) < WARMUP.get(x["playlist"], 0):
            x["warmup"] = True
            if base_name(x["scen"]) in INT_NAMES: continue
        by.setdefault((x["day"], x["scen"]), []).append(x)
    for (day, scen), xs in by.items():
        s = [v for d, v in history(scen) if d == day]
        k = min(len(xs), len(s))
        for i, x in enumerate(xs[len(xs) - k:]): x["score"] = s[len(s) - k + i]; x["score_i"] = len(s) - k + i


def window(day):
    d = dt.date.fromisoformat(day)
    return (d - dt.timedelta(days=WINDOW)).isoformat(), (d - dt.timedelta(days=1)).isoformat()


# ---------- aim data ----------

def aim_runs(xs, cache):
    """Map each run to its aim recorder entry in aim_summary.json (file starts between the run's start and end)."""
    idx = {}
    for k, v in cache.items():
        if "on_target" not in v: continue
        try: t = dt.datetime.strptime(v["date"] + " " + v["time"], "%Y-%m-%d %H:%M:%S")
        except Exception: continue
        idx.setdefault(norm(v["scenario"]), []).append((t, k, v))
    out = {}
    for x in xs:
        lo = (x["start"] or x["end"] - dt.timedelta(seconds=150)) - dt.timedelta(seconds=20)
        c = [e for e in idx.get(norm(x["scen"]), []) if lo <= e[0] <= x["end"]]
        if c: out[id(x)] = max(c)[1:]
    return out


def travel_ratio(fname, tcache):
    """Aim travel / bot travel, left-right, over the whole run (coach_metrics' input economy, all phases together)."""
    if fname in tcache: return tcache[fname]
    from aim_analysis import moving_ids, thin60
    p = os.path.join(RUNS_DIR, fname)
    if not os.path.exists(p): p += ".gz"
    if not os.path.exists(p): return None
    rows = list(csv.DictReader(gzip.open(p, "rt", encoding="utf-8") if p.endswith(".gz") else open(p, encoding="utf-8")))
    rows = thin60(rows); ids = moving_ids(rows); hits = [int(r["hits"]) for r in rows]
    rs = [i for i in range(1, len(rows)) if hits[i] < hits[i - 1]]; s0 = rs[-1] if rs else 0
    acc = prev = pb = None; aim = bot = 0.0; ok = False
    py = None
    for r in rows[s0:]:                       # same angles as coach_metrics.series
        k = next((j for j in range(1, 9) if r.get(f"b{j}_x") not in (None, "", "0.0") and (r.get(f"b{j}_id") or str(j)) in ids), None)
        y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y
        if k is None: py = pb = None; continue
        dx, dy = float(r[f"b{k}_x"]) - float(r["cam_x"]), float(r[f"b{k}_y"]) - float(r["cam_y"])
        b = math.degrees(math.atan2(dy, dx)); b = acc + ((b - acc + 180) % 360 - 180)
        if py is not None: aim += abs(acc - py); bot += abs(b - pb)
        py, pb = acc, b
    v = round(aim / bot, 3) if bot > 1 else None
    tcache[fname] = v
    return v


def med(v): return st.median(v) if v else None


# ---------- facts for one play ----------

def facts(day, pl, xs, all_runs, cache, tcache):
    lo, hi = window(day)
    best, _ = P.read_rank_data()
    scen = {}
    for x in xs:
        if x.get("warmup") or x.get("score") is None: continue
        scen.setdefault(x["scen"], []).append(x)
    res = {"scen": [], "bests": [], "gaps": [], "measured": set()}
    for s, rs in scen.items():
        h = history(s); b = base_name(s)
        base = [v for d, v in h if lo <= d <= hi]
        f = dict(scen=s, name=short(s), scores=[x["score"] for x in rs], base_n=len(base))
        if len(base) >= MIN_BASE:
            f.update(typ=round(med(f["scores"])), usual=round(med(base)))
            f["rel"] = (f["typ"] - f["usual"]) / f["usual"]
        res["scen"].append(f)
        # bests: the top score of the play against every earlier score of this scenario
        top = max(rs, key=lambda x: x["score"])
        day_s = [v for d, v in h if d == top["day"]]
        earlier = [v for d, v in h if d < top["day"]] + day_s[:top["score_i"]]
        off = best.get(INT_NAMES.get(b)) if b in INT_NAMES else None
        if len(earlier) >= 10 and top["score"] > max(earlier):
            kind = "new" if off is not None and top["score"] >= off else "log"
            res["bests"].append(dict(scen=s, name=short(s), score=top["score"], kind=kind, old=max(earlier), official=off))
    # aim recorder measures, per scenario: this play vs the 14 days before
    m = aim_runs(xs, cache)
    base_entries = {}
    for k, v in cache.items():
        if "on_target" in v and lo <= v["date"] <= hi: base_entries.setdefault(norm(v["scenario"]), []).append((k, v))
    for s, rs in scen.items():
        mine = [m[id(x)] for x in rs if id(x) in m]
        base = base_entries.get(norm(s), [])
        def far(v):
            b_ = (v.get("by_distance") or {}).get("far")
            return b_["points_per_sec"] if b_ and b_.get("seconds", 0) >= 10 else None
        for metric, get, worse_if_higher, thr, min_d in (
                ("overaim", lambda k, v: v.get("overshoot_pct"), True, 0.10, 3),
                ("far", lambda k, v: far(v), False, 0.08, 0.3),
                ("input", lambda k, v: travel_ratio(k, tcache), True, 0.08, 0.1)):
            a = [y for y in (get(k, v) for k, v in mine) if y is not None]
            b_ = [y for y in (get(k, v) for k, v in base) if y is not None]
            if len(a) < 2 or len(b_) < MIN_BASE: continue
            res["measured"].add(metric)
            pa, pb_ = med(a), med(b_)
            d = (pa - pb_) if worse_if_higher else (pb_ - pa)
            score = (d / pb_) / thr if pb_ else 0
            res["gaps"].append(dict(metric=metric, scen=s, name=short(s), now=pa, usual=pb_, real=d >= min_d and score >= 1, score=score,
                                    n=len(a), base_n=len(b_)))
    # rests inside the play vs all rests in the 14 days before (breaks of 15 min+ left out)
    rest_now = [x["rest"] for x in xs[1:] if x["rest"] is not None and x["rest"] < P.BREAK_MIN]
    rest_base = [x["rest"] for x in all_runs if lo <= x["day"] <= hi and x["rest"] is not None and x["rest"] < P.BREAK_MIN]
    if len(rest_now) >= 5 and len(rest_base) >= 20:
        res["measured"].add("rest")
        a, b_ = med(rest_now), med(rest_base)
        if a < b_:   # short rests matter below 20 s (the rest data: 20 s to 2 min looks a little better)
            res["gaps"].append(dict(metric="rest_short", scen=None, name=None, now=a, usual=b_, real=a < 20 and b_ / max(a, 1) >= 1.5,
                                    score=(b_ / max(a, 1) - 1) / 0.5, n=len(rest_now), base_n=len(rest_base)))
        else:        # long rests matter over 2 min
            res["gaps"].append(dict(metric="rest_long", scen=None, name=None, now=a, usual=b_, real=a > 120 and a / b_ >= 1.5,
                                    score=(a / b_ - 1) / 0.5, n=len(rest_now), base_n=len(rest_base)))
    res["gaps"].sort(key=lambda g: -g["score"])
    return res


# ---------- wording ----------

BEST = {"new": "a new best (the old one was {old})", "log": "your best since the score log started"}

def answer_lines(F, seed):
    """Candidates for the answer line, best first: (signature, text, numbers used)."""
    out = []
    cmp_ = [f for f in F["scen"] if "rel" in f]
    up = [f for f in cmp_ if f["rel"] >= 0.02]; down = [f for f in cmp_ if f["rel"] <= -0.02]
    n = len(cmp_)
    if not n: summary = ""
    elif len(up) == n: summary = pick(["Above your usual on every scenario.", "Every scenario beat your usual.", "All of it was above your usual."], seed + "sum")[1]
    elif len(down) == n: summary = pick(["Below your usual on every scenario.", "Every scenario came in under your usual.", "All of it was under your usual."], seed + "sum")[1]
    elif not up and not down: summary = pick(["Right at your usual level.", "Scores sat on your usual level.", "A typical play: scores matched your usual."], seed + "sum")[1]
    elif not down: summary = f"Above your usual on {word(len(up))} of {word(n)} scenarios, the rest about level."
    elif not up: summary = f"Below your usual on {word(len(down))} of {word(n)} scenarios, the rest about level."
    elif len(up) >= len(down): summary = f"Above your usual on {word(len(up))} of {word(n)} scenarios, below on {word(len(down))}."
    else: summary = f"Below your usual on {word(len(down))} of {word(n)} scenarios, above on {word(len(up))}."
    for b in sorted(F["bests"], key=lambda b: (b["kind"] != "new", -b["score"])):
        what = BEST[b["kind"]].format(old=b["old"])
        _, t = pick(["{name} hit {score}, {what}.", "{name} reached {score}, {what}.", "Best moment: {name} at {score}, {what}."], seed + "best" + b["scen"])
        nums = 2 if b["kind"] == "new" else 1
        out.append((["best", b["scen"]], (t.format(name=b["name"], score=b["score"], what=what) + " " + summary).strip(), nums))
    for f in sorted(cmp_, key=lambda f: -abs(f["rel"])):
        word_ = "above" if f["rel"] >= 0.02 else "below" if f["rel"] <= -0.02 else "on"
        if word_ == "on":
            _, t = pick(["{name} sat right on your usual: a typical {typ}, against {usual} over the last 14 days.",
                         "{name} was a typical {typ}, the same level as your last 14 days ({usual})."], seed + "on" + f["scen"])
        elif word_ == "above":
            _, t = pick(["{name} stood out: a typical {typ}, against {usual} over the last 14 days.",
                         "{name} led the way, a typical {typ} against your 14-day typical of {usual}.",
                         "Clearest gain: {name}, a typical {typ} against {usual} over the last 14 days."], seed + "up" + f["scen"])
        else:
            _, t = pick(["{name} dropped the most: a typical {typ}, against {usual} over the last 14 days.",
                         "{name} was the weak spot, a typical {typ} against your 14-day typical of {usual}.",
                         "Biggest drop: {name}, a typical {typ} against {usual} over the last 14 days."], seed + "down" + f["scen"])
        out.append((["typ", f["scen"], word_], (summary + " " + t.format(name=f["name"], typ=f["typ"], usual=f["usual"])).strip(), 2))
    if not out:
        out.append((["none"], "Not enough earlier runs of these scenarios in the last 14 days to compare scores.", 0))
    return out


def fmt(metric, v):
    if metric == "overaim": return f"{round(v)}%"
    if metric == "far": return f"{v:.1f}"
    if metric == "input": return f"{v:.1f}"
    return f"{round(v)} seconds"


GAP = {
    "overaim": (["On {name}, {now} of your corrections went past the bot (over-aim), more than {usual}.",
                 "Over-aim rose on {name}: {now} of corrections went through the bot, more than {usual}.",
                 "{name} had more over-aim than {usual}: {now} of corrections went past the bot."],
                "your last 14 days", "your usual {u}"),
    "far": (["While the bot was far away on {name}, you scored {now} points a second, fewer than {usual}.",
             "The far-away part of {name} was the weak spot: {now} points a second, under {usual}.",
             "{name} lost points while the bot was far: {now} a second, below {usual}."],
            "your last 14 days", "your usual {u}"),
    "input": (["On {name}, your aim travelled {now} times as far as the bot, more than {usual}.",
               "{name} took extra mouse movement: your aim covered {now} times the bot's path, more than {usual}.",
               "Your mouse did more work than the bot needed on {name}: {now} times its path, more than {usual}."],
              "your last 14 days", "your usual {u}"),
    "rest_short": (["Your rests between runs were short, about {now}, shorter than {usual}.",
                    "You moved between runs quickly: rests of about {now}, shorter than {usual}."],
                   "your last 14 days", "your usual {u}"),
    "rest_long": (["Your rests between runs ran long, about {now}, longer than {usual}.",
                   "Rests between runs stretched to about {now}, longer than {usual}."],
                  "your last 14 days", "your usual {u}"),
}

CUES = {
    "overaim": ["One thing to try: the over-aim comes from corrections that are bigger than the bot's move. Make them with your wrist and fingers, and make them smaller. It should feel like a nudge that stops on the near edge of the bot, a little late rather than through it.",
                "One thing to try: too much arm in each correction carries the crosshair past the bot. Correct with wrist and fingers only, and smaller than feels natural. It should feel calm and slightly behind, not like a swing.",
                "One thing to try: after each turn, the correction is landing past the bot. Use a smaller input from the wrist and fingers and aim to stop on the bot's near side. It should feel quiet, almost too small."],
    "far": ["One thing to try: while the bot is far, its strafes are small on screen, so arm movement overdoes them. Keep the arm still and use small wrist motions until the bot comes close. It should feel quiet, almost too slow.",
            "One thing to try: far away, the bot only moves a little on screen, and big inputs throw you off it. Track it with small wrist motions and save the arm for close range. It should feel light and patient.",
            "One thing to try: the far part is where small moves matter most. Anchor your arm and follow with the wrist only, in small motions. It should feel like barely moving."],
    "input": ["One thing to try: your aim is moving more than the bot does, and every extra move needs a fix later. Reduce your overall input: follow the bot's path and add nothing on top. It should feel lazy and smooth.",
              "One thing to try: extra mouse movement on top of the bot's path costs points. Move less overall, only as far as the bot goes. It should feel calmer than usual, like you're under-doing it.",
              "One thing to try: the extra input comes from chasing every small change. Let small bot moves go and reduce your input to the bot's real path. It should feel slower and steadier."],
    "rest_short": ["One thing to try: rests this short don't give your hand time to reset. Take about a minute between runs: let go of the mouse and loosen your hand, then start. The next run should feel fresh, not rushed.",
                   "One thing to try: going straight into the next run carries tension over. Rest half a minute to a minute and shake out your hand first. Starting should feel relaxed."],
    "rest_long": ["One thing to try: long gaps between runs let your hand cool down. Keep rests to a minute or two so you stay warm. Each run should feel like it carries on from the last.",
                  "One thing to try: the long pauses cost your warm-up. Start the next run within a minute or two. It should feel like one steady block, not a series of fresh starts."],
}
STEADY = "Nothing slipped clearly against your last 14 days: {what} were all close to usual or better."
MEASURE_WORDS = {"overaim": "over-aim", "far": "far-away scoring", "input": "mouse movement", "rest": "rests"}


def gap_line(g, seed, budget):
    variants, plain, with_u = GAP[g["metric"]]
    _, t = pick(variants, seed + "gap" + g["metric"] + (g["scen"] or ""))
    usual = with_u.format(u=fmt(g["metric"], g["usual"])) if budget >= 2 else plain
    return t.format(name=g["name"], now=fmt(g["metric"], g["now"]), usual=usual), (2 if budget >= 2 else 1)


def entry(key, day, pl, k, F, last):
    seed = key
    lines = [f"Playlist: {pl}" + ("" if k == 1 else f", {['', 'first', 'second', 'third', 'fourth'][k] if k < 5 else str(k) + 'th'} play of the day")]
    # answer
    cands = answer_lines(F, seed)
    sig2, l2, used = next((c for c in cands if c[0] != last.get("l2")), cands[0])
    lines.append(l2)
    # biggest gap, then its cue
    real = [g for g in F["gaps"] if g["real"]]
    sig3, l3, cue_g = None, None, None
    for g in real:
        s = ["gap", g["metric"], g["scen"]]
        if s == last.get("l3"): continue
        l3, n = gap_line(g, seed, MAX_NUMBERS - used); sig3, cue_g = s, g; break
    if l3 is None and real: cue_g = real[0]                  # same gap as last time: line dropped, cue kept
    if l3 is None and not real and F["measured"]:
        what = [MEASURE_WORDS[m] for m in ("overaim", "far", "input", "rest") if m in F["measured"]]
        what = what[0] if len(what) == 1 else ", ".join(what[:-1]) + " and " + what[-1]
        if ["steady"] != last.get("l3"):
            sig3, l3 = ["steady"], STEADY.format(what=what)
    if l3: lines.append(l3)
    cue = (cue_g or (F["gaps"][0] if F["gaps"] else {"metric": "overaim"}))["metric"]
    avoid = last.get("cue", [None, None])[1] if last.get("cue", [None])[0] == cue else None
    ci, ct = pick(CUES[cue], seed + "cue", avoid)
    lines.append(ct)
    return "\n".join(lines), {"l2": sig2, "l3": sig3, "cue": [cue, ci]}


# ---------- main ----------

def load_state():
    try: return json.load(open(STATE, encoding="utf-8"))
    except Exception: return None


def append_journal(day, text):
    with open(P.JOURNAL, "a", encoding="utf-8") as f: f.write(f"\n## {day} {AUTHOR}\n{text}\n")


def run(dry_run=False, day=None, explain=False):
    """Write entries for newly completed plays. Returns the list of (key, text) written (or that would be)."""
    import rest_analysis as R
    importlib.reload(R)
    runs = R.runs
    all_plays = plays(runs)
    attach_scores(runs)
    s = load_state()
    if s is None:                                          # first run: everything before START was reviewed by hand
        s = {"done": {k: "before AimJournal" for k, d, *_ in all_plays if d < START}, "last": {}}
    try:
        import aim_analysis
        if not dry_run: aim_analysis.main()               # make sure the newest runs are in aim_summary.json
    except Exception as e: log(f"aim_analysis skipped: {e}")
    cache = json.load(open(os.path.join(HERE, "aim_summary.json"), encoding="utf-8")) if os.path.exists(os.path.join(HERE, "aim_summary.json")) else {}
    try: tcache = json.load(open(TRAVEL, encoding="utf-8"))
    except Exception: tcache = {}
    out, last = [], dict(s.get("last") or {})
    for key, d, pl, k, xs in all_plays:
        if d < START or key in s["done"] or (day and d != day): continue
        try:
            F = facts(d, pl, xs, runs, cache, tcache)
            text, sigs = entry(key, d, pl, k, F, last)
        except Exception as e:
            log(f"{key} failed: {e!r}"); continue
        if explain:
            print(f"--- {key}  ({xs[0]['end']:%Y-%m-%d %H:%M} to {xs[-1]['end']:%Y-%m-%d %H:%M}, {len(xs)} runs)")
            for f in F["scen"]: print("  scores", f)
            for b in F["bests"]: print("  best", b)
            for g in F["gaps"]: print("  gap", {k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in g.items()})
        out.append((key, d, text)); last = sigs
        if dry_run:
            print(f"## {d} {AUTHOR}\n{text}\n")
        else:
            append_journal(d, text)
            s["done"][key] = dt.datetime.now().isoformat(timespec="minutes"); s["last"] = sigs
            log(f"{key} written")
    if not dry_run:
        os.makedirs(REVIEWS, exist_ok=True)
        json.dump(s, open(STATE, "w", encoding="utf-8"), indent=1)
    try: json.dump(tcache, open(TRAVEL, "w", encoding="utf-8"))
    except Exception: pass
    return out


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv
    run(dry_run="--dry-run" in a, day=a[a.index("--day") + 1] if "--day" in a else None, explain="--explain" in a)
