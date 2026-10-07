-- Keep Elun's arrival gate open when the scenario loads.

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

-- Wrap Elun's gate handlers after scenario setup, then open the gate.
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

  -- Elun loads its saved state after Scenario.InitFromBlackboard.
  local orig_init = Scenario.InitFromBlackboard
  Scenario.InitFromBlackboard = function(...)
    orig_init(...)
    -- Open the gate before Elun checks whether its gates should be open.
    pcall(ApElunArrivalGate.EnsureWrapped)
  end

  if type(Scenario.OnLoadScenarioFinished) == "function" then
    local orig_onload = Scenario.OnLoadScenarioFinished
    Scenario.OnLoadScenarioFinished = function(...)
      orig_onload(...)
      pcall(ApElunArrivalGate.OnScenarioReady)
    end
  end

  -- Also handle Elun already being loaded when this script starts.
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
