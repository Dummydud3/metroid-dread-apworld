-- Keep health at least 1 on arrival and while saving.
-- DeathLink can otherwise leave a checkpoint with zero health.
-- Raise health only if every readable value is below 1.

ApMinLife = ApMinLife or {}
ApMinLife.FLOOR = 1
ApMinLife._orig = ApMinLife._orig or {}

local function log_floor(reason, lowest)
  if RL == nil or type(RL.SendApLog) ~= "function" then
    return
  end
  -- Keep AP_LIFE logs hidden unless debug logging is on.
  pcall(
    RL.SendApLog,
    "AP_LIFE: floor "
      .. tostring(reason)
      .. " low="
      .. tostring(lowest)
      .. " to "
      .. tostring(ApMinLife.FLOOR)
  )
end

function ApMinLife.PlayerSection()
  if Game == nil or type(Game.GetPlayerBlackboardSectionName) ~= "function" then
    return nil
  end
  local ok, section = pcall(Game.GetPlayerBlackboardSectionName)
  if ok and type(section) == "string" and section ~= "" then
    return section
  end
  return nil
end

function ApMinLife.ReadCopies()
  local copies = {}
  local section = ApMinLife.PlayerSection()
  if section ~= nil and Blackboard ~= nil then
    local ok, value = pcall(Blackboard.GetProp, section, "ITEM_CURRENT_LIFE")
    if ok and tonumber(value) ~= nil then
      copies[#copies + 1] = tonumber(value)
    end
  end
  if Blackboard ~= nil then
    local ok, value = pcall(Blackboard.GetProp, "PLAYER_INVENTORY", "ITEM_CURRENT_LIFE")
    if ok and tonumber(value) ~= nil then
      copies[#copies + 1] = tonumber(value)
    end
  end
  if Game ~= nil and type(Game.GetItemAmount) == "function" and type(Game.GetPlayerName) == "function" then
    local ok, value = pcall(Game.GetItemAmount, Game.GetPlayerName(), "ITEM_CURRENT_LIFE")
    if ok and tonumber(value) ~= nil then
      copies[#copies + 1] = tonumber(value)
    end
  end
  if Game ~= nil and type(Game.GetPlayer) == "function" then
    local ok, player = pcall(Game.GetPlayer)
    if ok and player ~= nil and player.LIFE ~= nil then
      local life_ok, life = pcall(function()
        return player.LIFE.fCurrentLife
      end)
      if life_ok and tonumber(life) ~= nil then
        copies[#copies + 1] = tonumber(life)
      end
    end
  end
  return copies
end

-- True when all readable health values needed raising to FLOOR.
function ApMinLife.Clamp(reason)
  local copies = ApMinLife.ReadCopies()
  if #copies == 0 then
    return false
  end
  local lowest = copies[1]
  local highest = copies[1]
  for i = 2, #copies do
    local value = copies[i]
    if value < lowest then
      lowest = value
    end
    if value > highest then
      highest = value
    end
  end
  if highest >= ApMinLife.FLOOR then
    return false
  end
  local floor = ApMinLife.FLOOR
  if Game ~= nil and type(Game.SetItemAmount) == "function" and type(Game.GetPlayerName) == "function" then
    pcall(Game.SetItemAmount, Game.GetPlayerName(), "ITEM_CURRENT_LIFE", floor)
  end
  if Game ~= nil and type(Game.GetPlayer) == "function" then
    pcall(function()
      local player = Game.GetPlayer()
      if player ~= nil and player.LIFE ~= nil then
        player.LIFE.fCurrentLife = floor
      end
    end)
  end
  if Blackboard ~= nil then
    local section = ApMinLife.PlayerSection()
    if section ~= nil then
      pcall(Blackboard.SetProp, section, "ITEM_CURRENT_LIFE", "f", floor)
    end
    pcall(Blackboard.SetProp, "PLAYER_INVENTORY", "ITEM_CURRENT_LIFE", "f", floor)
  end
  ApMinLife._needsPersist = true
  log_floor(reason, lowest)
  return true
end

function ApMinLife.StartPoint()
  local section = ApMinLife.PlayerSection()
  if section == nil or Blackboard == nil then
    return nil
  end
  local ok, start = pcall(Blackboard.GetProp, section, "StartPoint")
  if ok and type(start) == "string" and start ~= "" then
    return start
  end
  return nil
end

function ApMinLife.ScenarioId()
  local scen = nil
  local section = ApMinLife.PlayerSection()
  if section ~= nil and Blackboard ~= nil then
    local ok, value = pcall(Blackboard.GetProp, section, "ScenarioID")
    if ok then
      scen = value
    end
  end
  if type(scen) ~= "string" or scen == "" then
    if type(CurrentScenarioID) == "string" and CurrentScenarioID ~= "" then
      scen = CurrentScenarioID
    end
  end
  if type(scen) == "string" and scen ~= "" then
    return scen
  end
  return nil
end

function ApMinLife.AtSaveStation()
  local start = ApMinLife.StartPoint()
  if type(start) ~= "string" then
    return false
  end
  local low = string.lower(start)
  if string.find(low, "savestation", 1, true) ~= nil then
    return true
  end
  if string.find(low, "weightactivatedplatform_save", 1, true) ~= nil then
    return true
  end
  return false
end

function ApMinLife.SaveBusy()
  if Game == nil or type(Game.IsSaveDataBusy) ~= "function" then
    return false
  end
  local ok, busy = pcall(Game.IsSaveDataBusy)
  return ok and busy and true or false
end

function ApMinLife.LifeLocked()
  if Game == nil or type(Game.GetPlayer) ~= "function" then
    return false
  end
  local ok, locked = pcall(function()
    local player = Game.GetPlayer()
    if player == nil or player.LIFE == nil then
      return false
    end
    return player.LIFE.bCurrentLifeLocked and true or false
  end)
  return ok and locked and true or false
end

function ApMinLife.InControl()
  if Scenario == nil or type(Scenario.IsUserInteractionEnabled) ~= "function" then
    return true
  end
  local ok, enabled = pcall(Scenario.IsUserInteractionEnabled, true)
  if not ok then
    return true
  end
  return enabled and true or false
end

function ApMinLife.BeginEnterGuard()
  -- Arrival cutscenes keep controls disabled after loading.
  -- Limit the guard so a later DeathLink can still kill the player.
  ApMinLife._enterTicks = 80
end

function ApMinLife.EnterGuarding()
  local ticks = ApMinLife._enterTicks or 0
  if ticks <= 0 then
    return false
  end
  if ApMinLife.InControl() then
    ApMinLife._enterTicks = 0
    return true
  end
  ApMinLife._enterTicks = ticks - 1
  return true
end

function ApMinLife.Protecting()
  if ApMinLife.SaveBusy() then
    return true
  end
  if ApMinLife.LifeLocked() then
    return true
  end
  return ApMinLife.EnterGuarding()
end

function ApMinLife.RewriteSlots(include_savedata)
  if ApMinLife._rewriting then
    return false
  end
  local save = ApMinLife._orig.SaveGame
  if type(save) ~= "function" then
    return false
  end
  local start = ApMinLife.StartPoint()
  local scen = ApMinLife.ScenarioId()
  if start == nil or scen == nil then
    return false
  end
  ApMinLife._rewriting = true
  ApMinLife.Clamp("rewrite")
  pcall(save, "checkpoint", scen, start, true)
  if include_savedata then
    pcall(save, "savedata", scen, start, true)
  end
  ApMinLife._rewriting = false
  return true
end

function ApMinLife.FlushPersist()
  if ApMinLife._rewriting or ApMinLife.SaveBusy() then
    return false
  end
  if not ApMinLife._needsPersist then
    return false
  end
  local savedata = ApMinLife._persistSavedata or ApMinLife.AtSaveStation()
  local wrote = ApMinLife.RewriteSlots(savedata)
  if not wrote then
    ApMinLife._flushMisses = (ApMinLife._flushMisses or 0) + 1
    if ApMinLife._flushMisses > 40 then
      ApMinLife._needsPersist = false
      ApMinLife._flushMisses = 0
    end
    return false
  end
  ApMinLife._needsPersist = false
  ApMinLife._persistSavedata = false
  ApMinLife._flushMisses = 0
  log_floor(savedata and "slot-savedata" or "slot-checkpoint", ApMinLife.FLOOR)
  return true
end

local function wrap_save(name)
  if Game == nil or type(Game[name]) ~= "function" then
    return
  end
  if ApMinLife._orig[name] ~= nil then
    return
  end
  local orig = Game[name]
  ApMinLife._orig[name] = orig
  Game[name] = function(...)
    if ApMinLife._rewriting then
      return orig(...)
    end
    local kind = select(1, ...)
    -- Raise health before saving so the snapshot cannot store zero.
    local raised = ApMinLife.Clamp("pre-" .. name)
    local r1, r2, r3, r4 = orig(...)
    if ApMinLife.Clamp("post-" .. name) then
      raised = true
      r1, r2, r3, r4 = orig(...)
    end
    if raised and name == "SaveGame" and kind == "savedata" then
      ApMinLife._persistSavedata = true
    end
    return r1, r2, r3, r4
  end
end

local function wrap_scenario(name, before, after, begin_guard)
  if Scenario == nil or type(Scenario[name]) ~= "function" then
    return
  end
  if ApMinLife._orig[name] ~= nil then
    return
  end
  local orig = Scenario[name]
  ApMinLife._orig[name] = orig
  Scenario[name] = function(...)
    if before then
      ApMinLife.Clamp("pre-" .. name)
    end
    local r1, r2, r3, r4 = orig(...)
    if begin_guard then
      ApMinLife.BeginEnterGuard()
    end
    if after then
      ApMinLife.Clamp("post-" .. name)
    end
    return r1, r2, r3, r4
  end
end

function ApMinLife._PollBody()
  -- Keep health at least 1 during saving and arrival cutscenes.
  -- This prevents a snapshot from storing zero during the animation.
  -- Update the save slot after the arrival point is set.
  if ApMinLife.Protecting() then
    ApMinLife.Clamp("protect")
    return
  end
  if ApMinLife._needsPersist then
    ApMinLife.FlushPersist()
  end
end

function ApMinLife.Poll()
  pcall(function()
    local mode = nil
    if Game ~= nil and type(Game.GetCurrentGameModeID) == "function" then
      mode = Game.GetCurrentGameModeID()
    end
    if mode ~= nil and mode ~= "INGAME" then
      return
    end
    ApMinLife._PollBody()
  end)
  if Game ~= nil and type(Game.AddSF) == "function" then
    Game.AddSF(0.1, "ApMinLife.Poll", "")
  end
end

function ApMinLife.Install()
  if not ApMinLife._installed then
    ApMinLife._installed = true
    wrap_scenario("InitScenario", true, true, true)
    wrap_scenario("OnLoadScenarioFinished", false, true, true)
    wrap_scenario("OnLoadGameFromSaveData", false, true, true)
    wrap_save("SaveGame")
    wrap_save("SaveGameToSnapshot")
    wrap_save("SaveSnapshotToCheckpoint")
  end
  if not ApMinLife._poll and Game ~= nil and type(Game.AddSF) == "function" then
    local ok = pcall(Game.AddSF, 0.1, "ApMinLife.Poll", "")
    if ok then
      ApMinLife._poll = true
    end
  end
end
