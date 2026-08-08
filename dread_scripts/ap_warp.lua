-- ApWarp: location-independent hotkey warps (not HK autosave / ProgressKeeper).
--
-- Must be bootstrapped at the END of scenario.lc so ODR Scenario.* methods exist.
-- Hotkey polling piggybacks on Scenario.CheckDebugInputs (ODR's proven input loop).
--
-- Hotkeys (INGAME, user interaction enabled):
--   Close pause/options while holding ZL → last checkpoint
--   Close pause/options while holding ZR → last save
--   ZL + DPAD_LEFT  → last checkpoint
--   ZR + DPAD_RIGHT → last save
--   ZL + ZR + DPAD_LEFT  → last checkpoint  (same style as suit-change debug)
--   ZL + ZR + DPAD_RIGHT → last save
--
-- Warp uses the same LoadScenario call as ODR warp-to-start.
-- Combos are edge-triggered (release and press again) — no sticky cooldown.

ApWarp = ApWarp or {
  enabled = true,
  level_id = "c10_samus",
  last_save = nil,       -- { scenario=, start= }
  last_checkpoint = nil, -- { scenario=, start= }
  menu_open = false,
  held_combo = nil,      -- edge detect: "checkpoint" | "save" | nil
  did_install = false,
}

-- Older builds left ApWarp.cooling=true forever after LoadScenario wiped AddSF.
ApWarp.cooling = false

-- Last blackboard spawn we classified, so GetEntities() is only walked on change.
ApWarp.seen_start = ApWarp.seen_start or nil
ApWarp.seen_scenario = ApWarp.seen_scenario or nil

-- Charclass of the weight plate the engine actually respawns Samus on. The
-- savestation/accesspoint/maproom actors the player interacts with are usables,
-- not spawn points, and LoadScenario silently falls back to the scenario's
-- default start when handed one.
local SAVE_PLATFORM_CHARCLASSES = {
  weightactivatedplatform_save = true,
}

-- Usables that mean "the game was saved". ODR's Scenario.IsSaveStation also
-- accepts accesspoint and maproom because warp-to-start works at all three,
-- but those never write a save.
local SAVE_USABLE_CHARCLASSES = {
  savestation = true,
}

local function log(msg)
  if Game and Game.LogWarn then
    Game.LogWarn(0, "[ApWarp] " .. tostring(msg))
  end
end

local function inputs(...)
  if not Input or not Input.CheckInputs then
    return false
  end
  local ok, held = pcall(Input.CheckInputs, ...)
  return ok and held == true
end

local function entities()
  if not Game or not Game.GetEntities then
    return nil
  end
  local ok, tbl = pcall(Game.GetEntities)
  if ok and type(tbl) == "table" then
    return tbl
  end
  return nil
end

-- Scenario.GetCharclass logs every lookup; read the table directly instead.
local function charclass_of(name, tbl)
  tbl = tbl or entities()
  if not tbl or type(name) ~= "string" then
    return nil
  end
  return tbl[name]
end

-- GetEntities only covers the loaded scenario, so spawns recorded in another
-- area need a name test. Every save plate in the game embeds the station name
-- (savestation_000_platform, PRP_CV_SaveStation002_WeightPlate).
local function name_looks_like_save(name)
  return string.find(string.lower(name), "savestation", 1, true) ~= nil
end

local function is_save_spawn(name)
  local charclass = charclass_of(name)
  if charclass ~= nil and SAVE_PLATFORM_CHARCLASSES[charclass] then
    return true
  end
  return name_looks_like_save(name)
end

-- Map a save station usable to the plate the engine spawns on. Suffixes are
-- inconsistent (_platform vs _WeightPlate), so prefer the SMARTOBJECT backlink
-- and fall back to a name prefix.
local function resolve_save_platform(usable_name)
  local tbl = entities()
  if not tbl then
    return nil
  end
  local prefixed = nil
  for name, charclass in pairs(tbl) do
    if SAVE_PLATFORM_CHARCLASSES[charclass] then
      local ok, actor = pcall(Game.GetActor, name)
      if ok and actor ~= nil and actor.SMARTOBJECT ~= nil
        and actor.SMARTOBJECT.sUsableEntity == usable_name then
        return name
      end
      if prefixed == nil
        and string.sub(name, 1, string.len(usable_name)) == usable_name then
        prefixed = name
      end
    end
  end
  return prefixed
end

local function current_scenario()
  if CurrentScenarioID then
    return CurrentScenarioID
  end
  if Game and Game.GetScenarioID then
    local ok, id = pcall(Game.GetScenarioID)
    if ok then return id end
  end
  return nil
end

local function capture_spawn(kind, scenario, start_point)
  if not scenario or not start_point or start_point == "" then
    return
  end
  local entry = {
    scenario = scenario,
    start = start_point,
    level = ApWarp.level_id,
  }
  if kind == "save" then
    ApWarp.last_save = entry
    log(string.format("last_save = %s @ %s", tostring(scenario), tostring(start_point)))
  else
    ApWarp.last_checkpoint = entry
    log(string.format("last_checkpoint = %s @ %s", tostring(scenario), tostring(start_point)))
  end
end

function ApWarp.NoteSaveStation(actor)
  if actor == nil then return end
  local name = actor.sName or actor
  if type(name) ~= "string" then return end
  local platform = resolve_save_platform(name)
  if platform == nil then
    -- Blackboard polling still catches it once the engine commits the respawn.
    log("save station " .. name .. " has no resolvable spawn plate")
    return
  end
  capture_spawn("save", current_scenario(), platform)
end

function ApWarp.NoteCheckpoint(scenario, start_point)
  capture_spawn("checkpoint", scenario, start_point)
end

--- Track the engine's own respawn point. Whatever sits in the player
--- blackboard is by definition a spawn actor LoadScenario accepts, so this is
--- both the most reliable save signal and the only warp target guaranteed to
--- put Samus where she expects to be.
function ApWarp.SyncFromBlackboard()
  local ps = Game.GetPlayerBlackboardSectionName and Game.GetPlayerBlackboardSectionName()
  if not ps then return end
  local start_point = Blackboard.GetProp(ps, "StartPoint")
  if type(start_point) ~= "string" or start_point == "" then
    return
  end
  local scenario = Blackboard.GetProp(ps, "ScenarioID") or current_scenario()
  if ApWarp.seen_start == start_point and ApWarp.seen_scenario == scenario then
    return
  end
  ApWarp.seen_start = start_point
  ApWarp.seen_scenario = scenario

  capture_spawn("checkpoint", scenario, start_point)
  if is_save_spawn(start_point) then
    capture_spawn("save", scenario, start_point)
  end
end

ApWarp.SyncCheckpointFromBlackboard = ApWarp.SyncFromBlackboard

function ApWarp.WarpTo(entry, label)
  if entry == nil or not entry.scenario or not entry.start then
    log("no " .. tostring(label) .. " spawn recorded yet")
    if GUI and GUI.ShowMessage then
      pcall(GUI.ShowMessage, "No " .. tostring(label) .. " recorded yet", true, "")
    end
    return false
  end
  local level = entry.level or ApWarp.level_id
  log(string.format("Warping to %s: %s / %s / %s", tostring(label), level, entry.scenario, entry.start))
  ApWarp.seen_start = nil
  ApWarp.seen_scenario = nil
  local ok, err = pcall(Game.LoadScenario, level, entry.scenario, entry.start, "", 1)
  if not ok then
    log("LoadScenario failed: " .. tostring(err))
    return false
  end
  return true
end

function ApWarp.WarpLastCheckpoint()
  return ApWarp.WarpTo(ApWarp.last_checkpoint, "last checkpoint")
end

function ApWarp.WarpLastSave()
  return ApWarp.WarpTo(ApWarp.last_save, "last save")
end

local function menu_appears_open()
  local candidates = {
    "IngameMenuRoot.samusmenucomposition",
    "IngameMenuRoot.mapmenucomposition",
    "IngameMenuRoot",
  }
  for _, path in ipairs(candidates) do
    local ok, obj = pcall(GUI.GetDisplayObject, path)
    if ok and obj ~= nil then
      local vis = nil
      if obj.Visible ~= nil then
        vis = obj.Visible
      else
        local ok2, v = pcall(function() return obj.bVisible end)
        if ok2 then vis = v end
      end
      if vis == true then
        return true
      end
    end
  end
  if Game.GetCurrentGameModeID then
    local ok, mode = pcall(Game.GetCurrentGameModeID)
    if ok and type(mode) == "string" then
      local m = string.upper(mode)
      if m:find("MENU", 1, true) or m:find("PAUSE", 1, true) then
        return true
      end
    end
  end
  return false
end

local function current_combo()
  if inputs("ZL", "ZR", "DPAD_LEFT") then
    return "checkpoint"
  end
  if inputs("ZL", "ZR", "DPAD_RIGHT") then
    return "save"
  end
  if inputs("ZL", "DPAD_LEFT") and not inputs("ZR") then
    return "checkpoint"
  end
  if inputs("ZR", "DPAD_RIGHT") and not inputs("ZL") then
    return "save"
  end
  return nil
end

local function fire_combo(combo)
  if combo == "checkpoint" then
    ApWarp.WarpLastCheckpoint()
  elseif combo == "save" then
    ApWarp.WarpLastSave()
  end
end

--- Called every CheckDebugInputs tick (ODR already schedules this in INGAME).
function ApWarp.Tick()
  if not ApWarp.enabled then
    return
  end

  ApWarp.cooling = false
  pcall(ApWarp.SyncFromBlackboard)

  local open = false
  local ok_open, result = pcall(menu_appears_open)
  if ok_open then open = result and true or false end

  -- Closing pause/options while holding a shoulder (one-shot on the close edge).
  if ApWarp.menu_open and not open then
    if inputs("ZL") and not inputs("ZR") then
      ApWarp.WarpLastCheckpoint()
    elseif inputs("ZR") and not inputs("ZL") then
      ApWarp.WarpLastSave()
    end
  end
  ApWarp.menu_open = open

  if not Scenario or not Scenario.IsUserInteractionEnabled then
    ApWarp.held_combo = nil
    return
  end
  local ok_ui, ui_ok = pcall(Scenario.IsUserInteractionEnabled, true)
  if not ok_ui or not ui_ok then
    ApWarp.held_combo = nil
    return
  end

  local combo = current_combo()
  if combo and combo ~= ApWarp.held_combo then
    fire_combo(combo)
  end
  ApWarp.held_combo = combo
end

function ApWarp.Install()
  -- Always clear sticky latch from older builds, even if already installed.
  ApWarp.cooling = false

  if ApWarp.did_install then
    return
  end

  -- Bootstrap must run after ODR defines these (end of scenario.lc).
  if not Scenario or type(Scenario.CheckDebugInputs) ~= "function" then
    log("Install deferred — waiting for Scenario.CheckDebugInputs")
    if Game.AddSF then
      Game.AddSF(0.25, "ApWarp.Install", "")
    end
    return
  end

  ApWarp.did_install = true

  local orig_debug = Scenario.CheckDebugInputs
  Scenario.CheckDebugInputs = function()
    pcall(ApWarp.Tick)
    return orig_debug()
  end

  if type(Scenario.CheckWarpToStart) == "function" then
    local orig_warp = Scenario.CheckWarpToStart
    Scenario.CheckWarpToStart = function(actor)
      local name = nil
      if actor ~= nil then
        name = actor.sName or actor
      end
      if type(name) == "string" and SAVE_USABLE_CHARCLASSES[charclass_of(name) or ""] then
        pcall(ApWarp.NoteSaveStation, actor)
      end
      -- ODR sends the player to the seed's starting location on plain ZL+ZR.
      -- Our combos are ZL+ZR plus a d-pad direction, so let those through to
      -- ApWarp.Tick instead of racing two LoadScenario calls.
      if inputs("DPAD_LEFT") or inputs("DPAD_RIGHT") then
        return
      end
      return orig_warp(actor)
    end
  else
    log("WARN: Scenario.CheckWarpToStart missing — save station use will not track")
  end

  if type(Scenario.OnLoadScenarioFinished) == "function" then
    local orig_onload = Scenario.OnLoadScenarioFinished
    Scenario.OnLoadScenarioFinished = function(...)
      orig_onload(...)
      ApWarp.cooling = false
      ApWarp.held_combo = nil
      ApWarp.seen_start = nil
      ApWarp.seen_scenario = nil
      pcall(ApWarp.SyncFromBlackboard)
    end
  else
    log("WARN: Scenario.OnLoadScenarioFinished missing — checkpoint seed may lag")
  end

  log("Install complete (ZL+DPAD_LEFT / ZL+ZR+DPAD_LEFT=checkpoint; ZR+DPAD_RIGHT / ZL+ZR+DPAD_RIGHT=save; ZL/ZR+close menu)")
end
