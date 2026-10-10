import json, math, statistics as st
from zeus_data import Run, zeus_runs, DT
def corr(a, b):
    ma, mb = st.mean(a), st.mean(b); return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
rows = []; leads = []; reacts = []
for f in zeus_runs():
    r = Run(f)
    av = [r.vel(r.YAW, i, 3) for i in range(r.n)]; bv = [r.vel(r.BY, i, 3) for i in range(r.n)]
    # bias check: at hit moments, is the aim behind the recorded bot centre (in the bot's direction of travel)?
    for i in r.hit_i:
        if bv[i] and abs(bv[i]) > 5: leads.append((r.YAW[i] - r.BY[i]) * (1 if bv[i] > 0 else -1) * math.pi / 180 * r.D[i] / r.HW)
    sec = dict(far_pts=0, far_t=0, chase=0, wrong=0, ahead=0, ud=0, long=0)
    for a, b in r.rounds:
        if b - a < 120: continue
        off = 0
        for i in range(a + 10, min(b, a + int(20 / DT))):
            if r.ex[i] is None or bv[i] is None or av[i] is None: continue
            if r.D[i] > 1500: sec["far_pts"] += max(0, r.HITS[i] - r.HITS[i - 1]); sec["far_t"] += DT
            if r.on[i]:
                if off >= 30: sec["long"] += 1
                off = 0; continue
            off += 1
            if abs(r.ey[i]) > 1 and abs(r.ey[i]) > abs(r.ex[i]): sec["ud"] += DT
            else:
                side = 1 if r.YAW[i] > r.BY[i] else -1; v = 1 if bv[i] > 0 else -1
                if side == v: sec["ahead"] += DT
                elif av[i] * v > 0: sec["chase"] += DT
                else: sec["wrong"] += DT
        # reaction after bot turns
        i = a + 30
        while i < min(b, a + int(20 / DT)) - 40:
            if bv[i - 6] and bv[i + 6] and (bv[i - 6] > 0) != (bv[i + 6] > 0) and abs(bv[i - 6]) > 4 and abs(bv[i + 6]) > 4 and bv[i - 1] and bv[i] and (bv[i - 1] > 0) != (bv[i] > 0):
                want = 1 if bv[i + 6] > 0 else -1
                j = i
                while j < i + 36 and not (av[j] and av[j] * want > 0 and abs(av[j]) > 0.5 * abs(bv[i + 6])): j += 1
                if j < i + 36: reacts.append((j - i) * DT * 1000)
                i += 9
            else: i += 1
    rows.append(dict(run=r.name, score=r.score(), far_pps=round(sec["far_pts"] / sec["far_t"], 2), **{k: round(sec[k], 1) for k in ("chase", "wrong", "ahead", "ud", "long")}))
for k in ("far_pps", "chase", "wrong", "ahead", "ud", "long"):
    print(k, "corr with score", round(corr([x[k] for x in rows], [x["score"] for x in rows]), 2), "median", st.median(x[k] for x in rows))
print("aim lead at hit moments (half-widths, + = ahead of recorded centre): median", round(st.median(leads), 2), "mean", round(st.mean(leads), 2))
print("reaction to bot turns ms median", st.median(reacts), "n", len(reacts))
json.dump(rows, open("per_run.json", "w"), indent=1)
for x in rows: print(x)
