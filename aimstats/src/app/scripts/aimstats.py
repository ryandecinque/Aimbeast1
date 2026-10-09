# AimStats: a small web server on this PC only (127.0.0.1) plus a watcher. Started by "Open AimStats.bat".
# The watcher copies new AimRecorder recordings out of the game folder (it never changes or deletes anything there),
# analyses them, makes a best-run clip per scenario and day, a swing-past GIF once a session goes quiet, checks for
# PBs, and writes data/page.json, which the page reloads every few seconds. Nothing is sent anywhere.
# Usage: python aimstats.py [--no-browser] [--once]
import datetime as dt, glob, http.server, json, os, re, shutil, socket, statistics as st, sys, threading, time, traceback
import urllib.parse, urllib.request, webbrowser
import config, aim_analysis, pb_events

PORTS = range(8765, 8776)
WEB = os.path.join(config.APP, "web")
MEDIA = {"clips": os.path.join(config.DATA, "clips"), "gifs": os.path.join(config.DATA, "gifs"),
         "videos": os.path.join(config.DATA, "videos"), "pb": os.path.join(config.DATA, "pb")}
PAGE = os.path.join(config.DATA, "page.json")
WATCH = os.path.join(config.DATA, "watch.json")
LOG = os.path.join(config.DATA, "aimstats.log")
QUIET = 120                 # seconds without a new run before swing-past GIFs are made
status = {"busy": "", "started": time.time(), "last_check": None}
jobs = {}                   # target-score videos: id -> state
job_lock = threading.Lock()


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


def score_for(v, hist):
    """The game's own score for a recorded run: a same-day score in the statistics file within 3 of the recorded
    hits (the closest one), else the recorded hits."""
    same = [s for d, s in hist if d == v["date"]]
    near = [s for s in same if abs(s - v["hits"]) <= 3]
    return min(near, key=lambda s: abs(s - v["hits"])) if near else v["hits"]


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
        agree = sum(any(d == v["date"] and abs(x - v["hits"]) <= 3 for d, x in h) for v in mine)
        hists[s] = h if mine and agree >= 0.5 * len(mine) else []

    # best-run clip per scenario and day
    by_sd = {}
    for k, v in track.items():
        by_sd.setdefault((v["scenario"], v["date"]), []).append((score_for(v, hists[v["scenario"]]), k, v))
    for (scen, date), runs in sorted(by_sd.items(), key=lambda x: x[0][1]):
        score, k, v = max(runs, key=lambda x: x[0])
        tag = f"{scen}|{date}"
        if watch["clips"].get(tag, {}).get("run") == k: continue
        p = run_path(k)
        if not p: continue
        title, _ = title_of(scen)
        out = os.path.join(MEDIA["clips"], f"{slug(scen)}-{date}.mp4")
        os.makedirs(MEDIA["clips"], exist_ok=True)
        status["busy"] = f"Making the best-run clip for {title}"
        ok, msg = config.run_script("best_run_gif.py", p, score, f"{title}, best run ({score})", out)
        if ok: watch["clips"][tag] = {"run": k, "score": score, "mp4": os.path.basename(out), "png": os.path.basename(out)[:-4] + ".png"}
        else:
            log(f"best-run clip failed for {k}: {msg[-300:]}"); watch["clips"][tag] = {"run": k, "failed": True}
        save_json(WATCH, watch)

    # swing-past GIF per scenario and day, once the session has gone quiet
    if time.time() - watch.get("last_new", 0) > QUIET:
        for (scen, date), runs in sorted(by_sd.items(), key=lambda x: x[0][1]):
            tag = f"{scen}|{date}"
            if watch["gifs"].get(tag, {}).get("n") == len(runs): continue
            title, _ = title_of(scen)
            status["busy"] = f"Finding a swing-past moment in {title}"
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
    for tag, c in watch["clips"].items():
        if c.get("png"): stills[tag.split("|")[0]] = os.path.join(MEDIA["clips"], c["png"])
    pbs = pb_events.update({s: title_of(s)[0] for s in scen_names}, stills)
    save_json(WATCH, watch)
    build_page(summ, track, hists, watch, pbs)
    status["busy"] = ""
    status["last_check"] = time.time()


def build_page(summ, track, hists, watch, pbs):
    today = dt.date.today()
    scen_out = []
    for scen in sorted({v["scenario"] for v in track.values()}):
        title, ranked = title_of(scen)
        h = hists.get(scen) or []
        runs = sorted(((k, v) for k, v in track.items() if v["scenario"] == scen), key=lambda kv: kv[0])
        rows = [dict(file=k, date=v["date"], time=v["time"][:5], score=score_for(v, h), on_target=v["on_target"],
                     swing_past=v.get("overshoot_pct"), reaction_ms=v.get("reaction_ms"),
                     by_distance={b: x["points_per_sec"] for b, x in (v.get("by_distance") or {}).items()},
                     first20=v.get("first20"), last20=v.get("last20")) for k, v in runs]
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
        clip = watch["clips"].get(f"{scen}|{last_day}") or next((watch["clips"][t] for t in sorted(watch["clips"], reverse=True)
                                                                  if t.startswith(scen + "|") and watch["clips"][t].get("mp4")), None)
        clip_date = last_day if watch["clips"].get(f"{scen}|{last_day}") else None
        gif_tag = next((t for t in sorted(watch["gifs"], reverse=True) if t.startswith(scen + "|") and watch["gifs"][t].get("gif")), None)
        scen_out.append(dict(
            name=scen, title=title, ranked=ranked, last_day=last_day, runs_recorded=len(rows),
            last_day_numbers=dict(runs=len(day_rows), best=max(r["score"] for r in day_rows), typical=round(st.median(r["score"] for r in day_rows)),
                                  on_target=med(r["on_target"] for r in day_rows), swing_past=med(r["swing_past"] for r in day_rows),
                                  reaction_ms=med(r["reaction_ms"] for r in day_rows), by_distance=dist),
            week=dict(this=round(st.median(this_w)) if this_w else None, this_runs=len(this_w),
                      last=round(st.median(last_w)) if last_w else None, last_runs=len(last_w)),
            all_time_best=max([s for _, s in scores] + [r["score"] for r in rows]),
            trend=trend,
            clip=dict(clip, date=clip_date or (clip or {}).get("date")) if clip and clip.get("mp4") else None,
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
    page = dict(game_found=bool(config.GAME),
                recorder_installed=bool(config.MODS and os.path.isdir(os.path.join(config.MODS, "AimRecorder"))),
                last_recording=last_run, warning=recorder_warning(last_run), scenarios=scen_out,
                skipped={k: sorted(v) for k, v in skipped.items()}, events_recent=recent[::-1], events_all=pbs["events"][::-1][:30])
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
            return self.send(200, page)
        m = re.match(r"^/media/(clips|gifs|videos|pb)/([^/\\]+)$", p)
        if m:
            name = urllib.parse.unquote(m.group(2))
            path = os.path.join(MEDIA[m.group(1)], name)
            if ".." in name or not os.path.isfile(path): return self.send(404, {"error": "not found"})
            ctype = {".mp4": "video/mp4", ".gif": "image/gif", ".png": "image/png"}.get(os.path.splitext(name)[1].lower(), "application/octet-stream")
            return self.file(path, ctype)
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/target": return self.send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            k, target = str(body["run"]), int(body["target"])
        except Exception: return self.send(400, {"error": "Pick a run and type a score."})
        if not (1 <= target <= 100000): return self.send(400, {"error": "Type a score between 1 and 100000."})
        if not run_path(k) or "on_target" not in load_json(aim_analysis.OUT, {}).get(k, {}):
            return self.send(400, {"error": "That run isn't available."})
        with job_lock:
            if any(j["status"] in ("queued", "running") for j in jobs.values()):
                return self.send(409, {"error": "A video is already being made. Wait for it to finish."})
            jid = str(int(time.time() * 1000))
            jobs[jid] = dict(id=jid, run=k, target=target, status="queued", stage="Waiting", pct=0)
        threading.Thread(target=target_job, args=(jid, k, target), daemon=True).start()
        self.send(200, jobs[jid])


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
    threading.Thread(target=watcher, daemon=True).start()
    if "--no-browser" not in sys.argv: webbrowser.open(f"http://127.0.0.1:{port}/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
