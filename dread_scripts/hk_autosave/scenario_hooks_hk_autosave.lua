-- Glue to wire ProgressKeeper into an ODR-style custom_scenario bootstrap.
-- Usage (in custom_scenario.lua after other DoFiles):
--   Game.DoFile("system/scripts/progress_keeper.lua")
--   Game.DoFile("system/scripts/actor_consistency.lua")
--   Game.DoFile("system/scripts/scenario_hooks_hk_autosave.lua")
--   HkAutosave.Install()

HkAutosave = HkAutosave or {}

function HkAutosave.Install()
  if HkAutosave._installed then return end
  HkAutosave._installed = true

  if ProgressKeeper then
    ProgressKeeper.Init()
  end

  -- After ODR Scenario.InitScenario body would run DeathCounter.OnScenarioInitialized
  if Scenario and Scenario.InitScenario then
    local orig_init = Scenario.InitScenario
    Scenario.InitScenario = function(...)
      orig_init(...)
      if ProgressKeeper then
        -- Slight delay so InitFromBlackboard / entities exist
        if Game.AddSF then
          Game.AddSF(0.05, "ProgressKeeper.OnScenarioInitialized", "")
        else
          ProgressKeeper.OnScenarioInitialized()
        end
      end
    end
  end

  if Scenario and Scenario.OnLoadScenarioFinished then
    local orig_onload = Scenario.OnLoadScenarioFinished
    Scenario.OnLoadScenarioFinished = function(...)
      orig_onload(...)
      if ProgressKeeper then
        ProgressKeeper.OnAfterLoad()
      end
    end
  end

  -- Save station / access point / map room → update RespawnAnchor
  if Scenario then
    local orig_warp = Scenario.CheckWarpToStart
    Scenario.CheckWarpToStart = function(actor)
      if Scenario.IsSaveStation and Scenario.IsSaveStation(actor) and ProgressKeeper then
        ProgressKeeper.OnSaveStationUsed(actor)
      end
      if orig_warp then
        return orig_warp(actor)
      end
    end
  end

  -- AP remote item grant hook (call from multiworld receive path)
  function HkAutosave.OnRemoteItemGranted()
    if ProgressKeeper then
      ProgressKeeper.CaptureNow()
      ProgressKeeper.MarkDirty("ap_item")
    end
  end

  if Game and Game.LogWarn then
    Game.LogWarn(0, "[HkAutosave] Install complete")
  end
end
