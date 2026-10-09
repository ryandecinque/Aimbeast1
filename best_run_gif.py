# GIF of the best 8 seconds (most hits) of one recorded run, at real speed, from AimRecorder data.
# Usage: python best_run_gif.py <run csv> <score> <label> <out.gif>
import csv, math, sys
from PIL import Image, ImageDraw, ImageFont

path, score, label, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
from aim_analysis import moving_ids
rows = list(csv.DictReader(open(path, encoding="utf-8")))
IDS = moving_ids(rows)                            # skip bots left over from earlier scenarios (they never move)
S = []
for r in rows:
    k = next((i for i in range(1, 9) if r.get(f"b{i}_x") not in (None, "", "0.0") and (r.get(f"b{i}_id") or str(i)) in IDS), None)
    if k is None: S.append(None); continue
    y, p = float(r["yaw"]), float(r["pitch"])
    dx, dy, dz = float(r[f"b{k}_x"]) - float(r["cam_x"]), float(r[f"b{k}_y"]) - float(r["cam_y"]), float(r[f"b{k}_z"]) - float(r["cam_z"])
    ex = (math.degrees(math.atan2(dy, dx)) - y + 180) % 360 - 180
    ey = math.degrees(math.atan2(dz, math.hypot(dx, dy))) - p
    S.append(dict(ex=ex, ey=ey, d=math.sqrt(dx * dx + dy * dy + dz * dz), hits=int(r["hits"]), t=float(r["t"])))
hits = [s["hits"] if s else None for s in S]
resets = [i for i in range(1, len(S)) if hits[i] is not None and hits[i - 1] is not None and hits[i] < hits[i - 1]]   # run starts when the game zeroes the counter
first = resets[-1] if resets else next(i for i in range(1, len(S)) if hits[i] and hits[i - 1] is not None and hits[i] > hits[i - 1])
last = max(i for i in range(len(S)) if hits[i] is not None)
WIN = 8 * 60
best, a = -1, first
for i in range(first, last - WIN, 6):
    if hits[i] is None or hits[i + WIN] is None: continue
    h = hits[i + WIN] - hits[i]
    if h > best: best, a = h, i
b = a + WIN
total = hits[last] - hits[first]

# the bot's real size and centre, from where the aim was when hits landed (in world units, so it grows as it comes close)
import statistics as st
hit_i = [i for i in range(first + 1, last) if S[i] and S[i - 1] and hits[i] > hits[i - 1]]
U = lambda deg, d: math.tan(math.radians(deg)) * d
OFF = st.median(U(S[i]["ey"], S[i]["d"]) for i in hit_i)                      # aim point vs the recorded bot position
hw = sorted(abs(U(S[i]["ex"], S[i]["d"])) for i in hit_i)[int(.9 * len(hit_i))]
hh = sorted(abs(U(S[i]["ey"], S[i]["d"]) - OFF) for i in hit_i)[int(.9 * len(hit_i))]
hw = max(hw, 0.45 * hh)
LR_ONLY = abs(OFF) > 4 * sorted(abs(U(S[i]["ex"], S[i]["d"])) for i in hit_i)[int(.9 * len(hit_i))]   # recorded height unreliable (flying bots)
if LR_ONLY: hh = 2.2 * hw
if "SPHERE" in label.upper(): hh = hw = max(hw, sorted(abs(U(S[i]["ex"], S[i]["d"])) for i in hit_i)[int(.98 * len(hit_i))])   # a ball, not a capsule          # precise left-right aim underestimates width: keep a capsule shape
D0 = st.median(S[i]["d"] for i in hit_i)
W, H = 640, 360
try: F = ImageFont.truetype("arialbd.ttf", 18); FS = ImageFont.truetype("arial.ttf", 13); FB = ImageFont.truetype("arialbd.ttf", 28)
except Exception: F = FS = FB = ImageFont.load_default()
BG, PANEL, INK, DIM, BOT, AIM, ACC = (22, 22, 21), (40, 40, 38), (244, 243, 238), (150, 149, 140), (90, 220, 210), (255, 70, 70), (240, 122, 69)
SCALE = 40 / math.degrees(math.atan(hh / D0))       # the bot is about 80 px tall at its typical distance
frames = []
for i in range(a, b, 2):                          # every other sample: 30 frames a second, real speed
    s = S[i]
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([10, 40, W - 10, 280], fill=PANEL)
    d.text((14, 10), label, fill=INK, font=F)
    cx, cy = W // 2, 160
    if s:
        cey = 0.0 if LR_ONLY else math.degrees(math.atan2(U(s["ey"], s["d"]) - OFF, s["d"]))     # aim error to the bot's centre
        bx, by = cx + s["ex"] * SCALE, cy - cey * SCALE
        rx, ry = math.degrees(math.atan(hw / s["d"])) * SCALE, math.degrees(math.atan(hh / s["d"])) * SCALE
        d.rounded_rectangle([bx - rx, by - ry, bx + rx, by + ry], radius=min(rx, ry), fill=BOT)
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
    d.text((tx0, ty + 34), f"Final score {score}.  Real speed." + ("  Left-right only." if LR_ONLY else ""), fill=DIM, font=FS)
    frames.append(im.convert("P", palette=Image.ADAPTIVE, colors=24))
frames += [frames[-1]] * 15
frames[0].save(out, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=True)
print(out, len(frames), "frames; best 8 s =", best, "hits from", round(S[a]["t"], 1), "s")
