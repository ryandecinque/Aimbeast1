# Renders full 60-second runs from AimRecorder data, in Ryan's own view (103 horizontal FOV, 16:9):
#  - the real run (his camera), and
#  - a model run on the SAME bot movement, tuned to a target score (e.g. Master 3, 726).
# Outputs: <out>_solo.mp4 (model only) and <out>_side.mp4 (real left, model right).
# Usage: python ideal_run_video.py <run csv> <real score> <target score> <out prefix>
import csv, math, subprocess, sys, statistics as st
from PIL import Image, ImageDraw, ImageFont

path, real_score, target, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
HFOV = 103.0
DT = 1 / 60

rows = list(csv.DictReader(open(path, encoding="utf-8")))
T, CAM, YAW, PIT, BOT, HITS = [], [], [], [], [], []
acc = prev = None
for r in rows:
    y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y
    T.append(float(r["t"])); YAW.append(acc); PIT.append(float(r["pitch"])); HITS.append(int(r["hits"]))
    CAM.append((float(r["cam_x"]), float(r["cam_y"]), float(r["cam_z"])))
    BOT.append(None if r["b1_x"] in ("", "0.0") else (float(r["b1_x"]), float(r["b1_y"]), float(r["b1_z"])))
n = len(T)

def bot_angles(i):
    if BOT[i] is None: return None
    c, b = CAM[i], BOT[i]
    dx, dy, dz = b[0] - c[0], b[1] - c[1], b[2] - c[2]
    by = math.degrees(math.atan2(dy, dx)); bp = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    by = YAW[i] + ((by - YAW[i] + 180) % 360 - 180)          # unwrap next to the camera's yaw
    return by, bp, math.sqrt(dx * dx + dy * dy + dz * dz)
BA = [bot_angles(i) for i in range(n)]

# run window: from the first hit to the last sample with a bot
resets = [i for i in range(1, n) if HITS[i] < HITS[i - 1]]      # the game zeroes the hit counter when the run really starts
start = resets[-1] if resets else next(i for i in range(1, n) if HITS[i] > HITS[i - 1])
# the bot moves to its start point a few samples after the counter reset: start the picture there
VIEW0 = next((i for i in range(start, min(n, start + 30)) if BOT[i] and BOT[i - 1] and math.dist(BOT[i], BOT[i - 1]) > 500), start)
TELEPORTS = [i for i in range(start + 60, n) if BOT[i] and BOT[i - 1] and math.dist(BOT[i], BOT[i - 1]) > 500]
end = max(i for i in range(n) if BA[i] is not None)

# target size (degrees) the same way the analysis measures it: aim error at the moments hits landed
hx = sorted(abs(BA[i][0] - YAW[i]) for i in range(start, end) if BA[i] and HITS[i] > HITS[i - 1])
hy = sorted(abs(BA[i][1] - PIT[i]) for i in range(start, end) if BA[i] and HITS[i] > HITS[i - 1])
WX, WY = hx[int(.9 * len(hx))], hy[int(.9 * len(hy))]
on = lambda i, ay, ap: BA[i] is not None and abs(BA[i][0] - ay) <= WX and abs(BA[i][1] - ap) <= WY
real_on = sum(on(i, YAW[i], PIT[i]) for i in range(start, end))
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
        out_.append((sy, sp))
    return out_

def score_of(sim):
    return round(PER_FRAME * sum(on(i, *sim[i]) for i in range(start, end)))

# tune: keep Ryan's reaction time (about 130 ms = 8 samples); vary only smoothness and how well it reads the bot
best = None
for w in (24, 26, 28, 30, 32, 34, 36):
    for pred in [1.0 + x / 50 for x in range(0, 21)]:
        s = score_of(simulate(8, w, pred))
        if best is None or abs(s - target) < abs(best[0] - target): best = (s, w, pred)
SIM_SCORE, W_, PRED = best
SIM = simulate(8, W_, PRED)
print(f"real {real_score} (on target {100*real_on/(end-start):.0f}%), model {SIM_SCORE} with w={W_} pred={PRED}, "
      f"on target {100*sum(on(i,*SIM[i]) for i in range(start,end))/(end-start):.0f}%")

# ---- rendering ------------------------------------------------------------------
try:
    FB = ImageFont.truetype("arialbd.ttf", 30); FM = ImageFont.truetype("arialbd.ttf", 22); FS = ImageFont.truetype("arial.ttf", 18)
except Exception: FB = FM = FS = ImageFont.load_default()
BG_TOP, BG_BOT, GRID, BOTC, AIMC, INK, DIM = (44, 46, 48), (30, 31, 32), (78, 80, 82), (90, 225, 215), (255, 60, 60), (240, 240, 236), (170, 170, 164)
med_d = st.median(BA[i][2] for i in range(start, end) if BA[i])
BOT_R = med_d * math.tan(math.radians(2.5))             # capsule size matched to the stream footage (56 x 88 px at 1600 wide)
BOT_HH = med_d * math.tan(math.radians(3.95))
FLOOR = st.median(BOT[i][2] for i in range(start, end) if BOT[i]) - BOT_HH * 1.6

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
    # sky/wall gradient above the horizon
    hz = proj(cx0 + 1e6 * cy_, cy0 + 1e6 * sy_, cz0)
    hy = hz[1] if hz else Ht / 2
    d.rectangle([0, 0, Wd, max(0, min(Ht, hy))], fill=BG_TOP)
    # floor grid
    step, span = 250, 2500
    gx0, gy0 = round(cx0 / step) * step, round(cy0 / step) * step
    for k in range(-span, span + 1, step):
        for a_, b_ in (((gx0 + k, gy0 - span), (gx0 + k, gy0 + span)), ((gx0 - span, gy0 + k), (gx0 + span, gy0 + k))):
            pts = []
            for s_ in range(0, 25):
                u = s_ / 24
                p = proj(a_[0] + (b_[0] - a_[0]) * u, a_[1] + (b_[1] - a_[1]) * u, FLOOR)
                if p: pts.append(p)
                elif len(pts) > 1: d.line(pts, fill=GRID, width=1); pts = []
                else: pts = []
            if len(pts) > 1: d.line(pts, fill=GRID, width=1)
    # bot
    if BOT[i] is not None:
        c = proj(*BOT[i])
        if c:
            k_ = med_d / BA[i][2]                         # same apparent size as on stream at the typical distance
            rx, ry = f * math.tan(math.radians(2.5)) * k_, f * math.tan(math.radians(3.95)) * k_
            d.rounded_rectangle([c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry], radius=rx, fill=BOTC)
    # crosshair, timer, score, name (laid out like the game's HUD)
    d.ellipse([Wd / 2 - 3, Ht / 2 - 3, Wd / 2 + 3, Ht / 2 + 3], fill=AIMC)
    tl_ = max(0, int(t_left)); tt = f"{tl_ // 60}:{tl_ % 60:02d}"
    d.text((Wd / 2, 28), tt, fill=INK, font=FB, anchor="mm")
    d.text((Wd / 2, 62), f"{score}", fill=INK, font=FM, anchor="mm")
    d.text((Wd / 2, Ht - 30), "ZEUS TRACK EVO - NOBLINK", fill=INK, font=FS, anchor="mm")
    d.text((16, 14), label, fill=DIM, font=FM)
    for r_, k in enumerate(TELEPORTS):
        if 0 <= i - k < 90:
            d.text((Wd / 2, 100), f"Round {r_ + 2} of {len(TELEPORTS) + 1}: the bot restarts far away", fill=(240, 200, 90), font=FM, anchor="mm")
    return im

def run_score(i, sim=None):
    if sim is None: return max(0, HITS[i] - HITS[start]) if i >= start else 0
    return round(PER_FRAME * sum(on(k, *sim[k]) for k in range(start, i + 1))) if i >= start else 0

# cumulative scores, computed once
real_cum = [run_score(i) for i in range(n)]
sim_cum, accu = [], 0
for i in range(n):
    if start <= i < end and on(i, *SIM[i]): accu += PER_FRAME
    sim_cum.append(round(accu))

def write(name, Wd, Ht, frame_fn):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{Wd}x{Ht}", "-r", "30", "-i", "-",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", "-movflags", "+faststart", name], stdin=subprocess.PIPE, creationflags=0x08000000)   # no console window popping up over the game
    lead = frame_fn(VIEW0).tobytes()                     # 3 s still of the start position (no countdown footage)
    for _ in range(90): p.stdin.write(lead)
    for i in range(VIEW0, end, 2):                       # the run, 30 fps
        p.stdin.write(frame_fn(i).tobytes())
    last = frame_fn(end, final=True).tobytes()           # hold the final score for 2 s
    for _ in range(60): p.stdin.write(last)
    p.stdin.close(); p.wait()
    print("wrote", name)

run_len = (end - start) * DT
tl = lambda i: 60 - max(0, (i - start) * DT) * 60 / run_len
write(out + "_solo.mp4", 1280, 720, lambda i, final=False: view(1280, 720, min(i, end - 1), *SIM[min(i, end - 1)], target if final else sim_cum[i], f"Model run tuned to Master 3 ({target})", 0 if final else tl(i)))
def side(i, final=False):
    if final:
        i = end - 1
        im = Image.new("RGB", (1920, 560), (14, 14, 13))
        im.paste(view(944, 531, i, YAW[i], PIT[i], real_score, f"Ryan, real run ({real_score})", 0), (10, 18))
        im.paste(view(944, 531, i, *SIM[i], target, f"Model, Master 3 ({target})", 0), (966, 18))
        return im
    im = Image.new("RGB", (1920, 560), (14, 14, 13))
    im.paste(view(944, 531, i, YAW[i], PIT[i], real_cum[i], f"Ryan, real run ({real_score})", tl(i)), (10, 18))
    im.paste(view(944, 531, i, *SIM[i], sim_cum[i], f"Model, Master 3 ({target})", tl(i)), (966, 18))
    return im
write(out + "_side.mp4", 1920, 560, side)
