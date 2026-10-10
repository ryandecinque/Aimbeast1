# Renders Robidashka's ANY STRAFES run (recon.npz) as a full in-game view, 1920x1080 at 60 fps, from their own
# camera position and 103 FOV. scale = 1 is their real aim; scale < 1 makes every miss smaller by that factor,
# pulled toward their usual aim point on the bot (better.py). Bots, paths and timing are the same in every version.
# Usage: python render.py <scale> <out.mp4> "<label line>" ["<second label line>"]
import json, math, os, subprocess, sys, numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import better
S, OUT, LABEL = float(sys.argv[1]), sys.argv[2], sys.argv[3]
LABEL2 = sys.argv[4] if len(sys.argv) > 4 else ""
D = np.load(os.path.join(HERE, "recon.npz"))
CAM = np.array([-200.0, 0.0, 3362.2]); BODY_Z, HALF_H, F = 3301.6, 96.9, 960 / math.tan(math.radians(103 / 2))
R_VIS = HALF_H * 0.236 * 2 / 2 * 1.0       # visible capsule radius: width/height on screen = 0.236 -> ~22.9 units
K, C, V0 = better.K, better.C, better.V0
W, H = 1920, 1080
n = len(D["t"])
alive = D["alive"].astype(bool)

# --- camera for this version: aim at the (scaled) point on the bot ---
yaw = np.full(n, np.nan); pit = np.full(n, np.nan); u2 = np.full(n, np.nan); v2 = np.full(n, np.nan)
for j in range(n):
    if not alive[j] or np.isnan(D["u"][j]): continue
    u, v = D["u"][j], D["v"][j]
    uu, vv = S * u, V0 + S * (v - V0)
    a = math.atan2(D["by"][j] - CAM[1], D["bx"][j] - CAM[0]); d = D["dist"][j]
    rw = D["hw"][j] * d / F                       # the bot's half-width on screen, in world units at its distance
    px = D["bx"][j] - math.sin(a) * uu * rw; py = D["by"][j] + math.cos(a) * uu * rw
    pz = BODY_Z + HALF_H - vv * 2 * HALF_H
    yaw[j] = math.atan2(py - CAM[1], px - CAM[0]); pit[j] = math.atan2(pz - CAM[2], math.hypot(px - CAM[0], py - CAM[1]))
    u2[j], v2[j] = uu, vv
ok = ~np.isnan(yaw)
jj = np.arange(n)
yaw = np.interp(jj, jj[ok], np.unwrap(yaw[ok])); pit = np.interp(jj, jj[ok], pit[ok])   # gaps between bots: turn smoothly
if S == 1.0:   # check: rebuilding the real aim reproduces the camera found from the video
    dif = np.degrees(np.abs((yaw[ok] - D["yaw"][ok] + np.pi) % (2 * np.pi) - np.pi))
    print("real-aim camera vs video camera, degrees: median", round(float(np.median(dif)), 3), "98%", round(float(np.percentile(dif, 98)), 3))

# --- score: shots at 33.3 a second, a hit when the crosshair is on the head (same rule as better.py) ---
su, sv = S * better.U, V0 + S * (better.V - V0)
shot_hit = np.nan_to_num((np.abs(su) <= C) & (sv >= 0) & (sv <= K)).astype(int)
shot_t = np.array(better.cal.shots) - better.cal.T0
cum = np.cumsum(shot_hit)
FINAL = int(cum[-1])
print("score", FINAL)

try:
    FB = ImageFont.truetype("arialbd.ttf", 44); FM = ImageFont.truetype("arialbd.ttf", 56); FS = ImageFont.truetype("arial.ttf", 26)
    FL = ImageFont.truetype("arialbd.ttf", 36); FBIG = ImageFont.truetype("arialbd.ttf", 150); FT = ImageFont.truetype("arialbd.ttf", 30)
except Exception: FB = FM = FS = FL = FBIG = FT = ImageFont.load_default()
SKY, WALL, WALL_L, FLOOR, LINE, FLINE = (118, 119, 121), (150, 158, 166), (162, 170, 178), (112, 119, 128), (128, 135, 143), (98, 104, 112)
BOTC, OUTL, HEADL, AIMC, INK, DIM, ACC = (8, 8, 8), (235, 225, 40), (120, 110, 30), (255, 50, 50), (245, 245, 240), (40, 42, 46), (255, 210, 80)
FLOOR_Z, WALL_TOP = 3200.0, 3600.0
# room outline (from DECEIVING STRAFES.map, inner faces): back wall y=-1000, side walls, wall behind the player y=200
ROOM = [(-1200, 200), (-1200, -1000), (800, -1000), (800, 200)]

def cam_basis(y, p):
    cy, sy, cp, sp = math.cos(y), math.sin(y), math.cos(p), math.sin(p)
    return cy, sy, cp, sp

def to_cam(P, B):
    cy, sy, cp, sp = B
    dx, dy, dz = P[0] - CAM[0], P[1] - CAM[1], P[2] - CAM[2]
    fh = dx * cy + dy * sy; right = -dx * sy + dy * cy
    return (fh * cp + dz * sp, right, -fh * sp + dz * cp)          # forward, right, up

def clip_poly(pts):
    """Clip a camera-space polygon to forward > 1 and project it."""
    out = []
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        ina, inb = a[0] > 1, b[0] > 1
        if ina: out.append(a)
        if ina != inb:
            k = (1 - a[0]) / (b[0] - a[0]); out.append(tuple(a[q] + k * (b[q] - a[q]) for q in range(3)))
    return [(W / 2 + F * c[1] / c[0], H / 2 - F * c[2] / c[0]) for c in out]

def seg(d, P, Q, B, fill, width=1):
    a, b = to_cam(P, B), to_cam(Q, B)
    if a[0] <= 1 and b[0] <= 1: return
    if a[0] <= 1: k = (1 - a[0]) / (b[0] - a[0]); a = tuple(a[q] + k * (b[q] - a[q]) for q in range(3))
    if b[0] <= 1: k = (1 - b[0]) / (a[0] - b[0]); b = tuple(b[q] + k * (a[q] - b[q]) for q in range(3))
    d.line([(W / 2 + F * a[1] / a[0], H / 2 - F * a[2] / a[0]), (W / 2 + F * b[1] / b[0], H / 2 - F * b[2] / b[0])], fill=fill, width=width)

def frame(j, final=False):
    im = Image.new("RGB", (W, H), SKY); d = ImageDraw.Draw(im)
    B = cam_basis(yaw[j], pit[j])
    fl = clip_poly([to_cam((x, y, FLOOR_Z), B) for x, y in ROOM])
    if len(fl) > 2: d.polygon(fl, fill=FLOOR)
    for (x1, y1), (x2, y2) in zip(ROOM, ROOM[1:]):
        poly = clip_poly([to_cam(p, B) for p in ((x1, y1, FLOOR_Z), (x2, y2, FLOOR_Z), (x2, y2, WALL_TOP), (x1, y1, WALL_TOP))])
        if len(poly) > 2: d.polygon(poly, fill=WALL if y1 == y2 else WALL_L)
    for g in range(-1200, 801, 100): seg(d, (g, -1000, FLOOR_Z), (g, 200, FLOOR_Z), B, FLINE)
    for g in range(-1000, 201, 100): seg(d, (-1200, g, FLOOR_Z), (800, g, FLOOR_Z), B, FLINE)
    for z in range(3300, 3600, 100): seg(d, (-1200, -1000, z), (800, -1000, z), B, LINE)
    for x in range(-1200, 801, 100): seg(d, (x, -1000, FLOOR_Z), (x, -1000, WALL_TOP), B, LINE)
    for (x1, y1), (x2, y2) in zip(ROOM, ROOM[1:]): seg(d, (x1, y1, FLOOR_Z), (x2, y2, FLOOR_Z), B, LINE, 2)
    # spawn marker
    mk = to_cam((-200, -800, FLOOR_Z + 2), B)
    if mk[0] > 1:
        mx, my = W / 2 + F * mk[1] / mk[0], H / 2 - F * mk[2] / mk[0]
        d.polygon([(mx - 11, my), (mx + 11, my), (mx, my - 11)], fill=(100, 200, 245))
    if alive[j] and not final:
        c = to_cam((D["bx"][j], D["by"][j], BODY_Z), B)
        if c[0] > 1:
            cx, cy = W / 2 + F * c[1] / c[0], H / 2 - F * c[2] / c[0]
            rx = R_VIS * F / c[0]; ry = HALF_H * F / c[0]
            d.rounded_rectangle([cx - rx - 3, cy - ry - 3, cx + rx + 3, cy + ry + 3], radius=rx + 3, fill=OUTL)
            d.rounded_rectangle([cx - rx, cy - ry, cx + rx, cy + ry], radius=rx, fill=BOTC)
            yh = cy - ry + K * 2 * ry                  # bottom of the head area
            d.line([(cx - rx + 2, yh), (cx + rx - 2, yh)], fill=HEADL, width=2)
    d.ellipse([W / 2 - 5, H / 2 - 5, W / 2 + 5, H / 2 + 5], fill=AIMC, outline=(30, 0, 0))
    t = D["t"][j]
    left = 0 if final else max(0, math.floor(90 - max(0.0, t)))
    d.rectangle([W / 2 - 70, 66, W / 2 + 70, 126], fill=(52, 54, 58))
    d.text((W / 2, 96), f"{left // 60}:{left % 60:02d}", fill=INK, font=FB, anchor="mm")
    sc = FINAL if final else (int(cum[np.searchsorted(shot_t, t, side="right") - 1]) if t >= 0 else 0)
    d.text((W / 2, 900), f"{sc}", fill=INK, font=FM, anchor="mm")
    d.text((W / 2, 960), "ANY STRAFES", fill=INK, font=FT, anchor="mm")
    d.rectangle([0, 0, W, 54], fill=(28, 29, 31))
    d.text((24, 27), LABEL, fill=ACC, font=FL, anchor="lm")
    if LABEL2: d.text((W - 24, 27), LABEL2, fill=INK, font=FS, anchor="rm")
    d.text((W - 24, H - 20), "Rebuilt from Robidashka's 360 fps video. Line on the bot = bottom of the head area.", fill=DIM, font=FS, anchor="rd")
    if final:
        d.rectangle([W / 2 - 330, H / 2 - 170, W / 2 + 330, H / 2 + 120], fill=(28, 29, 31))
        d.text((W / 2, H / 2 - 120), "FINAL SCORE", fill=INK, font=FL, anchor="mm")
        d.text((W / 2, H / 2 - 10), f"{FINAL}", fill=ACC, font=FBIG, anchor="mm")
        d.text((W / 2, H / 2 + 85), f"{100 * FINAL / 3000:.1f}% of 3000 shots", fill=INK, font=FS, anchor="mm")
    return im

if __name__ == "__main__":
    if os.environ.get("STILL"):
        frame(int(os.environ["STILL"])).save(OUT); sys.exit()
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "60", "-i", "-",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "slow", "-tune", "animation",
                          "-movflags", "+faststart", OUT], stdin=subprocess.PIPE, creationflags=0x08000000)
    first = frame(0).tobytes()
    for _ in range(60): p.stdin.write(first)                      # 1 s still before the start
    for j in range(n): p.stdin.write(frame(j).tobytes())
    last = frame(n - 1, final=True).tobytes()
    for _ in range(180): p.stdin.write(last)                      # hold the final score 3 s
    p.stdin.close(); p.wait()
    print("wrote", OUT, round(os.path.getsize(OUT) / 1e6, 1), "MB")
