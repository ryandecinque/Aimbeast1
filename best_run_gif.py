# GIF of the best 8 seconds (most hits) of one recorded run, at real speed, from AimRecorder data.
# Usage: python best_run_gif.py <run csv> <score> <label> <out.gif>
import csv, math, sys
from PIL import Image, ImageDraw, ImageFont

path, score, label, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
rows = list(csv.DictReader(open(path, encoding="utf-8")))
S = []
for r in rows:
    if r["b1_x"] in ("", "0.0"): S.append(None); continue
    y, p = float(r["yaw"]), float(r["pitch"])
    dx, dy, dz = float(r["b1_x"]) - float(r["cam_x"]), float(r["b1_y"]) - float(r["cam_y"]), float(r["b1_z"]) - float(r["cam_z"])
    ex = (math.degrees(math.atan2(dy, dx)) - y + 180) % 360 - 180
    ey = math.degrees(math.atan2(dz, math.hypot(dx, dy))) - p
    S.append(dict(ex=ex, ey=ey, hits=int(r["hits"]), t=float(r["t"])))
hits = [s["hits"] if s else None for s in S]
first = next(i for i in range(1, len(S)) if hits[i] and hits[i - 1] is not None and hits[i] > hits[i - 1])
last = max(i for i in range(len(S)) if hits[i] is not None)
WIN = 8 * 60
best, a = -1, first
for i in range(first, last - WIN, 6):
    if hits[i] is None or hits[i + WIN] is None: continue
    h = hits[i + WIN] - hits[i]
    if h > best: best, a = h, i
b = a + WIN
total = hits[last] - hits[first]

W, H = 640, 360
try: F = ImageFont.truetype("arialbd.ttf", 18); FS = ImageFont.truetype("arial.ttf", 13); FB = ImageFont.truetype("arialbd.ttf", 28)
except Exception: F = FS = FB = ImageFont.load_default()
BG, PANEL, INK, DIM, BOT, AIM, ACC = (22, 22, 21), (40, 40, 38), (244, 243, 238), (150, 149, 140), (90, 220, 210), (255, 70, 70), (240, 122, 69)
SCALE = 11
frames = []
for i in range(a, b, 2):                          # every other sample: 30 frames a second, real speed
    s = S[i]
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([10, 40, W - 10, 280], fill=PANEL)
    d.text((14, 10), label, fill=INK, font=F)
    cx, cy = W // 2, 160
    if s:
        bx, by = cx + s["ex"] * SCALE, cy - s["ey"] * SCALE
        d.rounded_rectangle([bx - 13, by - 24, bx + 13, by + 24], radius=13, fill=BOT)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=AIM)
    # hits in this clip (hits are the score)
    if s and hits[i] is not None:
        d.text((W - 150, 48), f"{hits[i] - hits[first] + 1}", fill=INK, font=FB)
        d.text((W - 150, 82), f"score so far (of {score})", fill=DIM, font=FS)
    # where this clip sits in the 60-second run
    tx0, tx1, ty = 20, W - 20, 300
    d.rectangle([tx0, ty, tx1, ty + 8], fill=(60, 60, 56))
    X = lambda k: tx0 + (k - first) / max(last - first, 1) * (tx1 - tx0)
    d.rectangle([X(a), ty, X(b), ty + 8], fill=(90, 90, 84))
    d.rectangle([X(first), ty, X(i), ty + 8], fill=ACC)
    d.text((tx0, ty + 14), "the full 60-second run: this clip is the 8 seconds with the most hits", fill=DIM, font=FS)
    d.text((tx0, ty + 34), f"Final score {score}.  Real speed.", fill=DIM, font=FS)
    frames.append(im.convert("P", palette=Image.ADAPTIVE, colors=24))
frames += [frames[-1]] * 15
frames[0].save(out, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=True)
print(out, len(frames), "frames; best 8 s =", best, "hits from", round(S[a]["t"], 1), "s")
