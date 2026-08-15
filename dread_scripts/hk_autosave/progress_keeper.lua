-- ProgressKeeper: Hollow Knight–style progression persistence for Metroid Dread
-- Load via Game.DoFile("system/scripts/progress_keeper.lua") from ODR custom_scenario.
--
-- Design: RespawnAnchor (bench) vs ProgressStore (inventory + BB + visits).
-- Always reinject ProgressStore AFTER checkpoint/save load (see death_counter pattern).

ProgressKeeper = ProgressKeeper or {
  enabled = true,
  dirty = false,
  flush_scheduled = false,
  debounce_seconds = 1.0,
  pending_death = false,
  store = {
    inventory = {},
    player_props = {},
    game_progress = {},
    game_section = {},
    scenario_props = {}, -- [scenarioId] = { [key] = {type=, value=} }
    visit_meta = {},     -- opaque; filled if OdrMap / native bind present
  },
  anchor = {
    LevelID = "c10_samus",
    ScenarioID = nil,
    StartPoint = nil,
  },
  -- Keys restored to MAX on death (not mid-fight CURRENT from store)
  vitals_keys = {
    "ITEM_CURRENT_LIFE",
    "ITEM_CURRENT_SPECIAL_ENERGY",
    "ITEM_WEAPON_MISSILE_CURRENT",
    "ITEM_WEAPON_POWER_BOMB_CURRENT",
  },
  persist_item_keys = {
    "ITEM_DOUBLE_JUMP", "ITEM_FLOOR_SLIDE", "ITEM_GHOST_AURA", "ITEM_GRAVITY_SUIT",
    "ITEM_HYPER_SUIT", "ITEM_MAGNET_GLOVE", "ITEM_MAX_LIFE", "ITEM_MAX_SPECIAL_ENERGY",
    "ITEM_METROIDNIZATION", "ITEM_METROID_COUNT", "ITEM_METROID_TOTAL_COUNT",
    "ITEM_MORPH_BALL", "ITEM_MULTILOCKON", "ITEM_OPTIC_CAMOUFLAGE",
    "ITEM_RESERVE_TANK_LIFE", "ITEM_RESERVE_TANK_LIFE_SIZE",
    "ITEM_RESERVE_TANK_MISSILE", "ITEM_RESERVE_TANK_MISSILE_SIZE",
    "ITEM_RESERVE_TANK_SPECIAL_ENERGY", "ITEM_RESERVE_TANK_SPECIAL_ENERGY_SIZE",
    "ITEM_SCREW_ATTACK", "ITEM_SONAR", "ITEM_SPACE_JUMP", "ITEM_SPEED_BOOSTER",
    "ITEM_SPRING_BALL", "ITEM_VARIA_SUIT", "ITEM_WEAPON_BOMB", "ITEM_WEAPON_CHARGE_BEAM",
    "ITEM_WEAPON_DIFFUSION_BEAM", "ITEM_WEAPON_GRAPPLE_BEAM", "ITEM_WEAPON_HYPER_BEAM",
    "ITEM_WEAPON_ICE_MISSILE", "ITEM_WEAPON_LINE_BOMB", "ITEM_WEAPON_MISSILE_MAX",
    "ITEM_WEAPON_PLASMA_BEAM", "ITEM_WEAPON_POWER_BOMB", "ITEM_WEAPON_POWER_BOMB_MAX",
    "ITEM_WEAPON_SUPER_MISSILE", "ITEM_WEAPON_WAVE_BEAM", "ITEM_WEAPON_WIDE_BEAM",
    "ITEM_WEAPON_MISSILE_LAUNCHER", "ITEM_WEAPON_POWER_BEAM", "ITEM_WEAPON_STORM_MISSILE",
    "ITEM_ENERGY_TANKS", "ITEM_LIFE_SHARDS",
    "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", "ITEM_UPGRADE_SPEED_BOOST_CHARGE",
  },
  game_progress_keys = {
    "QUARENTINE_OPENED", "TeleportWorldUnlocked", "RandoTeleportWorldUnlocked",
    "RandoVisitScenarios", "RandoUnlockTeleportal", "X_RELEASE_TRUE",
  },
  game_section_keys = {
    "NumTanksPickedUp", "Completion", "Rando_PlayerDeathCount",
  },
  player_prop_keys = {
    "InventoryIndex", "THIS_RANDO_IDENTIFIER", "RANDO_GAME_INITIALIZED",
  },
  did_patch_hooks = false,
}

local function log(msg)
  if Game and Game.LogWarn then
    Game.LogWarn(0, "[ProgressKeeper] " .. tostring(msg))
  end
end

local function player_name()
  if Game.GetPlayerName then
    return Game.GetPlayerName()
  end
  return "Samus"
end

local function get_item(item_id)
  local ok, amount = pcall(Game.GetItemAmount, player_name(), item_id)
  if ok then return amount end
  return Blackboard.GetProp("PLAYER_INVENTORY", item_id)
end

local function set_item(item_id, amount)
  if amount == nil then return end
  local ok = pcall(Game.SetItemAmount, player_name(), item_id, amount)
  if not ok then
    Blackboard.SetProp("PLAYER_INVENTORY", item_id, "f", amount)
  end
end

local function is_vital(item_id)
  for _, k in ipairs(ProgressKeeper.vitals_keys) do
    if k == item_id then return true end
  end
  return false
end

local function save_busy()
  if Game.IsSaveDataBusy then
    local ok, busy = pcall(Game.IsSaveDataBusy)
    return ok and busy
  end
  return false
end

function ProgressKeeper.Init()
  log("Init")
  ProgressKeeper.PatchHooks()
  ProgressKeeper.CaptureAnchorFromBlackboard()
  ProgressKeeper.CaptureNow()
end

function ProgressKeeper.CaptureAnchorFromBlackboard()
  local ps = Game.GetPlayerBlackboardSectionName()
  if not ps then return end
  ProgressKeeper.anchor.LevelID = Blackboard.GetProp(ps, "LevelID") or ProgressKeeper.anchor.LevelID
  ProgressKeeper.anchor.ScenarioID = Blackboard.GetProp(ps, "ScenarioID") or CurrentScenarioID
  ProgressKeeper.anchor.StartPoint = Blackboard.GetProp(ps, "StartPoint") or ProgressKeeper.anchor.StartPoint
end

function ProgressKeeper.SetRespawnAnchor(scenarioId, startPointActor)
  ProgressKeeper.anchor.ScenarioID = scenarioId or CurrentScenarioID
  ProgressKeeper.anchor.StartPoint = startPointActor
  local ps = Game.GetPlayerBlackboardSectionName()
  if ps and startPointActor then
    -- Keep live BB aligned so vanilla Continue spawn matches bench
    Blackboard.SetProp(ps, "ScenarioID", "s", ProgressKeeper.anchor.ScenarioID)
    Blackboard.SetProp(ps, "StartPoint", "s", startPointActor)
    if ProgressKeeper.anchor.LevelID then
      Blackboard.SetProp(ps, "LevelID", "s", ProgressKeeper.anchor.LevelID)
    end
  end
  log(string.format("RespawnAnchor = %s @ %s", tostring(scenarioId), tostring(startPointActor)))
  ProgressKeeper.MarkDirty("save_station")
end

function ProgressKeeper.GetRespawnAnchor()
  return ProgressKeeper.anchor
end

function ProgressKeeper.CaptureNow()
  local inv = {}
  for _, key in ipairs(ProgressKeeper.persist_item_keys) do
    local amount = get_item(key)
    if amount ~= nil then
      inv[key] = amount
    end
  end
  ProgressKeeper.store.inventory = inv

  local ps = Game.GetPlayerBlackboardSectionName()
  local player_props = {}
  if ps then
    for _, key in ipairs(ProgressKeeper.player_prop_keys) do
      local v = Blackboard.GetProp(ps, key)
      if v ~= nil then
        player_props[key] = v
      end
    end
    -- Capture Location_Collected_* via known ODR increments is incomplete;
    -- hooked writers should call CapturePlayerProp. Best-effort: keep prior keys.
    if ProgressKeeper.store.player_props then
      for k, v in pairs(ProgressKeeper.store.player_props) do
        if type(k) == "string" and k:find("^Location_Collected_", 1) then
          local live = Blackboard.GetProp(ps, k)
          player_props[k] = live ~= nil and live or v
        end
      end
    end
  end
  ProgressKeeper.store.player_props = player_props

  local gp = {}
  for _, key in ipairs(ProgressKeeper.game_progress_keys) do
    local v = Blackboard.GetProp("GAME_PROGRESS", key)
    if v ~= nil then gp[key] = v end
  end
  -- Preserve previously seen dynamic keys (RandoVisited*, teleportal ids, …)
  if ProgressKeeper.store.game_progress then
    for k, v in pairs(ProgressKeeper.store.game_progress) do
      local live = Blackboard.GetProp("GAME_PROGRESS", k)
      gp[k] = live ~= nil and live or v
    end
  end
  ProgressKeeper.store.game_progress = gp

  local gs = {}
  for _, key in ipairs(ProgressKeeper.game_section_keys) do
    local v = Blackboard.GetProp("GAME", key)
    if v ~= nil then gs[key] = v end
  end
  ProgressKeeper.store.game_section = gs

  local scenarioId = CurrentScenarioID
  if scenarioId then
    ProgressKeeper.store.scenario_props[scenarioId] = ProgressKeeper.store.scenario_props[scenarioId] or {}
    -- Scenario props are filled by hooked WriteToBlackboard / CaptureScenarioProp
  end

  if OdrMap and OdrMap.DumpVisitBits then
    ProgressKeeper.store.visit_meta = OdrMap.DumpVisitBits()
  end

  log("CaptureNow complete")
end

function ProgressKeeper.CapturePlayerProp(key, typ, value)
  ProgressKeeper.store.player_props[key] = value
  ProgressKeeper._prop_types = ProgressKeeper._prop_types or {}
  ProgressKeeper._prop_types["player:" .. key] = typ or "b"
  ProgressKeeper.MarkDirty("player_prop")
end

function ProgressKeeper.CaptureScenarioProp(scenarioId, key, typ, value)
  scenarioId = scenarioId or CurrentScenarioID
  if not scenarioId then return end
  ProgressKeeper.store.scenario_props[scenarioId] = ProgressKeeper.store.scenario_props[scenarioId] or {}
  ProgressKeeper.store.scenario_props[scenarioId][key] = value
  ProgressKeeper._prop_types = ProgressKeeper._prop_types or {}
  ProgressKeeper._prop_types["scenario:" .. scenarioId .. ":" .. key] = typ or "b"
  ProgressKeeper.MarkDirty("scenario_prop")
end

function ProgressKeeper.CaptureGameProgressProp(key, typ, value)
  ProgressKeeper.store.game_progress[key] = value
  ProgressKeeper._prop_types = ProgressKeeper._prop_types or {}
  ProgressKeeper._prop_types["gp:" .. key] = typ or "b"
  ProgressKeeper.MarkDirty("game_progress")
end

function ProgressKeeper.MarkDirty(reason)
  if not ProgressKeeper.enabled then return end
  ProgressKeeper.dirty = true
  ProgressKeeper.last_dirty_reason = reason
  local immediate = reason == "major_item" or reason == "boss" or reason == "save_station" or reason == "ap_item"
  if immediate then
    ProgressKeeper.Flush()
    return
  end
  if ProgressKeeper.flush_scheduled then return end
  ProgressKeeper.flush_scheduled = true
  if Game.AddSF then
    Game.AddSF(ProgressKeeper.debounce_seconds, "ProgressKeeper._DebouncedFlush", "")
  end
end

function ProgressKeeper._DebouncedFlush()
  ProgressKeeper.flush_scheduled = false
  ProgressKeeper.Flush()
end

function ProgressKeeper.Flush()
  if not ProgressKeeper.enabled then return end
  if not ProgressKeeper.dirty and not ProgressKeeper.pending_force_flush then
    return
  end
  if save_busy() then
    log("Flush deferred — save busy")
    if Game.AddSF then
      Game.AddSF(0.5, "ProgressKeeper._DebouncedFlush", "")
      ProgressKeeper.flush_scheduled = true
    end
    return
  end

  ProgressKeeper.CaptureNow()

  -- Prefer profile autosave with FROZEN respawn anchor (quit-to-title safety).
  local anchor = ProgressKeeper.anchor.StartPoint
  if anchor and Game.SaveGame then
    local ok, err = pcall(Game.SaveGame, "savedata", "HKAutosave", anchor, true)
    if not ok then
      log("SaveGame savedata failed: " .. tostring(err))
    else
      log("Flushed profile savedata @ " .. tostring(anchor))
    end
  else
    log("Flush skipped profile save — no RespawnAnchor.StartPoint yet")
  end

  -- Optional native: merge progress into live checkpoint without moving spawn
  if OdrProgress and OdrProgress.MergeCheckpointProgress then
    OdrProgress.MergeCheckpointProgress(ProgressKeeper.store)
  end

  if minimap and minimap.SetProfileDataDirty then
    pcall(minimap.SetProfileDataDirty)
  end

  ProgressKeeper.dirty = false
  ProgressKeeper.pending_force_flush = false
end

function ProgressKeeper.ReinjectInventory()
  for key, amount in pairs(ProgressKeeper.store.inventory or {}) do
    if not is_vital(key) then
      set_item(key, amount)
    end
  end
end

function ProgressKeeper.ReinjectBlackboard()
  local ps = Game.GetPlayerBlackboardSectionName()
  local types = ProgressKeeper._prop_types or {}

  if ps then
    for key, value in pairs(ProgressKeeper.store.player_props or {}) do
      local typ = types["player:" .. key] or (type(value) == "boolean" and "b") or (type(value) == "string" and "s") or "f"
      Blackboard.SetProp(ps, key, typ, value)
    end
  end

  for key, value in pairs(ProgressKeeper.store.game_progress or {}) do
    local typ = types["gp:" .. key] or (type(value) == "boolean" and "b") or (type(value) == "string" and "s") or "f"
    Blackboard.SetProp("GAME_PROGRESS", key, typ, value)
  end

  for key, value in pairs(ProgressKeeper.store.game_section or {}) do
    local typ = (type(value) == "boolean" and "b") or (type(value) == "string" and "s") or "i"
    Blackboard.SetProp("GAME", key, typ, value)
  end

  for scenarioId, props in pairs(ProgressKeeper.store.scenario_props or {}) do
    local section = Game.GetScenarioBlackboardSectionID and Game.GetScenarioBlackboardSectionID(scenarioId)
    if section then
      for key, value in pairs(props) do
        local typ = types["scenario:" .. scenarioId .. ":" .. key]
          or (type(value) == "boolean" and "b")
          or (type(value) == "string" and "s")
          or "i"
        Blackboard.SetProp(section, key, typ, value)
      end
    end
  end

  -- Never let reinject overwrite RespawnAnchor with stale store values
  ProgressKeeper.ApplyAnchorToBlackboard()
end

function ProgressKeeper.ApplyAnchorToBlackboard()
  local ps = Game.GetPlayerBlackboardSectionName()
  local a = ProgressKeeper.anchor
  if not ps or not a.StartPoint then return end
  if a.LevelID then Blackboard.SetProp(ps, "LevelID", "s", a.LevelID) end
  if a.ScenarioID then Blackboard.SetProp(ps, "ScenarioID", "s", a.ScenarioID) end
  Blackboard.SetProp(ps, "StartPoint", "s", a.StartPoint)
end

function ProgressKeeper.ReinjectVisits()
  if OdrMap and OdrMap.RestoreVisitBits and ProgressKeeper.store.visit_meta then
    OdrMap.RestoreVisitBits(ProgressKeeper.store.visit_meta)
  end
end

function ProgressKeeper.RecoverVitals()
  if Scenario and Scenario.RecoverPlayerMaxItemsAmounts then
    Scenario.RecoverPlayerMaxItemsAmounts()
    return
  end
  -- Fallback: CURRENT = MAX for known vitals pairs
  local pairs_map = {
    ITEM_CURRENT_LIFE = "ITEM_MAX_LIFE",
    ITEM_CURRENT_SPECIAL_ENERGY = "ITEM_MAX_SPECIAL_ENERGY",
    ITEM_WEAPON_MISSILE_CURRENT = "ITEM_WEAPON_MISSILE_MAX",
    ITEM_WEAPON_POWER_BOMB_CURRENT = "ITEM_WEAPON_POWER_BOMB_MAX",
  }
  for cur, maxk in pairs(pairs_map) do
    local maxv = get_item(maxk)
    if maxv ~= nil then set_item(cur, maxv) end
  end
  if Game.ReinitPlayerFromBlackboard then
    Game.ReinitPlayerFromBlackboard()
  end
end

function ProgressKeeper.OnPlayerDead()
  -- Capture latest progress BEFORE Continue wipes BB; do not write BB here.
  ProgressKeeper.pending_death = true
  ProgressKeeper.CaptureNow()
  log("OnPlayerDead — store snapshotted; reinject scheduled for after load")
end

function ProgressKeeper.OnAfterLoad()
  if not ProgressKeeper.enabled then return end
  log("OnAfterLoad — reinjecting ProgressStore")
  ProgressKeeper.ReinjectInventory()
  ProgressKeeper.ReinjectBlackboard()
  ProgressKeeper.ReinjectVisits()

  if Game.ReinitPlayerFromBlackboard then
    pcall(Game.ReinitPlayerFromBlackboard)
  end

  if ActorConsistency and ActorConsistency.Apply then
    ActorConsistency.Apply()
  end

  if ProgressKeeper.pending_death then
    ProgressKeeper.RecoverVitals()
    ProgressKeeper.pending_death = false
  end

  -- Ensure profile matches reinjected state
  ProgressKeeper.dirty = true
  ProgressKeeper.pending_force_flush = true
  ProgressKeeper.Flush()

  if RandomizerPowerup and RandomizerPowerup.UpdateWeapons then
    pcall(RandomizerPowerup.UpdateWeapons)
  end
  if RandomizerPowerup and RandomizerPowerup.ApplyTunableChanges then
    pcall(RandomizerPowerup.ApplyTunableChanges)
  end
end

function ProgressKeeper.OnPickableItemPickedUp(...)
  ProgressKeeper.CaptureNow()
  ProgressKeeper.MarkDirty("pickup")
end

function ProgressKeeper.OnMinimapCellVisited(...)
  ProgressKeeper.MarkDirty("map_cell")
end

function ProgressKeeper.OnSaveStationUsed(actor)
  if actor == nil then return end
  local name = actor.sName or actor
  ProgressKeeper.SetRespawnAnchor(CurrentScenarioID, name)
  ProgressKeeper.Flush()
end

function ProgressKeeper.PatchHooks()
  if ProgressKeeper.did_patch_hooks then return end
  ProgressKeeper.did_patch_hooks = true

  if guicallbacks then
    local orig_pickup = guicallbacks.OnPickableItemPickedUp
    guicallbacks.OnPickableItemPickedUp = function(...)
      if orig_pickup then orig_pickup(...) end
      ProgressKeeper.OnPickableItemPickedUp(...)
    end

    local orig_visit = guicallbacks.OnMinimapCellVisited
    guicallbacks.OnMinimapCellVisited = function(...)
      if orig_visit then orig_visit(...) end
      ProgressKeeper.OnMinimapCellVisited(...)
    end
  end

  if DamagePlants then
    local orig_dead = DamagePlants.OnPlayerDead
    DamagePlants.OnPlayerDead = function(...)
      ProgressKeeper.OnPlayerDead()
      if orig_dead then return orig_dead(...) end
    end
  end

  if Scenario and Scenario.WriteToBlackboard then
    local orig_write = Scenario.WriteToBlackboard
    Scenario.WriteToBlackboard = function(prop, typ, value)
      orig_write(prop, typ, value)
      ProgressKeeper.CaptureScenarioProp(CurrentScenarioID, prop, typ, value)
    end
  end

  if Scenario and Scenario.IsSaveStation and Scenario.CheckWarpToStart then
    -- Warp-to-start already detects save stations; wrap a generic usable hook if present later.
  end

  log("Hooks patched")
end

function ProgressKeeper.DebugDump()
  log("dirty=" .. tostring(ProgressKeeper.dirty)
    .. " anchor=" .. tostring(ProgressKeeper.anchor.ScenarioID)
    .. "/" .. tostring(ProgressKeeper.anchor.StartPoint))
  local n = 0
  for _ in pairs(ProgressKeeper.store.inventory or {}) do n = n + 1 end
  log("inventory_keys=" .. n)
end

-- ODR / custom_scenario integration helpers
function ProgressKeeper.OnScenarioInitialized()
  ProgressKeeper.OnAfterLoad()
end
