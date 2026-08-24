-- World-map region unlock smoke (AreaBox probe + OdrMap.UnlockWorldRegion).
-- Loaded on demand via Game.DoFile — kept out of connect bootstrap (fits 4096 buffer).
if not RL then RL = {} end

RL.MapRegionToScenario = RL.MapRegionToScenario or {
  ["Artaria"] = "s010_cave",
  ["Cataris"] = "s020_magma",
  ["Dairon"] = "s030_baselab",
  ["Burenia"] = "s040_aqua",
  ["Ghavoran"] = "s050_forest",
  ["Elun"] = "s060_quarantine",
  ["Ferenia"] = "s070_basesanc",
  ["Hanubia"] = "s080_shipyard",
  ["Itorash"] = "s090_skybase",
}

-- Compact AreaBox AABBs (gridDef inset cell_size 100). Prefer DoFile table when present.
RL.ScenarioAreaBox = RL.ScenarioAreaBox or {
  ["s010_cave"] = {-27700.0, -9900.0, 33700.0, 11000.0},
  ["s020_magma"] = {-20300.0, -8300.0, 19500.0, 9600.0},
  ["s030_baselab"] = {-26500.0, -10000.0, 27100.0, 8000.0},
  ["s040_aqua"] = {-8800.0, -12900.0, 13900.0, 13100.0},
  ["s050_forest"] = {-15300.0, -6400.0, 20000.0, 8100.0},
  ["s060_quarantine"] = {-16000.0, -2400.0, 9500.0, 3700.0},
  ["s070_basesanc"] = {-26500.0, -7800.0, 13500.0, 7400.0},
  ["s080_shipyard"] = {-19200.0, -8600.0, 18400.0, 8900.0},
  ["s090_skybase"] = {-5800.0, -4700.0, 6700.0, 3600.0},
}

function RL.ProbeAreaBox(scenario)
  local sc = tostring(scenario or "")
  local bits = {}
  local function try_get(section, key)
    if not Blackboard or not Blackboard.GetProp then
      return nil
    end
    local ok, v = pcall(Blackboard.GetProp, section, key)
    if ok and v ~= nil then
      return v
    end
    return nil
  end
  local probes = {
    {"MINIMAP", "AreaBox[" .. sc .. "]"},
    {"MINIMAP", "AreaBox"},
    {"MINIMAP", sc},
    {"GAME", "MINIMAP:AreaBox[" .. sc .. "]"},
    {"GAME_PROGRESS", "AreaBox[" .. sc .. "]"},
  }
  for _, p in ipairs(probes) do
    local v = try_get(p[1], p[2])
    local label = p[1] .. "/" .. p[2]
    if v ~= nil then
      bits[#bits + 1] = label .. "=" .. tostring(v)
    else
      bits[#bits + 1] = label .. "=nil"
    end
  end
  return table.concat(bits, "; ")
end

function RL.MapUnlockRegionSmoke(scenario)
  local scen = scenario
  if scen == nil or scen == "" then
    scen = "s020_magma"
  end
  scen = tostring(scen)
  if RL.MapRegionToScenario and RL.MapRegionToScenario[scen] then
    scen = RL.MapRegionToScenario[scen]
  else
    local lower = string.lower(scen)
    if RL.MapRegionToScenario then
      for name, id in pairs(RL.MapRegionToScenario) do
        if string.lower(tostring(name)) == lower then
          scen = id
          break
        end
      end
    end
  end
  local mode, current = "?", "?"
  pcall(function() mode = tostring(Game.GetCurrentGameModeID()) end)
  pcall(function() current = tostring(Game.GetScenarioID()) end)
  if mode ~= "INGAME" then
    RL.SendApLog(
      "AP_MAP: unlock-region WARN not-INGAME mode=" .. mode
        .. " target=" .. tostring(scen) .. " current=" .. current
        .. " (INGAME preferred)"
    )
  end
  local before = RL.ProbeAreaBox(scen)
  RL.SendApLog(
    "AP_MAP: unlock-region before target=" .. tostring(scen)
      .. " mode=" .. mode .. " current=" .. current .. " " .. before
  )
  for _, name in ipairs({"MinimapOnLevelStartUsingElevator", "GetMinimapAreaGameProgress"}) do
    if Game and Game[name] then
      local ok, ret = pcall(Game[name])
      RL.SendApLog(
        "AP_MAP: unlock-region stub-probe " .. name
          .. " ok=" .. tostring(ok) .. " ret=" .. tostring(ret)
          .. " (retail no-op on 1.0.0)"
      )
    else
      RL.SendApLog("AP_MAP: unlock-region stub-probe " .. name .. " missing")
    end
  end
  if not RL.ScenarioAreaBox or not RL.ScenarioAreaBox[scen] then
    pcall(function() Game.DoFile("system/scripts/ap_reachable_map_cells.lua") end)
  end
  local aabb = nil
  if RL.ScenarioAreaBox then
    aabb = RL.ScenarioAreaBox[scen]
  end
  local aabb_s = "none"
  if aabb then
    aabb_s = "(" .. tostring(aabb[1]) .. "," .. tostring(aabb[2])
      .. ")-(" .. tostring(aabb[3]) .. "," .. tostring(aabb[4]) .. ")"
  end
  RL.SendApLog(
    "AP_MAP: unlock-region proposed-aabb target=" .. tostring(scen)
      .. " aabb=" .. aabb_s .. " (gridDef inset 100)"
  )
  local dirty = false
  local verdict = "ok"
  if OdrMap and OdrMap.UnlockWorldRegion then
    local ret, reason = nil, nil
    local ok, err = pcall(function()
      if aabb then
        ret, reason = OdrMap.UnlockWorldRegion(scen, aabb[1], aabb[2], aabb[3], aabb[4])
      else
        ret, reason = OdrMap.UnlockWorldRegion(scen)
      end
    end)
    if not ok then
      verdict = "fail"
      RL.SendApLog(
        "AP_MAP: unlock-region FAIL err=" .. tostring(err)
          .. " target=" .. tostring(scen) .. " aabb=" .. aabb_s
      )
    else
      if ret == false or ret == nil then
        verdict = "soft-fail"
      end
      RL.SendApLog(
        "AP_MAP: unlock-region " .. verdict
          .. " target=" .. tostring(scen) .. " aabb=" .. aabb_s
          .. " ret=" .. tostring(ret) .. " reason=" .. tostring(reason)
          .. " ver=" .. tostring(OdrMap and OdrMap.Version)
      )
      if verdict == "ok" then
        dirty = true
      end
    end
  else
    verdict = "no-api"
    RL.SendApLog(
      "AP_MAP: unlock-region FAIL no-UnlockWorldRegion (binder not shipped)"
        .. " target=" .. tostring(scen) .. " would-write aabb=" .. aabb_s
    )
  end
  local after = RL.ProbeAreaBox(scen)
  RL.SendApLog("AP_MAP: unlock-region after target=" .. tostring(scen) .. " " .. after)
  if before ~= after then
    dirty = true
    RL.SendApLog("AP_MAP: unlock-region probe-delta changed=yes")
  else
    RL.SendApLog("AP_MAP: unlock-region probe-delta changed=no")
  end
  if dirty then
    pcall(function()
      if minimap and minimap.SetProfileDataDirty then
        minimap.SetProfileDataDirty()
      end
    end)
  end
  return verdict
end
