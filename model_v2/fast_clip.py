# "Same bots, 20% faster": a model run on the SAME bots as a real run, in the SAME order, on their REAL recorded paths,
# that kills each one sooner. Each bot only uses an earlier slice of the path it really took, and the next bot appears
# as soon as the model's kill happens, so the whole run ends sooner (about real time / factor). Nothing is invented.
# For scenarios where bots die and come back when killed, and don't react to being hit (scen_rules.py).
#
# The model: same human reaction (~130 ms) and spring-follow aim as ideal_run_video.py. It flicks to each next target
# with no over-aim (a critically damped spring can't overshoot a still target), then stays on it until the bot dies.
# Time on target needed per kill is Ryan's own from the run: his time on target per hit x hits per kill.
# Only the aim strength is tuned, until the model's total time is real time / factor.
#
# Outputs: <out>_side.mp4 (real left, model right, model holds a "done in Xs" card) and <out>_solo.mp4 (model only).
# Usage: python model_v2/fast_clip.py <run csv> <out prefix> [factor=1.2]
import bisect, math, os, statistics as st, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
import lives as lv, scen_rules
import scenario_profile as sp
from aim_analysis import run_name

CONFIG = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Trainer/Config.cfg"
DELAY = 0.13          # s, Ryan's reaction time (the same 8 samples the other model videos use)
DT = 1 / 60
SUB = 8

def fov():
    try:
        v = float(sp.read(CONFIG).get("FOV", 103)); return v if 60 <= v <= 150 else 103.0
    except Exception: return 103.0

# ---------------------------------------------------------------------------------------------------- the real run
def load(path):
    date, _, scen = run_name(path)
    R = scen_rules.rules(scen)
    a = lv.analyse(path, R.get("bot"))
    a["scenario"], a["date"], a["rules"] = scen, date, R
    return a

def radius(a):
    """Bot half-width in world units: sphere size from the .bot file (base ball ~30 units, as pb_video.py),
    otherwise the widest hits."""
    b = a["rules"].get("bot") or {}
    if b.get("BotType") == "SPHERE" and b.get("SphereRadiusMin") and not b.get("SphereRandomRadius?"):
        return 30.0 * b["SphereRadiusMin"], "sphere"
    lat = [abs(e[0]) for e in hit_errors(a)]
    return sorted(lat)[int(.98 * len(lat))] if lat else 40.0, "capsule"

def life_pos(L, t):
    """Visible position of a life at real time t (linear between samples)."""
    p = L.path; k = bisect.bisect_left(p, (t,))
    if k <= 0: return p[0][1:]
    if k >= len(p): return p[-1][1:]
    (t0, *a0), (t1, *a1) = p[k - 1], p[k]
    u = (t - t0) / (t1 - t0) if t1 > t0 else 0
    return tuple(x + (y - x) * u for x, y in zip(a0, a1))

def alive(a, L, i): return L.i0 <= i <= L.i1

def hit_errors(a, zfix=None):
    """At every hit: (left-right units, aim height minus bot height in units, life) for the bot nearest the crosshair."""
    out, T, cam = [], a["T"], a["cam"]
    for i in range(a["start"] + 1, a["n"]):
        if a["hits"][i] <= a["hits"][i - 1]: continue
        j, best = i - 1, None
        for L in a["lives"]:
            if not alive(a, L, j): continue
            x, y, z = life_pos(L, T[j])
            if zfix: z = zfix(L, T[j], z)
            c = cam[j]; dx, dy = x - c[0], y - c[1]; d = math.hypot(dx, dy)
            lat = math.tan(math.radians((math.degrees(math.atan2(dy, dx)) - a["yaw"][j] + 180) % 360 - 180)) * d
            up = c[2] + math.tan(math.radians(a["pitch"][j])) * d - z
            if best is None or abs(lat) < abs(best[0]): best = (lat, up, L, T[j])
        if best: out.append(best)
    return out

def fix_heights(a, R):
    """Older recordings (before the body columns) only have the bot's root. If hits land far above or below it,
    the visible height is taken from the aim at hit moments, per life, and interpolated (as pb_video.py does)."""
    errs = [e for e in hit_errors(a) if abs(e[0]) < 2 * R]
    if not errs or abs(st.median(e[1] for e in errs)) < 2 * R: return False
    med = st.median(e[1] for e in errs)
    pts = {}
    for lat, up, L, t in errs: pts.setdefault(id(L), []).append((t, up))
    for L in a["lives"]:
        p = sorted(pts.get(id(L), []))
        def off(t, p=p):
            if not p: return med
            k = bisect.bisect_left(p, (t,))
            if k <= 0: return p[0][1]
            if k >= len(p): return p[-1][1]
            (t0, o0), (t1, o1) = p[k - 1], p[k]
            return o0 + (o1 - o0) * (t - t0) / (t1 - t0) if t1 > t0 else o0
        L.path = [(t, x, y, z + off(t)) for t, x, y, z in L.path]
    return True

def on_target(cam, ay, ap, pos, R):
    dx, dy, dz = pos[0] - cam[0], pos[1] - cam[1], pos[2] - cam[2]
    d = math.sqrt(dx * dx + dy * dy + dz * dz)
    if d < 1: return False
    by = math.degrees(math.atan2(dy, dx)); bp = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    ex = (by - ay + 180) % 360 - 180; ey = bp - ap
    return math.hypot(ex, ey) <= math.degrees(math.atan(R / d))

def bot_angles(cam, pos, near_yaw):
    dx, dy, dz = pos[0] - cam[0], pos[1] - cam[1], pos[2] - cam[2]
    by = math.degrees(math.atan2(dy, dx))
    return near_yaw + ((by - near_yaw + 180) % 360 - 180), math.degrees(math.atan2(dz, math.hypot(dx, dy)))

# ---------------------------------------------------------------------------------------------------- the model
def build(a, R):
    T, s0 = a["T"], a["start"]
    kills = [k for k in a["kills"] if k["life"] is not None]
    t0 = T[s0]
    Y = kills[-1]["t"] - t0                                     # real time to the last kill
    # time on target a kill takes: Ryan's own, the median unbroken stretch on the bot right before each of his kills
    # (bot health at his damage rate for tracking bots, his confirm time for 1-health clicking bots)
    streaks = []
    for k in kills:
        L, i, s = k["life"], k["i"] - 1, 0.0
        while i > L.i0 and on_target(a["cam"][i], a["yaw"][i], a["pitch"][i], life_pos(L, T[i]), R):
            s += T[i] - T[i - 1]; i -= 1
        streaks.append(s)
    need = max(DT, st.median(streaks))
    hits = a["hits"][kills[-1]["i"]] - a["hits"][s0]
    return dict(kills=kills, t0=t0, Y=Y, need=need, hpk=max(1, round(hits / len(kills))), hits=hits)

def simulate(a, R, M, w, pred=1.0):
    """Runs the model with aim strength w. Returns per-step aim, the model kill times, each life's model spawn time,
    and the lives whose real path ran out before the model killed them."""
    T, s0, cam0 = a["T"], a["start"], a["cam"][a["start"]]
    kills, t0 = M["kills"], M["t0"]
    spawn = {}                                                   # life -> model spawn time (s after run start)
    for L in a["lives"]:
        if L.spawn != "kill": spawn[id(L)] = T[L.i0] - t0
    kt = []                                                      # model kill times
    def lpos(L, tau):
        """Position of life L at model time tau: its own real path, shifted to start at its model spawn."""
        s = spawn.get(id(L))
        if s is None or tau < s: return None
        return life_pos(L, T[L.i0] + (tau - s))
    def ran_out(L, tau): return T[L.i0] + (tau - spawn[id(L)]) > T[L.i1] + 1.5 / 60
    by_kill = {}
    for L in a["lives"]:
        if L.spawn == "kill": by_kill.setdefault(L.after_kill, []).append(L)
    kno = {id(k["life"]): n for n, k in enumerate(kills)}       # life -> order in the kill list
    idx_of = {n: a["kills"].index(k) for n, k in enumerate(kills)}
    sy, sp_ = a["yaw"][s0], a["pitch"][s0]; vy = vp = 0.0
    aim, k, dmg, tau, bad = [], 0, 0.0, 0.0, []
    limit = M["Y"] * 1.6 + 5
    while k < len(kills) and tau < limit:
        # what the model sees: the world DELAY ago (the current target as of then)
        seen = tau - DELAY
        kt_seen = sum(1 for x in kt if x <= seen)
        tgt_seen = kills[min(kt_seen, len(kills) - 1)]["life"]
        p = lpos(tgt_seen, max(seen, 0.0)) if seen >= 0 else None
        if p is not None:
            p2 = lpos(tgt_seen, max(seen - 2 * DT, spawn[id(tgt_seen)]))
            ty, tp = bot_angles(cam0, p, sy)
            py, pp = bot_angles(cam0, p2, sy)
            ty += pred * (ty - py) / (2 * DT) * DELAY * (seen - 2 * DT >= spawn[id(tgt_seen)])
            tp += pred * (tp - pp) / (2 * DT) * DELAY * (seen - 2 * DT >= spawn[id(tgt_seen)])
            for _ in range(SUB):                                 # small steps keep a stiff spring stable
                ay = w * w * (ty - sy) - 2 * w * vy; ap = w * w * (tp - sp_) - 2 * w * vp
                vy += ay * DT / SUB; vp += ap * DT / SUB
                sy += vy * DT / SUB; sp_ += vp * DT / SUB
        else:
            vy *= 0.9; vp *= 0.9
            sy += vy * DT; sp_ += vp * DT
        aim.append((tau, sy, sp_))
        # damage on the real current target
        L = kills[k]["life"]
        pos = lpos(L, tau)
        if pos is not None and on_target(cam0, sy, sp_, pos, R): dmg += DT
        if pos is not None and ran_out(L, tau) and id(L) not in {id(x) for x in bad}: bad.append(L)
        if dmg >= M["need"]:
            kt.append(tau); dmg = 0.0
            real_k = kills[k]
            for NL in by_kill.get(idx_of[k], []):                 # lives this kill brought in
                spawn[id(NL)] = tau + (T[NL.i0] - real_k["t"])
            k += 1
        tau += DT
    return dict(aim=aim, kt=kt, spawn=spawn, bad=bad, done=k == len(kills), w=w, lpos=lpos)

def overruns(a, M, s):
    """Bots whose real path ends before the model kills them: [(kill number, seconds short)]."""
    T, out = a["T"], []
    for n, k in enumerate(M["kills"][:len(s["kt"])]):
        L = k["life"]; short = (s["kt"][n] - s["spawn"][id(L)]) - (T[L.i1] - T[L.i0])
        if short > 1.5 / 60: out.append((n + 1, round(short, 2)))
    return out

def tune(a, R, M, factor):
    """Every aim strength from soft to stiff. Picks the one whose total time is closest to real / factor among those
    where no bot runs past its real path. Returns (sim, sim closest to the asked factor ignoring paths)."""
    want = M["Y"] / factor
    runs = []
    for w in range(10, 101, 2):
        s = simulate(a, R, M, w)
        if not s["done"]: continue
        s["X"] = s["kt"][-1]; s["over"] = overruns(a, M, s); runs.append(s)
    if not runs: return None, None
    asked = min(runs, key=lambda s: abs(s["X"] - want))
    ok = [s for s in runs if not s["over"] and s["X"] < M["Y"]]
    return (min(ok, key=lambda s: abs(math.log(M["Y"] / s["X"] / factor))) if ok else None), asked

# ---------------------------------------------------------------------------------------------------- drawing
try:
    FB = ImageFont.truetype("arialbd.ttf", 30); FM = ImageFont.truetype("arialbd.ttf", 22); FS = ImageFont.truetype("arial.ttf", 17)
    FBIG = ImageFont.truetype("arialbd.ttf", 54)
except Exception: FB = FM = FS = FBIG = ImageFont.load_default()
BG_TOP, BG_BOT, GRID, BOTC, AIMC, INK, DIM, ACC = (44, 46, 48), (30, 31, 32), (78, 80, 82), (90, 225, 215), (255, 60, 60), (240, 240, 236), (170, 170, 164), (255, 200, 90)

def view(Wd, Ht, cam, ay, ap, bots, R, shape, floor, hfov, hud):
    """One frame in the player's own view, drawn like pb_video.py: floor grid, horizon, bots, red dot, HUD."""
    f = (Wd / 2) / math.tan(math.radians(hfov / 2))
    im = Image.new("RGB", (Wd, Ht), BG_BOT); d = ImageDraw.Draw(im)
    cy_, sy_ = math.cos(math.radians(ay)), math.sin(math.radians(ay))
    cp, sp_ = math.cos(math.radians(ap)), math.sin(math.radians(ap))
    cx0, cy0, cz0 = cam
    def proj(x, y, z):
        dx, dy, dz = x - cx0, y - cy0, z - cz0
        fwd = dx * cy_ + dy * sy_; right = -dx * sy_ + dy * cy_
        fz = fwd * cp + dz * sp_; up = -fwd * sp_ + dz * cp
        if fz < 5: return None
        return (Wd / 2 + right / fz * f, Ht / 2 - up / fz * f), fz
    hz = proj(cx0 + 1e6 * cy_, cy0 + 1e6 * sy_, cz0)
    hy = hz[0][1] if hz else (0 if ap < 0 else Ht)
    d.rectangle([0, 0, Wd, max(0, min(Ht, hy))], fill=BG_TOP)
    step, span = 250, 2500
    gx0, gy0 = round(cx0 / step) * step, round(cy0 / step) * step
    for k in range(-span, span + 1, step):
        for a_, b_ in (((gx0 + k, gy0 - span), (gx0 + k, gy0 + span)), ((gx0 - span, gy0 + k), (gx0 + span, gy0 + k))):
            pts = []
            for s_ in range(25):
                u = s_ / 24
                p = proj(a_[0] + (b_[0] - a_[0]) * u, a_[1] + (b_[1] - a_[1]) * u, floor)
                if p: pts.append(p[0])
                elif len(pts) > 1: d.line(pts, fill=GRID, width=1); pts = []
                else: pts = []
            if len(pts) > 1: d.line(pts, fill=GRID, width=1)
    for pos in sorted(bots, key=lambda q: -math.dist(q, cam)):          # far bots first
        p = proj(*pos)
        if not p: continue
        (cx, cy), fz = p
        rx = max(3, R / fz * f); ry = rx if shape == "sphere" else max(6, 2.2 * R / fz * f)
        d.rounded_rectangle([cx - rx, cy - ry, cx + rx, cy + ry], radius=rx, fill=BOTC)
    d.ellipse([Wd / 2 - 3, Ht / 2 - 3, Wd / 2 + 3, Ht / 2 + 3], fill=AIMC)
    hud(d, Wd, Ht)
    return im

# ---------------------------------------------------------------------------------------------------- main
def make(path, out, factor=1.2, render=True):
    a = load(path)
    rules = a["rules"]
    report = dict(run=os.path.basename(path), scenario=a["scenario"], rules_ok=rules["ok"], rules_why=rules["why"],
                  game_kills=a["game_kills"], detected=a["detected"], kill_spawns=a["kill_spawns"], timer_spawns=a["timer_spawns"])
    if not a["has_kills"]: report["verdict"] = "older recording without a kill counter: can't check kills"; return report
    if not rules["ok"]: report["verdict"] = "scenario doesn't qualify: " + "; ".join(rules["why"]); return report
    if a["detected"] != a["game_kills"] or a["detected"] < 3:
        report["verdict"] = f"kills found {a['detected']} vs game {a['game_kills']}: not safe to rebuild"; return report
    if a["timer_spawns"] > 0.1 * max(1, a["kill_spawns"]):
        report["verdict"] = "new bots in this run don't only come after kills"; return report
    R, shape = radius(a)
    a["floor"] = min(min(c[2] for c in a["cam"]) - 350, min(q[3] for L in a["lives"] for q in L.path) - R)   # below the bots
    est = fix_heights(a, R)
    M = build(a, R)
    report.update(radius=round(R), shape=shape, height_from_hits=est, need_on_target_s=round(M["need"], 3), hits_per_kill=M["hpk"],
                  real_s=round(M["Y"], 2), kills=len(M["kills"]))
    sim, asked = tune(a, R, M, factor)
    if asked:
        report["at_asked"] = dict(factor=round(M["Y"] / asked["X"], 2), bots_past_real_path=len(asked["over"]),
                                  worst_short_s=max([o[1] for o in asked["over"]], default=0), which=asked["over"][:10])
    if sim is None:
        report["verdict"] = f"no aim strength gets through without a bot running past its real path"; return report
    X = sim["X"]; f_got = round(M["Y"] / X, 2)
    report.update(factor=f_got, factor_asked=factor, model_s=round(X, 2), w=sim["w"])
    if abs(f_got - factor) <= 0.03: report["verdict"] = "ok"
    else:
        report["verdict"] = (f"{factor}x isn't possible on this run: {len(asked['over'])} bots' real paths end before the model "
                             f"reaches them (worst by {report['at_asked']['worst_short_s']}s). Nearest that works: {f_got}x.")
    if not render: return report
    draw(a, R, shape, est, M, sim, f_got, out)
    return report

def draw(a, R, shape, est, M, sim, factor, out):
    T, s0, t0, Y = a["T"], a["start"], M["t0"], M["Y"]
    X = sim["kt"][-1]; HF = fov()
    cam0 = a["cam"][s0]
    floor = a["floor"]
    title = a["scenario"]; nk = len(M["kills"])
    pct = round(100 * (factor - 1))
    lab_m = f"Same bots, {pct}% faster"
    note = "Same bots, same order, real paths. Spacing between bots is approximate." + (" Bot height estimated from hits." if est else "")
    real_kt = [k["t"] - t0 for k in M["kills"]]
    def real_frame(Wd, Ht, tau, final=False):
        i = min(bisect.bisect_left(T, t0 + tau), a["n"] - 1)
        bots = [life_pos(L, T[i]) for L in a["lives"] if alive(a, L, i)]
        kc = sum(1 for x in real_kt if x <= tau + 1e-9)
        def hud(d, Wd, Ht):
            d.text((Wd / 2, 28), f"{min(tau, Y):.1f}s", fill=INK, font=FB, anchor="mm")
            d.text((Wd / 2, 62), f"{kc} / {nk} kills", fill=INK, font=FM, anchor="mm")
            d.text((16, 14), f"Ryan, real run", fill=DIM, font=FM)
            d.text((Wd / 2, Ht - 28), title, fill=INK, font=FS, anchor="mm")
            if final:
                d.text((Wd / 2, Ht / 2 - 80), f"done in {Y:.1f}s", fill=ACC, font=FBIG, anchor="mm")
        return view(Wd, Ht, a["cam"][i], a["yaw"][i], a["pitch"][i], bots, R, shape, floor, HF, hud)
    aim = sim["aim"]
    def model_frame(Wd, Ht, tau, caption=True):
        done = tau >= X
        tq = min(tau, X)
        k = min(int(round(tq / DT)), len(aim) - 1)
        _, ay, ap = aim[k]
        kt = sim["kt"]
        kc = sum(1 for x in kt if x <= tq + 1e-9)
        bots = []
        for L in a["lives"]:
            s = sim["spawn"].get(id(L))
            if s is None or tq < s: continue
            n_ = next((n for n, kk in enumerate(M["kills"]) if kk["life"] is L), None)
            if n_ is not None and n_ < len(kt) and kt[n_] <= tq: continue        # killed already
            if n_ is None and T[L.i0] + (tq - s) > T[L.i1]: continue               # never killed: its path ran out
            bots.append(sim["lpos"](L, tq))
        def hud(d, Wd, Ht):
            d.text((Wd / 2, 28), f"{tq:.1f}s", fill=INK, font=FB, anchor="mm")
            d.text((Wd / 2, 62), f"{kc} / {nk} kills", fill=INK, font=FM, anchor="mm")
            d.text((16, 14), lab_m, fill=ACC, font=FM)
            d.text((Wd / 2, Ht - 28), title, fill=INK, font=FS, anchor="mm")
            if caption: d.text((Wd - 14, Ht - 8), note, fill=(120, 120, 116), font=FS, anchor="rd")
            if done:
                d.rectangle([Wd / 2 - 300, Ht / 2 - 135, Wd / 2 + 300, Ht / 2 - 25], fill=(20, 20, 19))
                d.text((Wd / 2, Ht / 2 - 100), f"done in {X:.1f}s", fill=ACC, font=FBIG, anchor="mm")
                d.text((Wd / 2, Ht / 2 - 50), f"real: {Y:.1f}s  ({nk} kills each)", fill=INK, font=FM, anchor="mm")
        return view(Wd, Ht, cam0, ay, ap, bots, R, shape, floor, HF, hud)

    def write(name, Wd, Ht, frames):
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{Wd}x{Ht}", "-r", "30", "-i", "-",
                              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21", "-preset", "medium", "-movflags", "+faststart", "-an", name],
                             stdin=subprocess.PIPE)
        for im in frames: p.stdin.write(im.tobytes())
        p.stdin.close(); p.wait(); print("wrote", name)

    def side_frames():
        for _ in range(45): yield side(0.0)                      # 1.5 s still at the start
        tau = 0.0
        while tau <= Y + 1e-9:
            yield side(tau); tau += 1 / 30
        last = side(Y, final=True)
        for _ in range(75): yield last
    def side(tau, final=False):
        im = Image.new("RGB", (1920, 580), (14, 14, 13))
        im.paste(real_frame(944, 531, tau, final), (10, 10))
        im.paste(model_frame(944, 531, tau, caption=False), (966, 10))
        d = ImageDraw.Draw(im)
        d.text((960, 562), note, fill=DIM, font=FS, anchor="mm")
        return im
    def solo_frames():
        for _ in range(45): yield model_frame(1280, 720, 0.0)
        tau = 0.0
        while tau <= X + 1e-9:
            yield model_frame(1280, 720, tau); tau += 1 / 30
        last = model_frame(1280, 720, X + 1e-6)
        for _ in range(75): yield last
    write(out + "_side.mp4", 1920, 580, side_frames())
    write(out + "_solo.mp4", 1280, 720, solo_frames())
    model_frame(1280, 720, X * 0.5).save(out + "_solo.png")

if __name__ == "__main__":
    import json
    path, out = sys.argv[1], sys.argv[2]
    factor = float(sys.argv[3]) if len(sys.argv) > 3 else 1.2
    r = make(path, out, factor, render=os.environ.get("NO_RENDER") != "1")
    print(json.dumps(r, indent=1))
