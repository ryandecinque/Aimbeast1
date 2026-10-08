# Rebuilds what the screen looked like around one tracking stutter, from AimRecorder data (no video needed).
# Usage: python stall_view.py <run csv> <stall number> <out.png>
import csv, math, sys
from PIL import Image, ImageDraw, ImageFont

path, which, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
rows = list(csv.DictReader(open(path, encoding="utf-8")))
yaw, boty, ex, ey, t = [], [], [], [], []
acc = prev = None
for r in rows:
    if r["b1_x"] in ("", "0.0"):
        yaw.append(None); boty.append(None); ex.append(None); ey.append(None); t.append(float(r["t"])); continue
    y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y
    dx, dy, dz = float(r["b1_x"]) - float(r["cam_x"]), float(r["b1_y"]) - float(r["cam_y"]), float(r["b1_z"]) - float(r["cam_z"])
    e = (math.degrees(math.atan2(dy, dx)) - y + 180) % 360 - 180
    p = math.degrees(math.atan2(dz, math.hypot(dx, dy))) - float(r["pitch"])
    yaw.append(acc); boty.append(acc + e); ex.append(e); ey.append(p); t.append(float(r["t"]))
n, dt = len(yaw), 1 / 60
def v(a, i):
    if i < 2 or i > n - 3 or a[i - 2] is None or a[i + 2] is None: return None
    return (a[i + 2] - a[i - 2]) / (4 * dt)
av = [v(yaw, i) for i in range(n)]; bv = [v(boty, i) for i in range(n)]
stalls = []; i = 0
while i < n - 12:
    if av[i] is None or bv[i] is None: i += 1; continue
    if abs(bv[i]) > 25 and av[i] * bv[i] > 0 and abs(av[i]) > 0.6 * abs(bv[i]):
        j = i + 1
        while j < min(n, i + 10) and bv[j] is not None and av[j] is not None and bv[j] * bv[i] > 0 and abs(bv[j]) > 25 and abs(av[j]) < 0.35 * abs(bv[j]): j += 1
        if 3 <= j - i - 1 <= 9 and bv[j] is not None and av[j] is not None and av[j] * bv[i] > 0:
            stalls.append((i + 1, j)); i = j; continue
    i += 1
s0, s1 = stalls[which]
a, b = max(0, s0 - 30), min(n, s1 + 30)          # half a second either side

W, H = 1200, 700
img = Image.new("RGB", (W, H), (26, 26, 25)); d = ImageDraw.Draw(img)
try: F = ImageFont.truetype("arial.ttf", 18); FS = ImageFont.truetype("arial.ttf", 14)
except Exception: F = FS = ImageFont.load_default()
ink, dim, acc_c, bot_c, warn = (244, 243, 238), (143, 142, 134), (240, 122, 69), (90, 220, 210), (230, 70, 70)
d.text((30, 20), f"Stutter {which + 1} of {len(stalls)}  ·  {path.split('/')[-1][:-4]}  ·  run time {t[s0]:.2f}s", fill=ink, font=F)

# frame strip: what the screen looked like (crosshair fixed in the middle, bot where it was)
picks = [a + k * (b - a) // 7 for k in range(8)]
fw, fh, scale = 135, 150, 9          # 9 px per degree
for k, i in enumerate(picks):
    x0, y0 = 30 + k * (fw + 6), 60
    stalled = s0 <= i < s1
    d.rectangle([x0, y0, x0 + fw, y0 + fh], fill=(40, 40, 38), outline=warn if stalled else (60, 60, 56), width=3 if stalled else 1)
    cx, cy = x0 + fw // 2, y0 + fh // 2
    if ex[i] is not None:
        bx, by = cx + ex[i] * scale, cy - ey[i] * scale
        d.rounded_rectangle([bx - 11, by - 20, bx + 11, by + 20], radius=11, fill=bot_c)
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 60, 60))
    d.text((x0 + 6, y0 + fh + 6), f"{(i - s0) * dt * 1000:+.0f} ms", fill=warn if stalled else dim, font=FS)
d.text((30, 250), "Each box: your crosshair (red dot, centre) and where the bot was. Red boxes = during the stutter.", fill=dim, font=FS)

# speed graph: how fast your aim turned vs how fast the bot moved across your screen
gx0, gy0, gw, gh = 60, 300, 1100, 330
d.rectangle([gx0, gy0, gx0 + gw, gy0 + gh], outline=(60, 60, 56))
vals = [abs(x) for x in av[a:b] + bv[a:b] if x is not None]; top = max(vals) * 1.1 if vals else 1
X = lambda i: gx0 + (i - a) / max(b - a - 1, 1) * gw
Y = lambda val: gy0 + gh - abs(val) / top * gh
d.rectangle([X(s0), gy0, X(s1), gy0 + gh], fill=(70, 34, 34))
for series, col in ((bv, bot_c), (av, acc_c)):
    pts = [(X(i), Y(series[i])) for i in range(a, b) if series[i] is not None]
    if len(pts) > 1: d.line(pts, fill=col, width=3)
d.text((gx0, gy0 + gh + 10), "Speed across the screen (degrees per second):", fill=dim, font=FS)
d.text((gx0 + 330, gy0 + gh + 10), "bot", fill=bot_c, font=FS)
d.text((gx0 + 370, gy0 + gh + 10), "your aim", fill=acc_c, font=FS)
d.text((gx0 + 450, gy0 + gh + 10), "shaded = your aim nearly stopped while the bot kept going", fill=warn, font=FS)
img.save(out)
print(len(stalls), "stutters; showing", which + 1, "at", round(t[s0], 2), "s")
