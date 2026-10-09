# One recorded run rebuilt from AimRecorder data, plus a model run on the SAME bot movement. Used by target_video.py
# (whole run, solo + side by side) and model_clip.py (an 8-second side-by-side window).
# The model keeps a human reaction time (8 samples, about 130 ms) and only varies how smooth it is (w) and how well it
# reads the bot's movement (pred). No AI: a spring that follows where the bot was 130 ms ago.
# Bot shape and size come from the scenario's .bot file (scenario_profile.py), the visible height from the recorder's
# body position (phase 5) or, for older recordings of flying bots, from the aim at hit moments.
import csv, math, os, statistics as st
from PIL import Image, ImageDraw, ImageFont
from aim_analysis import moving_ids, height_source
import config, scenario_profile

DT = 1 / 60
try:
    FB = ImageFont.truetype("arialbd.ttf", 30); FM = ImageFont.truetype("arialbd.ttf", 22); FS = ImageFont.truetype("arial.ttf", 18)
except Exception: FB = FM = FS = ImageFont.load_default()
BG_TOP, BG_BOT, GRID, BOTC, AIMC, INK, DIM = (44, 46, 48), (30, 31, 32), (78, 80, 82), (90, 225, 215), (255, 60, 60), (240, 240, 236), (170, 170, 164)


class Run:
    def __init__(self, path, real_score):
        self.real_score = real_score
        self.hfov = config.fov()
        scen = os.path.basename(path)[18:].replace(".gz", "").replace(".csv", "").replace("_", " ").strip()
        self.scen, self.title = scen, " ".join(scen.split())
        rows = list(csv.DictReader(config.open_run(path)))
        ids = moving_ids(rows); src = height_source(rows, ids)
        P = lambda r, k, a: r[f"b{k}_{src}{a}"] if src and r.get(f"b{k}_{src}z") else r[f"b{k}_{a}"]
        T, CAM, YAW, PIT, BOT, HITS = [], [], [], [], [], []
        acc = prev = None
        for r in rows:
            y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y
            T.append(float(r["t"])); YAW.append(acc); PIT.append(float(r["pitch"])); HITS.append(int(r["hits"]))
            CAM.append((float(r["cam_x"]), float(r["cam_y"]), float(r["cam_z"])))
            k = next((i for i in range(1, 9) if r.get(f"b{i}_x") not in (None, "", "0.0") and (r.get(f"b{i}_id") or str(i)) in ids), None)
            BOT.append(None if k is None else (float(P(r, k, "x")), float(P(r, k, "y")), float(P(r, k, "z"))))
        n = len(T)
        self.T, self.CAM, self.YAW, self.PIT, self.BOT, self.HITS, self.n = T, CAM, YAW, PIT, BOT, HITS, n
        resets = [i for i in range(1, n) if HITS[i] < HITS[i - 1]]      # the game zeroes the hit counter when the run starts
        self.start = start = resets[-1] if resets else next(i for i in range(1, n) if HITS[i] > HITS[i - 1])
        self.end = end = max(i for i in range(n) if BOT[i] is not None)
        hit_i = [i for i in range(start + 1, end) if BOT[i] and HITS[i] > HITS[i - 1]]
        HW = sorted(abs(math.tan(math.radians(self.bot_yaw(i) - YAW[i])) * self.hd(i)) for i in hit_i)[int(.98 * len(hit_i))]
        OFFU = st.median(math.tan(math.radians(self.raw_pitch(i) - PIT[i])) * self.hd(i) for i in hit_i)
        self.EST = abs(OFFU) > 3 * HW
        if self.EST:     # recorded height unusable: take it from the aim at hit moments, interpolated, lightly smoothed
            BP = [None] * n
            for a_, b_ in zip(hit_i, hit_i[1:]):
                for k in range(a_, b_ + 1): BP[k] = PIT[a_] + (PIT[b_] - PIT[a_]) * (k - a_) / (b_ - a_)
            for k in range(0, hit_i[0]): BP[k] = PIT[hit_i[0]]
            for k in range(hit_i[-1], n): BP[k] = PIT[hit_i[-1]]
            BP = [st.mean(BP[max(0, k - 3):k + 4]) for k in range(n)]
        else:
            BP = [self.raw_pitch(i) - math.degrees(math.atan(OFFU / self.hd(i))) if BOT[i] else None for i in range(n)]
        self.BP = BP
        prof = scenario_profile.bot_profile(scen)
        self.sphere = prof.get("BotType") == "SPHERE" if prof else False
        if self.sphere and prof.get("SphereRadiusMin") and not prof.get("SphereRandomRadius?"):
            HW = 30.0 * prof["SphereRadiusMin"]
        self.HW, self.HH = HW, (HW if self.sphere else 2.2 * HW)
        self.BA = [None if BOT[i] is None else (self.bot_yaw(i), BP[i], self.hd(i)) for i in range(n)]
        self.real_on = sum(self.on(i, YAW[i], PIT[i]) for i in range(start, end)) or 1
        self.per_frame = real_score / self.real_on              # points per on-target frame, from the real run
        self.floor = min(c[2] for c in CAM) - 350
        self.real_cum = [max(0, HITS[i] - HITS[start]) if i >= start else 0 for i in range(n)]
        if real_score and HITS[end] - HITS[start] > 0:          # game points per hit (some scenarios give 5)
            k = real_score / max(1, HITS[end] - HITS[start]); self.real_cum = [round(x * k) for x in self.real_cum]

    def hd(self, i): c, b = self.CAM[i], self.BOT[i]; return math.hypot(b[0] - c[0], b[1] - c[1])
    def bot_yaw(self, i):
        c, b = self.CAM[i], self.BOT[i]; a = math.degrees(math.atan2(b[1] - c[1], b[0] - c[0]))
        return self.YAW[i] + ((a - self.YAW[i] + 180) % 360 - 180)
    def raw_pitch(self, i): c, b = self.CAM[i], self.BOT[i]; return math.degrees(math.atan2(b[2] - c[2], self.hd(i)))

    def on(self, i, ay, ap):
        if self.BA[i] is None: return False
        wx, wy = math.degrees(math.atan(self.HW / self.BA[i][2])), math.degrees(math.atan(self.HH / self.BA[i][2]))
        return abs(self.BA[i][0] - ay) <= wx and (self.EST or abs(self.BA[i][1] - ap) <= wy)

    def simulate(self, delay, w, pred):
        BA, sy, sp, vy, vp = self.BA, self.YAW[self.start], self.PIT[self.start], 0.0, 0.0
        out = []
        for i in range(self.n):
            if i < self.start: out.append((self.YAW[i], self.PIT[i])); continue
            j = i - delay
            if BA[j] is not None and BA[j - 2] is not None:
                ty = BA[j][0] + pred * (BA[j][0] - BA[j - 2][0]) / 2 * delay
                tp = BA[j][1] + pred * (BA[j][1] - BA[j - 2][1]) / 2 * delay
                ay = w * w * (ty - sy) - 2 * w * vy; ap = w * w * (tp - sp) - 2 * w * vp
                vy += ay * DT; vp += ap * DT
            else: vy *= 0.9; vp *= 0.9                        # no bot on screen: ease to a stop
            sy += vy * DT; sp += vp * DT
            if self.EST: sp, vp = self.PIT[i], 0.0             # height not measured: the model only works left-right
            out.append((sy, sp))
        return out

    def score_of(self, sim):
        return round(self.per_frame * sum(self.on(i, *sim[i]) for i in range(self.start, self.end)))

    def tune(self, target, progress=None):
        """Model run whose whole-run score is closest to target. Sets self.sim, self.sim_score, self.sim_cum."""
        best = None
        grid = [(w, 1.0 + x / 50) for w in (14, 18, 22, 26, 30, 34, 38, 42, 50, 60, 72) for x in range(0, 21, 2)]
        for gi, (w, pred) in enumerate(grid):
            s = self.score_of(self.simulate(8, w, pred))
            if best is None or abs(s - target) < abs(best[0] - target): best = (s, w, pred)
            if progress and gi % 10 == 0: progress(gi / len(grid))
        self.sim_score, self.w, self.pred = best
        self.sim = self.simulate(8, self.w, self.pred)
        acc, self.sim_cum = 0, []
        for i in range(self.n):
            if self.start <= i < self.end and self.on(i, *self.sim[i]): acc += self.per_frame
            self.sim_cum.append(round(acc))
        return self.sim_score

    def t_left(self, i):
        run_len = (self.end - self.start) * DT
        return 60 - max(0, (i - self.start) * DT) * 60 / run_len

    def view(self, Wd, Ht, i, ay, ap, score, label, t_left):
        f = (Wd / 2) / math.tan(math.radians(self.hfov / 2))
        im = Image.new("RGB", (Wd, Ht), BG_BOT); d = ImageDraw.Draw(im)
        cy_, sy_ = math.cos(math.radians(ay)), math.sin(math.radians(ay))
        cp, sp_ = math.cos(math.radians(ap)), math.sin(math.radians(ap))
        cx0, cy0, cz0 = self.CAM[i]
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
                    p = proj(a_[0] + (b_[0] - a_[0]) * u, a_[1] + (b_[1] - a_[1]) * u, self.floor)
                    if p: pts.append(p)
                    elif len(pts) > 1: d.line(pts, fill=GRID, width=1); pts = []
                    else: pts = []
                if len(pts) > 1: d.line(pts, fill=GRID, width=1)
        if self.BOT[i] is not None:
            b = self.BOT[i]
            c = proj(b[0], b[1], cz0 + math.tan(math.radians(self.BP[i])) * self.hd(i))
            if c:
                rx, ry = max(3, self.HW / self.hd(i) * f), max(3 if self.sphere else 6, self.HH / self.hd(i) * f)
                d.rounded_rectangle([c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry], radius=rx, fill=BOTC)
        d.ellipse([Wd / 2 - 3, Ht / 2 - 3, Wd / 2 + 3, Ht / 2 + 3], fill=AIMC)
        tl_ = max(0, math.ceil(t_left - 1e-6)); d.text((Wd / 2, 28), f"{tl_ // 60}:{tl_ % 60:02d}", fill=INK, font=FB, anchor="mm")
        d.text((Wd / 2, 62), f"{score}", fill=INK, font=FM, anchor="mm")
        d.text((Wd / 2, Ht - 30), self.title, fill=INK, font=FS, anchor="mm")
        d.text((16, 14), label, fill=DIM, font=FM)
        return im
