# PB celebrations, local only. For every tracking scenario the player has recordings of, reads the game's own
# statistics file (Trainer/Statistics/Ranked, Normal or Custom) and finds:
#   - "pb":   a score above every earlier score
#   - "week": a new best 7-day typical (median) score (needs 8+ runs in the window)
# A PB only counts after 10+ earlier runs of that scenario, so first plays never trigger it.
# State lives in data/pbs.json (known bests, events with the time they were first seen). The page shows events
# seen in the last 24 hours as a banner. Each event also gets a share card PNG in data/pb/.
import datetime as dt, json, os, statistics as st
from PIL import Image, ImageDraw, ImageFont
import config

STATE = os.path.join(config.DATA, "pbs.json")
CARDS = os.path.join(config.DATA, "pb")
MIN_EARLIER = 10
WEEK_MIN_RUNS = 8


def stats_file(scenario):
    """The game's statistics file for a recorded scenario name ('X - RANKED' lives in Ranked/ as 'X.json')."""
    if not config.STATS: return None
    ranked = config.key(scenario).endswith("RANKED")
    want = config.key(scenario)[:-6] if ranked else config.key(scenario)
    for folder in (["Ranked"] if ranked else ["Normal", "Custom"]):
        d = os.path.join(config.STATS, folder)
        if not os.path.isdir(d): continue
        for f in os.listdir(d):
            if f.endswith(".json") and config.key(f[:-5]) == want: return os.path.join(d, f)
    return None


def history(scenario):
    """[(date, score)] in play order from the game's statistics file."""
    p = stats_file(scenario)
    if not p: return []
    try: j = json.loads(open(p, "rb").read().decode("utf-16"))
    except Exception: return []
    out = []
    for s, d in zip(j.get("Score", []), j.get("Date", [])):
        try: dd, mm, yy = d.split("/"); out.append((f"{yy}-{int(mm):02d}-{int(dd):02d}", round(s)))
        except ValueError: pass
    return out


def week_medians(h):
    """{date: median of the 7 days ending that date} for dates with enough runs."""
    days = sorted({d for d, _ in h}); out = {}
    for d in days:
        lo = (dt.date.fromisoformat(d) - dt.timedelta(days=6)).isoformat()
        xs = [s for dd, s in h if lo <= dd <= d]
        if len(xs) >= WEEK_MIN_RUNS: out[d] = round(st.median(xs))
    return out


def card(ev, still=None):
    """Share card PNG (1200x675) for Discord or X."""
    W, H = 1200, 675
    try:
        FB = ImageFont.truetype("arialbd.ttf", 150); FM = ImageFont.truetype("arialbd.ttf", 44)
        FS = ImageFont.truetype("arial.ttf", 30); FT = ImageFont.truetype("arialbd.ttf", 30)
    except Exception: FB = FM = FS = FT = ImageFont.load_default()
    im = Image.new("RGB", (W, H), (20, 20, 19)); d = ImageDraw.Draw(im)
    acc, ink, dim = (240, 122, 69), (244, 243, 238), (150, 149, 140)
    d.text((60, 56), {"pb": "NEW PERSONAL BEST", "week": "BEST WEEK YET"}[ev["kind"]], fill=acc, font=FT)
    d.text((60, 100), ev["title"], fill=ink, font=FM)
    d.text((54, 170), str(ev["score"] if ev["kind"] == "pb" else ev["median"]), fill=ink, font=FB)
    sub = f"Old best {ev['old']}" if ev["kind"] == "pb" else f"Typical score over 7 days (was {ev['old']})"
    d.text((60, 350), sub, fill=dim, font=FS)
    if ev["kind"] == "pb" and still and os.path.exists(still):
        s = Image.open(still).convert("RGB").resize((520, 293)); im.paste(s, (W - 580, 330))
    tr = ev.get("trend") or []
    if ev["kind"] == "week" and len(tr) >= 3:                 # the 7-day typical score over time, latest highlighted
        x0, y0, x1, y1 = W - 600, 410, W - 60, 530
        lo, hi = min(tr), max(tr); hi = hi if hi > lo else lo + 1
        pts = [(x0 + (x1 - x0) * i / (len(tr) - 1), y1 - (y1 - y0) * (v - lo) / (hi - lo)) for i, v in enumerate(tr)]
        d.line(pts, fill=dim, width=3, joint="curve")
        d.ellipse([pts[-1][0] - 9, pts[-1][1] - 9, pts[-1][0] + 9, pts[-1][1] + 9], fill=acc)
        d.text((x0, y1 + 20), f"7-day typical score, last {len(tr)} practice days", fill=dim, font=FS)
    d.text((60, H - 70), f"{ev['date']}  ·  Aimbeast  ·  AimStats", fill=dim, font=FS)
    os.makedirs(CARDS, exist_ok=True)
    name = f"{ev['date']}-{config.key(ev['title'])[:40]}-{ev['kind']}.png"
    im.save(os.path.join(CARDS, name))
    return name


def update(scenarios, stills=None):
    """scenarios: {recorded scenario name: display title}. stills: {scenario: best-run poster PNG path}.
    Returns {"events": [...], "history": {scenario: [(date, score)]}}."""
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {"best": {}, "week": {}, "events": []}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hist = {}
    for name, title in scenarios.items():
        h = history(name)
        hist[name] = h
        if not h: continue
        k = config.key(name)
        top = max(s for _, s in h)
        known = state["best"].get(k)
        if known is None:
            state["best"][k] = top                                    # first look: just remember, no event
        elif top > known:
            i = next(i for i, (_, s) in enumerate(h) if s == top)
            if i >= MIN_EARLIER:
                ev = dict(kind="pb", scenario=name, title=title, score=top, old=known, date=h[i][0], seen_utc=now)
                ev["card"] = card(ev, (stills or {}).get(name))
                state["events"].append(ev)
            state["best"][k] = top
        wm = week_medians(h)
        if wm:
            last_d = max(wm); cur = wm[last_d]
            kw = state["week"].get(k)
            if kw is None:
                state["week"][k] = max(wm.values())
            elif cur > kw:
                ev = dict(kind="week", scenario=name, title=title, median=cur, old=kw, date=last_d, seen_utc=now,
                          trend=[wm[d] for d in sorted(wm)][-12:])
                ev["card"] = card(ev)
                state["events"].append(ev); state["week"][k] = cur
    os.makedirs(config.DATA, exist_ok=True)
    json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
    return {"events": state["events"], "history": hist}
