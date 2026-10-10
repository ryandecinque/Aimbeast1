# Loads one Zeus Track recording into plain per-sample arrays (60 a second), split into its 3 rounds.
# Read-only on the game folder. Used by evidence.py and the video renderer.
import csv, glob, math, os, statistics as st, sys
sys.path.insert(0, r"C:/Users/Ryan/aimbeast-progress")
from aim_analysis import moving_ids, thin60
RUNS = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Binaries/Win64/ue4ss/Mods/AimRecorder/runs"
DT = 1 / 60

def zeus_runs(day=None):
    fs = sorted(glob.glob(RUNS + "/*ZEUS TRACK EVO - NOBLINK.csv"))
    return [f for f in fs if day is None or os.path.basename(f).startswith(day)]

class Run:
    def __init__(self, path):
        self.path = path; self.name = os.path.basename(path)[:17]
        rows = thin60(list(csv.DictReader(open(path, encoding="utf-8"))))
        ids = moving_ids(rows)
        T, YAW, PIT, CAM, BOT, HITS, M1 = [], [], [], [], [], [], []
        acc = prev = None
        for r in rows:
            y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y
            T.append(float(r["t"])); YAW.append(acc); PIT.append(float(r["pitch"])); HITS.append(int(r["hits"])); M1.append(r["m1"] == "1")
            CAM.append((float(r["cam_x"]), float(r["cam_y"]), float(r["cam_z"])))
            k = next((i for i in range(1, 9) if r.get(f"b{i}_x") not in (None, "", "0.0") and (r.get(f"b{i}_id") or str(i)) in ids), None)
            src = "m" if (k and r.get(f"b{k}_mz")) else ""
            BOT.append(None if k is None else (r.get(f"b{k}_id"), float(r[f"b{k}_{src}x"]), float(r[f"b{k}_{src}y"]), float(r[f"b{k}_{src}z"])))
        # resample to an even 60 a second (the recorder's real rate varies, ~45-60 a second)
        import bisect
        T0 = T; G = [T0[0] + k / 60 for k in range(int((T0[-1] - T0[0]) * 60))]
        def lerp(arr, tup=False):
            o = []
            for t in G:
                j = min(max(bisect.bisect_right(T0, t) - 1, 0), len(T0) - 2); u = (t - T0[j]) / (T0[j + 1] - T0[j])
                a_, b_ = arr[j], arr[j + 1]
                if tup:
                    if a_ is None or b_ is None or a_[0] != b_[0]: o.append(a_ if u < .5 else b_); continue
                    o.append((a_[0],) + tuple(x + (y - x) * u for x, y in zip(a_[1:], b_[1:])))
                else: o.append(a_ + (b_ - a_) * u)
            return o
        def hold(arr): return [arr[min(max(bisect.bisect_right(T0, t) - 1, 0), len(T0) - 1)] for t in G]
        YAW, PIT = lerp(YAW), lerp(PIT); CAM = [tuple(c) for c in zip(*(lerp([c[k] for c in CAM]) for k in range(3)))]
        BOT = lerp(BOT, tup=True); HITS, M1 = hold(HITS), hold(M1); T = G
        n = len(T)
        resets = [i for i in range(1, n) if HITS[i] < HITS[i - 1]]
        self.start = resets[-1] if resets else next(i for i in range(1, n) if HITS[i] > HITS[i - 1])
        self.end = max(i for i in range(n) if BOT[i] is not None)
        self.T, self.YAW, self.PIT, self.CAM, self.HITS, self.M1, self.n = T, YAW, PIT, CAM, HITS, M1, n
        self.BID = [b[0] if b else None for b in BOT]
        self.BP = [b[1:] if b else None for b in BOT]
        # bot direction from the camera
        self.D, self.BY, self.BZ = [None] * n, [None] * n, [None] * n
        for i in range(n):
            if not self.BP[i]: continue
            c, b = CAM[i], self.BP[i]
            dx, dy, dz = b[0] - c[0], b[1] - c[1], b[2] - c[2]
            hd = math.hypot(dx, dy); self.D[i] = hd
            self.BY[i] = YAW[i] + ((math.degrees(math.atan2(dy, dx)) - YAW[i] + 180) % 360 - 180)
            self.BZ[i] = math.degrees(math.atan2(dz, hd))
        # rounds: a new round starts when the bot jumps back far away (bot id changes or distance jumps up)
        self.rounds = []
        cur = self.start
        for i in range(self.start + 1, self.end):
            if self.D[i] and self.D[i - 1] and self.D[i] - self.D[i - 1] > 800:
                self.rounds.append((cur, i)); cur = i
        self.rounds.append((cur, self.end))
        hit_i = [i for i in range(self.start + 1, self.end) if self.D[i] and HITS[i] > HITS[i - 1]]
        U = lambda deg, d: math.tan(math.radians(deg)) * d
        self.HW = sorted(abs(U(self.BY[i] - YAW[i], self.D[i])) for i in hit_i)[int(.98 * len(hit_i))]
        offs = [U(self.BZ[i] - PIT[i], self.D[i]) for i in hit_i]
        self.OFF = st.median(offs)                                          # aim point height on the body vs recorded centre
        self.HH = sorted(abs(o - self.OFF) for o in offs)[int(.98 * len(offs))]
        self.hit_i = hit_i
        self.HW_hits, self.HH_hits = self.HW, self.HH
        # Fixed capsule size. The game uses the bot file's Min fields when CapsuleRandomDimensions? is False (the XL/EZ/70%/50%
        # Zeus bots differ only in CapsuleRadiusMin, and EZ's 0.9/0.75 matches its 1.17x wider hits). Radius 0.75 x 42 = 31.5,
        # matching the hits' half-width (~32). Height: the stream footage showed the capsule 56 x 88 px (1.57 x taller than
        # wide), so half-height ~50. (Hits only reach ~35 up-down because he aims at the middle.)
        self.HW, self.HH = 31.5, 49.5
        # centre pitch of the visible body
        self.CZ = [None if self.D[i] is None else math.degrees(math.atan2(U(self.BZ[i], self.D[i]) - self.OFF, self.D[i])) for i in range(n)]
        # errors in bot half-widths (1.0 = edge of the bot)
        self.ex = [None if self.D[i] is None else U(self.BY[i] - YAW[i], self.D[i]) / self.HW for i in range(n)]   # + = bot is to the left? (yaw grows left/right per engine)
        self.ey = [None if self.D[i] is None else (U(self.CZ[i] - PIT[i], self.D[i])) / self.HH for i in range(n)]
        self.on = [self.ex[i] is not None and abs(self.ex[i]) <= 1 and abs(self.ey[i]) <= 1 for i in range(n)]

    def vel(self, a, i, w=2):
        lo, hi = max(i - w, 0), min(i + w, self.n - 1)
        if a[lo] is None or a[hi] is None: return None
        return (a[hi] - a[lo]) / ((hi - lo) * DT)

    def score(self): return self.HITS[self.end] - self.HITS[self.start]
