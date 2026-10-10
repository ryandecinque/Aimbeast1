# Reads the on-screen score from the HUD crops (hud/s<frame>.png, every 90 frames = 0.25 s) with digit templates
# taken from crops whose value was read by eye. Output: score.json {frame: score}.
import glob, json, os, re, numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
KNOWN = {540: "5", 1080: "40", 1620: "70", 8730: "437", 9270: "459", 9810: "497", 10350: "537", 17280: "833",
         17820: "866", 18360: "896", 18900: "933", 25830: "1237", 26370: "1260", 26910: "1289", 27450: "1315"}

def glyphs(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    m = (a.min(axis=2) > 200)
    cols = np.nonzero(m.any(axis=0))[0]
    if not len(cols): return []
    out, run = [], [cols[0]]
    for c in cols[1:]:
        if c == run[-1] + 1: run.append(c)
        else: out.append(run); run = [c]
    out.append(run)
    gl = []
    for r in out:
        sub = m[:, r[0]:r[-1] + 1]
        rows = np.nonzero(sub.any(axis=1))[0]
        if len(rows) < 8: continue
        g = sub[rows[0]:rows[-1] + 1]
        im = Image.fromarray((g * 255).astype(np.uint8)).resize((12, 20), Image.BILINEAR)
        gl.append((np.asarray(im, float) / 255, len(r)))
    return gl

T = {}
for fr, s in KNOWN.items():
    g = glyphs(os.path.join(HERE, "hud", f"s{fr:06d}.png"))
    assert len(g) == len(s), (fr, s, len(g))
    for (x, w), ch in zip(g, s): T.setdefault(ch, []).append((x, w))

def read(path):
    out = ""
    for x, w in glyphs(path):
        best = min(((np.sum((x - tx) ** 2) + 0.05 * (w - tw) ** 2, ch) for ch, L in T.items() for tx, tw in L))
        if best[0] > 25: return None
        out += best[1]
    return int(out) if out else None

if __name__ == "__main__":
    res = {}
    for p in sorted(glob.glob(os.path.join(HERE, "hud", "s*.png"))):
        res[int(re.findall(r"\d+", os.path.basename(p))[0])] = read(p)
    json.dump(res, open(os.path.join(HERE, "score.json"), "w"))
    v = [(k, s) for k, s in sorted(res.items()) if s is not None]
    bad = [(a, b) for a, b in zip(v, v[1:]) if b[1] < a[1]]
    print(len(res), "crops,", len(v), "read; decreasing pairs:", bad[:10])
    print(v[:12], v[-12:])
