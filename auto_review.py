# Writes a journal review after each completed playlist.
# A playlist counts as complete when its completed runs for the day reach its full size (and again at 2x, 3x...).
# For each new one: builds a data packet, asks `claude -p` (no tools) for a 10-question QnA and a short entry,
# saves the QnA privately in reviews/ and appends the entry to journal.md. Called by publish.py.
import json, os, statistics as st, subprocess, datetime as dt, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import publish as P

SIZES = {"RANK INT A": 26, "RANK INT B": 26, "ZEUS BUILDER": 16}   # each includes a 2-run warm-up (since 2026-10-08)
REVIEWS = os.path.join(HERE, "reviews")
STATE = os.path.join(REVIEWS, "state.json")
LOG = os.path.join(REVIEWS, "log.txt")
CLAUDE = os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")   # not the npm copy: Store Python cannot see AppData/Roaming
MODEL = "claude-opus-5-5"
TRIES = 3

def log(m):
    os.makedirs(REVIEWS, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(dt.datetime.now().strftime("%Y-%m-%d %H:%M ") + m + "\n")

def load_state():
    try: return json.load(open(STATE, encoding="utf-8"))
    except Exception: return {"done": {}, "tries": {}}

def save_state(s):
    os.makedirs(REVIEWS, exist_ok=True)
    json.dump(s, open(STATE, "w", encoding="utf-8"), indent=1)

def completed_blocks(runs):
    """{(day, playlist, k): [runs]} for every full play of a known playlist."""
    out, by = {}, {}
    for x in runs:
        if x["playlist"] in SIZES: by.setdefault((x["day"], x["playlist"]), []).append(x)
    for (day, pl), xs in by.items():
        n = SIZES[pl]
        for k in range(1, len(xs) // n + 1): out[(day, pl, k)] = xs[(k - 1) * n:k * n]
    return out

def key(day, pl, k): return f"{day}|{pl}|{k}"

def history_before(scen, day):
    """Median, best and count of this scenario's scores before `day`, from the game's statistics."""
    import rest_analysis as R
    base = scen[:-9] if scen.endswith(" - RANKED") else scen
    y, m, d = map(int, day.split("-")); cut = dt.date(y, m, d)
    s = []
    for f in ("Ranked", "Normal", "Custom"):
        for name in {base, scen}:
            j = R.load(os.path.join(P.TRAINER_STATS, f, name + ".json"))
            if not j: continue
            for dd, sc in zip(j.get("Date", []), j.get("Score", [])):
                dd_, mm_, yy_ = map(int, dd.split("/"))
                if dt.date(yy_, mm_, dd_) < cut: s.append(sc)
    return {"runs_before": len(s), "median_before": round(st.median(s)) if s else None, "best_before": round(max(s)) if s else None}

def packet(day, pl, k, xs):
    ranks = {r["name"]: r for r in P.ranks()}
    hist = {h.get("name"): h for h in P.history()} if isinstance(P.history(), list) else {}
    entries = [e for e in P.journal() if e["date"] == day]
    scen = {}
    for x in xs:
        s = scen.setdefault(x["scen"], {"scores": [], "rests_before_s": []})
        s["scores"].append(x.get("score")); s["rests_before_s"].append(x["rest"])
    for name, s in scen.items():
        s.update(history_before(name, day))
        r = ranks.get(name[:-9] if name.endswith(" - RANKED") else name) or ranks.get(name)
        if r: s.update({"master3": r.get("master3"), "best_last_14_days": r.get("best_14d"), "baseline_before_plan": (hist.get(r["name"]) or {}).get("baseline")})
    day_stats = next((d for d in P.sessions_by_day(P.read_log()) if d["date"] == day), {})
    return {
        "playlist": pl, "play_number_today": k, "date": day,
        "first_run": xs[0]["start"].strftime("%H:%M") if xs[0]["start"] else None, "last_run": xs[-1]["end"].strftime("%H:%M"),
        "runs": [{"time": x["end"].strftime("%H:%M"), "scenario": x["scen"], "score": x.get("score"), "rest_before_s": x["rest"]} for x in xs],
        "scenarios": scen,
        "day": {k2: day_stats.get(k2) for k2 in ("runs", "restarts", "rest_median_s", "breaks", "playlists")},
        "ryans_notes_today": [e["text"] for e in entries if e["author"].lower() != "claude"],
        "earlier_claude_reviews_today": [e["text"] for e in entries if e["author"].lower() == "claude"],
        "plan": "Goal: Master 3 on 6 Intermediate ranked tracking scenarios. Daily: RANK INT A or B (24 runs), optional ZEUS BUILDER (14 runs, 7 drills x2, a trial for ZEUS TRACK until the Oct 25 check-in) and the main playlist again. Plan started 2026-10-07.",
        "known_findings": "Rest data so far: first attempt on each scenario scores about 3% below usual, first run after a 15+ minute break about 6% below (warm-up). Short rests (20 s-2 min) inside a scenario look slightly better than none, tentative.",
    }

PROMPT = """You are Ryan's aim-training coach. Ryan plays Aimbeast (an aim trainer). He just finished a playlist. Using ONLY the data below, run a 10-question QnA about this playlist, then write a short public journal entry.

QnA rules:
- Ask and answer 10 questions from different angles: results vs his past and Master 3, warm-up and rest, conditions from his notes, technique, what to change next time, risks of over-reading small samples.
- At least 1 question must start with "Falsifying:" and attack your own leading conclusion.
- Answers 1-3 sentences. Cite only numbers present in the data. If something is a guess, write (guess). With 1-2 runs per scenario, say the sample is small.

Journal entry rules (it is published on his public website):
- Plain, friendly English, no jargon, scenario names in normal capitalisation.
- Exactly these lines, each one to three sentences:
  Playlist: <playlist name> (<number of runs> runs, <first>-<last>)
  What happened: ...
  Conditions: ... (from his notes or the data: gaps, interruptions, time of day; if nothing is known, say so)
  Next time: ... (one or two concrete things)
- Don't repeat earlier reviews from today word for word.

Output format, exactly:
=== QNA ===
<the QnA in markdown: a "# QnA: ..." heading, then numbered questions with bold questions>
=== JOURNAL ===
<the journal entry lines>

DATA:
"""

def ask(pk):
    os.makedirs(REVIEWS, exist_ok=True)
    p = subprocess.run([CLAUDE, "-p", "--model", MODEL, "--tools", "", "--strict-mcp-config", "--no-session-persistence"],
                       input=PROMPT + json.dumps(pk, indent=1, default=str), capture_output=True, text=True, encoding="utf-8",
                       timeout=300, cwd=REVIEWS, creationflags=0x08000000)
    out = p.stdout
    if p.returncode != 0 or "=== JOURNAL ===" not in out: raise RuntimeError((p.stderr or out)[-400:])
    qna, journal = out.split("=== JOURNAL ===", 1)
    qna = qna.replace("=== QNA ===", "").strip(); journal = journal.strip()
    lines = [l for l in journal.splitlines() if l.strip()]
    if not lines or not lines[0].startswith("Playlist:"): raise RuntimeError("bad journal entry: " + journal[:200])
    return qna, "\n".join(lines)

def append_journal(day, text):
    with open(P.JOURNAL, "a", encoding="utf-8") as f: f.write(f"\n## {day} Claude\n{text}\n")

def run(only=None, mark_existing=False):
    """Review newly completed playlists. Returns True if journal.md changed."""
    import importlib, rest_analysis as R
    importlib.reload(R)
    blocks = completed_blocks(R.runs)
    s = load_state(); changed = False
    for (day, pl, k), xs in sorted(blocks.items(), key=lambda kv: kv[1][-1]["end"]):
        kk = key(day, pl, k)
        if kk in s["done"]: continue
        if mark_existing and kk != only:
            s["done"][kk] = "skipped (before auto reviews)"; continue
        if only and kk != only: continue
        if s["tries"].get(kk, 0) >= TRIES: continue
        try:
            qna, entry = ask(packet(day, pl, k, xs))
        except Exception as e:
            s["tries"][kk] = s["tries"].get(kk, 0) + 1; log(f"{kk} failed ({s['tries'][kk]}/{TRIES}): {e}"); continue
        name = f"QnA - {day} {pl}{'' if k == 1 else ' ' + str(k)}.md"
        open(os.path.join(REVIEWS, name), "w", encoding="utf-8").write(qna + "\n\n## Journal entry\n" + entry + "\n")
        append_journal(day, entry); changed = True
        s["done"][kk] = dt.datetime.now().isoformat(timespec="minutes"); log(f"{kk} reviewed -> {name}")
    save_state(s)
    return changed

if __name__ == "__main__":
    # first setup: python auto_review.py --init "2026-10-07|ZEUS BUILDER|1"
    if "--init" in sys.argv: print(run(only=sys.argv[sys.argv.index("--init") + 1], mark_existing=True))
    else: print(run())
