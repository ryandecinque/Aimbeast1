# PB celebrations for the site. Called by publish.py after each session.
# Finds, for the 6 ranked Intermediate scenarios:
#   - "pb":   a score above the official all-time best (rank-up noted when the new score crosses a rank step)
#   - "week": a new best 7-day median (the plan's real measure; needs 8+ runs in the window)
#   - "plan_best" chips: a day's best above every earlier day since the plan started (small, day view only)
# A PB only counts after 10+ earlier runs of that scenario, so first plays never trigger it.
# State lives in pbs.json (known bests, events with the time they were first seen). The page shows events
# seen in the last 24 hours as a banner. Each event also gets a share card PNG in assets/pb/.
import datetime as dt, json, os, statistics as st
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "pbs.json")
STATS = r"C:/Program Files (x86)/Steam/steamapps/common/Aimbeast/Aimbeast/Trainer/Statistics/Ranked"
TIERS = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master"]
MIN_EARLIER = 10
WEEK_MIN_RUNS = 8


def rank_name(i):
    if i <= 0: return "Unranked"
    if i > 18: return "Grandmaster"
    return f"{TIERS[(i - 1) // 3]} {(i - 1) % 3 + 1}"


def rank_of(score, steps, disabled=0):
    j = max((k for k, v in enumerate(steps) if score >= v), default=-1)
    return j + disabled + 1 if j >= 0 else 0


def history(name):
    """[(date, score)] in play order from the game's ranked statistics file."""
    p = os.path.join(STATS, name + " - RANKED.json")
    if not os.path.exists(p): p = os.path.join(STATS, name + ".json")
    if not os.path.exists(p): return []
    j = json.loads(open(p, "rb").read().decode("utf-16"))
    out = []
    for s, d in zip(j.get("Score", []), j.get("Date", [])):
        dd, mm, yy = d.split("/"); out.append((f"{yy}-{int(mm):02d}-{int(dd):02d}", round(s)))
    return out


def week_medians(h):
    """{date: median of the 7 days ending that date} for dates with enough runs."""
    days = sorted({d for d, _ in h}); out = {}
    for d in days:
        lo = (dt.date.fromisoformat(d) - dt.timedelta(days=6)).isoformat()
        xs = [s for dd, s in h if lo <= dd <= d]
        if len(xs) >= WEEK_MIN_RUNS: out[d] = round(st.median(xs))
    return out


def card(ev, slug):
    """Share card PNG (1200x675) for X or Discord."""
    W, H = 1200, 675
    try:
        FB = ImageFont.truetype("arialbd.ttf", 150); FM = ImageFont.truetype("arialbd.ttf", 44)
        FS = ImageFont.truetype("arial.ttf", 30); FT = ImageFont.truetype("arialbd.ttf", 30)
    except Exception: FB = FM = FS = FT = ImageFont.load_default()
    im = Image.new("RGB", (W, H), (20, 20, 19)); d = ImageDraw.Draw(im)
    acc, ink, dim = (240, 122, 69), (244, 243, 238), (150, 149, 140)
    head = {"pb": "NEW PERSONAL BEST", "week": "BEST WEEK YET"}[ev["kind"]]
    if ev.get("rank_to"): head = f"RANK UP: {ev['rank_to'].upper()}"
    d.text((60, 56), head, fill=acc, font=FT)
    d.text((60, 100), ev["title"], fill=ink, font=FM)
    big = str(ev["score"]) if ev["kind"] == "pb" else str(ev["median"])
    d.text((54, 170), big, fill=ink, font=FB)
    sub = (f"Old best {ev['old']}" if ev["kind"] == "pb" else f"Typical score over 7 days (was {ev['old']})")
    if ev.get("master3"): sub += f"  ·  Master 3 is {ev['master3']}"
    d.text((60, 350), sub, fill=dim, font=FS)
    still = os.path.join(HERE, "assets", "aim", f"best-{slug}-{ev['date']}.png")
    if ev["kind"] == "pb" and os.path.exists(still):
        s = Image.open(still).convert("RGB").crop((10, 40, 630, 280)).resize((520, 201))
        im.paste(s, (W - 580, 420))
    tr = ev.get("trend") or []
    if ev["kind"] == "week" and len(tr) >= 3:                 # the 7-day typical score over time, latest highlighted
        x0, y0, x1, y1 = W - 600, 410, W - 60, 530
        lo, hi = min(tr), max(tr); hi = hi if hi > lo else lo + 1
        pts = [(x0 + (x1 - x0) * i / (len(tr) - 1), y1 - (y1 - y0) * (v - lo) / (hi - lo)) for i, v in enumerate(tr)]
        d.line([(x0, y1 + 12), (x1, y1 + 12)], fill=(60, 60, 56), width=1)
        d.line(pts, fill=dim, width=3, joint="curve")
        d.ellipse([pts[-1][0] - 9, pts[-1][1] - 9, pts[-1][0] + 9, pts[-1][1] + 9], fill=acc)
        d.text((x0, y1 + 20), f"7-day typical score, last {len(tr)} practice days", fill=dim, font=FS)
    d.text((60, H - 70), f"{ev['date']}  ·  Road to Master 3  ·  ryandecinque.github.io/Aimbeast1", fill=dim, font=FS)
    os.makedirs(os.path.join(HERE, "assets", "pb"), exist_ok=True)
    name = f"{ev['date']}-{slug}-{ev['kind']}.png"
    im.save(os.path.join(HERE, "assets", "pb", name))
    return name


def update(ranks, plan_start, int_list):
    """ranks: publish.ranks() rows. int_list: [(workshop id, ranked name)]. Returns the data for data.json."""
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {"best": {}, "week": {}, "events": []}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rk = {r["name"]: r for r in ranks}
    from best_runs_auto import INT as SLUGS
    slug = {n: s for _, n, _, s in SLUGS}; title = {n: t for _, n, t, _ in SLUGS}
    plan_bests = {}
    for ws, name in int_list:
        r = rk.get(name, {}); h = history(name)
        if not h: continue
        steps = r.get("steps") or []; off = r.get("official_best"); m3 = r.get("master3")
        top = max(s for _, s in h)
        # all-time PB
        known = state["best"].get(ws)
        if known is None:
            state["best"][ws] = max(top, off or 0)                    # first run: just remember, no event
        elif top > known:
            k = next(i for i, (_, s) in enumerate(h) if s == top)
            if k >= MIN_EARLIER:
                ev = dict(kind="pb", ws=ws, name=name, title=title.get(name, name), score=top, old=known, date=h[k][0],
                          seen_utc=now, master3=int(m3) if m3 else None)
                if steps:
                    a, b = rank_of(known, steps), rank_of(top, steps)
                    if b > a: ev.update(rank_from=rank_name(a), rank_to=rank_name(b))
                ev["card"] = card(ev, slug.get(name, "x"))
                state["events"].append(ev)
            state["best"][ws] = top
        elif off and off > known:
            state["best"][ws] = off
        # best week (7-day median)
        wm = week_medians(h)
        if wm:
            last_d = max(wm); cur = wm[last_d]
            kw = state["week"].get(ws)
            if kw is None:
                state["week"][ws] = max(wm.values())
            elif cur > kw:
                ev = dict(kind="week", ws=ws, name=name, title=title.get(name, name), median=cur, old=kw, date=last_d,
                          seen_utc=now, master3=int(m3) if m3 else None, trend=[wm[k] for k in sorted(wm)][-12:])
                ev["card"] = card(ev, slug.get(name, "x"))
                state["events"].append(ev); state["week"][ws] = cur
        # plan-best chips: a day's best above every earlier day since the plan started
        days = sorted({d for d, _ in h if d >= plan_start})
        for i, d in enumerate(days[1:], 1):
            prev = max(s for dd, s in h if plan_start <= dd < d)
            today = max(s for dd, s in h if dd == d)
            if today > prev:
                plan_bests.setdefault(d, []).append(dict(title=title.get(name, name), score=today, old=prev))
    json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
    return {"events": state["events"], "plan_bests": plan_bests}
