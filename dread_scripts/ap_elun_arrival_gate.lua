-- ApElunArrivalGate: keep Elun's arrival seal (ev_gatesealed_second) open on load.
--
-- Vanilla only ForceOpens that gate at the end of cutscene 113 (Save Station →
-- Exterior Bridge). CheckGatesOpened restores the X-release pair only, so after
-- ApWarp (or any leave that skips persisting EVENTPROP state) re-entry lands
-- the player in Transport/Save with the second gate sealed and CS113 already
-- consumed — softlock for transport-rando early Elun.
--
-- Fix: wrap s060_quarantine.CheckGatesOpened to ForceOpen the arrival gate
-- every time. Hook Scenario.InitFromBlackboard so the wrap is in place before
-- Elun's InitFromBlackboard calls CheckGatesOpened.

ApElunArrivalGate = ApElunArrivalGate or {
  did_install = false,
  enabled = true,
}

local function log(msg)
  if Game and Game.LogWarn then
    Game.LogWarn(0, "ApElunArrivalGate: " .. tostring(msg))
  end
end

function ApElunArrivalGate.ForceOpenArrivalGate()
  if not ApElunArrivalGate.enabled then
    return
  end
  local gate = Game.GetActor("ev_gatesealed_second")
  if gate == nil or gate.EVENTPROP == nil then
    return
  end
  pcall(function()
    gate.EVENTPROP:ForceOpen()
  end)
end

function ApElunArrivalGate.EnsureWrapped()
  if not ApElunArrivalGate.enabled then
    return
  end
  if type(s060_quarantine) ~= "table" then
    return
  end
  if s060_quarantine._ap_arrival_gate_wrapped then
    return
  end
  local orig = s060_quarantine.CheckGatesOpened
  if type(orig) ~= "function" then
    return
  end
  s060_quarantine.CheckGatesOpened = function()
    orig()
    ApElunArrivalGate.ForceOpenArrivalGate()
  end
  s060_quarantine._ap_arrival_gate_wrapped = true
  log("wrapped CheckGatesOpened (ForceOpen ev_gatesealed_second)")
end

--- After any scenario init: wrap Elun gates if that table exists, then open now
--- if actors are already spawned (Continue into Elun / late wrap).
function ApElunArrivalGate.OnScenarioReady()
  pcall(ApElunArrivalGate.EnsureWrapped)
  if type(s060_quarantine) == "table" and s060_quarantine._ap_arrival_gate_wrapped then
    pcall(ApElunArrivalGate.ForceOpenArrivalGate)
  end
end

function ApElunArrivalGate.Install()
  if ApElunArrivalGate.did_install then
    return
  end
  if not Scenario or type(Scenario.InitFromBlackboard) ~= "function" then
    log("Install deferred — waiting for Scenario.InitFromBlackboard")
    if Game and Game.AddSF then
      Game.AddSF(0.25, "ApElunArrivalGate.Install", "")
    end
    return
  end

  ApElunArrivalGate.did_install = true

  -- Elun InitFromBlackboard calls Scenario.InitFromBlackboard *then*
  -- CheckGatesOpened. Wrapping here means EnsureWrapped runs in between.
  local orig_init = Scenario.InitFromBlackboard
  Scenario.InitFromBlackboard = function(...)
    orig_init(...)
    -- Between Scenario.InitFromBlackboard and Elun's CheckGatesOpened call.
    pcall(ApElunArrivalGate.EnsureWrapped)
  end

  if type(Scenario.OnLoadScenarioFinished) == "function" then
    local orig_onload = Scenario.OnLoadScenarioFinished
    Scenario.OnLoadScenarioFinished = function(...)
      orig_onload(...)
      pcall(ApElunArrivalGate.OnScenarioReady)
    end
  end

  -- Fallback: first INGAME ticks if Elun was already loaded before Install.
  if type(Scenario.CheckDebugInputs) == "function" then
    local orig_debug = Scenario.CheckDebugInputs
    local ticks = 0
    Scenario.CheckDebugInputs = function()
      if ticks < 8 then
        ticks = ticks + 1
        pcall(ApElunArrivalGate.OnScenarioReady)
      end
      return orig_debug()
    end
  end

  pcall(ApElunArrivalGate.OnScenarioReady)
  log("Install complete")
end
