# What kind of miss is each off-target moment? Share of off-target time, by distance.
import json, math, statistics as st
from zeus_data import Run, zeus_runs, DT
K = ["behind_chasing", "behind_wrong_way", "ahead", "updown"]
tot = {b: dict.fromkeys(K, 0) for b in ("far", "mid", "close", "all")}
ratio = {b: [] for b in ("far", "mid", "close")}
per_run = []
for f in zeus_runs():
    r = Run(f)
    av = [r.vel(r.YAW, i, 3) for i in range(r.n)]; bv = [r.vel(r.BY, i, 3) for i in range(r.n)]
    rk = dict.fromkeys(K, 0)
    for a, b in r.rounds:
        if b - a < 120: continue
        for i in range(a + 10, min(b, a + int(20 / DT))):     # live part of the round (20 s)
            if r.ex[i] is None or bv[i] is None or av[i] is None: continue
            band = "far" if r.D[i] > 1500 else "mid" if r.D[i] > 800 else "close"
            if r.on[i]:
                if abs(bv[i]) > 5: ratio[band].append(abs(av[i]) / abs(bv[i]))
                continue
            if abs(r.ey[i]) > 1 and abs(r.ey[i]) * 1.0 > abs(r.ex[i]): k = "updown"
            else:
                side = 1 if r.YAW[i] > r.BY[i] else -1          # which side of the bot the aim is
                v = 1 if bv[i] > 0 else -1
                if side == v: k = "ahead"
                else: k = "behind_chasing" if av[i] * v > 0 else "behind_wrong_way"
            tot[band][k] += 1; tot["all"][k] += 1; rk[k] += 1
    s = sum(rk.values()); per_run.append(dict(run=r.name, score=r.score(), **{k: round(100 * v / s) for k, v in rk.items()}))
out = {b: {k: round(100 * v / max(1, sum(d.values()))) for k, v in d.items()} | {"off_seconds_per_run": round(sum(d.values()) * DT / 21, 1)} for b, d in tot.items()}
out["aim_speed_vs_bot_while_on"] = {b: dict(median=round(st.median(v), 2), p10=round(sorted(v)[len(v) // 10], 2), p90=round(sorted(v)[9 * len(v) // 10], 2)) for b, v in ratio.items()}
print(json.dumps(out, indent=1)); json.dump(dict(out=out, per_run=per_run), open("kinds.json", "w"), indent=1)
for p in per_run: print(p)
