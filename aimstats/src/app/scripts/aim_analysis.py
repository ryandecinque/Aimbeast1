# Turns AimRecorder run files into per-run numbers: time on target, reaction time to direction changes,
# overshoot rate, long losses, left-right vs up-down misses, M1 held, and start vs end of the run.
# Tracking scenarios only: switching, multi-bot and clicking runs are marked "skipped" (not analysed yet).
# Input: data/runs/*.csv(.gz) (AimStats' copies)   Output: data/aim_summary.json (one entry per run, cached)
# Usage: python aim_analysis.py [--all] [--print N]
import csv, glob, gzip, json, math, os, statistics as st, sys, time, datetime as dt
import config
RUNS = config.RUNS
OUT = os.path.join(config.DATA, "aim_summary.json")
LOSS = 0.5            # seconds off target that count as "lost the target"

def thin60(rows):
    """Recorder phase 6 samples clicking runs at 120 a second. Tracking numbers assume even 60-a-second steps,
    so keep only rows at least ~1/60 s apart (unchanged for 60-a-second files)."""
    ts = [float(r["t"]) for r in rows]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    if not gaps or sum(g < 0.0095 for g in gaps) < 0.2 * len(gaps): return rows      # a normal 60-a-second file
    out, last = [], None
    for r in rows:
        t = float(r["t"])
        if last is None or t - last >= 1 / 60 - 0.002: out.append(r); last = t
    return out

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

def height_source(rows, ids):
    """Recorder phase 5 also saves the visible body parts ("m" body, "s" sphere). Flying bots move those, not the root.
    Pick the source whose up-down error at hit moments is smallest; "" = the bot's root (older files)."""
    best, best_err = "", None
    for src in ("", "m", "s"):
        errs = []
        for i in range(1, len(rows)):
            r, q = rows[i], rows[i - 1]
            if int(r["hits"]) <= int(q["hits"]): continue
            for k in range(1, 9):
                z = r.get(f"b{k}_{src}z") if src else r.get(f"b{k}_z")
                if not z or (r.get(f"b{k}_id") or str(k)) not in ids: continue
                x, y = float(r[f"b{k}_{src}x"] if src else r[f"b{k}_x"]), float(r[f"b{k}_{src}y"] if src else r[f"b{k}_y"])
                dx, dy, dz = x - float(r["cam_x"]), y - float(r["cam_y"]), float(z) - float(r["cam_z"])
                errs.append(abs(math.degrees(math.atan2(dz, math.hypot(dx, dy))) - float(r["pitch"])))
        if len(errs) >= 20:
            e = st.median(errs)
            if best_err is None or e < best_err: best, best_err = src, e
    return best

def angles(r, ids=None, src=""):
    """Aim error to the nearest bot, in degrees: (left-right, up-down, distance). None if no bot."""
    best = None
    cx, cy, cz = float(r["cam_x"]), float(r["cam_y"]), float(r["cam_z"])
    yaw, pitch = float(r["yaw"]), float(r["pitch"])
    for i in range(1, 9):              # up to 8 bots (older files have 3)
        x = r.get(f"b{i}_x")
        if not x or x == "0.0": continue
        if ids is not None and (r.get(f"b{i}_id") or str(i)) not in ids: continue
        if src and r.get(f"b{i}_{src}z"):
            dx, dy, dz = float(r[f"b{i}_{src}x"]) - cx, float(r[f"b{i}_{src}y"]) - cy, float(r[f"b{i}_{src}z"]) - cz
        else:
            dx, dy, dz = float(x) - cx, float(r[f"b{i}_y"]) - cy, float(r[f"b{i}_z"]) - cz
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d < 1: continue
        by = math.degrees(math.atan2(dy, dx)); bp = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        ex = (by - yaw + 180) % 360 - 180; ey = bp - pitch
        if best is None or ex * ex + ey * ey < best[0] ** 2 + best[1] ** 2: best = (ex, ey, d)
    return best

def analyse(path, size=None):
    rows = thin60(list(csv.DictReader(config.open_run(path))))
    if len(rows) < 600: return None
    ids = moving_ids(rows)
    live = lambda r: sum(1 for i in range(1, 9) if r.get(f"b{i}_x") not in (None, "", "0.0") and (r.get(f"b{i}_id") or str(i)) in ids)
    if len(ids) > 3 or max(live(r) for r in rows) > 2:     # switching / multi-bot: tracking numbers don't apply
        return {"skipped": "switching or multi-bot scenario (not analysed yet)"}
    src = height_source(rows, ids)
    s = []
    for r in rows:
        a = angles(r, ids, src)
        if a: s.append(dict(t=float(r["t"]), ex=a[0], ey=a[1], d=a[2], hits=int(r["hits"]), m1=r["m1"] == "1"))
    if len(s) < 600: return None
    # skip the countdown: start from the first hit (or 3 s in)
    resets = [i for i in range(1, len(s)) if s[i]["hits"] < s[i - 1]["hits"]]      # run starts when the game zeroes the counter
    first_hit = resets[-1] if resets else next((i for i in range(1, len(s)) if s[i]["hits"] > s[i - 1]["hits"]), None)
    s = s[first_hit if first_hit is not None else 180:]
    if len(s) < 600: return None
    if s[-1]["hits"] - s[0]["hits"] < 10: return None          # no real run (paused, or left in the menu)
    if sum(x["m1"] for x in s) < 0.5 * len(s):      # fire button mostly up during the run: a clicking scenario
        return {"skipped": "clicking scenario (not analysed yet)"}
    # target size from the data itself: aim error at the moments a hit landed (90th percentile)
    for x in s:                                      # error converted to distance at the bot: same bot size near or far
        x["ex0"] = x["ex"]
        x["ex"] = math.degrees(math.atan(math.tan(math.radians(x["ex"])) * x["d"] / 1000))
        x["ey"] = math.degrees(math.atan(math.tan(math.radians(x["ey"])) * x["d"] / 1000))
    # in some scenarios (Air Track, Sphere S) the bot's recorded height isn't where it is on screen: at hit moments the
    # up-down error is far bigger than the left-right one. Then only left-right is measured.
    hi_ = [i for i in range(1, len(s)) if s[i]["hits"] > s[i - 1]["hits"]]
    lr_only = bool(hi_) and abs(st.median(s[i]["ey"] for i in hi_)) > 4 * sorted(abs(s[i]["ex"]) for i in hi_)[int(.9 * len(hi_))]
    if lr_only:
        for x in s: x["ey"] = 0.0
    hx = sorted(abs(s[i]["ex"]) for i in range(1, len(s)) if s[i]["hits"] > s[i - 1]["hits"])
    hy = sorted(abs(s[i]["ey"]) for i in range(1, len(s)) if s[i]["hits"] > s[i - 1]["hits"])
    if len(hx) < 20: return None
    wx, wy = size if size else (hx[int(.9 * len(hx))], hy[int(.9 * len(hy))])
    if lr_only: wy = max(wy, 1.0)
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
        updown_pct=None if lr_only else round(100 * sum(e["dur"] for e in real if e["axis"] == "ud") / offt), left_right_only=lr_only,
        m1_held=pct([x["m1"] for x in s]), hits=s[-1]["hits"] - s[0]["hits"], seconds=round(s[-1]["t"] - s[0]["t"], 1),
        target_deg=[round(wx, 2), round(wy, 2)], by_distance=bands)

def run_name(path):
    b = os.path.basename(path).replace(".csv.gz", "").replace(".csv", "")
    d, t, scen = b[:10], b[11:17], b[18:]
    return d, f"{t[:2]}:{t[2:4]}:{t[4:]}", scen.replace("_", "").strip()

def update(full=False):
    """Analyse runs not in the cache yet. Returns the file names that are new or changed."""
    cache = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) and not full else {}
    for p in sorted(glob.glob(RUNS + "/*.csv")):          # compress AimStats' own copies older than a week (5-10x smaller)
        if time.time() - os.path.getmtime(p) > 7 * 86400:
            with open(p, "rb") as a, gzip.open(p + ".gz", "wb") as b: b.write(a.read())
            os.remove(p)
    files = sorted(glob.glob(RUNS + "/*.csv") + glob.glob(RUNS + "/*.csv.gz"))
    todo = [p for p in files if os.path.basename(p).replace(".gz", "") not in cache]
    changed = set()
    for p in todo:                                   # pass 1: each run's own target-size estimate
        k = os.path.basename(p).replace(".gz", "")
        try: res = analyse(p)
        except Exception as e: res = {"error": str(e)}
        d, t, scen = run_name(p)
        cache[k] = dict(date=d, time=t, scenario=scen, **(res or {"skipped": "too short"}))
        changed.add(k)
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
                if res and "on_target" in res:
                    cache[k] = dict(date=v["date"], time=v["time"], scenario=sc, pooled=[round(x, 2) for x in pooled[sc]], **res)
                    changed.add(k)
            except Exception: pass
    os.makedirs(config.DATA, exist_ok=True)
    tmp = OUT + ".tmp"
    json.dump(cache, open(tmp, "w", encoding="utf-8"), indent=1); os.replace(tmp, OUT)
    return changed


def main():
    update("--all" in sys.argv)
    cache = json.load(open(OUT, encoding="utf-8"))
    if "--print" in sys.argv:
        n = int(sys.argv[sys.argv.index("--print") + 1])
        for k in sorted(cache)[-n:]: print(json.dumps(cache[k]))

if __name__ == "__main__":
    main()
