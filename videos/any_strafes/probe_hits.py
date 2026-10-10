# Where Ryan's hits land relative to the recorded head centre, and where his misses are (world units at the bot).
import csv, math, statistics as st
P = r'C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods/AimRecorder/runs/2026-10-10_193218_143 ANY STRAFES.csv'
rows = list(csv.DictReader(open(P, encoding='utf-8')))
def off(r):
    cx, cy, cz = float(r['cam_x']), float(r['cam_y']), float(r['cam_z'])
    hx, hy, hz = float(r['b1_hx']), float(r['b1_hy']), float(r['b1_hz'])
    dx, dy = hx - cx, hy - cy; d = math.hypot(dx, dy)
    yaw, pit = math.radians(float(r['yaw'])), math.radians(float(r['pitch']))
    ba = math.atan2(dy, dx)
    ex = ((math.degrees(yaw - ba) + 180) % 360 - 180)
    lat = math.tan(math.radians(ex)) * d           # + = crosshair left/right of head
    vert = cz + math.tan(pit) * d - hz              # + = crosshair above head centre
    return lat, vert, d
H, M = [], []
for a, b in zip(rows, rows[1:]):
    if b['b1_hx'] == '' or float(b['t']) < 6.1: continue
    dh = int(b['hits']) - int(a['hits']); dm = int(b['misses']) - int(a['misses'])
    if dh > 0: H.append(off(b))
    elif dm > 0: M.append(off(b))
print(len(H), 'hit samples', len(M), 'miss samples')
for nm, L in (('hits', H), ('misses', M)):
    la = sorted(abs(x[0]) for x in L); ve = sorted(x[1] for x in L); rr = sorted(math.hypot(x[0], x[1]) for x in L)
    q = lambda s, p: round(s[int(p * (len(s) - 1))], 1)
    print(nm, 'lat|.5 .9 .98 max', q(la,.5), q(la,.9), q(la,.98), q(la,1), ' vert .02 .5 .98', q(ve,.02), q(ve,.5), q(ve,.98), ' radius .5 .9 .98 max', q(rr,.5), q(rr,.9), q(rr,.98), q(rr,1), 'dist', round(st.median(x[2] for x in L)))
# misses closest to the head centre (the head can't be bigger than this, apart from timing noise)
print('closest misses', sorted(round(math.hypot(x[0], x[1]), 1) for x in M)[:15])
# 2d histogram of hits
import collections
c = collections.Counter((round(x[0] / 5) * 5, round(x[1] / 5) * 5) for x in H)
for v in range(40, -45, -5):
    print(f'{v:4d}', ''.join(f'{c.get((h, v), 0):4d}' for h in range(-40, 45, 5)))
print('hit share by |lat| (vert band all)')
A = [(x, 1) for x in H] + [(x, 0) for x in M]
for lo in range(0, 60, 4):
    s = [h for x, h in A if lo <= abs(x[0]) < lo + 4]
    if s: print(f'  {lo:3d}-{lo+4:<3d} n={len(s):4d} hit={sum(s)/len(s):.2f}')
print('hit share by vert (|lat|<12)')
for lo in range(-60, 0, 4):
    s = [h for x, h in A if lo <= x[1] < lo + 4 and abs(x[0]) < 12]
    if s: print(f'  {lo:4d} n={len(s):4d} hit={sum(s)/len(s):.2f}')
