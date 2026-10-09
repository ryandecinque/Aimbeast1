# Clip of the best 8 seconds (most hits) of one recorded run, at real speed, in the full in-game view (looping MP4,
# drawn by pb_video.py). Usage: python best_run_gif.py <run csv> <score> <label> <out.mp4>
import csv, math, sys
from PIL import Image, ImageDraw, ImageFont

path, score, label, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
from aim_analysis import moving_ids, thin60
import config
rows = thin60(list(csv.DictReader(config.open_run(path))))
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
# full in-game view (same renderer as the PB video), not zoomed: this is a showcase, not a technique clip
import os, re, subprocess
title = re.sub(r",? best run.*$", "", label).strip()
out = out[:-4] + ".mp4" if out.lower().endswith(".gif") else out     # looping MP4: sharper and ~10x smaller than a GIF
ok, msg = config.run_script("pb_video.py", path, score, title.upper(), out, f"Best 8 seconds of {score}", env={"CLIP": f"{a},{b}"})
print(msg[-600:])
if not ok: sys.exit(1)
print(out, "best 8 s =", best, "hits from", round(S[a]["t"], 1), "s")
print("WINDOW", a, b)
