# Bot lives in one AimRecorder run: when each bot appeared, when it died, and the path it took in between.
# Shared code for the "same bots, killed sooner" video (fast_clip.py) and later for the switching analysis.
#
# A kill = the game's kill counter goes up, and at that moment a bot's health drops to 0 or the bot jumps more than
# 150 units in one sample (some scenarios move a dead bot to its next spawn point instead of deleting it). When more
# than one bot could be the one, the one nearest the crosshair gets it.
# A new life starts when a bot appears, comes back from 0 health, or jumps. It counts as kill-based when a kill
# happened up to 0.3 s before it, timer-based otherwise.
# Bots that never move (left over from earlier scenarios) are ignored. Read-only on the recordings.
# Usage: python model_v2/lives.py <run csv> [...]      (prints a check against the game's kill counter)
import csv, gzip, math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from aim_analysis import moving_ids

JUMP = 150.0          # units in one sample: a teleport, not movement
KILL_WINDOW = 0.07    # s either side of the counter going up to look for the bot that died
SPAWN_AFTER_KILL = 0.3

def f(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def read_rows(path):
    with (gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8")) as fh:
        return list(csv.DictReader(fh))

def body_source(rows, profile=None):
    """Which recorded point is the visible bot: 's' sphere, 'm' body, or '' root. Phase 5+ files fill the body parts;
    flying bots move those, not the root."""
    cols = rows[0].keys()
    want = "s" if (profile or {}).get("BotType") == "SPHERE" else "m"
    for src in (want, "m", "s"):
        if f"b1_{src}x" in cols and any(f(r.get(f"b{i}_{src}x")) for r in rows[::50] for i in range(1, 9)):
            return src
    return ""

class Life:
    def __init__(self, bid, i0):
        self.id, self.i0, self.i1 = bid, i0, None   # first and last sample alive (inclusive)
        self.end = None                             # 'kill' / 'gone' / 'run end'
        self.kill_no = None                         # index into kills
        self.spawn = "start"                        # 'start' / 'kill' / 'timer'
        self.after_kill = None                      # kill index that brought this life in
        self.path = []                              # [(t, x, y, z)] visible body position

def analyse(path, profile=None):
    rows = read_rows(path)
    n = len(rows)
    ids = moving_ids(rows)
    src = body_source(rows, profile)
    T = [float(r["t"]) for r in rows]
    yaw, acc, prev = [], None, None
    for r in rows:
        y = float(r["yaw"]); acc = y if prev is None else acc + ((y - prev + 180) % 360 - 180); prev = y; yaw.append(acc)
    pitch = [float(r["pitch"]) for r in rows]
    cam = [(float(r["cam_x"]), float(r["cam_y"]), float(r["cam_z"])) for r in rows]
    hits = [int(r["hits"]) for r in rows]
    has_kills = "kills" in rows[0]
    kills_c = [int(r["kills"]) for r in rows] if has_kills else [0] * n
    # the run starts when the game zeroes the counters (countdown before that)
    resets = [i for i in range(1, n) if hits[i] < hits[i - 1] or kills_c[i] < kills_c[i - 1]]
    start = resets[-1] if resets else 0

    # per sample: {id: (root, body, hp)}
    snap = []
    for r in rows:
        d = {}
        for k in range(1, 9):
            bid = r.get(f"b{k}_id") or str(k)
            x = f(r.get(f"b{k}_x"))
            if x is None or r.get(f"b{k}_x") == "0.0" or bid not in ids: continue
            root = (x, f(r[f"b{k}_y"]), f(r[f"b{k}_z"]))
            body = (f(r.get(f"b{k}_{src}x")), f(r.get(f"b{k}_{src}y")), f(r.get(f"b{k}_{src}z"))) if src else (None,)
            body = root if None in body else body
            d[bid] = (root, body, f(r.get(f"b{k}_hp")))
        snap.append(d)

    lives, open_ = [], {}
    ends = []                                       # (sample index of the event, life) for lives that ended mid-run
    for i in range(start, n):
        cur = snap[i]; prv = snap[i - 1] if i > start else {}
        for bid in set(open_) | set(cur):
            L = open_.get(bid)
            if bid not in cur:                                       # gone
                if L: L.i1, L.end = i - 1, "gone"; ends.append((i, L)); del open_[bid]
                continue
            root, body, hp = cur[bid]
            dead = hp is not None and hp <= 0
            jump = bid in prv and max(math.dist(root, prv[bid][0]), math.dist(body, prv[bid][1])) > JUMP
            if L and (dead or jump):
                L.i1, L.end = i - 1, "gone"; ends.append((i, L)); del open_[bid]; L = None
            if L is None and not dead and (bid not in open_):
                L = Life(bid, i); open_[bid] = L; lives.append(L)
                if i > start: L.spawn = "timer"
            if L: L.path.append((T[i], *body))
    for L in open_.values(): L.i1, L.end = n - 1, "run end"
    # the first few samples after the counter reset: the game places its bots (they flash at an old spot, then jump)
    first = [L for L in lives if T[L.i0] - T[start] < 0.5]
    lives = [L for L in lives if not (L in first and L.end == "gone" and T[L.i1] - T[L.i0] < 0.2)]
    ends = [(e, L) for e, L in ends if L in lives]
    for L in lives:
        if T[L.i0] - T[start] < 0.5: L.spawn = "start"

    # the game's kills: match each counter step to the ending life nearest the crosshair
    def aim_err(i, L):
        _, x, y, z = L.path[-1]
        c = cam[min(i, n - 1)]
        dx, dy, dz = x - c[0], y - c[1], z - c[2]
        by = math.degrees(math.atan2(dy, dx)); bp = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        k = min(i, n - 1)
        return math.hypot((by - yaw[k] + 180) % 360 - 180, bp - pitch[k])
    kills, unmatched = [], 0
    used = set()
    for i in range(start + 1, n):
        step = kills_c[i] - kills_c[i - 1]
        for _ in range(max(0, step)):
            cands = [(aim_err(i - 1, L), e, L) for e, L in ends
                     if id(L) not in used and abs(T[min(e, n - 1)] - T[i]) <= KILL_WINDOW + 1e-6]
            if not cands: unmatched += 1; kills.append(dict(i=i, t=T[i], life=None)); continue
            _, e, L = min(cands, key=lambda c: c[0])
            used.add(id(L)); L.end = "kill"; L.kill_no = len(kills)
            kills.append(dict(i=i, t=T[i], life=L, err_deg=round(aim_err(i - 1, L), 2)))
    # what brought each new life in
    taken = set()
    for L in lives:
        if L.spawn == "start": continue
        k = next((k for k in range(len(kills) - 1, -1, -1) if kills[k]["life"] is not None and k not in taken
                  and 0 <= T[L.i0] - kills[k]["t"] <= SPAWN_AFTER_KILL + 1e-6), None)
        if k is not None: L.spawn, L.after_kill = "kill", k; taken.add(k)
    lives = [L for L in lives if L.path]
    game_kills = kills_c[-1] - kills_c[start] if has_kills else None
    return dict(path=path, rows=rows, n=n, start=start, T=T, yaw=yaw, pitch=pitch, cam=cam, hits=hits, kills_c=kills_c,
                src=src, lives=lives, kills=kills, game_kills=game_kills, has_kills=has_kills,
                detected=sum(k["life"] is not None for k in kills), unmatched=unmatched,
                kill_spawns=sum(L.spawn == "kill" for L in lives), timer_spawns=sum(L.spawn == "timer" for L in lives),
                non_kill_ends=sum(L.end == "gone" for L in lives))

def summary(a):
    gk = a["game_kills"]
    lines = [os.path.basename(a["path"]),
             f"  kills: detected {a['detected']} / game counter {gk}" + ("  MATCH" if gk is not None and a["detected"] == gk else ""),
             f"  lives: {len(a['lives'])} (at start {sum(L.spawn == 'start' for L in a['lives'])}, after a kill {a['kill_spawns']}, "
             f"on their own {a['timer_spawns']}); ended without a kill: {a['non_kill_ends']}"]
    if not a["has_kills"]: lines.append("  (older recording: no kill counter or health columns)")
    return "\n".join(lines)

if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(summary(analyse(p)))
