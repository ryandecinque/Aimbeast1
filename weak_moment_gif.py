# Animated GIF of one weak moment: left = what Ryan actually did (from AimRecorder data),
# right = the same bot movement followed smoothly (a simulated aim with the same reaction time,
# no overshoot, no hard stop). Played at half speed.
# Usage: python weak_moment_gif.py <run csv> <stutter number> <out.gif>
import csv, math, sys
from PIL import Image, ImageDraw, ImageFont

path, which, out = sys.argv[1], sys.argv[2], sys.argv[3]   # which: stutter number, or @seconds for an overshoot moment
rows = list(csv.DictReader(open(path, encoding="utf-8")))
yaw, pit, by, bp = [], [], [], []
acc = prev = None
for r in rows:
    if r["b1_x"] in ("", "0.0"): yaw.append(None); pit.append(None); by.append(None); bp.append(None); continue
    y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y
    dx, dy, dz = float(r["b1_x"]) - float(r["cam_x"]), float(r["b1_y"]) - float(r["cam_y"]), float(r["b1_z"]) - float(r["cam_z"])
    e = (math.degrees(math.atan2(dy, dx)) - y + 180) % 360 - 180
    yaw.append(acc); pit.append(float(r["pitch"])); by.append(acc + e); bp.append(math.degrees(math.atan2(dz, math.hypot(dx, dy))))
n, dt = len(yaw), 1 / 60
def v(a, i):
    if i < 2 or i > n - 3 or a[i - 2] is None or a[i + 2] is None: return None
    return (a[i + 2] - a[i - 2]) / (4 * dt)
av = [v(yaw, i) for i in range(n)]; bv = [v(by, i) for i in range(n)]
stalls = []; i = 0
while i < n - 12:
    if av[i] is None or bv[i] is None: i += 1; continue
    if abs(bv[i]) > 25 and av[i] * bv[i] > 0 and abs(av[i]) > 0.6 * abs(bv[i]):
        j = i + 1
        while j < min(n, i + 10) and bv[j] is not None and av[j] is not None and bv[j] * bv[i] > 0 and abs(bv[j]) > 25 and abs(av[j]) < 0.35 * abs(bv[j]): j += 1
        if 3 <= j - i - 1 <= 9 and bv[j] is not None and av[j] is not None and av[j] * bv[i] > 0:
            stalls.append((i + 1, j)); i = j; continue
    i += 1
ts = [float(r["t"]) for r in rows]
if which.startswith("@"):
    kind = "overshoot"; c = min(range(n), key=lambda k: abs(ts[k] - float(which[1:]))); s0, s1 = c, c + 10
else:
    kind = "stutter"; s0, s1 = stalls[int(which)]
a, b = s0 - 42, s1 + 36                       # about 0.7 s before, 0.6 s after

# smooth version: follows the bot with the same ~130 ms reaction, critically damped (no overshoot, no hard stop)
import os
DELAY = 8; w = float(os.environ.get('SM_W', '40')); PRED = float(os.environ.get('SM_PRED', '1'))
sy, sp, svy, svp = yaw[a], pit[a], (av[a] or 0), 0.0
sim = []
for k in range(a, b):
    # what it saw 130 ms ago, carried forward at the speed it saw then (reading the bot's movement)
    vy = bv[k - DELAY] or 0
    vp = ((bp[k - DELAY] - bp[k - DELAY - 2]) / (2 * dt)) if bp[k - DELAY - 2] is not None else 0
    ty, tp = by[k - DELAY] + PRED * vy * DELAY * dt, bp[k - DELAY] + PRED * vp * DELAY * dt
    ay = w * w * (ty - sy) - 2 * w * svy; ap = w * w * (tp - sp) - 2 * w * svp
    svy += ay * dt; svp += ap * dt; sy += svy * dt; sp += svp * dt
    sim.append((sy, sp, svy))

W, H, PW = 860, 400, 420
try: F = ImageFont.truetype("arialbd.ttf", 20); FS = ImageFont.truetype("arial.ttf", 15); FT = ImageFont.truetype("arialbd.ttf", 16)
except Exception: F = FS = FT = ImageFont.load_default()
BG, PANEL, INK, DIM = (22, 22, 21), (40, 40, 38), (244, 243, 238), (150, 149, 140)
BOT, AIM, GOOD, BAD = (90, 220, 210), (255, 70, 70), (120, 210, 120), (240, 122, 69)
SCALE = 14                                      # px per degree
topspeed = max(abs(x) for x in av[a:b] + bv[a:b] if x is not None) * 1.05

def phase(k):
    if kind == "overshoot":
        if k < s0 - 10: return "behind the bot"
        if k < s0: return "fast correction"
        if k < s1 + 6: return "too far: past the bot"
        return "correcting back"
    if k < s0 - 14: return "the bot pulls away"
    if k < s0: return "big catch-up"
    if k < s1: return "hard stop"
    return "back on, speeding up again"

frames = []
for idx, k in enumerate(range(a, b)):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    for p, (title, ay_, ap_, avel, col) in enumerate((
            ("YOU", yaw[k], pit[k], av[k] or 0, BAD),
            ("SMOOTH VERSION", sim[idx][0], sim[idx][1], sim[idx][2], GOOD))):
        x0 = 10 + p * (PW + 10); y0 = 44
        d.rectangle([x0, y0, x0 + PW, y0 + 250], fill=PANEL)
        d.text((x0 + 12, 14), title, fill=col, font=F)
        cx, cy = x0 + PW // 2, y0 + 125
        bx, byy = cx + (by[k] - ay_) * SCALE, cy - (bp[k] - ap_) * SCALE
        bx = max(x0 + 14, min(x0 + PW - 14, bx))
        d.rounded_rectangle([bx - 14, byy - 26, bx + 14, byy + 26], radius=14, fill=BOT)
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=AIM)
        # speed bars: the bot's speed vs the aim's speed
        sy0 = y0 + 262
        d.text((x0, sy0), "bot speed", fill=DIM, font=FS)
        d.text((x0, sy0 + 26), "aim speed", fill=DIM, font=FS)
        bw = lambda s: int(abs(s) / topspeed * (PW - 90))
        d.rectangle([x0 + 85, sy0 + 4, x0 + 85 + bw(bv[k] or 0), sy0 + 16], fill=BOT)
        d.rectangle([x0 + 85, sy0 + 30, x0 + 85 + bw(avel), sy0 + 42], fill=col)
    msg = phase(k)
    d.text((10, H - 44), "Your run: " + msg, fill=BAD if k < s1 else INK, font=FT)
    d.text((10, H - 22), "Smooth: same reaction time, eases in and matches the bot's speed. No overshoot, no hard stop.  (half speed)", fill=DIM, font=FS)
    frames.append(im.convert("P", palette=Image.ADAPTIVE, colors=32))
frames += [frames[-1]] * 20
on = lambda ey, ep: abs(ey) < 1.9 and abs(ep) < 2.0
real_on = sum(on(by[k] - yaw[k], bp[k] - pit[k]) for k in range(a, b)) / (b - a)
sim_on = sum(on(by[k] - sim[k - a][0], bp[k] - sim[k - a][1]) for k in range(a, b)) / (b - a)
print(f"on target in this clip: you {real_on:.0%}, smooth version {sim_on:.0%}")                     # hold the last frame
frames[0].save(out, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=True)
print(out, len(frames), "frames")
