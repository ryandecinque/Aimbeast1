# "X% better" versions of Robidashka's run: same bots, same paths, same timing, same aim pattern, with every miss
# made smaller by one factor s (s < 1 pulls the crosshair toward their own usual aim point on the bot:
# the bot's centre line, at their median height on it). Score = shots (33.3 a second) with the crosshair on the head
# area found by calibrate.py. Finds s for 5/10/15/20% and writes better.json.
import json, os, numpy as np
import calibrate as cal
HERE = os.path.dirname(os.path.abspath(__file__))
K, C = 0.6, 1.15                     # head: top 60% of the capsule's height, 1.15 x its visible half-width
U, V = [], []
for g in cal.G:
    if g is None: U.append(np.nan); V.append(np.nan); continue
    yt, yb, xc, hw = g
    U.append((960 - xc) / hw); V.append((540 - yt) / (yb - yt))
U, V = np.array(U), np.array(V)
V0 = float(np.nanmedian(V[np.abs(U) <= 1]))

def score(s):
    u, v = s * U, V0 + s * (V - V0)
    return int(np.nansum((np.abs(u) <= C) & (v >= 0) & (v <= K)))

if __name__ == "__main__":
    base = score(1.0)
    print("rebuilt score", base, " aim point on the bot: centre line,", round(V0, 3), "of the height from the top")
    res = {"base": base, "V0": V0, "K": K, "C": C, "versions": {}}
    for pct in (5, 10, 15, 20):
        target = round(1585 * (1 + pct / 100))
        lo, hi = 0.2, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if score(mid) >= target: lo = mid
            else: hi = mid
        s = lo
        res["versions"][pct] = dict(target=target, scale=round(s, 4), score=score(s), misses_smaller_by_pct=round(100 * (1 - s), 1))
        print(pct, res["versions"][pct])
    json.dump(res, open(os.path.join(HERE, "better.json"), "w"), indent=1)
