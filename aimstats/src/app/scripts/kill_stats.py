# Simple numbers for switching and clicking runs: kills (found by lives.py and checked against the game's kill
# counter), time per kill, misses and clicks. Read-only on the recordings.
# Usage: python kill_stats.py <run csv> [...]
import json, sys
import fast_clip


def summarize(path):
    """{kills, game_kills, match, seconds, time_per_kill, misses, clicks, hits, type} or {"old": True} for recordings
    from before the kill counter."""
    a = fast_clip.load(path)
    if not a["has_kills"]: return {"old": True}
    rows, s0, T = a["rows"], a["start"], a["T"]
    end = a["n"] - 1
    secs = T[end] - T[s0]
    kills = a["detected"]
    m = lambda r: int(r.get("misses") or 0)
    clicks = sum(1 for i in range(s0 + 1, end + 1) if rows[i].get("m1") == "1" and rows[i - 1].get("m1") != "1")
    return dict(kills=kills, game_kills=a["game_kills"], match=kills == a["game_kills"], seconds=round(secs, 1),
                time_per_kill=round(secs / kills, 2) if kills else None, misses=m(rows[end]) - m(rows[s0]) if "misses" in rows[0] else None,
                clicks=clicks, hits=a["hits"][end] - a["hits"][s0],
                type=str((a["rules"].get("settings") or {}).get("ScenarioType") or "").upper())


if __name__ == "__main__":
    for p in sys.argv[1:]: print(json.dumps(summarize(p)))
