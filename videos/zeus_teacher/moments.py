# Picks one clear, typical moment per weakness from tonight's Zeus runs and writes motion/src/data.json:
# per-frame (60 a second) aim, bot and the smooth version (same 133 ms reaction), plus the round chart and the
# top-down bot path. Read-only on the game folder.
# Usage: python moments.py
import json, math, os, statistics as st
from zeus_data import Run, zeus_runs, DT

HERE = os.path.dirname(os.path.abspath(__file__))
TONIGHT = [Run(f) for f in zeus_runs("2026-10-10_21")]

def prep(r):
    if hasattr(r, "av"): return
    r.av = [r.vel(r.YAW, i, 3) for i in range(r.n)]; r.bv = [r.vel(r.BY, i, 3) for i in range(r.n)]
    r.apv = [r.vel(r.PIT, i, 3) for i in range(r.n)]; r.bpv = [r.vel(r.CZ, i, 3) for i in range(r.n)]
    r.wdeg = [None if r.D[i] is None else math.degrees(math.atan(r.HW / r.D[i])) for i in range(r.n)]
    r.hdeg = [None if r.D[i] is None else math.degrees(math.atan(r.HH / r.D[i])) for i in range(r.n)]

def on_at(r, k, ay, ap):
    return r.BY[k] is not None and abs(r.BY[k] - ay) <= r.wdeg[k] and abs(r.CZ[k] - ap) <= r.hdeg[k]

def simulate(r, a, b, w, delay=8):
    """Smooth follower (weak_moment_auto.py): same reaction delay, eases in, aims where the bot will be."""
    sy, sp, svy, svp = r.YAW[a], r.PIT[a], r.av[a] or 0, r.apv[a] or 0
    out = []
    for k in range(a, b):
        j = k - delay
        if r.BY[j] is not None and r.bv[j] is not None and r.bpv[j] is not None:
            ty, tp = r.BY[j] + r.bv[j] * delay * DT, r.CZ[j] + r.bpv[j] * delay * DT
            ay = w * w * (ty - sy) - 2 * w * svy; ap = w * w * (tp - sp) - 2 * w * svp
            svy += ay * DT; svp += ap * DT
        sy += svy * DT; sp += svp * DT
        out.append((sy, sp))
    return out

def best_smooth(r, a, b):
    res = []
    for w in (24, 30, 36, 42):
        s = simulate(r, a, b, w)
        res.append((sum(on_at(r, k, *s[k - a]) for k in range(a, b)) / (b - a), w, s))
    return max(res, key=lambda x: x[0])

def real_on(r, a, b): return sum(r.on[k] for k in range(a, b)) / (b - a)

def live(r, i):
    for a, b in r.rounds:
        if a + 60 <= i < min(b, a + int(19.5 / DT)) - 60: return (a, b)
    return None

# ---------------------------------------------------------------- 1. after it turns, you keep going
c1 = []
for r in TONIGHT:
    prep(r); i = 60
    while i < r.n - 120:
        ok = live(r, i) and all(r.bv[k] is not None and r.av[k] is not None and r.ex[k] is not None for k in range(i - 40, i + 70))
        if ok and (r.bv[i - 1] > 0) != (r.bv[i] > 0) and abs(r.bv[i - 8]) > 0.6 * abs(r.bv[i - 8]) and (r.bv[i - 8] > 0) != (r.bv[i + 8] > 0) \
                and min(abs(r.bv[i - 8]), abs(r.bv[i + 8])) > 25 and r.D[i] < 800:
            v0 = 1 if r.bv[i - 8] > 0 else -1
            # wrong side = past the bot on the side it was heading before it turned, in half-widths
            past = [((r.YAW[k] - r.BY[k]) * v0) / r.wdeg[k] for k in range(i, i + 30)]
            pk = max(range(30), key=lambda k: past[k])
            before_on = sum(r.on[k] for k in range(i - 20, i)) >= 12
            if before_on and past[pk] > 1.6 and max(abs(r.ey[k]) for k in range(i - 20, i + 40)) < 1.0 and (r.av[i + 6] or 0) * v0 > 0:
                a, b = i - 36, i + 60
                on_s, w, _ = best_smooth(r, a, b)
                c1.append(dict(r=r, i=i, a=a, b=b, past=past[pk], peak=i + pk, you=real_on(r, a, b), smooth=on_s, w=w))
                i += 30; continue
        i += 1
print("turn moments:", len(c1))
# typical, not the worst: run-through size near the median of the clean candidates where the smooth version stays on
good = [c for c in c1 if c["smooth"] >= 0.8]
med = st.median(c["past"] for c in good)
M1 = min(good, key=lambda c: abs(c["past"] - med) - 0.5 * (c["smooth"] - c["you"]))
print(f"  chose {M1['r'].name} t={M1['r'].T[M1['i']] - M1['r'].T[M1['r'].start]:.1f}s past={M1['past']:.1f} (median {med:.1f}) you={M1['you']:.0%} smooth={M1['smooth']:.0%}")

# ---------------------------------------------------------------- 2. behind: sprint, then brake
c2 = []
for r in TONIGHT:
    i = 60
    while i < r.n - 120:
        ok = live(r, i) and all(r.bv[k] is not None and r.av[k] is not None and r.ex[k] is not None for k in range(i - 40, i + 70))
        if not ok or r.D[i] > 1500 or r.D[i] < 700: i += 1; continue
        v = 1 if r.bv[i] > 0 else -1
        seg = range(i, i + 24)                                   # 0.4 s with the bot going one way
        if all(r.bv[k] * v > 0.6 * abs(r.bv[i]) for k in seg) and abs(r.bv[i]) > 12:
            ratio = [r.av[k] * v / abs(r.bv[k]) for k in seg]
            k1 = max(range(12), key=lambda k: ratio[k])
            if ratio[k1] > 2.0 and min(ratio[k1:]) < 0.5:
                k2 = k1 + min(range(len(ratio) - k1), key=lambda k: ratio[k1 + k])
                behind_after = (r.BY[i + k2 + 6] - r.YAW[i + k2 + 6]) * v / r.wdeg[i + k2 + 6]
                if behind_after > 1.0 and max(abs(r.ey[k]) for k in range(i - 20, i + 40)) < 1.0:
                    a, b = i - 36, i + 60
                    on_s, w, _ = best_smooth(r, a, b)
                    c2.append(dict(r=r, i=i, a=a, b=b, sprint=i + k1, brake=i + k2, top=ratio[k1], low=min(ratio[k1:]), you=real_on(r, a, b), smooth=on_s, w=w))
                    i += 40; continue
        i += 1
print("brake moments:", len(c2))
good = [c for c in c2 if c["smooth"] >= 0.7]
medt = st.median(c["top"] for c in good)
M2 = min(good, key=lambda c: abs(c["top"] - medt) - 0.5 * (c["smooth"] - c["you"]))
print(f"  chose {M2['r'].name} t={M2['r'].T[M2['i']] - M2['r'].T[M2['r'].start]:.1f}s top={M2['top']:.1f}x low={M2['low']:.1f}x you={M2['you']:.0%} smooth={M2['smooth']:.0%}")

# ---------------------------------------------------------------- 3. the far start
c3 = []
for r in TONIGHT:
    for a0, b0 in r.rounds:
        if b0 - a0 < 600: continue
        for a in range(a0 + 40, a0 + int(4.0 / DT), 15):
            b = a + 120
            if any(r.ex[k] is None for k in range(a - 10, b + 10)) or r.D[a] < 1800: continue
            sides = [r.ex[k] for k in range(a, b) if abs(r.ex[k]) > 1]
            if max(abs(r.ey[k]) for k in range(a, b)) > 1.2: continue
            flips = sum(1 for x, y in zip(sides, sides[1:]) if (x > 0) != (y > 0))
            on_s, w, _ = best_smooth(r, a, b)
            c3.append(dict(r=r, a=a, b=b, i=a + 60, flips=flips, you=real_on(r, a, b), smooth=on_s, w=w))
good = [c for c in c3 if c["smooth"] >= 0.75 and c["flips"] >= 2]
medy = st.median(c["you"] for c in good)
M3 = min(good, key=lambda c: abs(c["you"] - medy) - 0.3 * (c["smooth"] - c["you"]))
print(f"far moments: {len(c3)}; chose {M3['r'].name} t={M3['r'].T[M3['a']] - M3['r'].T[M3['r'].start]:.1f}s you={M3['you']:.0%} (median {medy:.0%}) smooth={M3['smooth']:.0%} flips={M3['flips']}")

# ---------------------------------------------------------------- export
def clip(m, key, pad_a=0, pad_b=0):
    r = m["r"]; a, b = m["a"] - pad_a, m["b"] + pad_b
    _, w, s = best_smooth(r, m["a"], m["b"])
    s = simulate(r, m["a"], b, w)
    f = lambda x: round(x, 4)
    sm = [None] * (m["a"] - a) + [[f(y), f(p)] for y, p in s]
    out = dict(run=r.name, score=r.score(), t0=round(r.T[a] - r.T[r.start], 2), hw=r.HW, hh=r.HH, off=round(r.OFF, 1), cam=r.CAM[a],
               yaw=[f(r.YAW[k]) for k in range(a, b)], pitch=[f(r.PIT[k]) for k in range(a, b)],
               bot=[[round(c, 1) for c in r.BP[k]] for k in range(a, b)], botyaw=[f(r.BY[k]) for k in range(a, b)], botpitch=[f(r.CZ[k]) for k in range(a, b)],
               hits=[r.HITS[k] - r.HITS[r.start] for k in range(a, b)], on=[int(r.on[k]) for k in range(a, b)],
               aimspd=[round(abs(r.av[k] or 0), 1) for k in range(a, b)], botspd=[round(abs(r.bv[k] or 0), 1) for k in range(a, b)],
               smooth=sm, you_on=round(m["you"], 2), smooth_on=round(m["smooth"], 2), timeleft=[round(60 - (r.T[k] - r.T[r.start]) * 60 / (r.T[r.end] - r.T[r.start]), 2) for k in range(a, b)])
    out["mark"] = {k: v - a for k, v in m.items() if k in ("i", "peak", "sprint", "brake")}
    return out

# smooth version's speed for the speed graph
def add_smooth_speed(c):
    s = c["smooth"]; sp = []
    for k in range(len(s)):
        if s[k] is None or k < 3 or k > len(s) - 4 or s[k - 3] is None: sp.append(None); continue
        sp.append(round(abs(s[k + 3][0] - s[k - 3][0]) / (6 * DT), 1))
    c["smoothspd"] = sp

data = {}
data["turn"] = clip(M1, "turn", 30, 30)
data["brake"] = clip(M2, "brake", 30, 30); add_smooth_speed(data["brake"])
data["far"] = clip(M3, "far", 30, 30)
# cold open: 7 s of the best run tonight at real speed, close range in round 1 (seconds 11-18)
best = max(TONIGHT, key=lambda r: r.score())
a1 = best.rounds[[k for k, (a, b) in enumerate(best.rounds) if b - a > 600][0]][0]
data["open"] = clip(dict(r=best, a=a1 + 11 * 60, b=a1 + 18 * 60, you=0, smooth=0), "open")
# top-down: one full round of the bot's path (every 3rd sample) and the camera
ra, rb = best.rounds[[k for k, (a, b) in enumerate(best.rounds) if b - a > 600][1]]
data["topdown"] = dict(cam=best.CAM[ra], path=[[round(best.BP[k][0]), round(best.BP[k][1]), round(best.T[k] - best.T[ra], 2)] for k in range(ra, min(rb, ra + int(20 / DT)), 3) if best.BP[k]])
ev = json.load(open(os.path.join(HERE, "evidence.json")))
data["chart"] = [dict(s=int(s), pps=v["pps"], dist=v["dist"]) for s, v in ev["by_second"].items() if int(s) < 20]
os.makedirs(os.path.join(HERE, "motion", "src"), exist_ok=True)
json.dump(data, open(os.path.join(HERE, "motion", "src", "data.json"), "w"))
json.dump({k: {kk: vv for kk, vv in v.items() if kk in ("run", "score", "t0", "you_on", "smooth_on", "mark")} for k, v in data.items() if k not in ("topdown", "chart")},
          open(os.path.join(HERE, "moments_chosen.json"), "w"), indent=1)
print(json.dumps(json.load(open(os.path.join(HERE, "moments_chosen.json"))), indent=0))
