# Reads Robidashka's ANY STRAFES video (1920x1080, 360 fps) frame by frame.
# Per frame: the bot (the black capsule inside its yellow outline), its row-by-row half-width (to find the head),
# and the cyan spawn marker on the floor (a fixed world point, used to find where the camera looks).
# HUD crops (score, side stats, clock) are saved every 0.25 s for reading the score.
# Output: frames_<a>_<b>.npz. Usage: python extract.py <video> <first frame> <last frame>
import os, sys, numpy as np, cv2

VID, A, B = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(HERE, "hud"), exist_ok=True)
cap = cv2.VideoCapture(VID)
FPS = cap.get(cv2.CAP_PROP_FPS)
cap.set(cv2.CAP_PROP_POS_FRAMES, A)
NP = 48
# columns: frame, t, found, x0, x1, y0, y1 (dark interior bbox), cx, cy (dark centroid), area,
#          ox0, ox1, oy0, oy1 (yellow outline bbox), tri_x, tri_y (triangle base), tri_n
rows, prof = [], []
HUD = np.zeros((1080, 1920), bool)
HUD[:110, :] = True; HUD[815:, :] = True; HUD[:150, :200] = True
for i in range(A, B):
    ok, f = cap.read()
    if not ok: break
    t = i / FPS
    rec = [i, t, 0] + [np.nan] * 14
    pr = [np.nan] * NP
    s = cv2.resize(f, (480, 270), interpolation=cv2.INTER_AREA)
    ds = s.max(axis=2) < 70
    ds[:28, :] = False; ds[203:, :] = False; ds[:38, :50] = False
    k, lab, st, cen = cv2.connectedComponentsWithStats(ds.astype(np.uint8), connectivity=8)
    if k > 1:
        j = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        if st[j, cv2.CC_STAT_AREA] >= 4:
            X0, Y0 = max(0, 4 * st[j, 0] - 24), max(110, 4 * st[j, 1] - 24)
            X1, Y1 = min(1920, 4 * (st[j, 0] + st[j, 2]) + 24), min(815, 4 * (st[j, 1] + st[j, 3]) + 24)
            roi = f[Y0:Y1, X0:X1]
            dark = (roi.max(axis=2) < 60).astype(np.uint8)
            k2, lab2, st2, cen2 = cv2.connectedComponentsWithStats(dark, connectivity=8)
            if k2 > 1:
                j2 = 1 + int(np.argmax(st2[1:, cv2.CC_STAT_AREA]))
                a = st2[j2, cv2.CC_STAT_AREA]
                if a >= 60:
                    x0, y0, w, h = st2[j2, 0], st2[j2, 1], st2[j2, 2], st2[j2, 3]
                    rec[2:10] = [1, X0 + x0, X0 + x0 + w - 1, Y0 + y0, Y0 + y0 + h - 1, X0 + cen2[j2][0], Y0 + cen2[j2][1], a]
                    b_, g_, r_ = roi[..., 0], roi[..., 1], roi[..., 2]
                    yl = (r_ > 170) & (g_ > 170) & (b_ < 110)
                    cy0, cx0 = 540 - Y0, 960 - X0                       # the yellow crosshair isn't the outline
                    yl[max(0, cy0 - 9):max(0, cy0 + 10), max(0, cx0 - 9):max(0, cx0 + 10)] = False
                    ys, xs = np.nonzero(yl)
                    if len(xs) > 20: rec[10:14] = [X0 + xs.min(), X0 + xs.max(), Y0 + ys.min(), Y0 + ys.max()]
                    m = lab2[y0:y0 + h, x0:x0 + w] == j2
                    for q in range(NP):
                        c = np.nonzero(m[int((q + 0.5) * h / NP)])[0]
                        if len(c): pr[q] = (c.max() - c.min() + 1) / 2
    # cyan spawn marker: B high, G high, R low
    sb, sg, sr = s[..., 0].astype(int), s[..., 1].astype(int), s[..., 2].astype(int)
    cm = (sb > 190) & (sg > 160) & (sr < 160); cm[:28, :] = False; cm[203:, :] = False
    ys, xs = np.nonzero(cm)
    if len(xs):
        X0, X1 = max(0, 4 * xs.min() - 12), min(1920, 4 * xs.max() + 16)
        Y0, Y1 = max(110, 4 * ys.min() - 12), min(815, 4 * ys.max() + 16)
        roi = f[Y0:Y1, X0:X1].astype(int)
        c = (roi[..., 0] > 200) & (roi[..., 1] > 170) & (roi[..., 2] < 150)
        yy, xx = np.nonzero(c)
        if len(xx) >= 6: rec[14:17] = [X0 + xx.mean(), Y0 + yy.max(), len(xx)]
    rows.append(rec); prof.append(pr)
    if i % 90 == 0:
        cv2.imwrite(os.path.join(HERE, "hud", f"s{i:06d}.png"), f[915:985, 860:1060])        # score
        cv2.imwrite(os.path.join(HERE, "hud", f"a{i:06d}.png"), f[890:1010, 70:160])         # side stats (accuracy)
        cv2.imwrite(os.path.join(HERE, "hud", f"c{i:06d}.png"), f[48:90, 915:1005])          # clock
np.savez_compressed(os.path.join(HERE, f"frames_{A:06d}_{B:06d}.npz"), rows=np.array(rows, float), prof=np.array(prof, float), fps=FPS)
print("done", A, B, len(rows))
