# Which scenarios can get a "same bots, killed sooner" model video, read from the scenario's own .scen and .bot files.
# A scenario qualifies when:
#   - bots come back because they were killed (kill-based respawn), not on a timer, and
#   - the bot doesn't react to being hit (no blink/leap on hit, no "ON HIT" event, no size change with health),
#     so killing it sooner can't change how it would have moved.
# The recording is checked too (lives.py); this file only answers what the scenario's settings say.
# Usage: python model_v2/scen_rules.py "<scenario name>" [...]
import glob, os, re, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scenario_profile as sp

SPAWN_FIELDS = ["ScenarioType", "BotNumber", "SpawningSystem", "CustomSpawnDelay?", "CustomSpawnDelay", "SkipFirstSpawnDelay?",
                "SpawnInOrderBots?", "CycleBotProfiles?", "OnBotCycleFinished", "TimeLimit", "KillLimit?", "KillLimit"]

def key(s): return re.sub(r"[^A-Z0-9]", "", s.upper().replace(" - RANKED", ""))

def find_scen(scenario):
    """The .scen file for a scenario name (a recording's name: '_' stands for '%' and similar)."""
    want = key(scenario)
    hits = [p for p in glob.glob(os.path.join(sp.WORKSHOP, "*", "*.scen")) if key(os.path.basename(p)[:-5]) == want]
    hits.sort(key=lambda p: " - RANKED" not in p)          # the ranked copy if both exist
    return hits[0] if hits else None

def field(d, name):
    """One named field from an unpacked .scen. sp.read() stops at the bot list, so the spawn fields after it are read here."""
    nb = name.encode() + b"\x00"
    i = d.find(struct.pack("<i", len(nb)) + nb)
    if i < 0: return None
    o = i + 4 + len(nb) + 8
    if name.endswith("?"): return bool(d[o])
    s = sp.fstr_at(d, o)
    if s and s[0] and re.match(r"^[ -~]+$", s[0]): return s[0]
    f = struct.unpack("<f", d[o:o + 4])[0]; n = struct.unpack("<i", d[o:o + 4])[0]
    return n if abs(n) < 100000 and abs(f) < 1e-30 else round(f, 3)

def scen_settings(scenario):
    p = find_scen(scenario)
    if not p: return {}
    d = sp.unpack(p)
    out = {k: field(d, k) for k in SPAWN_FIELDS}
    out["file"] = p
    out["bot_files"] = sorted(glob.glob(os.path.join(os.path.dirname(p), "*.bot")))
    return out

def hit_reactions(bot):
    """Ways the bot reacts to being hit, from its .bot settings. [] = it doesn't."""
    out = []
    if bot.get("BlinkOnHit?") and bot.get("EnableBlink?", True): out.append("blinks when hit")
    if bot.get("LeapOnHit?") and bot.get("EnableLeap?", True): out.append("leaps when hit")
    if bot.get("EnableEvents?"):
        for n in range(1, int(bot.get("EventsCount") or 0) + 1):
            if str(bot.get(f"EventTrigger_{n}", "")).upper() == "ON HIT":
                out.append(f"event {n} on hit: {bot.get(f'EventTriggered_{n}')}")
    if bot.get("EnableSizeShifting?") and str(bot.get("SizeShiftEndTrigger", "")).upper() not in ("", "NONE", "LOOP"):
        out.append(f"changes size with damage ({bot.get('SizeShiftEndTrigger')})")
    if bot.get("EnableSizeShifting?") and bot.get("SizeShiftEndDamage"):
        out.append("changes size with damage")
    return out

def rules(scenario):
    """{'ok': bool, 'why': [plain reasons], 'settings': {...}, 'bot': {...}} from the files alone."""
    s = scen_settings(scenario)
    if not s: return dict(ok=False, why=["scenario file not found in the Workshop folder"], settings={}, bot={})
    bots = []
    for b in s["bot_files"]:
        try: bots.append(sp.read(b))
        except Exception: pass
    why, ok = [], True
    if not bots: return dict(ok=False, why=["no bot file next to the scenario"], settings=s, bot={})
    if s.get("ScenarioType") == "TRACKING":
        # tracking is scored on time on target, not kills: killing sooner isn't what a better run looks like
        ok = False; why.append("tracking scenario: the score is time on target, not kills (use ideal_run_video.py)")
    for b in bots:
        if b.get("Invincible?"): ok = False; why.append("bots can't die (invincible)")
        if b.get("LifeTime?"): ok = False; why.append(f"bots also vanish on a {b.get('LifeTime')}s timer (not only when killed)")
        r = hit_reactions(b)
        if r: ok = False; why.append("bot reacts to hits: " + ", ".join(r))
        if b.get("EnableHealthRegen?"):
            ok = False; why.append("bot heals over time, so how long a kill takes depends on how the damage was spread out")
    if s.get("CustomSpawnDelay?") and (s.get("CustomSpawnDelay") or 0) > 0.3:
        ok = False; why.append(f"new bots wait {s['CustomSpawnDelay']}s after a kill")
    if ok: why.append(f"bots have {bots[0].get('Health')} health, come back when killed (spawning: {s.get('SpawningSystem')}), "
                      "and nothing in the bot file reacts to hits")
    return dict(ok=ok, why=sorted(set(why), key=why.index), settings=s, bot=bots[0], bots=bots)

if __name__ == "__main__":
    for name in sys.argv[1:]:
        r = rules(name)
        print(f"== {name}: {'QUALIFIES' if r['ok'] else 'no'}")
        for w in r["why"]: print("   -", w)
        print("   spawn settings:", {k: v for k, v in r["settings"].items() if k not in ("bot_files",)})
        b = r["bot"]
        if b: print("   bot:", {k: b.get(k) for k in ("BotType", "Health", "SphereRadiusMin", "CapsuleRadiusMin", "CapsuleHeightMin", "LifeTime?", "EnableEvents?", "EventsCount")})
