# Target-score video: a full 60-second run rebuilt from AimRecorder data in the player's own view, next to a model run
# on the SAME bot movement, tuned to a target score (e.g. 700). See model_run.py for the model (no AI).
# Outputs: <out>_solo.mp4 (model only) and <out>_side.mp4 (real left, model right).
# Usage: python target_video.py <run csv> <real score> <target score> <out prefix>
import json, os, subprocess, sys
from PIL import Image
import config
from model_run import Run, model_check, tracking_run, NOT_AVAILABLE

path, real_score, target, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
PROGRESS = os.environ.get("AIMSTATS_PROGRESS")
def progress(stage, pct):
    if PROGRESS:
        try: json.dump({"stage": stage, "pct": pct}, open(PROGRESS, "w"))
        except OSError: pass

ok, why = model_check(os.path.basename(path)[18:].replace(".gz", "").replace(".csv", ""))
if not ok:                                          # the bot reacts to hits: the recorded movement can't be reused
    print(NOT_AVAILABLE, f"({why})"); sys.exit(3)
if not tracking_run(path): print("Not available: model videos are for tracking runs only."); sys.exit(3)
R = Run(path, real_score)
progress("Tuning the model", 2)
R.tune(target, lambda f: progress("Tuning the model", 2 + int(18 * f)))
print(f"real {real_score}, model {R.sim_score} with w={R.w} pred={R.pred}")
start, end = R.start, R.end


def write(name, Wd, Ht, frame_fn, p0, p1):
    p = subprocess.Popen([config.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{Wd}x{Ht}", "-r", "30", "-i", "-",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-preset", "veryfast", "-movflags", "+faststart", name],
                         stdin=subprocess.PIPE, creationflags=config.NO_WINDOW)
    lead = frame_fn(start).tobytes()                     # 2 s still of the start position
    for _ in range(60): p.stdin.write(lead)
    for i in range(start, end, 2):
        p.stdin.write(frame_fn(i).tobytes())
        if (i - start) % 120 == 0: progress("Drawing the video", p0 + int((p1 - p0) * (i - start) / (end - start)))
    last = frame_fn(end, final=True).tobytes()           # hold the final score for 2 s
    for _ in range(60): p.stdin.write(last)
    p.stdin.close(); p.wait()
    print("wrote", name)


NOTE = "Bot height estimated from hits" if R.EST else ""
MODEL = f"Model tuned to {target}" + (f" (closest it got: {R.sim_score})" if abs(R.sim_score - target) > 0.03 * target else "")     + (", same movement as your run" if R.moves else "")
def solo(i, final=False):
    i = min(i, end - 1)
    return R.view(1280, 720, i, *R.sim[i], R.sim_score if final else R.sim_cum[i], MODEL, 0 if final else R.t_left(i))
def side(i, final=False):
    i = min(i, end - 1)
    im = Image.new("RGB", (1920, 560), (14, 14, 13))
    im.paste(R.view(944, 531, i, R.YAW[i], R.PIT[i], real_score if final else R.real_cum[i], f"You, real run ({real_score})", 0 if final else R.t_left(i)), (10, 18))
    im.paste(R.view(944, 531, i, *R.sim[i], R.sim_score if final else R.sim_cum[i], MODEL, 0 if final else R.t_left(i)), (966, 18))
    if NOTE:
        from PIL import ImageDraw
        ImageDraw.Draw(im).text((1904, 556), NOTE, fill=(150, 150, 146), anchor="rd")
    return im
write(out + "_solo.mp4", 1280, 720, solo, 20, 50)
write(out + "_side.mp4", 1920, 560, side, 50, 99)
progress("Done", 100)
print(json.dumps({"model_score": R.sim_score, "target": target}))
