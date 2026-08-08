-- ActorConsistency: after ProgressKeeper reinject, make world entities match flags.
-- Prevents duplicate pickups / stale doors when Continue rebuilt actors from stale BB.

ActorConsistency = ActorConsistency or {
  enabled = true,
  reload_fallback = true,
  reload_scheduled = false,
}

local function log(msg)
  if Game and Game.LogWarn then
    Game.LogWarn(0, "[ActorConsistency] " .. tostring(msg))
  end
end

local function location_prop(scenarioId, actorName)
  return "Location_Collected_" .. scenarioId .. "_" .. actorName
end

function ActorConsistency.IsLocationCollected(scenarioId, actorName)
  local ps = Game.GetPlayerBlackboardSectionName()
  if not ps then return false end
  local v = Blackboard.GetProp(ps, location_prop(scenarioId, actorName))
  return v == true or v == 1
end

--- Disable a pickup actor that should already be collected.
function ActorConsistency.DisableCollectedPickup(actor)
  if actor == nil then return end
  -- Best-effort across component layouts used by Dread pickups / ODR
  pcall(function()
    if actor.PICKABLE ~= nil then
      if actor.PICKABLE.bPickedUp ~= nil then
        actor.PICKABLE.bPickedUp = true
      end
    end
  end)
  pcall(function()
    if actor.LIFE ~= nil and actor.LIFE.bDead ~= nil then
      actor.LIFE.bDead = true
    end
  end)
  pcall(function()
    Game.DeleteEntity(actor.sName)
  end)
  pcall(function()
    if actor.bEnabled ~= nil then actor.bEnabled = false end
  end)
end

function ActorConsistency.ApplyCollectedPickups()
  local scenarioId = CurrentScenarioID
  if not scenarioId or not Game.GetEntities then return end

  local entities = Game.GetEntities()
  if type(entities) ~= "table" then return end

  for name, _def in pairs(entities) do
    if ActorConsistency.IsLocationCollected(scenarioId, name) then
      local actor = Game.GetActor(name)
      if actor ~= nil then
        log("Disabling collected pickup " .. tostring(name))
        ActorConsistency.DisableCollectedPickup(actor)
      end
    end
  end
end

function ActorConsistency.ApplyRandoVisuals()
  if Scenario then
    if Scenario.UpdateProgressiveItemModels then
      pcall(Scenario.UpdateProgressiveItemModels)
    end
    if Scenario.UpdateBlastShields then
      pcall(Scenario.UpdateBlastShields)
    end
  end
end

--- Re-run scenario InitFromBlackboard if present so doors/bosses match reinjected props.
function ActorConsistency.ReplayScenarioBlackboardInit()
  if CurrentScenario and CurrentScenario.InitFromBlackboard then
    pcall(CurrentScenario.InitFromBlackboard)
  elseif LocalG and LocalG.CurrentScenario and LocalG.CurrentScenario.InitFromBlackboard then
    pcall(LocalG.CurrentScenario.InitFromBlackboard)
  end
end

function ActorConsistency.ScheduleScenarioReload()
  if not ActorConsistency.reload_fallback or ActorConsistency.reload_scheduled then
    return
  end
  if not Scenario or not Scenario.FadeOutAndReloadCurrentScenario then
    if Game.FadeOutAndReloadCurrentScenario then
      ActorConsistency.reload_scheduled = true
      log("Fallback: FadeOutAndReloadCurrentScenario")
      Game.FadeOutAndReloadCurrentScenario(0.3)
    end
    return
  end
  ActorConsistency.reload_scheduled = true
  log("Fallback: Scenario.FadeOutAndReloadCurrentScenario")
  Scenario.FadeOutAndReloadCurrentScenario(0.3)
end

--- Probe whether a collected pickup is still interactable (desync).
function ActorConsistency.NeedsReload()
  local scenarioId = CurrentScenarioID
  if not scenarioId or not Game.GetEntities then return false end
  local entities = Game.GetEntities()
  if type(entities) ~= "table" then return false end
  for name, _ in pairs(entities) do
    if ActorConsistency.IsLocationCollected(scenarioId, name) then
      local actor = Game.GetActor(name)
      if actor ~= nil and actor.PICKABLE ~= nil and actor.PICKABLE.bPickedUp == false then
        return true
      end
    end
  end
  return false
end

function ActorConsistency.Apply()
  if not ActorConsistency.enabled then return end
  log("Apply")
  ActorConsistency.ReplayScenarioBlackboardInit()
  ActorConsistency.ApplyCollectedPickups()
  ActorConsistency.ApplyRandoVisuals()

  if ActorConsistency.NeedsReload() then
    log("Desync detected after reinject")
    if Game.AddSF then
      Game.AddSF(0.2, "ActorConsistency.ScheduleScenarioReload", "")
    else
      ActorConsistency.ScheduleScenarioReload()
    end
  end
end
