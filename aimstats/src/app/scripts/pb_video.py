# Full-run video of one real run, rebuilt from AimRecorder data in the player's own view (their FOV from the game's
# settings, 16:9). Recorder phase 5 files carry the visible body position, which flying bots move (their root doesn't).
# For scenarios where the recorded bot height is wrong (Sphere S, Air Track: the visible bot moves up and down
# but the recorded position doesn't), the bot's height is taken from the aim at hit moments and interpolated.
# Bot shape and size come from the scenario's bot profile (scenario_profile.py); capsule size falls back to the hits.
# Usage: python pb_video.py <run csv> <score> <scenario title> <out.mp4|out.gif> [caption]
#   .gif output: set CLIP=<first sample>,<last sample> for a short full-view clip (640x360, real speed)
import csv, math, subprocess, sys, statistics as st
from PIL import Image, ImageDraw, ImageFont
from aim_analysis import moving_ids, height_source, thin60
import config

path, score, title, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
caption = sys.argv[5] if len(sys.argv) > 5 else ""
HFOV, DT = config.fov(), 1 / 60
import os
OUT_FPS = int(os.environ.get("OUT_FPS", "30"))           # video frame rate: 30 (default), 60 or 120
RAW = list(csv.DictReader(config.open_run(path)))
ROWS60 = thin60(RAW)
CLIP_T = None
if os.environ.get("CLIP"):                                # CLIP is given in 60-a-second sample numbers: turn it into times
    _a, _b = (int(x) for x in os.environ["CLIP"].split(","))
    CLIP_T = (float(ROWS60[_a]["t"]), float(ROWS60[min(_b, len(ROWS60) - 1)]["t"]))
rows = RAW if (OUT_FPS > 60 and not os.environ.get("AIM_PATTERN")) else ROWS60
IDS = moving_ids(rows)
SRC = height_source(rows, IDS)          # "m" body / "s" sphere / "" root
P = lambda r, k, a: r[f"b{k}_{SRC}{a}"] if SRC and r.get(f"b{k}_{SRC}z") else r[f"b{k}_{a}"]
T, CAM, YAW, PIT, BOT, HITS = [], [], [], [], [], []
acc = prev = None
for r in rows:
    y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y
    T.append(float(r["t"])); YAW.append(acc); PIT.append(float(r["pitch"])); HITS.append(int(r["hits"]))
    CAM.append((float(r["cam_x"]), float(r["cam_y"]), float(r["cam_z"])))
    k = next((i for i in range(1, 9) if r.get(f"b{i}_x") not in (None, "", "0.0") and (r.get(f"b{i}_id") or str(i)) in IDS), None)
    BOT.append(None if k is None else (float(P(r, k, "x")), float(P(r, k, "y")), float(P(r, k, "z"))))
n = len(T)
resets = [i for i in range(1, n) if HITS[i] < HITS[i - 1]]
start = resets[-1] if resets else next(i for i in range(1, n) if HITS[i] > HITS[i - 1])
end = max(i for i in range(n) if BOT[i] is not None)
hit_i = [i for i in range(start + 1, end) if BOT[i] and HITS[i] > HITS[i - 1]]

def hd(i): c, b = CAM[i], BOT[i]; return math.hypot(b[0] - c[0], b[1] - c[1])
def bot_yaw(i):
    c, b = CAM[i], BOT[i]; a = math.degrees(math.atan2(b[1] - c[1], b[0] - c[0]))
    return YAW[i] + ((a - YAW[i] + 180) % 360 - 180)
def raw_pitch(i): c, b = CAM[i], BOT[i]; return math.degrees(math.atan2(b[2] - c[2], hd(i)))

# horizontal size from hit errors (world units); is the recorded height usable?
HW = sorted(abs(math.tan(math.radians(bot_yaw(i) - YAW[i])) * hd(i)) for i in hit_i)[int(.98 * len(hit_i))]   # hits can't land outside the bot: the widest hits give its half-width
OFFU = st.median(math.tan(math.radians(raw_pitch(i) - PIT[i])) * hd(i) for i in hit_i)
EST = abs(OFFU) > 3 * HW
if EST:   # bot height from the aim at hit moments, linearly interpolated, lightly smoothed
    BP = [None] * n
    for a_, b_ in zip(hit_i, hit_i[1:]):
        for k in range(a_, b_ + 1): BP[k] = PIT[a_] + (PIT[b_] - PIT[a_]) * (k - a_) / (b_ - a_)
    for k in range(0, hit_i[0]): BP[k] = PIT[hit_i[0]]
    for k in range(hit_i[-1], n): BP[k] = PIT[hit_i[-1]]
    BP = [st.mean(BP[max(0, k - 3):k + 4]) for k in range(n)]
else:
    BP = [raw_pitch(i) - math.degrees(math.atan(OFFU / hd(i))) if BOT[i] else None for i in range(n)]
import scenario_profile
PROFILE = scenario_profile.bot_profile(title)
SPHERE = PROFILE.get("BotType") == "SPHERE" if PROFILE else "SPHERE" in title.upper()
if SPHERE and PROFILE.get("SphereRadiusMin") and not PROFILE.get("SphereRandomRadius?"):
    HW = 30.0 * PROFILE["SphereRadiusMin"]        # base ball radius ~30 units (fits the hits on Sphere S and Air Track)
HH = HW if SPHERE else 2.2 * HW
BOTW = []   # visible bot centre in world space
for i in range(n):
    if BOT[i] is None: BOTW.append(None); continue
    c, b = CAM[i], BOT[i]
    BOTW.append((b[0], b[1], c[2] + math.tan(math.radians(BP[i])) * hd(i)))
FLOOR = min(c[2] for c in CAM) - 350
print(f"bot half-width {HW:.0f} units, height {'estimated from hits' if EST else 'recorded'}; run {T[end] - T[start]:.1f}s")

try:
    FB = ImageFont.truetype("arialbd.ttf", 34); FM = ImageFont.truetype("arialbd.ttf", 24); FS = ImageFont.truetype("arial.ttf", 17)
    FBIG = ImageFont.truetype("arialbd.ttf", 64)
except Exception: FB = FM = FS = FBIG = ImageFont.load_default()
BG_TOP, BG_BOT, GRID, BOTC, AIMC, INK, DIM, ACC = (44, 46, 48), (30, 31, 32), (78, 80, 82), (90, 225, 215), (255, 60, 60), (240, 240, 236), (170, 170, 164), (255, 200, 90)
Wd, Ht = 1280, 720

def frame(i, final=False):
    f = (Wd / 2) / math.tan(math.radians(HFOV / 2))
    im = Image.new("RGB", (Wd, Ht), BG_BOT); d = ImageDraw.Draw(im)
    ay, ap = YAW[i], PIT[i]
    cy_, sy_ = math.cos(math.radians(ay)), math.sin(math.radians(ay))
    cp, sp_ = math.cos(math.radians(ap)), math.sin(math.radians(ap))
    cx0, cy0, cz0 = CAM[i]
    def proj(x, y, z):
        dx, dy, dz = x - cx0, y - cy0, z - cz0
        fwd = dx * cy_ + dy * sy_; right = -dx * sy_ + dy * cy_
        fz = fwd * cp + dz * sp_; up = -fwd * sp_ + dz * cp
        if fz < 5: return None
        return (Wd / 2 + right / fz * f, Ht / 2 - up / fz * f)
    hz = proj(cx0 + 1e6 * cy_, cy0 + 1e6 * sy_, cz0)
    hy = hz[1] if hz else (0 if ap < 0 else Ht)
    d.rectangle([0, 0, Wd, max(0, min(Ht, hy))], fill=BG_TOP)
    step, span = 250, 2500
    gx0, gy0 = round(cx0 / step) * step, round(cy0 / step) * step
    for k in range(-span, span + 1, step):
        for a_, b_ in (((gx0 + k, gy0 - span), (gx0 + k, gy0 + span)), ((gx0 - span, gy0 + k), (gx0 + span, gy0 + k))):
            pts = []
            for s_ in range(25):
                u = s_ / 24
                p = proj(a_[0] + (b_[0] - a_[0]) * u, a_[1] + (b_[1] - a_[1]) * u, FLOOR)
                if p: pts.append(p)
                elif len(pts) > 1: d.line(pts, fill=GRID, width=1); pts = []
                else: pts = []
            if len(pts) > 1: d.line(pts, fill=GRID, width=1)
    if BOTW[i] is not None:
        c = proj(*BOTW[i])
        if c:
            fz = math.hypot(BOTW[i][0] - cx0, BOTW[i][1] - cy0)
            rx, ry = max(3, HW / fz * f), max(3 if SPHERE else 6, HH / fz * f)
            d.rounded_rectangle([c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry], radius=rx, fill=BOTC)
    d.ellipse([Wd / 2 - 3, Ht / 2 - 3, Wd / 2 + 3, Ht / 2 + 3], fill=AIMC)
    run_len = T[end] - T[start]
    t_left = 0 if final else 60 - max(0, T[i] - T[start]) * 60 / run_len
    tl_ = max(0, math.ceil(t_left - 1e-6)) if not final else 0
    d.text((Wd / 2, 32), f"{tl_ // 60}:{tl_ % 60:02d}", fill=INK, font=FB, anchor="mm")
    sc = score if final else (max(0, HITS[i] - HITS[start]) if i >= start else 0)
    d.text((Wd / 2, 70), f"{sc}", fill=INK, font=FM, anchor="mm")
    d.text((Wd / 2, Ht - 34), title, fill=INK, font=FS, anchor="mm")
    if caption: d.text((18, 16), caption, fill=DIM, font=FM)
    d.text((Wd - 18, Ht - 14), "Rebuilt from your aim data" + (" (bot height estimated from hits)" if EST else ""), fill=(120, 120, 116), font=FS, anchor="rd")
    if final:
        d.text((Wd / 2, Ht / 2 - 90), f"{score}", fill=ACC, font=FBIG, anchor="mm")
    return im

import bisect
_gaps = sorted(T[i + 1] - T[i] for i in range(n - 1) if T[i + 1] > T[i])
REC_FPS = (120 if len(T) / max(1e-9, T[-1] - T[0]) > 90 else 60) if n > 1 else 60     # recorder writes 60 or 120 a second
FPS = min(OUT_FPS, max(30, REC_FPS))
if FPS < OUT_FPS: print(f"note: this recording has {REC_FPS} snapshots a second, so the video is {FPS} fps, not {OUT_FPS}")
def frames_between(t0, t1):
    k, out_ = 0, []
    while t0 + k / FPS <= t1:
        out_.append(min(n - 1, bisect.bisect_left(T, t0 + k / FPS))); k += 1
    return out_

if out.lower().endswith(".mp4") and os.environ.get("CLIP"):    # short full-view clip: real speed, loops on the site
    a, b = bisect.bisect_left(T, CLIP_T[0]), bisect.bisect_left(T, CLIP_T[1])
    p = subprocess.Popen([config.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{Wd}x{Ht}", "-r", str(FPS), "-i", "-",
                          "-vf", "scale=960:540", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "medium", "-movflags", "+faststart", "-an", out],
                         stdin=subprocess.PIPE, creationflags=config.NO_WINDOW)
    for i in frames_between(T[a], T[b]): p.stdin.write(frame(i).tobytes())
    p.stdin.close(); p.wait()
    frame((a + b) // 2).resize((960, 540), Image.LANCZOS).save(out[:-4] + ".png")
    print("wrote", out); sys.exit()
if out.lower().endswith(".gif"):
    import os
    a, b = bisect.bisect_left(T, CLIP_T[0]), bisect.bisect_left(T, CLIP_T[1])
    frames = [frame(i).resize((640, 360), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=48) for i in frames_between(T[a], T[b])[::max(1, FPS // 30)]]
    frames += [frames[-1]] * 12
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=True)
    frames[len(frames) // 2].convert("RGB").save(out[:-4] + ".png")
    print("wrote", out, len(frames), "frames"); sys.exit()
p = subprocess.Popen([config.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{Wd}x{Ht}", "-r", str(FPS), "-i", "-",
                      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21", "-preset", "medium", "-movflags", "+faststart", out], stdin=subprocess.PIPE, creationflags=config.NO_WINDOW)
lead = frame(start).tobytes()
for _ in range(2 * FPS): p.stdin.write(lead)                 # 2 s still of the start
for i in frames_between(T[start], T[end - 1]): p.stdin.write(frame(i).tobytes())
last = frame(end - 1, final=True).tobytes()
for _ in range(int(2.5 * FPS)): p.stdin.write(last)                 # hold the final score 2.5 s
p.stdin.close(); p.wait()
print("wrote", out, f"({FPS} fps)")
