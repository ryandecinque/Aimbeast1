-- PracticeLog: writes a timestamped line for every scenario load, start and finish.
-- Read-only: nothing is shown or changed in game. Output: ue4ss/Mods/PracticeLog/practice_log.csv
local TAG = "[PracticeLog] "
local FILE = "ue4ss/Mods/PracticeLog/practice_log.csv" -- relative to Binaries/Win64
local MAIN_GI = "/Game/Aimbeast/Main_GI.Main_GI_C"
local T_HUD = "/Game/Aimbeast/UI/HUD/T_HUD.T_HUD_C"
local FUNCS_LIB = "/Game/Aimbeast/Aimbeast_Functions_Lib.Aimbeast_Functions_Lib_C"
local function log(m) print(TAG .. m .. "\n") end

local currentScenario = ""

local function csv(v)
    v = tostring(v or "")
    if v:find('[,"]') then v = '"' .. v:gsub('"', '""') .. '"' end
    return v
end

local function routineInfo()
    local name, playing = "", false
    pcall(function()
        local gi = FindFirstOf("Main_GI_C")
        if gi and gi:IsValid() then
            playing = gi["PlayingRoutine?"] and true or false
            if playing then name = gi["Routine Name"]:ToString() end
        end
    end)
    return name, playing
end

local function write(event, scenario, completed, seconds)
    local h = io.open(FILE, "r"); local new = h == nil; if h then h:close() end
    local f = io.open(FILE, "a"); if not f then return end
    if new then f:write("time,event,scenario,routine,completed,session_seconds\n") end
    local routine = routineInfo()
    f:write(table.concat({ os.date("%Y-%m-%d %H:%M:%S"), event, csv(scenario), csv(routine),
        completed == nil and "" or tostring(completed), seconds and string.format("%.1f", seconds) or "" }, ","), "\n")
    f:close()
end

local hooks = {
    -- a scenario is loaded (from a routine or on its own)
    { MAIN_GI .. ":LoadScenario", function(Context, Mode, ScenarioName)
        pcall(function() currentScenario = ScenarioName:get():ToString() end)
        write("load", currentScenario)
    end },
    -- the countdown for a run starts (also fires on each restart)
    { T_HUD .. ":StartSession", function() write("start", currentScenario) end },
    -- a run ends; the game reports whether it was completed and how long it lasted
    { FUNCS_LIB .. ":Save Scenario To Training Streak", function(Context, ScenarioName, Time, Completed)
        local name, secs, done = currentScenario, nil, nil
        pcall(function() name = ScenarioName:get():ToString() end)
        pcall(function() secs = Time:get() end)
        pcall(function() done = Completed:get() end)
        write("end", name, done, secs)
    end },
}

local registered = {}
local function tryHooks()
    local all = true
    for i, h in ipairs(hooks) do
        if not registered[i] then
            if pcall(RegisterHook, h[1], h[2]) then registered[i] = true else all = false end
        end
    end
    return all
end
if not tryHooks() then
    LoopAsync(2000, function()
        local finished = false
        ExecuteInGameThread(function() finished = tryHooks() end)
        return finished
    end)
end
log("loaded, writing to " .. FILE)
