# Target-score video: a full 60-second run rebuilt from AimRecorder data in the player's own view, next to a model run
# on the SAME bot movement, tuned to a target score (e.g. 700). The model keeps a human reaction time (about 130 ms)
# and only varies how smooth it is and how well it reads the bot. No AI: a simple spring that follows the bot.
# Outputs: <out>_solo.mp4 (model only) and <out>_side.mp4 (real left, model right).
# Usage: python target_video.py <run csv> <real score> <target score> <out prefix>
import csv, json, math, os, subprocess, sys, statistics as st
from PIL import Image, ImageDraw, ImageFont
from aim_analysis import moving_ids, height_source
import config, scenario_profile

path, real_score, target, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
PROGRESS = os.environ.get("AIMSTATS_PROGRESS")
def progress(stage, pct):
    if PROGRESS:
        try: json.dump({"stage": stage, "pct": pct}, open(PROGRESS, "w"))
        except OSError: pass

HFOV, DT = config.fov(), 1 / 60
SCEN = os.path.basename(path)[18:].replace(".gz", "").replace(".csv", "").replace("_", " ").strip()
TITLE = " ".join(SCEN.split())
rows = list(csv.DictReader(config.open_run(path)))
IDS = moving_ids(rows)
SRC = height_source(rows, IDS)
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
resets = [i for i in range(1, n) if HITS[i] < HITS[i - 1]]      # the game zeroes the hit counter when the run really starts
start = resets[-1] if resets else next(i for i in range(1, n) if HITS[i] > HITS[i - 1])
end = max(i for i in range(n) if BOT[i] is not None)
hit_i = [i for i in range(start + 1, end) if BOT[i] and HITS[i] > HITS[i - 1]]

def hd(i): c, b = CAM[i], BOT[i]; return math.hypot(b[0] - c[0], b[1] - c[1])
def bot_yaw(i):
    c, b = CAM[i], BOT[i]; a = math.degrees(math.atan2(b[1] - c[1], b[0] - c[0]))
    return YAW[i] + ((a - YAW[i] + 180) % 360 - 180)
def raw_pitch(i): c, b = CAM[i], BOT[i]; return math.degrees(math.atan2(b[2] - c[2], hd(i)))

# bot size and visible height, the same way pb_video.py does it
HW = sorted(abs(math.tan(math.radians(bot_yaw(i) - YAW[i])) * hd(i)) for i in hit_i)[int(.98 * len(hit_i))]
OFFU = st.median(math.tan(math.radians(raw_pitch(i) - PIT[i])) * hd(i) for i in hit_i)
EST = abs(OFFU) > 3 * HW
if EST:   # recorded height unusable (older recordings of flying bots): take it from the aim at hit moments
    BP = [None] * n
    for a_, b_ in zip(hit_i, hit_i[1:]):
        for k in range(a_, b_ + 1): BP[k] = PIT[a_] + (PIT[b_] - PIT[a_]) * (k - a_) / (b_ - a_)
    for k in range(0, hit_i[0]): BP[k] = PIT[hit_i[0]]
    for k in range(hit_i[-1], n): BP[k] = PIT[hit_i[-1]]
    BP = [st.mean(BP[max(0, k - 3):k + 4]) for k in range(n)]
else:
    BP = [raw_pitch(i) - math.degrees(math.atan(OFFU / hd(i))) if BOT[i] else None for i in range(n)]
PROFILE = scenario_profile.bot_profile(SCEN)                   # bot shape from the scenario's bot file
SPHERE = PROFILE.get("BotType") == "SPHERE" if PROFILE else False
if SPHERE and PROFILE.get("SphereRadiusMin") and not PROFILE.get("SphereRandomRadius?"):
    HW = 30.0 * PROFILE["SphereRadiusMin"]
HH = HW if SPHERE else 2.2 * HW
BA = [None if BOT[i] is None else (bot_yaw(i), BP[i], hd(i)) for i in range(n)]

def on(i, ay, ap):
    if BA[i] is None: return False
    wx, wy = math.degrees(math.atan(HW / BA[i][2])), math.degrees(math.atan(HH / BA[i][2]))
    return abs(BA[i][0] - ay) <= wx and (EST or abs(BA[i][1] - ap) <= wy)
real_on = sum(on(i, YAW[i], PIT[i]) for i in range(start, end)) or 1
PER_FRAME = real_score / real_on                         # points per on-target frame, from the real run

def simulate(delay, w, pred):
    sy, sp, vy, vp = YAW[start], PIT[start], 0.0, 0.0
    out_ = []
    for i in range(n):
        if i < start: out_.append((YAW[i], PIT[i])); continue
        j = i - delay
        if BA[j] is not None and BA[j - 2] is not None:
            ty = BA[j][0] + pred * (BA[j][0] - BA[j - 2][0]) / 2 * delay
            tp = BA[j][1] + pred * (BA[j][1] - BA[j - 2][1]) / 2 * delay
            ay = w * w * (ty - sy) - 2 * w * vy; ap = w * w * (tp - sp) - 2 * w * vp
            vy += ay * DT; vp += ap * DT
        else:
            vy *= 0.9; vp *= 0.9                          # no bot on screen: ease to a stop
        sy += vy * DT; sp += vp * DT
        if EST: sp, vp = PIT[i], 0.0                       # height not measured: the model only works left-right
        out_.append((sy, sp))
    return out_

def score_of(sim):
    return round(PER_FRAME * sum(on(i, *sim[i]) for i in range(start, end)))

progress("Tuning the model", 2)
best = None
grid = [(w, 1.0 + x / 50) for w in (14, 18, 22, 26, 30, 34, 38, 42, 50, 60, 72) for x in range(0, 21, 2)]
for gi, (w, pred) in enumerate(grid):
    s = score_of(simulate(8, w, pred))
    if best is None or abs(s - target) < abs(best[0] - target): best = (s, w, pred)
    if gi % 10 == 0: progress("Tuning the model", 2 + int(18 * gi / len(grid)))
SIM_SCORE, W_, PRED = best
SIM = simulate(8, W_, PRED)
print(f"real {real_score} (on target {100 * real_on / (end - start):.0f}%), model {SIM_SCORE} with w={W_} pred={PRED}")

try:
    FB = ImageFont.truetype("arialbd.ttf", 30); FM = ImageFont.truetype("arialbd.ttf", 22); FS = ImageFont.truetype("arial.ttf", 18)
except Exception: FB = FM = FS = ImageFont.load_default()
BG_TOP, BG_BOT, GRID, BOTC, AIMC, INK, DIM = (44, 46, 48), (30, 31, 32), (78, 80, 82), (90, 225, 215), (255, 60, 60), (240, 240, 236), (170, 170, 164)
FLOOR = min(c[2] for c in CAM) - 350

def view(Wd, Ht, i, ay, ap, score, label, t_left):
    f = (Wd / 2) / math.tan(math.radians(HFOV / 2))
    im = Image.new("RGB", (Wd, Ht), BG_BOT); d = ImageDraw.Draw(im)
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
    if BOT[i] is not None:
        b = BOT[i]
        c = proj(b[0], b[1], cz0 + math.tan(math.radians(BP[i])) * hd(i))
        if c:
            rx, ry = max(3, HW / hd(i) * f), max(3 if SPHERE else 6, HH / hd(i) * f)
            d.rounded_rectangle([c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry], radius=rx, fill=BOTC)
    d.ellipse([Wd / 2 - 3, Ht / 2 - 3, Wd / 2 + 3, Ht / 2 + 3], fill=AIMC)
    tl_ = max(0, math.ceil(t_left - 1e-6)); d.text((Wd / 2, 28), f"{tl_ // 60}:{tl_ % 60:02d}", fill=INK, font=FB, anchor="mm")
    d.text((Wd / 2, 62), f"{score}", fill=INK, font=FM, anchor="mm")
    d.text((Wd / 2, Ht - 30), TITLE, fill=INK, font=FS, anchor="mm")
    d.text((16, 14), label, fill=DIM, font=FM)
    return im

real_cum = [max(0, HITS[i] - HITS[start]) if i >= start else 0 for i in range(n)]
sim_cum, accu = [], 0
for i in range(n):
    if start <= i < end and on(i, *SIM[i]): accu += PER_FRAME
    sim_cum.append(round(accu))

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

run_len = (end - start) * DT
tl = lambda i: 60 - max(0, (i - start) * DT) * 60 / run_len
MODEL = f"Model tuned to {target}" + (f" (closest it got: {SIM_SCORE})" if abs(SIM_SCORE - target) > 0.03 * target else "")
write(out + "_solo.mp4", 1280, 720, lambda i, final=False: view(1280, 720, min(i, end - 1), *SIM[min(i, end - 1)],
      SIM_SCORE if final else sim_cum[i], MODEL, 0 if final else tl(i)), 20, 50)
def side(i, final=False):
    i = min(i, end - 1)
    im = Image.new("RGB", (1920, 560), (14, 14, 13))
    im.paste(view(944, 531, i, YAW[i], PIT[i], real_score if final else real_cum[i], f"You, real run ({real_score})", 0 if final else tl(i)), (10, 18))
    im.paste(view(944, 531, i, *SIM[i], SIM_SCORE if final else sim_cum[i], MODEL, 0 if final else tl(i)), (966, 18))
    return im
write(out + "_side.mp4", 1920, 560, side, 50, 99)
progress("Done", 100)
print(json.dumps({"model_score": SIM_SCORE, "target": target}))
