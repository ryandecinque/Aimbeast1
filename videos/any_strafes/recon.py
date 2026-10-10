# Rebuilds Robidashka's run in world space from the video measurements (frames_*.npz), 60 samples a second.
# Camera: fixed at (-200, 0, 3362.2), 103 horizontal FOV (checked from the bot's size at each spawn).
# Per sample: from the bot's top, bottom and centre on screen -> camera pitch, the bot's distance and its angle from
# the view centre. The cyan spawn marker (a fixed point at (-200, -800) on the floor) gives the camera's turn; when the
# bot hides it, the bot's world direction is joined up across the gap (it's at the spawn point when it appears).
# Also stores where the crosshair sits on the bot in bot sizes (u: left-right in half-widths, v: down from the top
# as a share of the height), which is what the score is computed from (calibrate.py).
# Output: recon.npz. Usage: python recon.py
import glob, json, math, os, numpy as np
from scipy.optimize import least_squares
from scipy.signal import savgol_filter
HERE = os.path.dirname(os.path.abspath(__file__))
R = np.concatenate([np.load(f)["rows"] for f in sorted(glob.glob(os.path.join(HERE, "frames_*.npz")))])
FPS, F = 360.0, 960 / math.tan(math.radians(103 / 2))
CAM = np.array([-200.0, 0.0, 3362.2])
SPAWN = np.array([-200.0, -800.0])
BODY_Z, HALF_H = 3301.6, 96.9          # silhouette half-height in world units (185 px at 800 units, 103 FOV)
T0, LIFE, PERIOD = 1.356, 7.04, 7.5415
STEP = 6                               # 360 -> 60 samples a second

def proj(p, yaw, pit):
    d = p - CAM
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pit), math.sin(pit)
    fh = d[0] * cy + d[1] * sy; right = -d[0] * sy + d[1] * cy
    fwd = fh * cp + d[2] * sp; up = -fh * sp + d[2] * cp
    return 960 + F * right / fwd, 540 - F * up / fwd

def geom(r):
    if r[2] != 1: return None
    yt = (r[5] + r[12]) / 2 if not np.isnan(r[12]) else r[5] - 2
    yb = (r[6] + r[13]) / 2 if not np.isnan(r[13]) else r[6] + 2
    xl = (r[3] + r[10]) / 2 if not np.isnan(r[10]) else r[3] - 2
    xr = (r[4] + r[11]) / 2 if not np.isnan(r[11]) else r[4] + 2
    return yt, yb, (xl + xr) / 2, (xr - xl) / 2

def solve_bot(g, x0):
    """Camera pitch, the bot's angle from the view centre, and its distance (camera yaw = 0 in this frame)."""
    yt, yb, xc, hw = g
    def res(q):
        pit, b, d = q
        p = np.array([CAM[0] + d * math.cos(b), CAM[1] + d * math.sin(b), 0.0])
        top = proj(np.array([p[0], p[1], BODY_Z + HALF_H]), 0.0, pit)
        bot = proj(np.array([p[0], p[1], BODY_Z - HALF_H]), 0.0, pit)
        mid = proj(np.array([p[0], p[1], BODY_Z]), 0.0, pit)
        return [top[1] - yt, bot[1] - yb, mid[0] - xc]
    s = least_squares(res, x0, x_scale=[0.01, 0.01, 50])
    return s.x

def tri_yaw(xt, pit, z):
    """Camera yaw that puts the spawn marker (fixed world point) at screen x = xt."""
    p = np.array([SPAWN[0], SPAWN[1], z])
    yaw = math.atan2(p[1] - CAM[1], p[0] - CAM[0]) - math.atan((xt - 960) / F)
    for _ in range(4):
        x1 = proj(p, yaw, pit)[0]; x2 = proj(p, yaw + 1e-4, pit)[0]
        yaw -= (x1 - xt) / ((x2 - x1) / 1e-4)
    return yaw

if __name__ == "__main__":
    idx = list(range(int(T0 * FPS), int((T0 + 11 * PERIOD + LIFE) * FPS) + 1, STEP))
    out = dict(t=[], alive=[], pit=[], beta=[], dist=[], tri=[], u=[], v=[], hw=[], hh=[], life=[])
    x0 = [0.0, 0.0, 800.0]
    for i in idx:
        t = i / FPS
        k = int((t - T0) // PERIOD); al = 0 <= k < 12 and (t - T0) - k * PERIOD < LIFE
        g = geom(R[i]) if al else None
        out["t"].append(t - T0); out["alive"].append(bool(g)); out["life"].append(k if al else -1)
        if g:
            x0 = solve_bot(g, x0 if x0[2] > 100 else [0.0, 0.0, 800.0])
            out["pit"].append(x0[0]); out["beta"].append(x0[1]); out["dist"].append(x0[2])
            out["u"].append((960 - g[2]) / g[3]); out["v"].append((540 - g[0]) / (g[1] - g[0]))
            out["hw"].append(g[3]); out["hh"].append((g[1] - g[0]) / 2)
        else:
            for kk in ("pit", "beta", "dist", "u", "v", "hw", "hh"): out[kk].append(np.nan)
        out["tri"].append(R[i][14] if not np.isnan(R[i][14]) else np.nan)
    O = {k: np.array(v, float) for k, v in out.items()}
    # marker height: from its screen y where it's seen (fit once)
    n = len(O["t"])
    # camera yaw from the marker; bot world direction = yaw + beta
    yaw = np.full(n, np.nan)
    ZT = 3245.0
    for j in range(n):
        if O["alive"][j] and not np.isnan(O["tri"][j]):
            yaw[j] = tri_yaw(O["tri"][j], O["pit"][j], ZT)
    az = yaw + O["beta"]
    # the bot is at the spawn point for its first 0.07 s: its direction from the camera is exactly -90 degrees
    for j in range(n):
        if O["alive"][j] and (O["t"][j] - O["life"][j] * PERIOD) < 0.06: az[j] = -math.pi / 2
    # join up the bot's direction across gaps inside each life, then smooth lightly
    for L in range(12):
        m = O["life"] == L
        jj = np.nonzero(m & O["alive"].astype(bool))[0]
        ok = jj[~np.isnan(az[jj])]
        az[jj] = np.interp(jj, ok, az[ok])
        if len(jj) > 15:
            az[jj] = savgol_filter(az[jj], 9, 2)
            O["dist"][jj] = savgol_filter(O["dist"][jj], 9, 2)
    yaw_f = az - O["beta"]
    bx = CAM[0] + O["dist"] * np.cos(az); by = CAM[1] + O["dist"] * np.sin(az)
    # sanity: bot speed (units/s) and how often the marker was seen
    sp = np.hypot(np.diff(bx), np.diff(by)) * 60
    al = O["alive"].astype(bool)
    good = al[1:] & al[:-1] & (O["life"][1:] == O["life"][:-1])
    print("marker seen in", round(100 * np.mean(~np.isnan(yaw[al])), 1), "% of samples")
    print("bot speed percentiles 50/90/98/99.5:", np.round(np.nanpercentile(sp[good], [50, 90, 98, 99.5])))
    print("bot x range", np.nanmin(bx), np.nanmax(bx), " y range", np.nanmin(by), np.nanmax(by))
    print("distance at each spawn:", [round(float(O["dist"][np.nonzero(O["life"] == L)[0][2]])) for L in range(12)])
    np.savez_compressed(os.path.join(HERE, "recon.npz"), yaw=yaw_f, bx=bx, by=by, **O)
