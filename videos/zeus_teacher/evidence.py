# Re-checks Ryan's Zeus weaknesses on every recorded run (Oct 8 + Oct 10). Writes evidence.json.
import json, math, statistics as st, sys
from zeus_data import Run, zeus_runs, DT
out = {"runs": []}
bins = {}          # seconds into round -> [dist, pts, on, n]
rev_all = []       # per direction change: over-aim yes/no, round second, distance
side = {"behind": 0, "ahead": 0, "updown": 0}
pulse = []
for f in zeus_runs():
    r = Run(f)
    rounds = [(a, b) for a, b in r.rounds if b - a > 120]
    av = [r.vel(r.YAW, i) for i in range(r.n)]; bv = [r.vel(r.BY, i) for i in range(r.n)]
    info = dict(name=r.name, score=r.score(), HW=round(r.HW), HH=round(r.HH))
    early = late = 0; early_t = late_t = 0
    for a, b in rounds:
        for i in range(a + 1, b):
            if r.D[i] is None: continue
            s = int((i - a) * DT)
            e = bins.setdefault(s, [0, 0, 0, 0])
            e[0] += r.D[i]; e[1] += max(0, r.HITS[i] - r.HITS[i - 1]); e[2] += r.on[i]; e[3] += 1
            pts = max(0, r.HITS[i] - r.HITS[i - 1])
            if s < 5: early += pts; early_t += DT
            else: late += pts; late_t += DT
            # where is the aim when it's off the bot? behind = on the side the bot is coming from
            if not r.on[i] and bv[i] and abs(bv[i]) > 3:
                if abs(r.ey[i]) > 1 and abs(r.ey[i]) > abs(r.ex[i]): side["updown"] += 1
                else:
                    # ex>0 means bot yaw > aim yaw: bot is ahead of the aim in + direction
                    lead = r.ex[i] * (1 if bv[i] > 0 else -1)
                    side["behind" if lead > 0 else "ahead"] += 1
        # direction changes of the bot (left-right): clear motion one way 0.1 s before, the other way 0.1 s after
        i = a + 30
        while i < b - 40:
            if bv[i - 6] and bv[i + 6] and bv[i - 1] and bv[i] and (bv[i - 1] > 0) != (bv[i] > 0) and abs(bv[i - 6]) > 4 and abs(bv[i + 6]) > 4 and (bv[i - 6] > 0) != (bv[i + 6] > 0):
                sgn = 1 if bv[i + 6] > 0 else -1           # new bot direction
                # over-aim: within 0.5 s the aim gets past the bot's edge on the side the bot is now heading
                win = [r.ex[k] for k in range(i, min(b, i + 30)) if r.ex[k] is not None]
                over = any(-x * sgn > 1.0 for x in win[6:])      # aim ahead of the bot by more than its half-width
                rev_all.append(dict(over=over, sec=(i - a) * DT, d=r.D[i], run=r.name, i=i))
                i += 9
            else: i += 1
        # stop-go: while on the bot, how often does the aim speed swing above/below the bot's speed
        ons = [i for i in range(a + 30, b - 30) if r.on[i] and av[i] is not None and bv[i] is not None and abs(bv[i]) > 3]
        if ons:
            rel = [abs(av[i]) / abs(bv[i]) for i in ons]
            pulse.append(st.pstdev(rel))
    info.update(early_pps=round(early / early_t, 1), late_pps=round(late / late_t, 1))
    out["runs"].append(info)
out["by_second"] = {s: dict(dist=round(v[0] / v[3]), pps=round(v[1] / (v[3] * DT), 1), on=round(100 * v[2] / v[3])) for s, v in sorted(bins.items())}
out["over_aim_after_turns"] = dict(n=len(rev_all), pct=round(100 * sum(x["over"] for x in rev_all) / len(rev_all)),
    far_pct=round(100 * sum(x["over"] for x in rev_all if x["d"] > 1500) / max(1, sum(x["d"] > 1500 for x in rev_all))),
    close_pct=round(100 * sum(x["over"] for x in rev_all if x["d"] < 800) / max(1, sum(x["d"] < 800 for x in rev_all))))
tot = sum(side.values()); out["off_target_where"] = {k: round(100 * v / tot) for k, v in side.items()}
out["speed_swing_while_on"] = round(st.median(pulse), 2)
json.dump(out, open("evidence.json", "w"), indent=1)
json.dump(rev_all, open("turns.json", "w"))
print(json.dumps({k: v for k, v in out.items() if k != "runs"}, indent=0)[:3000])
for x in out["runs"]: print(x)
