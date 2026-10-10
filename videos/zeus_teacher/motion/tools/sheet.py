"""Tile stills (out/stills/<prefix>-t*.png) into labelled 3x4 contact sheets in out/stills/sheets/."""
import glob, os, re, subprocess, sys
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "stills"))
prefix = sys.argv[1] if len(sys.argv) > 1 else "main"
key = lambda f: float(re.sub(rf"{prefix}-t|\.png", "", f).replace("_", "."))
fs = sorted(glob.glob(f"{prefix}-t*.png"), key=key)
os.makedirs("sheets", exist_ok=True)
FONT = "C\:/Windows/Fonts/arial.ttf"
for k in range(0, len(fs), 12):
    grp = fs[k:k + 12]
    while len(grp) < 12:
        grp.append(grp[-1])
    args = sum([["-i", f] for f in grp], [])
    fc = "".join(f"[{i}]drawtext=fontfile='{FONT}':text='{key(grp[i]):.2f}s':x=10:y=10:fontsize=26:fontcolor=white:box=1:boxcolor=black@0.6[v{i}];" for i in range(12))
    fc += "".join(f"[v{i}]" for i in range(12)) + "xstack=inputs=12:layout=0_0|w0_0|w0+w1_0|0_h0|w0_h0|w0+w1_h0|0_h0+h3|w0_h0+h3|w0+w1_h0+h3|0_h0+h3+h6|w0_h0+h3+h6|w0+w1_h0+h3+h6,scale=1500:-1"
    out = f"sheets/{prefix}-{k // 12}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", fc, out], check=True)
    print(out)
