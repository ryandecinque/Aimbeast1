# Best-run clip for switching and clicking runs: the 8 seconds with the most kills, at real speed, in the player's own
# view with EVERY live bot drawn (best_run_gif.py draws one bot, for tracking). Uses fast_clip.py's drawing, so bots,
# sizes and click rings look the same as in the "same bots, faster" videos. Looping MP4 plus a poster PNG.
# Usage: python real_clip.py <run csv> <title> <out.mp4>
import bisect, subprocess, sys
import config, fast_clip as fc

path, title, out = sys.argv[1], sys.argv[2], sys.argv[3]
a = fc.load(path)
if not a["has_kills"]: print("older recording without a kill counter"); sys.exit(2)
R, shape = fc.radius(a)
a["floor"] = min(min(c[2] for c in a["cam"]) - 350, min(q[3] for L in a["lives"] for q in L.path) - R)
est = fc.fix_heights(a, R)
T, s0 = a["T"], a["start"]
t0, t_end = T[s0], T[-1]
kt = [k["t"] for k in a["kills"] if k["life"] is not None]
WIN = 8.0
best, ta = -1, t0
t = t0
while t + WIN <= t_end + 1e-9:                          # the 8 seconds with the most kills (earliest on a tie)
    n = bisect.bisect_right(kt, t + WIN) - bisect.bisect_right(kt, t)
    if n > best: best, ta = n, t
    t += 0.1
presses = [T[i] for i in range(s0 + 1, a["n"]) if a["rows"][i].get("m1") == "1" and a["rows"][i - 1].get("m1") != "1"]
HF = fc.fov()


def frame(tau):
    i = min(bisect.bisect_left(T, tau), a["n"] - 1)
    bots = [fc.life_pos(L, T[i]) for L in a["lives"] if fc.alive(a, L, i)]
    kc = bisect.bisect_right(kt, tau)
    k = bisect.bisect_right(presses, tau) - 1
    ring = tau - presses[k] if k >= 0 and tau - presses[k] < 0.12 else None
    def hud(d, Wd, Ht):
        d.text((Wd / 2, 28), f"{tau - t0:.1f}s", fill=fc.INK, font=fc.FB, anchor="mm")
        d.text((Wd / 2, 62), f"{kc} kills", fill=fc.INK, font=fc.FM, anchor="mm")
        d.text((16, 14), f"Best 8 seconds: {best} kills", fill=fc.DIM, font=fc.FM)
        d.text((Wd / 2, Ht - 28), title, fill=fc.INK, font=fc.FS, anchor="mm")
        d.text((Wd - 14, Ht - 8), "Rebuilt from your aim data" + (" (bot height estimated from hits)" if est else ""),
               fill=(120, 120, 116), font=fc.FS, anchor="rd")
    return fc.view(1280, 720, a["cam"][i], a["yaw"][i], a["pitch"][i], bots, R, shape, a["floor"], HF, hud, ring)


p = subprocess.Popen([config.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1280x720", "-r", "30", "-i", "-",
                      "-vf", "scale=960:540", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "medium", "-movflags", "+faststart", "-an", out],
                     stdin=subprocess.PIPE, creationflags=config.NO_WINDOW)
tau = ta
while tau <= ta + WIN:
    p.stdin.write(frame(tau).tobytes()); tau += 1 / 30
p.stdin.close(); p.wait()
frame(ta + WIN / 2).resize((960, 540)).save(out[:-4] + ".png")
print("wrote", out, f"best 8 s = {best} kills from {ta - t0:.1f} s")
