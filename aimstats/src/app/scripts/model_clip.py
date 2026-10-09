# Side-by-side clip of one window of a recorded run: the real run on the left, a model run on the right on the SAME
# bot movement, tuned so the WHOLE run would score `factor` times the real score (default 1.2 = 20% better).
# The model keeps a human reaction time (about 130 ms); only smoothness and reading the bot vary (model_run.py).
# If the target is out of reach, the model uses the closest score it gets and the clip says so.
# Looping MP4 at real speed, plus a poster PNG next to it. Prints a JSON line: {"model_score", "target", "reached"}.
# Usage: python model_clip.py <run csv> <real score> <first sample> <last sample> <out.mp4> [factor]
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
import config
from model_run import Run, model_check, tracking_run, NOT_AVAILABLE

path, real, a, b, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
factor = float(sys.argv[6]) if len(sys.argv) > 6 else 1.2
target = round(factor * real)
ok, why = model_check(os.path.basename(path)[18:].replace(".gz", "").replace(".csv", ""))
if not ok:                                          # the bot reacts to hits: the recorded movement can't be reused
    print(NOT_AVAILABLE, f"({why})"); sys.exit(3)
if not tracking_run(path): print("Not available: model videos are for tracking runs only."); sys.exit(3)
R = Run(path, real)
R.tune(target)
reached = abs(R.sim_score - target) <= 0.03 * target
pct = round(100 * (factor - 1))
label = f"Model, {'+' if pct >= 0 else ''}{pct}%: {R.sim_score}" if reached else f"Model reached {R.sim_score} (the closest it could get to {target})"
if R.moves: label += ", same movement as your run"
try: FT = ImageFont.truetype("arialbd.ttf", 18)
except Exception: FT = ImageFont.load_default()
PW, PH = 800, 450
a, b = max(a, R.start), min(b, R.end - 1)


def frame(i):
    im = Image.new("RGB", (2 * PW + 30, PH + 20), (14, 14, 13))
    im.paste(R.view(PW, PH, i, R.YAW[i], R.PIT[i], R.real_cum[i], f"You: {real}", R.t_left(i)), (10, 10))
    im.paste(R.view(PW, PH, i, *R.sim[i], R.sim_cum[i], label, R.t_left(i)), (PW + 20, 10))
    return im


W, H = 2 * PW + 30, PH + 20
p = subprocess.Popen([config.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "30", "-i", "-",
                      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "medium", "-movflags", "+faststart", "-an", out],
                     stdin=subprocess.PIPE, creationflags=config.NO_WINDOW)
for i in range(a, b, 2): p.stdin.write(frame(i).tobytes())
p.stdin.close(); p.wait()
frame((a + b) // 2).save(out[:-4] + ".png")
print("wrote", out)
print(json.dumps({"model_score": R.sim_score, "target": target, "reached": reached, "moves": R.moves}))
