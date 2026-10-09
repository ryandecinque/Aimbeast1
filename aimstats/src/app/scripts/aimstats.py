# AimStats: a small web server on this PC only (127.0.0.1) plus a watcher. Started by "Open AimStats.bat".
# The watcher copies new AimRecorder recordings out of the game folder (it never changes or deletes anything there),
# analyses them, makes a swing-past GIF per scenario once a session goes quiet, checks for PBs, and writes
# data/page.json, which the page reloads every few seconds. Videos are opt-in: the player ticks scenarios in the
# Videos panel (or sets them to Always), and each gets its best-run clip plus a "+20%" side-by-side companion.
# Nothing is sent anywhere.
# Usage: python aimstats.py [--no-browser] [--once]
import datetime as dt, glob, http.server, json, os, queue, re, shutil, socket, statistics as st, sys, threading, time, traceback
import urllib.parse, urllib.request, webbrowser
import config, aim_analysis, pb_events, rests, scenario_profile, model_run

PORTS = [int(os.environ["AIMSTATS_PORT"])] if os.environ.get("AIMSTATS_PORT") else range(8765, 8776)   # AIMSTATS_PORT: for testing
WEB = os.path.join(config.APP, "web")
MEDIA = {"clips": os.path.join(config.DATA, "clips"), "gifs": os.path.join(config.DATA, "gifs"),
         "videos": os.path.join(config.DATA, "videos"), "pb": os.path.join(config.DATA, "pb")}
PAGE = os.path.join(config.DATA, "page.json")
WATCH = os.path.join(config.DATA, "watch.json")
LOG = os.path.join(config.DATA, "aimstats.log")
QUIET = 120                 # seconds without a new run before swing-past GIFs are made
status = {"busy": "", "started": time.time(), "last_check": None}
jobs = {}                   # videos being made (target-score and best-run): id -> state
job_lock = threading.Lock()
work_q = queue.Queue()      # one render at a time
CLIPS = os.path.join(config.DATA, "clips.json")         # best-run clips made: "scenario|date" -> details
SETTINGS = os.path.join(config.DATA, "settings.json")   # {"ticked": [...], "always": [...]}; nothing is Always at first
clip_lock = threading.Lock()
BEST = {}                   # (scenario, date) -> (score, run file), refreshed by every watcher pass
FACTOR = 1.2                # the side-by-side companion's model run: 20% better
MODEL_OK = {}               # scenario -> (ok, reason): model videos only where the bot ignores the player's hits
MODEL_NOTE = {}             # scenario -> plain-words notice for the page


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
    except OSError: pass


def load_json(p, default):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return default


def save_json(p, obj):
    tmp = p + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), indent=1); os.replace(tmp, p)


def run_path(k):
    p = os.path.join(config.RUNS, k)
    return p if os.path.exists(p) else (p + ".gz" if os.path.exists(p + ".gz") else None)


def copy_new():
    """Copy recordings the recorder finished into data/runs. Read-only towards the game folder."""
    if not config.GAME_RUNS or not os.path.isdir(config.GAME_RUNS): return 0
    os.makedirs(config.RUNS, exist_ok=True)
    n = 0
    for p in glob.glob(os.path.join(config.GAME_RUNS, "*.csv")):
        name = os.path.basename(p); dest = os.path.join(config.RUNS, name)
        if os.path.exists(dest) or os.path.exists(dest + ".gz"): continue
        try:
            if time.time() - os.path.getmtime(p) < 5: continue          # still being written
            shutil.copy2(p, dest + ".part"); os.replace(dest + ".part", dest); n += 1
        except OSError as e: log(f"could not copy {name}: {e}")
    return n


def title_of(scen):
    """Display name and whether it's ranked. The statistics file keeps characters the recorder's file name lost ('%')."""
    ranked = scen.upper().endswith("- RANKED")
    base = re.sub(r"\s*-\s*RANKED$", "", scen, flags=re.I).strip()
    f = pb_events.stats_file(scen)
    if f and config.key(os.path.basename(f)[:-5]) == config.key(base): base = os.path.basename(f)[:-5]
    return " ".join(base.split()), ranked


def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


SCALE = {}                  # scenario -> game points per recorded hit (1, 5, ...), None if the scores don't line up


def near(score, expect): return abs(score - expect) <= max(3, 0.03 * score)


def find_scale(runs, hist):
    """Points per hit for a scenario: the ratio (game score / recorded hits) that lines up the most recordings with a
    same-day score in the game's statistics. Some scenarios give 5 points a hit. None if fewer than half line up."""
    by_day = {}
    for d, x in hist: by_day.setdefault(d, []).append(x)
    cands = sorted({round(x / v["hits"], 2) for v in runs if v["hits"] for x in by_day.get(v["date"], [])})
    best = None
    for r in cands:
        n = sum(any(near(x, v["hits"] * r) for x in by_day.get(v["date"], [])) for v in runs)
        if best is None or n > best[0] or (n == best[0] and abs(r - 1) < abs(best[1] - 1)): best = (n, r)
    return best[1] if best and best[0] >= max(1, 0.5 * len(runs)) else None


def score_for(v, hist):
    """The game's own score for a recorded run: the same-day score in the statistics file that matches the recorded
    hits times the scenario's points per hit. Recorded hits if the scenario's scores don't line up (shown as "hits")."""
    r = SCALE.get(v["scenario"])
    if not r: return v["hits"]
    same = [x for d, x in hist if d == v["date"] and near(x, v["hits"] * r)]
    return min(same, key=lambda x: abs(x - v["hits"] * r)) if same else round(v["hits"] * r)


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 1) if xs else None


def recorder_warning(last_run):
    """If the practice log shows finished runs well after the newest recording, the recorder may have stopped
    working (for example after an Aimbeast update)."""
    p = config.PRACTICE_LOG
    if not p or not os.path.exists(p): return None
    last_end = None
    try:
        for line in open(p, encoding="utf-8", errors="replace"):
            parts = line.split(",")
            if len(parts) > 4 and parts[1] == "end" and parts[-2].strip() == "true": last_end = parts[0]
    except OSError: return None
    if not last_end: return None
    lr = last_run.replace("_", " ") if last_run else "2000-01-01 00:00:00"
    t_end = dt.datetime.strptime(last_end, "%Y-%m-%d %H:%M:%S")
    t_run = dt.datetime.strptime(lr[:10] + " " + lr[11:13] + ":" + lr[13:15] + ":" + lr[15:17], "%Y-%m-%d %H:%M:%S") if last_run else dt.datetime(2000, 1, 1)
    if t_end - t_run > dt.timedelta(hours=3):
        when = t_run.strftime("%d %b") if last_run else "you installed AimStats"
        return f"No recordings since {when}, but you've played since then. The recorder may need an update (Aimbeast may have changed)."
    return None


def work(first=False):
    """One pass of the watcher."""
    new = copy_new()
    if new: log(f"{new} new recording(s)")
    watch = load_json(WATCH, {"clips": {}, "gifs": {}, "last_new": 0})
    if new: watch["last_new"] = time.time()
    if new or first or not os.path.exists(aim_analysis.OUT):
        status["busy"] = "Analysing new runs"
        aim_analysis.update()
    summ = load_json(aim_analysis.OUT, {})
    track = {k: v for k, v in summ.items() if "on_target" in v}
    scen_names = sorted({v["scenario"] for v in track.values()})
    hists = {}
    for s in scen_names:          # the game's statistics, only where its score is the hit count the recorder sees
        h = pb_events.history(s); mine = [v for v in track.values() if v["scenario"] == s]
        SCALE[s] = find_scale(mine, h) if mine else None
        if s not in MODEL_OK: MODEL_OK[s] = model_run.model_check(s)
        hists[s] = h if SCALE[s] else []

    by_sd = {}
    for k, v in track.items():
        by_sd.setdefault((v["scenario"], v["date"]), []).append((score_for(v, hists[v["scenario"]]), k, v))
    BEST.clear(); BEST.update({sd: max(runs, key=lambda x: x[0])[:2] for sd, runs in by_sd.items()})
    # videos are opt-in: only scenarios set to Always get them on their own, once the session has gone quiet
    if time.time() - watch.get("last_new", 0) > QUIET:
        always = set(load_json(SETTINGS, {}).get("always", [])); clips = load_json(CLIPS, {})
        today = dt.date.today().isoformat()
        for (scen, date), (score, k) in list(BEST.items()):
            if scen in always and date == today and clips.get(f"{scen}|{date}", {}).get("run") != k: queue_videos(scen)

    # swing-past GIF per scenario and day, once the session has gone quiet
    if time.time() - watch.get("last_new", 0) > QUIET:
        for (scen, date), runs in sorted(by_sd.items(), key=lambda x: x[0][1]):
            tag = f"{scen}|{date}"
            if watch["gifs"].get(tag, {}).get("n") == len(runs): continue
            title, _ = title_of(scen)
            status["busy"] = f"Finding an over-aim moment in {title}"
            out = os.path.join(MEDIA["gifs"], f"{slug(scen)}-{date}.gif")
            os.makedirs(MEDIA["gifs"], exist_ok=True)
            done = {"n": len(runs)}
            for _, k, v in sorted(runs, key=lambda x: x[2]["time"], reverse=True)[:3]:     # newest run that has one
                p = run_path(k)
                if not p: continue
                ok, msg = config.run_script("weak_moment_auto.py", p, out)
                if ok:
                    m = re.search(r"YOU=(\d+) SMOOTH=(\d+) T=([\d.]+)", msg)
                    done.update(run=k, gif=os.path.basename(out), png=os.path.basename(out)[:-4] + ".png", time=v["time"][:5],
                                you=int(m.group(1)) if m else None, smooth=int(m.group(2)) if m else None, at=float(m.group(3)) if m else None)
                    break
            watch["gifs"][tag] = done
            save_json(WATCH, watch)

    # PBs and best weeks
    stills = {}
    clips = load_json(CLIPS, {})
    for tag, c in clips.items():
        if c.get("png"): stills[tag.split("|")[0]] = os.path.join(MEDIA["clips"], c["png"])
    pbs = pb_events.update({s: title_of(s)[0] for s in scen_names}, stills)
    save_json(WATCH, watch)
    status["busy"] = "Reading rest times"
    rest_info, practice = rests.summary()              # None, None when there's no practice_log.csv
    build_page(summ, track, hists, watch, pbs, rest_info, practice, clips)
    status["busy"] = ""
    status["last_check"] = time.time()


def best_line(scen, ranked, h, rows):
    """Best score and how far back it reaches. Ranked: the game's own ranked record if it has one (it can be out of
    date, so the higher of it and the statistics). Otherwise 'best since' the first day the statistics file has."""
    known = max([x for _, x in h] + [r["score"] for r in rows])
    if ranked:
        off = scenario_profile.official_best(scen)
        if off and SCALE.get(scen): return dict(score=max(off[0], known), since=None)
    first = min([d for d, _ in h] + [r["date"] for r in rows])
    return dict(score=known, since=first)


def rest_of(rest_info, k):
    """Rest before a recorded run, from the practice log: (kind, seconds) or None."""
    try: when = dt.datetime.strptime(k[:17], "%Y-%m-%d_%H%M%S")
    except ValueError: return None
    return rests.rest_before(rest_info, when)


def build_page(summ, track, hists, watch, pbs, rest_info=None, practice=None, clips=None):
    clips = clips or {}
    today = dt.date.today()
    scen_out = []
    for scen in sorted({v["scenario"] for v in track.values()}):
        title, ranked = title_of(scen)
        h = hists.get(scen) or []
        runs = sorted(((k, v) for k, v in track.items() if v["scenario"] == scen), key=lambda kv: kv[0])
        rows = [dict(file=k, date=v["date"], time=v["time"][:5], score=score_for(v, h), on_target=v["on_target"],
                     swing_past=v.get("overshoot_pct"), reaction_ms=v.get("reaction_ms"),
                     by_distance={b: x["points_per_sec"] for b, x in (v.get("by_distance") or {}).items()},
                     first20=v.get("first20"), last20=v.get("last20"),
                     pps=round(v["hits"] / v["seconds"], 1) if v.get("seconds") else None,
                     rest=rest_of(rest_info, k)) for k, v in runs]
        aim_days = {}                                              # typical aim numbers per practice day
        for r in rows: aim_days.setdefault(r["date"], []).append(r)
        aim_trend = [dict(date=d, on_target=med(r["on_target"] for r in rs), swing_past=med(r["swing_past"] for r in rs),
                          pps=med(r["pps"] for r in rs), runs=len(rs)) for d, rs in sorted(aim_days.items())][-30:]
        last_day = rows[-1]["date"]
        day_rows = [r for r in rows if r["date"] == last_day]
        dist = {}
        for b in ("far", "mid", "close"):
            xs = [r["by_distance"][b] for r in day_rows if b in r["by_distance"]]
            if xs: dist[b] = round(st.median(xs), 1)
        # week to week, from every run in the game's statistics (recorded or not); recorded runs if there's no file
        scores = h or [(r["date"], r["score"]) for r in rows]
        wk = lambda a, b: [s for d, s in scores if (today - dt.timedelta(days=b)).isoformat() < d <= (today - dt.timedelta(days=a)).isoformat()]
        this_w, last_w = wk(0, 7), wk(7, 14)
        daily = {}
        for d, s in scores: daily.setdefault(d, []).append(s)
        trend = [{"date": d, "median": round(st.median(v)), "best": max(v), "runs": len(v)} for d, v in sorted(daily.items())][-30:]
        tag = next((t for t in ([f"{scen}|{last_day}"] + sorted(clips, reverse=True)) if t in clips and t.startswith(scen + "|")
                    and clips[t].get("mp4")), None)
        gif_tag = next((t for t in sorted(watch["gifs"], reverse=True) if t.startswith(scen + "|") and watch["gifs"][t].get("gif")), None)
        scen_out.append(dict(
            name=scen, title=title, ranked=ranked, last_day=last_day, runs_recorded=len(rows),
            last_day_numbers=dict(runs=len(day_rows), best=max(r["score"] for r in day_rows), typical=round(st.median(r["score"] for r in day_rows)),
                                  on_target=med(r["on_target"] for r in day_rows), swing_past=med(r["swing_past"] for r in day_rows),
                                  reaction_ms=med(r["reaction_ms"] for r in day_rows), by_distance=dist),
            week=dict(this=round(st.median(this_w)) if this_w else None, this_runs=len(this_w),
                      last=round(st.median(last_w)) if last_w else None, last_runs=len(last_w)),
            best=best_line(scen, ranked, h, rows), unit="score" if SCALE.get(scen) else "hits",
            model=MODEL_NOTE.setdefault(scen, model_run.model_notice(scen)),
            trend=trend, aim_trend=aim_trend,
            clip=dict(clips[tag], date=tag.split("|")[1]) if tag else None, clip_today=f"{scen}|{last_day}" in clips,
            swing=dict(watch["gifs"][gif_tag], date=gif_tag.split("|")[1]) if gif_tag else None,
            runs=rows[-40:][::-1]))
    scen_out.sort(key=lambda s: s["last_day"] + max(r["time"] for r in s["runs"] if r["date"] == s["last_day"]), reverse=True)
    skipped = {}
    for v in summ.values():
        if "skipped" in v and "not analysed" in v["skipped"]:
            kind = "clicking" if "clicking" in v["skipped"] else "switching"
            skipped.setdefault(kind, set()).add(v["scenario"])
    last_run = max(summ.keys())[:17] if summ else None
    now = dt.datetime.now(dt.timezone.utc)
    recent = [e for e in pbs["events"] if now - dt.datetime.strptime(e["seen_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc) < dt.timedelta(hours=24)]
    today = dt.date.today().isoformat()
    played_today = [dict(name=s_["name"], title=s_["title"], ranked=s_["ranked"], runs=s_["last_day_numbers"]["runs"],
                         best=s_["last_day_numbers"]["best"], unit=s_["unit"], done=s_["clip_today"])
                    for s_ in scen_out if s_["last_day"] == today]
    page = dict(game_found=bool(config.GAME), today=played_today,
                recorder_installed=bool(config.MODS and os.path.isdir(os.path.join(config.MODS, "AimRecorder"))),
                last_recording=last_run, warning=recorder_warning(last_run), scenarios=scen_out,
                skipped={k: sorted(v) for k, v in skipped.items()}, events_recent=recent[::-1], events_all=pbs["events"][::-1][:30],
                practice=practice)
    old = load_json(PAGE, {})
    old.pop("updated", None)
    if old != json.loads(json.dumps(page)):                       # only rewrite when something changed
        page["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_json(PAGE, page)


def watcher():
    first = True
    while True:
        try: work(first)
        except Exception: log("watcher error:\n" + traceback.format_exc()); status["busy"] = ""
        first = False
        time.sleep(10)


def queue_videos(scen):
    """Queue the latest day's best-run clip and its +20% companion for a scenario, once."""
    with job_lock:
        if any(j["kind"] == "videos" and j["scenario"] == scen and j["status"] in ("queued", "running") for j in jobs.values()): return None
        jid = str(int(time.time() * 1000)) + str(len(jobs))
        jobs[jid] = dict(id=jid, kind="videos", scenario=scen, status="queued", stage="Waiting", pct=0)
    work_q.put(jid)
    return jobs[jid]


def video_job(j):
    scen = j["scenario"]
    days = sorted(d for s_, d in BEST if s_ == scen)
    if not days: return j.update(status="failed", error="No recorded runs for this scenario.")
    date = days[-1]; score, k = BEST[(scen, date)]
    title, _ = title_of(scen)
    os.makedirs(MEDIA["clips"], exist_ok=True)
    out = os.path.join(MEDIA["clips"], f"{slug(scen)}-{date}.mp4")
    j.update(status="running", stage="Best-run clip", pct=10)
    ok, msg = config.run_script("best_run_gif.py", run_path(k), score, f"{title}, best run ({score})", out)
    m = re.search(r"WINDOW (\d+) (\d+)", msg)
    if not ok or not m:
        log(f"best-run clip failed for {k}: {msg[-300:]}"); return j.update(status="failed", error="The clip couldn't be made from this run.")
    entry = {"run": k, "score": score, "mp4": os.path.basename(out), "png": os.path.basename(out)[:-4] + ".png"}
    ok_m, why = MODEL_OK.get(scen) or model_run.model_check(scen)
    if not ok_m:                                   # the bot reacts to hits: no model run, just the clip
        entry["model_na"] = why
        with clip_lock:
            clips = load_json(CLIPS, {}); clips[f"{scen}|{date}"] = entry
            housekeeping(clips, scen); save_json(CLIPS, clips)
        return j.update(status="done", stage="Done", pct=100, date=date)
    j.update(stage="Side by side, 20% better", pct=55)
    mout = out[:-4] + "-model.mp4"
    ok, msg = config.run_script("model_clip.py", run_path(k), score, m.group(1), m.group(2), mout, FACTOR)
    mm = re.search(r'\{"model_score": (\d+), "target": (\d+), "reached": (true|false), "moves": (true|false)\}', msg)
    if ok and mm:
        entry["model"] = {"mp4": os.path.basename(mout), "png": os.path.basename(mout)[:-4] + ".png", "model_score": int(mm.group(1)),
                          "target": int(mm.group(2)), "reached": mm.group(3) == "true", "moves": mm.group(4) == "true"}
    else: log(f"model clip failed for {k}: {msg[-300:]}")
    with clip_lock:
        clips = load_json(CLIPS, {}); clips[f"{scen}|{date}"] = entry
        housekeeping(clips, scen); save_json(CLIPS, clips)
    j.update(status="done", stage="Done", pct=100, date=date)


def housekeeping(clips, scen):
    """Per scenario keep only the latest day's clip and the best run's clip; delete the others (AimStats' own files)."""
    tags = [t for t in clips if t.startswith(scen + "|") and clips[t].get("mp4")]
    if len(tags) <= 2: return
    keep = {max(tags), max(tags, key=lambda t: clips[t].get("score", 0))}
    for t in tags:
        if t in keep: continue
        c = clips.pop(t)
        for f in (c.get("mp4"), c.get("png"), (c.get("model") or {}).get("mp4"), (c.get("model") or {}).get("png")):
            if f and os.path.basename(f) == f:
                try: os.remove(os.path.join(MEDIA["clips"], f))
                except OSError: pass


def worker():
    while True:
        jid = work_q.get(); j = jobs.get(jid)
        try:
            if j["kind"] == "videos": video_job(j)
            else: target_job(jid, j["run"], j["target"])
        except Exception as e:
            log("video error:\n" + traceback.format_exc()); j.update(status="failed", error=str(e))


def target_job(jid, k, target):
    j = jobs[jid]
    try:
        summ = load_json(aim_analysis.OUT, {}); v = summ[k]
        score = score_for(v, pb_events.history(v["scenario"]))
        os.makedirs(MEDIA["videos"], exist_ok=True)
        prefix = os.path.join(MEDIA["videos"], f"{slug(v['scenario'])}-{k[:17]}-{target}")
        prog = os.path.join(config.DATA, f"job-{jid}.json")
        j.update(status="running", stage="Starting", pct=1)
        def poll():
            while j["status"] == "running":
                p = load_json(prog, None)
                if p: j.update(stage=p["stage"], pct=p["pct"])
                time.sleep(1)
        threading.Thread(target=poll, daemon=True).start()
        ok, msg = config.run_script("target_video.py", run_path(k), score, target, prefix, env={"AIMSTATS_PROGRESS": prog}, timeout=1800)
        m = re.search(r'\{"model_score": (\d+)', msg)
        if ok:
            j.update(status="done", pct=100, stage="Done", solo=os.path.basename(prefix) + "_solo.mp4", side=os.path.basename(prefix) + "_side.mp4",
                     model_score=int(m.group(1)) if m else None, real_score=score)
        else:
            log("target video failed: " + msg[-400:]); j.update(status="failed", error="The video couldn't be made from this run. Try another run.")
        try: os.remove(prog)
        except OSError: pass
    except Exception as e:
        log("target video error:\n" + traceback.format_exc()); j.update(status="failed", error=str(e))


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)): body = json.dumps(body).encode()
        elif isinstance(body, str): body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(body)

    def file(self, path, ctype):
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else max(0, size - int(b)); end = int(b) if a and b else size - 1
        with open(path, "rb") as f:
            f.seek(start); body = f.read(end - start + 1)
        extra = {"Accept-Ranges": "bytes"}
        if rng: extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self.send(206 if rng else 200, body, ctype, extra)

    def do_HEAD(self): self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); p = u.path
        if p in ("/", "/index.html"): return self.file(os.path.join(WEB, "index.html"), "text/html; charset=utf-8")
        if p == "/api/ping": return self.send(200, {"aimstats": True})
        if p == "/api/page":
            page = load_json(PAGE, {})
            with job_lock: page["jobs"] = list(jobs.values())
            page["busy"] = status["busy"]; page["last_check"] = status["last_check"]
            page["settings"] = load_json(SETTINGS, {"ticked": [], "always": []})
            return self.send(200, page)
        m = re.match(r"^/media/(clips|gifs|videos|pb)/([^/\\]+)$", p)
        if m:
            name = urllib.parse.unquote(m.group(2))
            path = os.path.join(MEDIA[m.group(1)], name)
            if ".." in name or not os.path.isfile(path): return self.send(404, {"error": "not found"})
            ctype = {".mp4": "video/mp4", ".gif": "image/gif", ".png": "image/png"}.get(os.path.splitext(name)[1].lower(), "application/octet-stream")
            return self.file(path, ctype)
        self.send(404, {"error": "not found"})

    def body(self):
        try: return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        except Exception: return None

    def do_POST(self):
        b = self.body()
        if b is None: return self.send(400, {"error": "Bad request."})
        known = {s_ for s_, _ in BEST}
        if self.path == "/api/target":
            try: k, target = str(b["run"]), int(b["target"])
            except Exception: return self.send(400, {"error": "Pick a run and type a score."})
            if not (1 <= target <= 100000): return self.send(400, {"error": "Type a score between 1 and 100000."})
            v = load_json(aim_analysis.OUT, {}).get(k, {})
            if not run_path(k) or "on_target" not in v:
                return self.send(400, {"error": "That run isn't available."})
            if not (MODEL_OK.get(v["scenario"]) or model_run.model_check(v["scenario"]))[0]:
                return self.send(400, {"error": model_run.NOT_AVAILABLE})
            with job_lock:
                if any(j.get("kind") == "target" and j["status"] in ("queued", "running") for j in jobs.values()):
                    return self.send(409, {"error": "A target-score video is already being made. Wait for it to finish."})
                jid = str(int(time.time() * 1000))
                jobs[jid] = dict(id=jid, kind="target", run=k, target=target, status="queued", stage="Waiting", pct=0)
            work_q.put(jid)
            return self.send(200, jobs[jid])
        if self.path == "/api/videos":                         # Videos panel: remember the ticks, make the videos
            ticked = [x for x in b.get("scenarios", []) if x in known]
            st_ = load_json(SETTINGS, {}); st_["ticked"] = ticked; save_json(SETTINGS, st_)
            return self.send(200, {"queued": [j for j in (queue_videos(x) for x in ticked) if j]})
        if self.path == "/api/settings":                       # Always on/off for one scenario, or the ticks
            st_ = load_json(SETTINGS, {})
            if "ticked" in b: st_["ticked"] = [x for x in b["ticked"] if x in known]
            if "scenario" in b and b["scenario"] in known:
                al = set(st_.get("always", []))
                if b.get("always"): al.add(b["scenario"])
                else: al.discard(b["scenario"])
                st_["always"] = sorted(al)
            save_json(SETTINGS, st_)
            return self.send(200, st_)
        if self.path == "/api/clip":                           # one-off "Make clip" on a card
            if b.get("scenario") not in known: return self.send(400, {"error": "Unknown scenario."})
            return self.send(200, queue_videos(b["scenario"]) or {"status": "queued"})
        self.send(404, {"error": "not found"})


def already_running():
    for port in PORTS:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1) as r:
                if json.load(r).get("aimstats"): return port
        except Exception: pass
    return None


def main():
    os.makedirs(config.DATA, exist_ok=True)
    port = already_running()
    if port:
        log(f"AimStats is already running, opening the page (port {port})")
        if "--no-browser" not in sys.argv: webbrowser.open(f"http://127.0.0.1:{port}/")
        return
    if "--once" in sys.argv: work(True); return
    srv = None
    for port in PORTS:
        try: srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler); break
        except OSError: continue
    if not srv: log("no free port between 8765 and 8775"); return
    log(f"AimStats running at http://127.0.0.1:{port}/  (game folder: {config.GAME or 'not found'})")
    log("Close this window to stop AimStats.")
    if not os.path.exists(CLIPS):                              # clips made by older versions
        old = load_json(WATCH, {}).get("clips", {})
        save_json(CLIPS, {t: c for t, c in old.items() if c.get("mp4")})
    threading.Thread(target=watcher, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    if "--no-browser" not in sys.argv: webbrowser.open(f"http://127.0.0.1:{port}/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
