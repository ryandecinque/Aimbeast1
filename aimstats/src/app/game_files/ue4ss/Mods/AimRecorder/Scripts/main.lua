-- AimRecorder, phase 5: READ-ONLY recorder (up to 8 bots with id, health and visible body position, plus kills and misses). Never writes to the game, never changes scores.
-- AimStats copy. During a run (ranked runs too) it samples 60 times a second: camera aim and position,
-- every bot's position, the hit counter and whether M1 is held. It only reads these values; it never sets
-- scores, timers, bots or anything ranked. Samples stay in memory and are written once, when the run ends,
-- to its own folder. F7 turns recording on/off.
-- Output: ue4ss/Mods/AimRecorder/runs/<date>_<time>_<scenario>.csv, summary lines in log.txt
local TAG = "[AimRecorder] "
local DIR = "ue4ss/Mods/AimRecorder/"
local HUD = "/Game/Aimbeast/UI/HUD/T_HUD.T_HUD_C"
local PAWN = "/Game/Aimbeast/Player/Trainer/AB_C_Trainer.AB_C_Trainer_C"
local MAIN_GI = "/Game/Aimbeast/Main_GI.Main_GI_C"
local RATE = 1 / 60
local MAXBOTS = 8                  -- switching scenarios have 4-6 bots at once (phase 3, 2026-10-08)
local RECORD_RANKED = true         -- ranked runs are recorded too. Still read-only.

local function log(m)
    print(TAG .. m .. "\n")
    local f = io.open(DIR .. "log.txt", "a"); if f then f:write(os.date("%Y-%m-%d %H:%M:%S ") .. m .. "\n"); f:close() end
end

local enabled = true
local scenario = ""
local rec = nil          -- current run: { rows = {}, t = 0, acc = 0, bots = {}, cm = nil, pawn = nil, cost = 0, ticks = 0 }

local function findBots()
    local list = {}
    for _, b in ipairs(FindAllOf("AB_M_BOT_C") or {}) do
        if b:IsValid() and not b:GetFullName():find("Default__", 1, true) then list[#list + 1] = b end
    end
    return list
end

-- world position of one visible body part ("" if this bot type doesn't have it). Flying bots move these parts
-- up and down while the bot's root stays at one height (found 2026-10-09 in Sphere S and Air Track).
local function partPos(b, name)
    local ok, s = pcall(function()
        local c = b[name]
        if not (c and c:IsValid()) then return ",," end
        local p = c:K2_GetComponentLocation()
        return string.format("%.1f,%.1f,%.1f", p.X, p.Y, p.Z)
    end)
    return ok and s or ",,"
end

local function startRun()
    rec = nil
    if not enabled then return end
    if scenario:find("RANKED", 1, true) and not RECORD_RANKED then log("skipping ranked run: " .. scenario); return end
    rec = { rows = {}, t = 0, acc = 0, bots = {}, cost = 0, ticks = 0, samples = 0, started = os.date("%Y-%m-%d_%H%M%S") }
end

local function sample(r)
    local pawn, cm = r.pawn, r.cm
    if not (pawn and pawn:IsValid()) then
        pawn = FindFirstOf("AB_C_Trainer_C"); r.pawn = pawn
        if not (pawn and pawn:IsValid()) then return end
    end
    if not (cm and cm:IsValid()) then
        local pc = pawn.Controller
        cm = pc and pc:IsValid() and pc.PlayerCameraManager or nil; r.cm = cm
        if not (cm and cm:IsValid()) then return end
    end
    local rot = cm:GetCameraRotation()
    local loc = cm:GetCameraLocation()
    -- bots: re-find when any is gone, and every 30 samples so newly spawned bots are noticed
    local ok = #r.bots > 0 and (r.samples % 30) ~= 0
    for _, b in ipairs(r.bots) do if not b:IsValid() then ok = false end end
    if not ok then r.bots = findBots() end
    local parts = { string.format("%.4f,%.3f,%.3f,%.1f,%.1f,%.1f,%d,%d,%d,%d,%d", r.t, rot.Pitch, rot.Yaw, loc.X, loc.Y, loc.Z,
        pawn.Hits or 0, pawn["isMouseLeftDown?"] and 1 or 0, #r.bots, pawn.Kills or 0, pawn.Misses or 0) }
    for i = 1, math.min(#r.bots, MAXBOTS) do
        local b = r.bots[i]
        if b:IsValid() then
            local p = b:K2_GetActorLocation()
            parts[#parts + 1] = string.format("%d,%.1f,%.1f,%.1f,%.1f", b:GetAddress(), p.X, p.Y, p.Z, b.Health or -1)
                .. "," .. partPos(b, "c_middle_c") .. "," .. partPos(b, "sphere_c") .. "," .. partPos(b, "c_head")
        else
            parts[#parts + 1] = ",,,,,,,,,,,,,"
        end
    end
    r.rows[#r.rows + 1] = table.concat(parts, ",")
    r.samples = r.samples + 1
end

local function endRun(reason)
    local r = rec; rec = nil
    if not r or #r.rows < 30 then return end
    local name = (scenario:gsub("[^%w%-%. ]", "_"))
    local path = DIR .. "runs/" .. r.started .. "_" .. name .. ".csv"
    local f = io.open(path, "w")
    if f then
        local head = "t,pitch,yaw,cam_x,cam_y,cam_z,hits,m1,bots,kills,misses"
        for i = 1, MAXBOTS do head = head .. string.format(",b%d_id,b%d_x,b%d_y,b%d_z,b%d_hp", i, i, i, i, i)
            .. string.format(",b%d_mx,b%d_my,b%d_mz,b%d_sx,b%d_sy,b%d_sz,b%d_hx,b%d_hy,b%d_hz", i, i, i, i, i, i, i, i, i) end
        f:write(head .. "\n")
        f:write(table.concat(r.rows, "\n")); f:write("\n"); f:close()
    end
    log(string.format("%s: %s, %d samples over %.1f s, cost %.3f ms per sample, %.4f ms per frame (%d frames) -> %s",
        reason, scenario, r.samples, r.t, r.samples > 0 and 1000 * r.cost / r.samples or 0, r.ticks > 0 and 1000 * r.cost / r.ticks or 0, r.ticks, path))
end

local hooked = { hud = false, pawn = false, gi = false }
local function tryHooks()
    if not hooked.gi then
        hooked.gi = pcall(function()
            RegisterHook(MAIN_GI .. ":LoadScenario", function(Context, Mode, ScenarioName)
                pcall(function() scenario = ScenarioName:get():ToString() end)
            end)
        end)
    end
    if not hooked.hud then
        hooked.hud = pcall(function()
            RegisterHook(HUD .. ":StartSession", function()
                if rec then endRun("restarted") end
                startRun()
            end)
            RegisterHook(HUD .. ":EndSession", function() endRun("run ended") end)
        end)
    end
    if not hooked.pawn then
        hooked.pawn = pcall(function()
            RegisterHook(PAWN .. ":ReceiveTick", function(Context, DeltaSeconds)
                local r = rec
                if not r then return end
                local c0 = os.clock()
                local dt = 0
                pcall(function() dt = DeltaSeconds:get() end)
                r.t = r.t + dt; r.acc = r.acc + dt; r.ticks = r.ticks + 1
                if r.acc >= RATE then
                    r.acc = r.acc % RATE
                    local ok, err = pcall(sample, r)
                    if not ok then
                        r.errors = (r.errors or 0) + 1
                        if r.errors <= 3 then log("sample error: " .. tostring(err)) end
                        if r.errors > 50 then log("too many errors, stopping this run"); rec = nil; return end
                    end
                end
                r.cost = r.cost + (os.clock() - c0)
            end)
        end)
    end
end

RegisterKeyBind(Key.F7, function()
    enabled = not enabled
    if not enabled then rec = nil end
    log("recording " .. (enabled and "ON" or "OFF") .. " (F7)")
end)
RegisterHook("/Script/Engine.PlayerController:ClientRestart", function() tryHooks() end)
log("loaded (phase 5 recorder, read-only, ranked " .. (RECORD_RANKED and "on" or "off") .. ")")
