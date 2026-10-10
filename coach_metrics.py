# Coach-style measurements for a tracking scenario, taken from Corporate Serf's VOD-review principles (Oct 2026):
#   - phases: the run split by bot distance (far / mid / close). A run isn't one thing; each phase needs its own technique.
#   - strafe width on screen per phase: small widths = wrist/fingertips, wide = arm (the technique follows on-screen distance).
#   - predicting vs reacting: did the aim reverse before a human could have reacted (< 60 ms after the bot)?
#   - wrong guesses: the aim reversed but the bot didn't, and the points lost in the next half second.
#   - input economy: how much the aim travelled compared with the bot (over 1 = extra input, "playing unsafe").
# Usage: python coach_metrics.py "<scenario name as in the run file names>" [more names...]
import csv, glob, json, math, statistics as st, sys
from aim_analysis import moving_ids, thin60
RUNS = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods/AimRecorder/runs"
PHASES = (("far", 1500, 1e9), ("mid", 800, 1500), ("close", 0, 800))

def phase(d): return next(p for p, lo, hi in PHASES if lo <= d < hi)

def series(path):
    rows = thin60(list(csv.DictReader(open(path, encoding="utf-8"))))
    ids = moving_ids(rows); hits = [int(r["hits"]) for r in rows]
    rs = [i for i in range(1, len(rows)) if hits[i] < hits[i - 1]]; s0 = rs[-1] if rs else 0
    Y, B, D, H = [], [], [], []; acc = prev = None
    for r in rows[s0:]:
        k = next((j for j in range(1, 9) if r.get(f"b{j}_x") not in (None, "", "0.0") and (r.get(f"b{j}_id") or str(j)) in ids), None)
        y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y; H.append(int(r["hits"]))
        if k is None: Y.append(None); B.append(None); D.append(None); continue
        dx, dy = float(r[f"b{k}_x"]) - float(r["cam_x"]), float(r[f"b{k}_y"]) - float(r["cam_y"])
        b = math.degrees(math.atan2(dy, dx)); B.append(acc + ((b - acc + 180) % 360 - 180)); Y.append(acc); D.append(math.hypot(dx, dy))
    return Y, B, D, H

def analyse(files):
    out = {p: dict(turns=0, predicted=0, aim_rev=0, wrong=0, widths=[], aim_travel=0.0, bot_travel=0.0) for p, _, _ in PHASES}
    after_wrong, after_ok, secs = [], [], 0.0
    for f in files:
        Y, B, D, H = series(f); n = len(Y); secs += n / 60
        if n < 600: continue
        def vel(A, i, w=3):
            if i < w or i >= n - w or A[i - w] is None or A[i + w] is None: return None
            return (A[i + w] - A[i - w]) / (2 * w / 60)
        bv = [vel(B, i) for i in range(n)]; av = [vel(Y, i) for i in range(n)]
        for i in range(1, n):
            if Y[i] is not None and Y[i - 1] is not None and D[i] is not None:
                o = out[phase(D[i])]; o["aim_travel"] += abs(Y[i] - Y[i - 1]); o["bot_travel"] += abs(B[i] - B[i - 1])
        last = None
        for i in range(8, n - 24):
            if None in (bv[i - 1], bv[i], bv[i - 6], bv[i + 6]) or D[i] is None: continue
            if (bv[i - 1] > 0) != (bv[i] > 0) and abs(bv[i - 6]) > 4 and abs(bv[i + 6]) > 4 and (bv[i - 6] > 0) != (bv[i + 6] > 0):
                o = out[phase(D[i])]; o["turns"] += 1
                if last is not None and B[last] is not None: o["widths"].append(abs(B[i] - B[last]))
                last = i
                nd = 1 if bv[i + 6] > 0 else -1
                j = next((k for k in range(i - 18, i + 24) if av[k] is not None and av[k - 1] is not None and av[k] * nd > 0 and av[k - 1] * nd <= 0), None)
                if j is not None and (j - i) / 60 * 1000 < 60: o["predicted"] += 1
        for i in range(10, n - 30):
            if None in (av[i - 1], av[i], av[i - 6], av[i + 6], bv[i]) or D[i] is None: continue
            if (av[i - 1] > 0) != (av[i] > 0) and abs(av[i - 6]) > 4 and abs(av[i + 6]) > 4 and (av[i - 6] > 0) != (av[i + 6] > 0):
                o = out[phase(D[i])]; o["aim_rev"] += 1
                ok = any(bv[k] is not None and bv[k - 1] is not None and (bv[k] > 0) != (bv[k - 1] > 0) for k in range(i - 15, i + 4))
                (after_ok if ok else after_wrong).append(H[min(n - 1, i + 30)] - H[i])
                if not ok: o["wrong"] += 1
    res = {"runs": len(files), "minutes": round(secs / 60, 1), "phases": {}}
    for p, o in out.items():
        res["phases"][p] = dict(
            strafe_width_on_screen_deg=round(st.median(o["widths"]), 1) if o["widths"] else None,
            predicted_turns_pct=round(100 * o["predicted"] / max(1, o["turns"])),
            wrong_guess_pct=round(100 * o["wrong"] / max(1, o["aim_rev"])),
            extra_input_ratio=round(o["aim_travel"] / max(1e-9, o["bot_travel"]), 2))
    res["wrong_guesses_per_min"] = round(sum(o["wrong"] for o in out.values()) / max(1e-9, secs) * 60, 1)
    res["points_half_second_after_wrong_guess"] = round(st.mean(after_wrong), 2) if after_wrong else None
    res["points_half_second_after_correct_turn"] = round(st.mean(after_ok), 2) if after_ok else None
    return res

if __name__ == "__main__":
    names = sys.argv[1:] or ["ZEUS TRACK EVO - NOBLINK"]
    files = sorted(f for nm in names for f in glob.glob(f"{RUNS}/*_{nm}.csv"))
    print(json.dumps(analyse(files), indent=1))
