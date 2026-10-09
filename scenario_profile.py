# Reads Aimbeast scenario / bot / map files (.scen .bot .map .lmp .char .weap) into plain dicts.
# They are zlib-compressed Unreal packages holding one "SGO" object: field name, an 8-byte offset, then the value
# (no type tags). Fields ending in "?" are booleans, text fields are length-prefixed strings, the rest are 4-byte
# numbers (shown as float, and as int when that reads cleaner).
# Usage: python scenario_profile.py <file> [<file> ...]
import re, struct, sys, zlib

def unpack(path):
    b = open(path, "rb").read(); out = b""; o = 0
    while o < len(b) and b[o:o + 4] == b"\xc1\x83\x2a\x9e":           # Unreal compressed chunk
        total = struct.unpack("<q", b[o + 16:o + 24])[0]; o += 32
        blocks, used = [], 0
        while used < total:
            c, u = struct.unpack("<qq", b[o:o + 16]); blocks.append(c); used += c; o += 16
        for c in blocks: out += zlib.decompress(b[o:o + c]); o += c
    return out or b

def fstr_at(d, o):
    if o + 4 > len(d): return None
    n = struct.unpack("<i", d[o:o + 4])[0]
    if 0 < n < 400 and o + 4 + n <= len(d) and d[o + 3 + n] == 0 and all(32 <= c < 127 for c in d[o + 4:o + 3 + n]):
        return d[o + 4:o + 3 + n].decode(), o + 4 + n
    if n == 0: return "", o + 4
    return None

NAME = re.compile(rb"([\x02-\x7f])\x00\x00\x00([A-Za-z_][ -~]*?)\x00")

def read(path):
    d = unpack(path)
    o = d.find(b".") ; start = d.find(b"_C\x00")                   # skip the header up to the class path
    o = start + 3 + 16 if start > 0 else 0
    out = {}
    while o < len(d) - 5:
        s = fstr_at(d, o)
        if not s or not s[0]: break
        name, o = s
        o += 8                                                         # offset/size field
        if name.endswith("?"): out[name] = bool(d[o]); o += 1; continue
        t = fstr_at(d, o)
        if t is not None and t[0] and re.match(r"^[ -~]+$", t[0]) and not fstr_at(d, t[1]) is None:
            out[name], o = t; continue
        v = d[o:o + 4]; f = struct.unpack("<f", v)[0]; i = struct.unpack("<i", v)[0]
        out[name] = i if (abs(i) < 100000 and (abs(f) < 1e-30 or abs(f) > 1e9)) else round(f, 4); o += 4
    return out

if __name__ == "__main__":
    for f in sys.argv[1:]:
        print("==", f)
        for k, v in read(f).items(): print(f"  {k}: {v}")
