# Model v2: same bots, killed sooner

For scenarios where bots die and come back. A "20% better" run can't add bots that weren't in the recording,
so this replays the **same bots, in the same order, on their real recorded paths**, and has a model kill each one
sooner. Each bot only uses an earlier slice of the path it really took, and the next bot appears as soon as the
model's kill happens. The whole run ends sooner. Nothing is invented.

## Files
- `lives.py`: finds each bot's life in a recording (when it appeared, when it died, the path in between) and matches
  every kill to a bot. It checks itself against the game's kill counter. This is shared code for the later switching analysis.
  `python model_v2/lives.py <run csv>`
- `scen_rules.py`: reads the scenario's `.scen` and `.bot` files and decides whether v2 is allowed.
  `python model_v2/scen_rules.py "<scenario>"`
- `fast_clip.py`: the model and the videos.
  `python model_v2/fast_clip.py <run csv> <out prefix> [factor=1.2]` writes `<out>_side.mp4` (real left, model right),
  `<out>_solo.mp4` and a still `<out>_solo.png`, and prints a report. `NO_RENDER=1` prints the report only.

## When a scenario qualifies
- Bots die (not invincible) and come back only when killed: no lifetime timer, no long spawn delay. The recording must agree:
  every new bot shows up within 0.3 s of a kill.
- The bot doesn't react to being hit: no blink or leap on hit, no event triggered "ON HIT", no size change with damage,
  and no healing (healing makes the kill time depend on how the damage was spread).
- The kills found in the recording equal the game's kill counter.

## The model
- Same as the other model videos: it reacts about 130 ms late and its aim follows a spring.
- The spring is critically damped, so a flick to the next bot never goes past it.
- It stays on each bot until it dies. The time on target a kill takes is Ryan's own: the median unbroken stretch he
  spent on each bot right before killing it.
- Only the spring strength is tuned, until the total time is the real time ÷ factor.
- Several bots can be alive at once. Each one keeps its own real path, shifted to its new spawn time, so the spacing
  between bots is approximate. The video says so.
- If a bot's real path ends before the model would kill it, the run can't be shown at that factor. The script then
  reports which bots ran out and uses the nearest factor that works.

## Older recordings
- Files from before the kill counter (VOX 125%, TRM, SUMO, 2026-10-08 20:2x) can't be checked, so they're skipped.
- Files from before the body columns only have each bot's root position. If the hits land far from it, as on VOX,
  the visible height is taken from the aim at each hit and joined up in between (as `pb_video.py` does). The video then says so.
