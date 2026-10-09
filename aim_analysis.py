# Turns AimRecorder run files into per-run numbers: time on target, reaction time to direction changes,
# overshoot rate, long losses, left-right vs up-down misses, M1 held, and start vs end of the run.
# Input: ue4ss/Mods/AimRecorder/runs/*.csv   Output: aim_summary.json (one entry per run, cached)
# Usage: python aim_analysis.py [--all] [--print N]
import csv, glob, gzip, json, math, os, statistics as st, sys, time, datetime as dt
RUNS = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods/AimRecorder/runs"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "aim_summary.json")
LOSS = 0.5            # seconds off target that count as "lost the target"

def moving_ids(rows):
    """Bots that actually move during the run. Bots left over from earlier scenarios stay in the level standing still."""
    span = {}
    for r in rows:
        for i in range(1, 9):
            x, k = r.get(f"b{i}_x"), r.get(f"b{i}_id") or str(i)
            if not x or x == "0.0": continue
            p = (float(x), float(r[f"b{i}_y"]), float(r[f"b{i}_z"]))
            lo, hi = span.get(k, (p, p))
            span[k] = (tuple(map(min, lo, p)), tuple(map(max, hi, p)))
    return {k for k, (lo, hi) in span.items() if max(b - a for a, b in zip(lo, hi)) > 50}

def angles(r, ids=None):
    """Aim error to the nearest bot, in degrees: (left-right, up-down, distance). None if no bot."""
    best = None
    cx, cy, cz = float(r["cam_x"]), float(r["cam_y"]), float(r["cam_z"])
    yaw, pitch = float(r["yaw"]), float(r["pitch"])
    for i in range(1, 9):              # up to 8 bots (older files have 3)
        x = r.get(f"b{i}_x")
        if not x or x == "0.0": continue
        if ids is not None and (r.get(f"b{i}_id") or str(i)) not in ids: continue
        dx, dy, dz = float(x) - cx, float(r[f"b{i}_y"]) - cy, float(r[f"b{i}_z"]) - cz
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d < 1: continue
        by = math.degrees(math.atan2(dy, dx)); bp = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        ex = (by - yaw + 180) % 360 - 180; ey = bp - pitch
        if best is None or ex * ex + ey * ey < best[0] ** 2 + best[1] ** 2: best = (ex, ey, d)
    return best

def analyse(path, size=None):
    rows = list(csv.DictReader((gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8"))))
    ids = moving_ids(rows)
    live = lambda r: sum(1 for i in range(1, 9) if r.get(f"b{i}_x") not in (None, "", "0.0") and (r.get(f"b{i}_id") or str(i)) in ids)
    if len(ids) > 3 or max(live(r) for r in rows) > 2:     # switching / multi-bot: tracking numbers don't apply
        return {"skipped": "switching or multi-bot scenario (not analysed yet)"}
    s = []
    for r in rows:
        a = angles(r, ids)
        if a: s.append(dict(t=float(r["t"]), ex=a[0], ey=a[1], d=a[2], hits=int(r["hits"]), m1=r["m1"] == "1"))
    if len(s) < 600: return None
    # skip the countdown: start from the first hit (or 3 s in)
    resets = [i for i in range(1, len(s)) if s[i]["hits"] < s[i - 1]["hits"]]      # run starts when the game zeroes the counter
    first_hit = resets[-1] if resets else next((i for i in range(1, len(s)) if s[i]["hits"] > s[i - 1]["hits"]), None)
    s = s[first_hit if first_hit is not None else 180:]
    if len(s) < 600: return None
    # target size from the data itself: aim error at the moments a hit landed (90th percentile)
    for x in s:                                      # error converted to distance at the bot: same bot size near or far
        x["ex0"] = x["ex"]
        x["ex"] = math.degrees(math.atan(math.tan(math.radians(x["ex"])) * x["d"] / 1000))
        x["ey"] = math.degrees(math.atan(math.tan(math.radians(x["ey"])) * x["d"] / 1000))
    hx = sorted(abs(s[i]["ex"]) for i in range(1, len(s)) if s[i]["hits"] > s[i - 1]["hits"])
    hy = sorted(abs(s[i]["ey"]) for i in range(1, len(s)) if s[i]["hits"] > s[i - 1]["hits"])
    if len(hx) < 20: return None
    wx, wy = size if size else (hx[int(.9 * len(hx))], hy[int(.9 * len(hy))])
    on = [abs(x["ex"]) <= wx and abs(x["ey"]) <= wy for x in s]
    dt_ = (s[-1]["t"] - s[0]["t"]) / (len(s) - 1)
    # off-target stretches
    eps, cur = [], None
    for i, x in enumerate(s):
        if not on[i]:
            axis = "lr" if abs(x["ex"]) / wx >= abs(x["ey"]) / wy else "ud"
            side = (1 if x["ex"] > 0 else -1) if axis == "lr" else (1 if x["ey"] > 0 else -1)
            if cur is None: cur = dict(a=i, b=i, axis=axis, side=side)
            else: cur["b"] = i
        elif cur is not None: eps.append(cur); cur = None
    if cur: eps.append(cur)
    for e in eps: e["dur"] = (e["b"] - e["a"] + 1) * dt_
    real = [e for e in eps if e["dur"] >= 0.1]
    over = 0
    for k in range(1, len(real)):
        p, e = real[k - 1], real[k]
        if p["axis"] == e["axis"] == "lr" and p["side"] == -e["side"] and (e["a"] - p["b"]) * dt_ <= 0.2: over += 1
    # reaction: bot's left-right motion seen from the camera reverses -> how long until the aim turns the same way
    # bot angular position = aim yaw + error; aim yaw = stored yaw
    rows_t = s
    by = [None] * len(s)
    yaw0 = None
    # rebuild absolute angles: bot yaw = yaw + ex (unwrapped)
    absyaw = []
    acc = 0.0; prev = None
    for r, x in zip(rows[len(rows) - len(s):], s):
        y = float(r["yaw"])
        if prev is not None:
            d = (y - prev + 180) % 360 - 180; acc += d
        else: acc = y
        prev = y; absyaw.append(acc)
    boty = [absyaw[i] + s[i]["ex0"] for i in range(len(s))]   # true angles, not the distance-scaled error
    def vel(a, i, w=3): return (a[min(i + w, len(a) - 1)] - a[max(i - w, 0)]) / ((min(i + w, len(a) - 1) - max(i - w, 0)) * dt_)
    bv = [vel(boty, i) for i in range(len(s))]; av = [vel(absyaw, i) for i in range(len(s))]
    reacts = []
    i = 5
    while i < len(s) - 5:
        k = 6   # 0.1 s either side: the bot was clearly moving one way, then clearly the other
        if (bv[i - 1] > 0) != (bv[i] > 0) and i + k < len(s) and abs(bv[i - k]) > 15 and abs(bv[i + k]) > 15 and (bv[i - k] > 0) != (bv[i + k] > 0):
            want = 1 if bv[i + k] > 0 else -1
            j = i
            while j < min(len(s), i + int(0.6 / dt_)) and not (av[j] * want > 0 and abs(av[j]) > 0.5 * abs(bv[i + k])): j += 1
            if j < min(len(s), i + int(0.6 / dt_)): reacts.append((j - i) * dt_ * 1000)
            i += int(0.15 / dt_)
        else: i += 1
    # split by how far away the bot is (Zeus rounds start far and end close): share of time, on target, points per second
    bands = {}
    for name, lo, hi in (("far", 1500, 1e9), ("mid", 800, 1500), ("close", 0, 800)):
        idx = [i for i in range(1, len(s)) if lo <= s[i]["d"] < hi]
        if len(idx) < 60: continue
        pts = sum(max(0, s[i]["hits"] - s[i - 1]["hits"]) for i in idx)
        bands[name] = dict(seconds=round(len(idx) * dt_, 1), on_target=round(100 * sum(on[i] for i in idx) / len(idx), 1),
                           points_per_sec=round(pts / (len(idx) * dt_), 1))
    n = len(s); third = n // 3
    pct = lambda a: round(100 * sum(a) / max(len(a), 1), 1)
    offt = sum(e["dur"] for e in real) or 1
    return dict(
        on_target=pct(on), first20=pct(on[:int(20 / dt_)]), last20=pct(on[-int(20 / dt_):]),
        reaction_ms=round(st.median(reacts)) if reacts else None, direction_changes=len(reacts),
        overshoot_pct=round(100 * over / max(len(real), 1)), misses=len(real),
        long_losses=sum(e["dur"] >= LOSS for e in real),
        updown_pct=round(100 * sum(e["dur"] for e in real if e["axis"] == "ud") / offt),
        m1_held=pct([x["m1"] for x in s]), hits=s[-1]["hits"] - s[0]["hits"], seconds=round(s[-1]["t"] - s[0]["t"], 1),
        target_deg=[round(wx, 2), round(wy, 2)], by_distance=bands)

def run_name(path):
    b = os.path.basename(path).replace(".csv.gz", "").replace(".csv", "")
    d, t, scen = b[:10], b[11:17], b[18:]
    return d, f"{t[:2]}:{t[2:4]}:{t[4:]}", scen.replace("_", "").strip()

def by_day():
    """{date: [{scenario, runs, on_target, reaction_ms, overshoot_pct}]} for the website, typical (median) values."""
    cache = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    days = {}
    for v in cache.values():
        if "on_target" not in v: continue
        days.setdefault(v["date"], {}).setdefault(v["scenario"], []).append(v)
    out = {}
    for d, sc in days.items():
        rows = []
        for name, vs in sorted(sc.items()):
            med = lambda k: (round(st.median([x[k] for x in vs if x.get(k) is not None])) if any(x.get(k) is not None for x in vs) else None)
            bands = {}
            for b in ("far", "mid", "close"):
                xs = [x["by_distance"][b]["points_per_sec"] for x in vs if b in (x.get("by_distance") or {})]
                if xs: bands[b] = round(st.median(xs), 1)
            rows.append(dict(scenario=name, runs=len(vs), on_target=med("on_target"), reaction_ms=med("reaction_ms"), overshoot_pct=med("overshoot_pct"), pps_by_distance=bands))
        out[d] = rows
    return out

def main():
    cache = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) and "--all" not in sys.argv else {}
    for p in sorted(glob.glob(RUNS + "/*.csv")):          # compress runs older than a week (about 5-10x smaller)
        if time.time() - os.path.getmtime(p) > 7 * 86400:
            with open(p, "rb") as a, gzip.open(p + ".gz", "wb") as b: b.write(a.read())
            os.remove(p)
    files = sorted(glob.glob(RUNS + "/*.csv") + glob.glob(RUNS + "/*.csv.gz"))
    todo = [p for p in files if os.path.basename(p).replace(".gz", "") not in cache]
    for p in todo:                                   # pass 1: each run's own target-size estimate
        k = os.path.basename(p).replace(".gz", "")
        try: res = analyse(p)
        except Exception as e: res = {"error": str(e)}
        d, t, scen = run_name(p)
        cache[k] = dict(date=d, time=t, scenario=scen, **(res or {"skipped": "too short"}))
    # pass 2: one target size per scenario (median of all its runs), so runs are measured the same way
    sizes = {}
    for v in cache.values():
        if "target_deg" in v: sizes.setdefault(v["scenario"], []).append(v["target_deg"])
    pooled = {sc: (st.median(a for a, b in L), st.median(b for a, b in L)) for sc, L in sizes.items()}
    for p in files:
        k = os.path.basename(p).replace(".gz", ""); v = cache.get(k, {})
        sc = v.get("scenario")
        if sc in pooled and v.get("pooled") != [round(x, 2) for x in pooled[sc]]:
            try:
                res = analyse(p, pooled[sc])
                if res: cache[k] = dict(date=v["date"], time=v["time"], scenario=sc, pooled=[round(x, 2) for x in pooled[sc]], **res)
            except Exception: pass
    json.dump(cache, open(OUT, "w", encoding="utf-8"), indent=1)
    if "--print" in sys.argv:
        n = int(sys.argv[sys.argv.index("--print") + 1])
        for k in sorted(cache)[-n:]: print(json.dumps(cache[k]))

if __name__ == "__main__":
    main()
