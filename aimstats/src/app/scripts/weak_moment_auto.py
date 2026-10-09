# Weak-moment GIF for any single-bot tracking scenario: finds the clearest "swung past the bot" moment in a run
# (the bot kept going the same way, the correction went through it and out the other side) and shows it next to a
# smooth version with the same reaction time. Bot size and on-target come from where the hits landed in this run.
# Usage: python weak_moment_auto.py <run csv> <out.gif> [@seconds]
import csv, math, os, statistics as st, sys
from PIL import Image, ImageDraw, ImageFont
from aim_analysis import moving_ids, height_source, thin60
import config

path, out = sys.argv[1], sys.argv[2]
rows = thin60(list(csv.DictReader(config.open_run(path))))
IDS = moving_ids(rows)
SRC = height_source(rows, IDS)          # visible body position where the recorder has it
P = lambda r, k, a: r[f"b{k}_{SRC}{a}"] if SRC and r.get(f"b{k}_{SRC}z") else r[f"b{k}_{a}"]
yaw, pit, by, bp, dist, hits, ts = [], [], [], [], [], [], []
acc = prev = None
for r in rows:
    k = next((i for i in range(1, 9) if r.get(f"b{i}_x") not in (None, "", "0.0") and (r.get(f"b{i}_id") or str(i)) in IDS), None)
    y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y
    ts.append(float(r["t"])); hits.append(int(r["hits"]))
    if k is None: yaw.append(None); pit.append(None); by.append(None); bp.append(None); dist.append(None); continue
    dx, dy, dz = float(P(r, k, "x")) - float(r["cam_x"]), float(P(r, k, "y")) - float(r["cam_y"]), float(P(r, k, "z")) - float(r["cam_z"])
    e = (math.degrees(math.atan2(dy, dx)) - y + 180) % 360 - 180
    yaw.append(acc); pit.append(float(r["pitch"])); by.append(acc + e); bp.append(math.degrees(math.atan2(dz, math.hypot(dx, dy))))
    dist.append(math.sqrt(dx * dx + dy * dy + dz * dz))
n, dt = len(yaw), 1 / 60
resets = [i for i in range(1, n) if hits[i] < hits[i - 1]]
start = resets[-1] if resets else 180

# bot size and the aim point's height on the bot, in world units, from the moments hits landed
U = lambda deg, d: math.tan(math.radians(deg)) * d
hit_i = [i for i in range(start + 1, n) if by[i] is not None and hits[i] > hits[i - 1]]
OFF = st.median(U(bp[i] - pit[i], dist[i]) for i in hit_i)
LR_ONLY = abs(OFF) > 4 * sorted(abs(U(by[i] - yaw[i], dist[i])) for i in hit_i)[int(.9 * len(hit_i))]   # recorded height unreliable
HW = sorted(abs(U(by[i] - yaw[i], dist[i])) for i in hit_i)[int(.9 * len(hit_i))]
HH = sorted(abs(U(bp[i] - pit[i], dist[i]) - OFF) for i in hit_i)[int(.9 * len(hit_i))]
if LR_ONLY: HH = 2.2 * HW                        # draw a normal capsule; its height isn't measured
HW = max(HW, 0.45 * HH)
import scenario_profile                           # bot shape from the scenario's bot file
_scen = os.path.basename(path)[18:].replace(".gz", "").replace(".csv", "")
if scenario_profile.bot_profile(_scen).get("BotType") == "SPHERE":    # a ball, not a capsule
    HH = HW = sorted(abs(U(by[i] - yaw[i], dist[i])) for i in hit_i)[int(.98 * len(hit_i))]
cbp = [None if bp[i] is None else (pit[i] if LR_ONLY else math.degrees(math.atan2(U(bp[i], dist[i]) - OFF, dist[i]))) for i in range(n)]   # bot centre pitch
ex = [None if by[i] is None else (by[i] - yaw[i]) for i in range(n)]
ey = [None if by[i] is None else (cbp[i] - pit[i]) for i in range(n)]
wx = [None if by[i] is None else math.degrees(math.atan(HW / dist[i])) for i in range(n)]
wy = [None if by[i] is None else math.degrees(math.atan(HH / dist[i])) for i in range(n)]
on = lambda i, ay, ap: by[i] is not None and abs(by[i] - ay) <= wx[i] and (LR_ONLY or abs(cbp[i] - ap) <= wy[i])

def vel(a, i):
    if i < 2 or i > n - 3 or a[i - 2] is None or a[i + 2] is None: return None
    return (a[i + 2] - a[i - 2]) / (4 * dt)
av = [vel(yaw, i) for i in range(n)]; bv = [vel(by, i) for i in range(n)]
apv = [vel(pit, i) for i in range(n)]; bpv = [vel(cbp, i) for i in range(n)]

def simulate(a, b, w, pred=1.0, delay=8):
    sy, sp, svy, svp = yaw[a], pit[a], (av[a] or 0), (apv[a] or 0)
    out_ = []
    for k in range(a, b):
        j = k - delay
        if by[j] is not None and bv[j] is not None and bpv[j] is not None:
            ty, tp = by[j] + pred * bv[j] * delay * dt, cbp[j] + pred * bpv[j] * delay * dt
            ay = w * w * (ty - sy) - 2 * w * svy; ap = w * w * (tp - sp) - 2 * w * svp
            svy += ay * dt; svp += ap * dt
        sy += svy * dt; sp += svp * dt
        if LR_ONLY: sp, svp = pit[k], 0.0
        out_.append((sy, sp, math.hypot(svy, svp)))
    return out_

# candidates (2D, so it works for up/down bots too): the aim is behind the bot, then within 0.25 s it is past it on the
# opposite side, while the bot keeps moving the same way (its direction turns less than 40 degrees)
nx = lambda k: ex[k] / wx[k]; ny = lambda k: ey[k] / wy[k]
cands = []
i = start + 60
while i < n - 60:
    if any(ex[k] is None or bv[k] is None or bpv[k] is None for k in range(i - 42, i + 36)): i += 1; continue
    m0 = math.hypot(nx(i - 6), ny(i - 6)); m1 = max(range(i, i + 15), key=lambda k: math.hypot(nx(k), ny(k)))
    dot = nx(i - 6) * nx(m1) + ny(i - 6) * ny(m1)
    if m0 > 1 and math.hypot(nx(m1), ny(m1)) > 1.3 and dot < -0.5 * m0 * math.hypot(nx(m1), ny(m1)) and on(i, yaw[i], pit[i]) is False or (
            m0 > 1 and math.hypot(nx(m1), ny(m1)) > 1.3 and dot < -0.5 * m0 * math.hypot(nx(m1), ny(m1))):
        v0, v1 = (bv[i - 20], bpv[i - 20]), (bv[i + 20], bpv[i + 20])
        s0_, s1_ = math.hypot(*v0), math.hypot(*v1)
        if s0_ > 8 and s1_ > 8 and (v0[0] * v1[0] + v0[1] * v1[1]) / (s0_ * s1_) > math.cos(math.radians(40)):
            a, b = i - 42, i + 36
            real = sum(on(k, yaw[k], pit[k]) for k in range(a, b)) / (b - a)
            best = max(((sum(on(k, s_[0], s_[1]) for k, s_ in zip(range(a, b), simulate(a, b, w))) / (b - a)), w) for w in (24, 30, 36, 42))
            cands.append((best[0] - real, 0, i, a, b, best[1], real, best[0]))
            i += 40; continue
    i += 1
if len(sys.argv) > 3:
    c = min(range(n), key=lambda k: abs(ts[k] - float(sys.argv[3][1:])))
    cands = [x for x in cands if abs(x[2] - c) < 30] or cands
if not cands: print("no over-aim moment in this run"); sys.exit(2)
cands.sort(key=lambda c: (c[6] >= 0.2, c[0]), reverse=True)   # prefer clean moments: on the bot for part of the clip
gain, peak, i0, a, b, W_, real_on, sim_on = cands[0]
sim = simulate(a, b, W_)
print(f"{len(cands)} over-aim moments; chose t={ts[i0] - ts[start]:.1f}s into the run: on target you {real_on:.0%}, smooth {sim_on:.0%} (w={W_})")

W, H, PW = 860, 400, 420
try: F = ImageFont.truetype("arialbd.ttf", 20); FS = ImageFont.truetype("arial.ttf", 15); FT = ImageFont.truetype("arialbd.ttf", 16)
except Exception: F = FS = FT = ImageFont.load_default()
BG, PANEL, INK, DIM = (22, 22, 21), (40, 40, 38), (244, 243, 238), (150, 149, 140)
BOT, AIM, GOOD, BAD = (90, 220, 210), (255, 70, 70), (120, 210, 120), (240, 122, 69)
D0 = st.median(dist[k] for k in range(a, b))
SCALE = 34 / math.degrees(math.atan(HH / D0))          # the bot is about 68 px tall at its distance in this clip
topspeed = max([abs(x) for x in av[a:b] + bv[a:b] if x is not None] + [s[2] for s in sim]) * 1.05

def phase(k):
    if k < i0 - 10: return "behind the bot"
    if k < i0: return "fast correction"
    if k < i0 + 16: return "over-aim: past the bot"
    return "correcting back"

frames = []
for idx, k in enumerate(range(a, b)):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    for p, (title, ay_, ap_, avel, col) in enumerate((
            ("YOU", yaw[k], pit[k], math.hypot(av[k] or 0, apv[k] or 0), BAD),
            ("SMOOTH VERSION", sim[idx][0], sim[idx][1], sim[idx][2], GOOD))):
        x0 = 10 + p * (PW + 10); y0 = 44
        d.rectangle([x0, y0, x0 + PW, y0 + 250], fill=PANEL)
        d.text((x0 + 12, 14), title, fill=col, font=F)
        cx, cy = x0 + PW // 2, y0 + 125
        rx, ry = wx[k] * SCALE, wy[k] * SCALE
        bx, byy = cx + (by[k] - ay_) * SCALE, cy - (cbp[k] - ap_) * SCALE
        bx = max(x0 + rx + 2, min(x0 + PW - rx - 2, bx)); byy = max(y0 + ry + 2, min(y0 + 248 - ry, byy))
        d.rounded_rectangle([bx - rx, byy - ry, bx + rx, byy + ry], radius=min(rx, ry), fill=BOT)
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=AIM)
        sy0 = y0 + 262
        d.text((x0, sy0), "bot speed", fill=DIM, font=FS)
        d.text((x0, sy0 + 26), "aim speed", fill=DIM, font=FS)
        bw = lambda s: int(min(abs(s), topspeed) / topspeed * (PW - 90))
        d.rectangle([x0 + 85, sy0 + 4, x0 + 85 + bw(math.hypot(bv[k] or 0, bpv[k] or 0)), sy0 + 16], fill=BOT)
        d.rectangle([x0 + 85, sy0 + 30, x0 + 85 + bw(avel), sy0 + 42], fill=col)
    d.text((10, H - 44), "Your run: " + phase(k), fill=BAD if i0 - 10 <= k < i0 + 16 else INK, font=FT)
    d.text((10, H - 22), "Smooth: same reaction time, eases in and matches the bot's speed. No over-aiming.  (half speed" + (", left-right only)" if LR_ONLY else ")"), fill=DIM, font=FS)
    frames.append(im.convert("P", palette=Image.ADAPTIVE, colors=32))
frames += [frames[-1]] * 20
frames[0].save(out, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=True)
frames[len(frames) // 2 - 10].convert("RGB").save(out[:-4] + ".png")
print(out, len(frames), "frames", f"YOU={round(100 * real_on)} SMOOTH={round(100 * sim_on)} T={ts[i0] - ts[start]:.1f}")
