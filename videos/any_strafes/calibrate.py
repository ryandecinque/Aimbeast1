# Finds the head's hit area on Robidashka's video so the shots that land on it equal the game's own hits (1585 of 3000),
# then checks the score over time against the on-screen score read by ocr.py.
# Works in bot sizes on screen (no FOV needed): the head is the capsule's top part, from its top down to a share K of
# its height, and as wide as the capsule times C. Shots: 33.3 a second, from the click that starts the run.
import glob, json, os, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
R = np.concatenate([np.load(f)["rows"] for f in sorted(glob.glob(os.path.join(HERE, "frames_*.npz")))])
FPS = 360.0
T0 = 1.356                      # first bot appears = the click that starts the run (first life 1.356-8.392 s)
LIFE, GAP = 7.04, 0.5015        # measured: lives start every 7.5415 s
SHOT = 60 / 2000
score_ocr = {int(k): v for k, v in json.load(open(os.path.join(HERE, "score.json"))).items() if v is not None}

def alive(t):
    k = int((t - T0) // (LIFE + GAP))
    return 0 <= k < 12 and (t - T0) - k * (LIFE + GAP) < LIFE

def frame_geom(i):
    r = R[i]
    if r[2] != 1: return None
    yt = (r[5] + r[12]) / 2 if not np.isnan(r[12]) else r[5] - 2
    yb = (r[6] + r[13]) / 2 if not np.isnan(r[13]) else r[6] + 2
    xl = (r[3] + r[10]) / 2 if not np.isnan(r[10]) else r[3] - 2
    xr = (r[4] + r[11]) / 2 if not np.isnan(r[11]) else r[4] + 2
    return yt, yb, (xl + xr) / 2, (xr - xl) / 2

shots = [T0 + n * SHOT for n in range(3000)]
G = []
for t in shots:
    i = int(round(t * FPS))
    g = frame_geom(i) if alive(t) else None
    G.append(g)

def hits(K, C):
    out = []
    for g in G:
        if g is None: out.append(0); continue
        yt, yb, xc, hw = g
        h = yb - yt
        out.append(int(yt <= 540 <= yt + K * h and abs(960 - xc) <= C * hw))
    return np.array(out)

if __name__ == "__main__":
    # where the crosshair sits on the bot, as a share of the bot's height from the top (when within the bot's width)
    ys = [(540 - g[0]) / (g[1] - g[0]) for g in G if g and abs(960 - g[2]) <= g[3]]
    print("shots while a bot is up:", sum(1 for t in shots if alive(t)), " crosshair within the bot's width:", len(ys))
    print("crosshair height on the bot (share from top) percentiles 5/25/50/75/95:", np.round(np.percentile(ys, [5, 25, 50, 75, 95]), 3))
    print("whole bot counts as head:", hits(1.0, 1.0).sum())
    best = []
    for C in (0.9, 1.0, 1.1):
        for K in np.arange(0.30, 1.001, 0.01):
            best.append((abs(hits(K, C).sum() - 1585), K, C, hits(K, C).sum()))
    best.sort()
    print("closest (|diff|, K, C, hits):", [(d, round(k, 2), c, s) for d, k, c, s in best[:8]])
    for C in (0.9, 1.0, 1.1):
        row = [(round(K, 2), hits(K, C).sum()) for K in np.arange(0.35, 0.75, 0.05)]
        print("C", C, row)
    d, K, C, s = best[0]
    h = hits(K, C); cum = np.cumsum(h)
    # compare with the on-screen score
    err = []
    for fr, sc in sorted(score_ocr.items()):
        t = fr / FPS
        n = int(np.searchsorted(shots, t - 0.02))           # shots fired before this frame (HUD lags a frame or so)
        if n: err.append((round(t, 2), sc, int(cum[n - 1])))
    diffs = [b - c for _, b, c in err]
    print("score vs model over time: median gap", np.median(diffs), " worst", min(diffs), max(diffs))
    print([e for e in err[::40]])
    json.dump(dict(K=K, C=C, hits=int(s), err=err), open(os.path.join(HERE, "calib.json"), "w"))
