# Ryan's ANY STRAFES recording: one bot at a time; split into its 12 lives and measure how each bot moves.
# A life starts when the bot reappears at the spawn point (-200,-800). Per life: health (300/400 tells the bot file
# apart a little), top speed, how often it turns round, distance and depth range, and Ryan's hits on it.
import csv, json, math, os, statistics as st
P = r'C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods/AimRecorder/runs/2026-10-10_193218_143 ANY STRAFES.csv'
HERE = os.path.dirname(os.path.abspath(__file__))
rows = [r for r in csv.DictReader(open(P, encoding='utf-8'))]
T = [float(r['t']) for r in rows]
X = [float(r['b1_x']) for r in rows]; Y = [float(r['b1_y']) for r in rows]
H = [int(r['hits']) for r in rows]; MS = [int(r['misses']) for r in rows]
start = max(i for i in range(1, len(rows)) if H[i] < H[i - 1] or MS[i] < MS[i - 1])     # last reset = the real run
jumps = [start] + [i for i in range(start + 1, len(rows)) if math.hypot(X[i] - X[i - 1], Y[i] - Y[i - 1]) > 60]
lives = []
for a, b in zip(jumps, jumps[1:] + [len(rows)]):
    # the bot is hidden for 0.5 s before reappearing: the recorder keeps it standing at the spawn point then
    idx = list(range(a, b))
    v = []
    for i in idx[1:]:
        dt = T[i] - T[i - 1]
        if dt > 0: v.append((T[i], (X[i] - X[i - 1]) / dt, (Y[i] - Y[i - 1]) / dt))
    vs = [math.hypot(p[1], p[2]) for p in v]
    # lateral reversals: sign changes of smoothed x velocity
    sm = [st.mean(p[1] for p in v[max(0, k - 3):k + 4]) for k in range(len(v))]
    rev = [v[k][0] for k in range(1, len(sm)) if sm[k] * sm[k - 1] < 0 and abs(sm[k]) + abs(sm[k-1]) > 20]
    legs = [b_ - a_ for a_, b_ in zip(rev, rev[1:])]
    moving = [t for t, s in zip([p[0] for p in v], vs) if s > 5]
    lives.append(dict(t0=round(T[a] - T[start], 2), dur=round(T[b - 1] - T[a], 2), hp=rows[a + 5]['b1_hp'],
                      move_from=round(moving[0] - T[a], 2) if moving else None, move_to=round(moving[-1] - T[a], 2) if moving else None,
                      top_speed=round(sorted(vs)[int(.98 * len(vs))]) if vs else 0,
                      x_range=[round(min(X[a:b])), round(max(X[a:b]))], y_range=[round(min(Y[a:b])), round(max(Y[a:b]))],
                      reversals=len(rev), leg_median=round(st.median(legs), 2) if legs else None,
                      leg_range=[round(min(legs), 2), round(max(legs), 2)] if legs else None,
                      hits=H[b - 1] - H[a], misses=MS[b - 1] - MS[a]))
for L in lives: print(L)
json.dump(dict(start_t=T[start], lives=lives), open(os.path.join(HERE, 'ryan_bots.json'), 'w'), indent=1)
