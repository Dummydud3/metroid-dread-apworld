-- ApStationWarp: pause-map warp to the Save / Map / Network station the cursor has locked onto.
--
-- YAML off leaves Init.bStationMapWarp unset and this file is not loaded.
-- The pause map snaps the cursor onto an icon and shows that icon's label.
-- A station lock is that snap: the cursor sits on a catalog station.
-- A still does normal pause-map actions, including world-map navigation and markers.
-- The marker list is allowed to open. BlockMarkerOpen is parked behind
-- ApStationWarp.block_marker if that needs to come back.
-- Do not touch that dialog during script load, and do not index its getters or
-- setters. Those reads null-deref and kill the game before the first popup.
-- Y on a locked station opens the warp prompt only while the pause map is on
-- screen (mapmenucomposition Enabled and Visible), and does not also cycle
-- highlights. Y during gameplay does nothing here. Y off a station still
-- highlights icons.
-- Init.sStationWarpRequirement is "visited" or "visible". Missing means visited.
-- Visited only warps to a station already used. An unused station shows
-- "You haven't saved here yet" (A closes it). Visible warps to any locked
-- catalog station that has a spawn point, including one never used. A station
-- with no spawn keeps that unused notice instead of LoadScenario.
-- Init.sStationWarpReach is "local" or "global". Missing means global, which
-- is the lock this script already did: the map header can name another region,
-- and the warp uses that catalog entry's scenario and start point. Local
-- ignores a station whose scenario is not the current one, even if the cursor
-- distance matches. A real warp asks whether to go there (A confirms, B cancels).
-- Hover reads the pause-map cursor. On 1.0.0 that cursor is the vec2 at
-- minimap-manager + 0x38, then + 0x560. vViewPos is the HUD minimap and stays
-- at the origin while this cursor moves. 2.1.0 keeps that path only when the
-- floats still look like world coordinates; otherwise the cursor is resolved
-- once, while the map is centered on Samus.

ApStationWarp = ApStationWarp or {
  did_install = false,
  visited = {},
  pending = nil,
  prompt_open = false,
  a_was = false,
  b_was = false,
  y_was = false,
  -- false: the vanilla marker list opens. true: force it closed again.
  block_marker = false,
  seen_start = nil,
  seen_scenario = nil,
  did_probe = false,
  level_id = "c10_samus",
  snap_radius = 1500,
  -- Magnetic snap sits about 150 units off the icon. Same-kind stations are ~6400 apart.
  lock_radius = 800,
  -- 1.0.0 CMinimapManager: pointer at +0x38, cursor vec2 at +0x560.
  view_ptr_off = 0x38,
  view_xy_off = 0x560,
}

ApStationWarp.snap_radius = 1500
ApStationWarp.lock_radius = 800
ApStationWarp.block_marker = false
ApStationWarp.view_ptr_off = 0x38
ApStationWarp.view_xy_off = 0x560

local BB_KEY = "AP_VisitedStations"
local MSG_KEY = "GUI_AP_STATION_WARP"

-- Same-kind stations in one region are at least ~6400 units apart.
local KIND_NOUN = {
  save = "save station",
  map = "map station",
  nav = "network station",
}

local REGION_SCENARIO = {
  ARTARIA = "s010_cave",
  CATARIS = "s020_magma",
  DAIRON = "s030_baselab",
  BURENIA = "s040_aqua",
  GHAVORAN = "s050_forest",
  ELUN = "s060_quarantine",
  FERENIA = "s070_basesanc",
  HANUBIA = "s080_shipyard",
  ITORASH = "s090_skybase",
}

local SAVE_PLATFORM_CHARCLASSES = {
  weightactivatedplatform_save = true,
  weightactivatedplatform_access = true,
  weightactivatedplatform_map = true,
}

-- scenario, kind, usable, plate, x, y, region, area
local CATALOG = {
  { "s010_cave", "map", "PRP_CV_MapStation001", "PRP_CV_MapStation001_WeightPlate", -13150, -2100, "Artaria", "Map Station" },
  { "s010_cave", "nav", "PRP_CV_AccessPoint001", "PRP_CV_AccessPoint001_WeightPlate", 7850, -7400, "Artaria", "Navigation Station South" },
  { "s010_cave", "nav", "PRP_CV_AccessPoint002", "PRP_CV_AccessPoint002_WeightPlate", 11850, 2600, "Artaria", "Navigation Station North" },
  { "s010_cave", "save", "PRP_CV_SaveStation001", "PRP_CV_SaveStation001_WeightPlate", 11850, -1900, "Artaria", "Save Station South" },
  { "s010_cave", "save", "PRP_CV_SaveStation002", "PRP_CV_SaveStation002_WeightPlate", 23850, 1300, "Artaria", "Save Station East" },
  { "s010_cave", "save", "PRP_CV_SaveStation003", "PRP_CV_SaveStation003_WeightPlate", -13150, 1100, "Artaria", "Save Station West" },
  { "s010_cave", "save", "PRP_CV_SaveStation004", "PRP_CV_SaveStation004_WeightPlate", 1750, 7300, "Artaria", "Save Station North" },
  { "s020_magma", "map", "maproom", "maproom_platform", -1650, 2100, "Cataris", "Map Station" },
  { "s020_magma", "nav", "accesspoint", "accesspoint_platform", 7450, -5900, "Cataris", "Navigation Station Southeast" },
  { "s020_magma", "nav", "accesspoint_000", "accesspoint_platform_000", -13450, 4800, "Cataris", "Navigation Station Northwest" },
  { "s020_magma", "save", "savestation_000", "savestation_000_platform", -19450, -600, "Cataris", "Save Station West" },
  { "s020_magma", "save", "savestation_001", "savestation_001_platform", 7450, 2900, "Cataris", "Save Station East" },
  { "s030_baselab", "map", "maproom_000", "maproom_000_platform", -8950, 6700, "Dairon", "Map Station" },
  { "s030_baselab", "nav", "accesspoint_000", "accesspoint_000_platform", 50, -1300, "Dairon", "Navigation Station South" },
  { "s030_baselab", "nav", "accesspoint_001", "accesspoint_001_platform", 4050, 6300, "Dairon", "Navigation Station North" },
  { "s030_baselab", "save", "savestation_000", "savestation_000_platform", 15050, 4700, "Dairon", "Save Station East" },
  { "s030_baselab", "save", "savestation_001", "savestation_001_platform", -17950, -800, "Dairon", "Save Station West" },
  { "s040_aqua", "map", "maproom", "maproom_platform", -3950, 6700, "Burenia", "Map Station" },
  { "s040_aqua", "nav", "accesspoint_000", "accesspoint_000_platform", -3950, 4900, "Burenia", "Navigation Station North" },
  { "s040_aqua", "nav", "accesspoint_001", "accesspoint_001_platform", 10050, -8000, "Burenia", "Navigation Station South" },
  { "s040_aqua", "save", "savestation_000", "savestation_000_platform", -5950, -700, "Burenia", "Save Station Middle" },
  { "s040_aqua", "save", "savestation_001", "savestation_001_platform", -7950, -8100, "Burenia", "Save Station South" },
  { "s040_aqua", "save", "savestation_002", "savestation_002_platform", 4650, 11600, "Burenia", "Save Station North" },
  { "s050_forest", "map", "maproom", "maproom_platform", -1950, 700, "Ghavoran", "Map Station" },
  { "s050_forest", "nav", "accesspoint_000", "accesspoint_000_platform", -3950, -2000, "Ghavoran", "Navigation Station" },
  { "s050_forest", "save", "savestation", "weightactivatedplatform_save", 8050, 3700, "Ghavoran", "Save Station East" },
  { "s050_forest", "save", "savestation_000", "savestation_000_platform", 3050, -300, "Ghavoran", "Save Station Center" },
  { "s060_quarantine", "save", "savestation", "weightactivatedplatform_save", -10650, 600, "Elun", "Save Station" },
  { "s070_basesanc", "map", "maproom", "maproom_platform", 2550, -3700, "Ferenia", "Map Station" },
  { "s070_basesanc", "nav", "accesspoint_000", "accesspoint_000_platform", -11450, 700, "Ferenia", "Navigation Station" },
  { "s070_basesanc", "save", "savestation_000", "savestation_000_platform", 1550, 5500, "Ferenia", "Save Station North" },
  { "s070_basesanc", "save", "savestation_001", "savestation_001_platform", 5550, -1200, "Ferenia", "Save Station Southeast" },
  { "s080_shipyard", "nav", "accesspoint_000", "weightactivatedplatform_access_000", 550, -1000, "Hanubia", "Navigation Station" },
  { "s090_skybase", "save", "savestation_000", "savestation_000_platform", 2450, -4500, "Itorash", "Save Station" },
}

local function log(msg)
  if Game and Game.LogWarn then
    Game.LogWarn(0, "[ApStationWarp] " .. tostring(msg))
  end
end

local function entry_from_row(row)
  return {
    scenario = row[1],
    kind = row[2],
    usable = row[3],
    plate = row[4],
    x = row[5],
    y = row[6],
    region = row[7],
    area = row[8],
  }
end

local function build_index()
  local by_actor = {}
  local list = {}
  for _, row in ipairs(CATALOG) do
    local entry = entry_from_row(row)
    list[#list + 1] = entry
    by_actor[entry.scenario .. "|" .. entry.plate] = entry
    by_actor[entry.scenario .. "|" .. entry.usable] = entry
  end
  ApStationWarp.stations = list
  ApStationWarp.by_actor = by_actor
end

function ApStationWarp.IsEnabled()
  return Init ~= nil and Init.bStationMapWarp == true
end

local function inputs(...)
  if not Input or not Input.CheckInputs then
    return false
  end
  local ok, held = pcall(Input.CheckInputs, ...)
  return ok and held == true
end

-- Lua 5.1 numbers are float32. Button bits stop at 2^23, which is exact.
local function bor32(a, b)
  a = math.floor(tonumber(a) or 0)
  b = math.floor(tonumber(b) or 0)
  if a < 0 then
    a = 0
  end
  if b < 0 then
    b = 0
  end
  local out = 0
  local bit = 1
  for _ = 0, 23 do
    if (a % 2) >= 1 or (b % 2) >= 1 then
      out = out + bit
    end
    a = math.floor(a / 2)
    b = math.floor(b / 2)
    bit = bit * 2
  end
  return out
end

local function btest(mask, bit)
  if Bit and Bit.btest then
    local ok, held = pcall(Bit.btest, mask, bit)
    if ok then
      return held == true
    end
  end
  mask = math.floor(tonumber(mask) or 0)
  bit = math.floor(tonumber(bit) or 0)
  if bit <= 0 then
    return false
  end
  return math.floor(mask / bit) % 2 >= 1
end

-- Input.CheckInputs calls IsDebugPadButtonPressed() with no name. That path
-- only sees the debug keyboard. A name other than L1/L2/R1/R2/CROSS/TRIANGLE/SQUARE
-- falls into the exefs stub that ORs the debug pad with the controller the
-- pause map actually uses. Face A is bit 0, B is bit 1 (same as Input.buttons).
local function pad_mask()
  local mask = 0
  if not (Game and Game.IsDebugPadButtonPressed) then
    return mask
  end
  local function acc(ok, value)
    if ok and type(value) == "number" then
      mask = bor32(mask, value)
    end
  end
  acc(pcall(Game.IsDebugPadButtonPressed))
  acc(pcall(Game.IsDebugPadButtonPressed, "PAD"))
  return mask
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

local function charclass_of(name)
  local tbl = entities()
  if not tbl or type(name) ~= "string" then
    return nil
  end
  return tbl[name]
end

local function current_scenario()
  if CurrentScenarioID then
    return CurrentScenarioID
  end
  if Game and Game.GetScenarioID then
    local ok, id = pcall(Game.GetScenarioID)
    if ok and type(id) == "string" then
      return id
    end
  end
  return nil
end

local function player_section()
  if Game and Game.GetPlayerBlackboardSectionName then
    local ok, ps = pcall(Game.GetPlayerBlackboardSectionName)
    if ok and type(ps) == "string" and ps ~= "" then
      return ps
    end
  end
  return nil
end

local function is_station_usable(name)
  if type(name) ~= "string" then
    return false
  end
  local cc = charclass_of(name)
  if cc == "savestation" or cc == "accesspoint" or cc == "maproom" then
    return true
  end
  local low = string.lower(name)
  return string.find(low, "savestation", 1, true) ~= nil
    or string.find(low, "mapstation", 1, true) ~= nil
    or string.find(low, "accesspoint", 1, true) ~= nil
    or string.find(low, "maproom", 1, true) ~= nil
end

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
      if prefixed == nil and string.sub(name, 1, string.len(usable_name)) == usable_name then
        prefixed = name
      end
    end
  end
  return prefixed
end

function ApStationWarp.LoadVisited()
  ApStationWarp.visited = ApStationWarp.visited or {}
  local ps = player_section()
  if not ps or not Blackboard or not Blackboard.GetProp then
    return
  end
  local blob = Blackboard.GetProp(ps, BB_KEY)
  if type(blob) ~= "string" or blob == "" then
    return
  end
  for token in string.gmatch(blob, "[^;]+") do
    ApStationWarp.visited[token] = true
  end
end

function ApStationWarp.SaveVisited()
  local ps = player_section()
  if not ps or not Blackboard or not Blackboard.SetProp then
    return
  end
  local parts = {}
  for key, on in pairs(ApStationWarp.visited or {}) do
    if on and type(key) == "string" then
      parts[#parts + 1] = key
    end
  end
  table.sort(parts)
  pcall(Blackboard.SetProp, ps, BB_KEY, "s", table.concat(parts, ";"))
end

local function remember(scenario, actor)
  if type(scenario) ~= "string" or scenario == "" then
    return
  end
  if type(actor) ~= "string" or actor == "" then
    return
  end
  local key = scenario .. "|" .. actor
  if ApStationWarp.visited[key] then
    return
  end
  ApStationWarp.visited[key] = true
  log("visited " .. key)
  ApStationWarp.SaveVisited()
end

function ApStationWarp.NoteUsable(usable_name)
  if not ApStationWarp.IsEnabled() then
    return
  end
  if type(usable_name) ~= "string" then
    return
  end
  local scenario = current_scenario()
  remember(scenario, usable_name)
  local plate = resolve_save_platform(usable_name)
  if not plate then
    for _, entry in ipairs(ApStationWarp.stations or {}) do
      if entry.usable == usable_name and (scenario == nil or entry.scenario == scenario) then
        plate = entry.plate
        break
      end
    end
  end
  if plate then
    remember(scenario, plate)
  else
    log("no plate for " .. usable_name)
  end
end

function ApStationWarp.StationUsed(entry)
  if entry == nil or type(entry.scenario) ~= "string" then
    return false
  end
  local visited = ApStationWarp.visited or {}
  if visited[entry.scenario .. "|" .. tostring(entry.plate)]
    or visited[entry.scenario .. "|" .. tostring(entry.usable)] then
    return true
  end
  local ps = player_section()
  if ps and Blackboard and Blackboard.GetProp then
    local start_point = Blackboard.GetProp(ps, "StartPoint")
    local scenario = Blackboard.GetProp(ps, "ScenarioID") or current_scenario()
    if scenario == entry.scenario
      and (start_point == entry.plate or start_point == entry.usable) then
      return true
    end
  end
  return false
end

function ApStationWarp.Requirement()
  local req = ""
  if Init ~= nil and type(Init.sStationWarpRequirement) == "string" then
    req = string.lower(Init.sStationWarpRequirement)
  end
  if req == "visible" then
    return "visible"
  end
  return "visited"
end

function ApStationWarp.Reach()
  local reach = ""
  if Init ~= nil and type(Init.sStationWarpReach) == "string" then
    reach = string.lower(Init.sStationWarpReach)
  end
  if reach == "local" then
    return "local"
  end
  -- Unset matches the lock below: the pause-map header can name another region.
  return "global"
end

function ApStationWarp.ReachAllows(entry)
  if entry == nil or type(entry.scenario) ~= "string" or entry.scenario == "" then
    return false
  end
  if ApStationWarp.Reach() ~= "local" then
    return true
  end
  local cur = current_scenario()
  return type(cur) == "string" and cur ~= "" and entry.scenario == cur
end

function ApStationWarp.HasSpawn(entry)
  return entry ~= nil
    and type(entry.scenario) == "string" and entry.scenario ~= ""
    and type(entry.plate) == "string" and entry.plate ~= ""
end

-- Visible: any locked catalog station that has a spawn. Visited: used only.
-- No spawn never becomes a LoadScenario target.
function ApStationWarp.OfferWarp(entry)
  if not ApStationWarp.ReachAllows(entry) then
    return false
  end
  if not ApStationWarp.HasSpawn(entry) then
    return false
  end
  if ApStationWarp.Requirement() == "visible" then
    return true
  end
  return ApStationWarp.StationUsed(entry) == true
end

function ApStationWarp.SyncSpawn()
  if not ApStationWarp.IsEnabled() then
    return
  end
  local ps = player_section()
  if not ps or not Blackboard or not Blackboard.GetProp then
    return
  end
  local start_point = Blackboard.GetProp(ps, "StartPoint")
  if type(start_point) ~= "string" or start_point == "" then
    return
  end
  local scenario = Blackboard.GetProp(ps, "ScenarioID") or current_scenario()
  if ApStationWarp.seen_start == start_point and ApStationWarp.seen_scenario == scenario then
    return
  end
  ApStationWarp.seen_start = start_point
  ApStationWarp.seen_scenario = scenario
  local entry = ApStationWarp.by_actor[tostring(scenario) .. "|" .. start_point]
  if entry then
    remember(entry.scenario, entry.plate)
    remember(entry.scenario, entry.usable)
  end
end

function ApStationWarp.WarpTo(entry)
  if not ApStationWarp.OfferWarp(entry) then
    log("warp refused")
    return false
  end
  -- Catalog scenario and plate. Never substitute the scenario Samus is in.
  local scenario = entry.scenario
  local plate = entry.plate
  log(string.format(
    "warp %s / %s / %s",
    tostring(scenario),
    tostring(plate),
    tostring(entry.area)
  ))
  ApStationWarp.seen_start = nil
  ApStationWarp.seen_scenario = nil
  local ok, err = pcall(Game.LoadScenario, ApStationWarp.level_id, scenario, plate, "", 1)
  if not ok then
    log("LoadScenario failed: " .. tostring(err))
    return false
  end
  return true
end

function ApStationWarp_OnAccept()
  if ApStationWarp.HideBox then
    ApStationWarp.HideBox()
  end
  -- Close animation finishes, then the warp runs.
  -- The unused notice leaves pending nil, so this close does not LoadScenario.
  local entry = ApStationWarp.pending
  if entry ~= nil and not ApStationWarp.OfferWarp(entry) then
    entry = nil
  end
  ApStationWarp._warp_entry = entry
  ApStationWarp.pending = nil
  ApStationWarp.prompt_open = false
  -- Keep the pause map up while the close animation plays. A during that
  -- window otherwise falls through and closes the map.
  ApStationWarp._hold_map = 30
  if ApStationWarp.HoldMapOpen then
    ApStationWarp.HoldMapOpen()
  end
  if ApStationWarp.HideNativePopup then
    ApStationWarp.HideNativePopup("hud_ok")
  elseif ApStationWarp._warp_entry then
    local entry = ApStationWarp._warp_entry
    ApStationWarp._warp_entry = nil
    ApStationWarp.WarpTo(entry)
  end
end

function ApStationWarp_OnDecline()
  if ApStationWarp.HideBox then
    ApStationWarp.HideBox()
  end
  if ApStationWarp.HideNativePopup then
    ApStationWarp.HideNativePopup("hud_back")
  end
  ApStationWarp.prompt_open = false
  ApStationWarp.pending = nil
  ApStationWarp._warp_entry = nil
  ApStationWarp._hold_map = 30
  ApStationWarp.HoldMapOpen()
  log("warp cancelled")
end

local function display_object(path)
  if not GUI or not GUI.GetDisplayObject then
    return nil
  end
  local ok, obj = pcall(GUI.GetDisplayObject, path)
  if ok then
    return obj
  end
  return nil
end

local function getter(obj, name)
  if obj == nil then
    return nil
  end
  local ok, fn = pcall(function() return obj["_" .. name .. "_GetterFunction"] end)
  if not ok or type(fn) ~= "function" then
    return nil
  end
  local ok_value, value = pcall(fn, obj)
  if ok_value then
    return value
  end
  return nil
end

local function map_root()
  return display_object("IngameMenuRoot.mapmenucomposition")
end

local function flag_on(obj, name)
  local value = getter(obj, name)
  return value == true or value == 1
end

local function map_open()
  local root = map_root()
  if root == nil then
    return false
  end
  -- The map page's Visible flag stays true after you close the pause menu, and
  -- the cursor stays on the last station. Enabled is what the game turns on
  -- while that page is showing and off again in gameplay. Visible alone is why
  -- Y after unpausing still opened the warp prompt.
  -- The first ticks never call this. Reading Enabled during boot used to walk
  -- the marker dialog and crash; that read stays behind the boot guard.
  return flag_on(root, "Enabled") and flag_on(root, "Visible")
end

function ApStationWarp.HoldMapOpen()
  if not (GUI and GUI.SetProperties) then
    return
  end
  local root = map_root()
  if root then
    pcall(GUI.SetProperties, root, { Enabled = true, Visible = true })
  end
  local menu = display_object("IngameMenuRoot")
  if menu then
    pcall(GUI.SetProperties, menu, { Enabled = true, Visible = true })
  end
end

local function find_child(root, name)
  if root == nil then
    return nil
  end
  local ok, child = pcall(function()
    return root:FindChild(name)
  end)
  if ok then
    return child
  end
  return nil
end

local function text_of(obj)
  if obj == nil then
    return nil
  end
  -- CLabel publishes _Text_GetterFunction. Call that, not a guessed field.
  -- Only used once the label is already visible, never during script load.
  local value = getter(obj, "Text")
  if type(value) == "string" and value ~= "" then
    return value
  end
  if GUI and GUI.GetLabelText then
    local ok, got = pcall(GUI.GetLabelText, obj)
    if ok and type(got) == "string" and got ~= "" then
      return got
    end
  end
  return nil
end

local function kind_from_label(text)
  if type(text) ~= "string" then
    return nil
  end
  local upper = string.upper(text)
  if string.find(upper, "NAVIGATION STATION", 1, true)
    or string.find(upper, "NETWORK STATION", 1, true)
    or string.find(upper, "ACCESS POINT", 1, true)
    or string.find(upper, "MAP_ICON_ACCESS_POINT", 1, true) then
    return "nav"
  end
  if string.find(upper, "MAP STATION", 1, true) or string.find(upper, "MAP_ICON_MAP_ROOM", 1, true) then
    return "map"
  end
  if string.find(upper, "SAVE STATION", 1, true) or string.find(upper, "MAP_ICON_SAVE_ROOM", 1, true) then
    return "save"
  end
  return nil
end

local function scenario_from_header(text)
  if type(text) ~= "string" then
    return nil
  end
  local upper = string.upper(text)
  for name, scenario in pairs(REGION_SCENARIO) do
    if string.find(upper, name, 1, true) then
      return scenario
    end
  end
  return nil
end

local function xy_of(value)
  if value == nil then
    return nil, nil
  end
  if type(value) == "number" then
    return nil, nil
  end
  if type(value) == "string" then
    local xs, ys = string.match(value, "([%-%.%d]+)%s+([%-%.%d]+)")
    return tonumber(xs), tonumber(ys)
  end
  if type(value) == "table" then
    local x = tonumber(value.x or value.X or value[1])
    local y = tonumber(value.y or value.Y or value[2])
    return x, y
  end
  local x, y
  local okx, xv = pcall(function() return value.x end)
  local oky, yv = pcall(function() return value.y end)
  if not okx then
    okx, xv = pcall(function() return value.X end)
  end
  if not oky then
    oky, yv = pcall(function() return value.Y end)
  end
  if okx then x = tonumber(xv) end
  if oky then y = tonumber(yv) end
  return x, y
end

local function read_prop(obj, name)
  if obj == nil then
    return nil
  end
  local ok, value = pcall(function() return obj[name] end)
  if ok and value ~= nil then
    return value
  end
  if GUI and GUI.GetProp then
    local ok2, value2 = pcall(GUI.GetProp, obj, name)
    if ok2 and value2 ~= nil then
      return value2
    end
  end
  return nil
end

local function world_xy(x, y)
  if type(x) ~= "number" or type(y) ~= "number" then
    return nil, nil
  end
  if x ~= x or y ~= y then
    return nil, nil
  end
  if math.abs(x) > 80000 or math.abs(y) > 80000 then
    return nil, nil
  end
  if math.abs(x) < 1 and math.abs(y) < 1 then
    return nil, nil
  end
  return x, y
end

local function read_view_at(ptr_off, xy_off)
  if not (OdrMap and OdrMap.ReadU64 and OdrMap.ReadFloatsAbs and Game and Game.GetMinimapManager) then
    return nil, nil
  end
  local ok, mgr = pcall(Game.GetMinimapManager)
  if not ok or mgr == nil then
    return nil, nil
  end
  local hex = OdrMap.ReadU64(mgr, ptr_off)
  if type(hex) ~= "string" then
    return nil, nil
  end
  local rows = OdrMap.ReadFloatsAbs(hex, xy_off, 2)
  if type(rows) ~= "table" then
    return nil, nil
  end
  return world_xy(rows[1], rows[2])
end

local function player_xy()
  local ok, player = pcall(Game.GetPlayer)
  if not ok or player == nil or player.vPos == nil then
    return nil, nil
  end
  local pos = player.vPos
  local old = debug.getmetatable(pos)
  local mt = debug.getregistry()["base::math::CVector3D"]
  if mt == nil then
    return nil, nil
  end
  debug.setmetatable(pos, mt)
  local x, y = pos.x, pos.y
  debug.setmetatable(pos, old)
  return tonumber(x), tonumber(y)
end

-- Other game versions keep the cursor behind a different pointer. The map opens
-- centered on Samus, so the matching float pair is the cursor.
local function discover_view()
  if not (OdrMap and OdrMap.ReadU64 and OdrMap.ReadFloatsAbs) then
    return false
  end
  local px, py = player_xy()
  if px == nil or py == nil then
    return false
  end
  local ok, mgr = pcall(Game.GetMinimapManager)
  if not ok or mgr == nil then
    return false
  end
  for ptr_off = 0, 0x180, 8 do
    local hex = OdrMap.ReadU64(mgr, ptr_off)
    if type(hex) == "string" then
      local n = tonumber(hex, 16) or 0
      if n >= 0x2100000000 and n < 0x2300000000 and (n % 8) == 0 then
        for start = 0, 0x600, 0x200 do
          local rows = OdrMap.ReadFloatsAbs(hex, start, 128)
          if type(rows) == "table" then
            for i = 1, #rows - 1 do
              local x, y = rows[i], rows[i + 1]
              if type(x) == "number" and type(y) == "number"
                and math.abs(x - px) < 250 and math.abs(y - py) < 250 then
                ApStationWarp.view_ptr_off = ptr_off
                ApStationWarp.view_xy_off = start + (i - 1) * 4
                log(string.format(
                  "cursor mgr+0x%X +0x%X",
                  ptr_off,
                  ApStationWarp.view_xy_off
                ))
                return true
              end
            end
          end
        end
      end
    end
  end
  return false
end

local function read_gui_point(path, ptr_off, xy_off)
  local obj = display_object(path)
  if obj == nil or not (OdrMap and OdrMap.ReadU64 and OdrMap.ReadFloatsAbs) then
    return nil, nil
  end
  local hex = OdrMap.ReadU64(obj, ptr_off)
  if type(hex) ~= "string" then
    return nil, nil
  end
  local rows = OdrMap.ReadFloatsAbs(hex, xy_off, 2)
  if type(rows) ~= "table" then
    return nil, nil
  end
  return world_xy(rows[1], rows[2])
end

-- 1.0.0 cursor at minimap-manager +0x38/+0x560. When that vec2 is NaN the
-- pause map still keeps a world point on the map composition (+0x10/+0x4C0).
-- Do not search for a pair near Samus: that latches the player blip and A
-- then places a marker on the station the player is actually hovering.
local function view_points()
  local points = {}
  local function add(x, y)
    if x ~= nil and y ~= nil then
      points[#points + 1] = { x, y }
    end
  end
  add(read_view_at(ApStationWarp.view_ptr_off or 0x38, ApStationWarp.view_xy_off or 0x560))
  add(read_gui_point("IngameMenuRoot.mapmenucomposition", 0x10, 0x4C0))
  return points
end

local function view_xy()
  local points = view_points()
  if points[1] == nil then
    return nil, nil, nil
  end
  return points[1][1], points[1][2], "mgr"
end

local function shown_scenario(header_text)
  local from_header = scenario_from_header(header_text)
  if from_header then
    return from_header, true
  end
  if minimap then
    if type(minimap.sCurrentScenarioID) == "string" and minimap.sCurrentScenarioID ~= "" then
      return minimap.sCurrentScenarioID, false
    end
    if type(minimap.sTargetScenarioID) == "string" and minimap.sTargetScenarioID ~= "" then
      return minimap.sTargetScenarioID, false
    end
  end
  return current_scenario(), false
end

-- The pause map magnetically locks the cursor onto the icon under it.
-- That lock, not the visited-station list, is the highlighted station.
-- Local reach drops the lock when that icon's scenario is not the current one,
-- even if this cursor distance matched it.
local function nearest_locked(scenario, x, y)
  if not scenario or x == nil or y == nil then
    return nil, nil
  end
  if ApStationWarp.Reach() == "local" then
    local cur = current_scenario()
    if type(cur) ~= "string" or cur == "" or scenario ~= cur then
      return nil, nil
    end
  end
  local best = nil
  local best_d = nil
  local radius = ApStationWarp.lock_radius or 800
  local limit = radius * radius
  for _, entry in ipairs(ApStationWarp.stations or {}) do
    if entry.scenario == scenario then
      local dx = entry.x - x
      local dy = entry.y - y
      local d2 = dx * dx + dy * dy
      if d2 <= limit and (best_d == nil or d2 < best_d) then
        best = entry
        best_d = d2
      end
    end
  end
  if best == nil or best_d == nil or not ApStationWarp.ReachAllows(best) then
    return nil, nil
  end
  return best, math.sqrt(best_d)
end

local MARKER_DIALOG = "IngameMenuRoot.mapmenucomposition.custommarkercomposition"

local function marker_dialog()
  return display_object(MARKER_DIALOG)
end

-- Parked while the marker list is allowed to open. Turn block_marker on to
-- call this again. No property reads: indexing a getter or setter on this
-- dialog null-derefs during startup.
function ApStationWarp.BlockMarkerOpen()
  local dlg = marker_dialog()
  if dlg and GUI and GUI.SetProperties then
    pcall(GUI.SetProperties, dlg, { Enabled = false, Visible = false })
  end
end

local function play_ui_sound(name)
  if not name or not Game then
    return
  end
  local path = name
  if string.sub(path, 1, 7) ~= "system/" then
    path = "system/snd/presets/hud/" .. path
  end
  -- Same call the pause menus use. This build wants volume, a second level,
  -- a loop flag, and one more number after the preset path.
  if Game.PlayGUISound then
    local ok = pcall(Game.PlayGUISound, path, 1, 1, false, 1)
    if ok then
      return
    end
  end
  if Game.PlayPresetSound then
    pcall(Game.PlayPresetSound, path)
  end
end

-- popupcomposition OnEnter / OnExit, played in 15 frames.
-- The panel draws out horizontally, then opens vertically. Close is the reverse.
-- Text stays hidden until the window is fully open.
-- Scale 1 is ignored by SetProperties, so the open pose uses 0.999.
local POPUP_FRAMES = 15
-- Tick is called about 1.5 times per displayed frame. 0.7s at 60fps is ~63 calls.
local B_LOCK_TICKS = 63
local POPUP_OPEN_X = { { 0, 0.01 }, { 7, 0.999 }, { POPUP_FRAMES, 0.999 } }
local POPUP_OPEN_Y = { { 0, 0.01 }, { 7, 0.01 }, { POPUP_FRAMES, 0.999 } }
local POPUP_CLOSE_X = { { 0, 0.999 }, { 8, 0.999 }, { POPUP_FRAMES, 0.01 } }
local POPUP_CLOSE_Y = { { 0, 0.999 }, { 7, 0.01 }, { POPUP_FRAMES, 0.01 } }
local POPUP_BG_OPEN = {
  R = { { 0, 1 }, { 7, 1 }, { 8, 0 }, { 11, 0 }, { 14, 1 }, { POPUP_FRAMES, 0.02745 } },
  G = { { 0, 1 }, { 7, 1 }, { 8, 0 }, { 11, 0 }, { 14, 1 }, { POPUP_FRAMES, 0.09020 } },
  B = { { 0, 1 }, { 7, 1 }, { 8, 0 }, { 11, 0 }, { 14, 1 }, { POPUP_FRAMES, 0.13333 } },
  A = { { 0, 1 }, { 7, 1 }, { 8, 0.8 }, { 11, 0.16863 }, { 14, 1 }, { POPUP_FRAMES, 0.90196 } },
}
local POPUP_BG_CLOSE = {
  R = { { 0, 0.02745 }, { 1, 0 }, { 2, 1 }, { 7, 0 }, { 8, 1 }, { POPUP_FRAMES, 1 } },
  G = { { 0, 0.09020 }, { 1, 0 }, { 2, 1 }, { 7, 0 }, { 8, 1 }, { POPUP_FRAMES, 1 } },
  B = { { 0, 0.13333 }, { 1, 0 }, { 2, 1 }, { 7, 0 }, { 8, 1 }, { POPUP_FRAMES, 1 } },
  A = { { 0, 0.90196 }, { 1, 0.16863 }, { 2, 1 }, { 7, 0.8 }, { 8, 1 }, { POPUP_FRAMES, 1 } },
}

local function popup_lerp(keys, frame)
  if frame <= keys[1][1] then
    return keys[1][2]
  end
  local i = 2
  while i <= #keys do
    local f0, v0 = keys[i - 1][1], keys[i - 1][2]
    local f1, v1 = keys[i][1], keys[i][2]
    if frame <= f1 then
      if f1 == f0 then
        return v1
      end
      local t = (frame - f0) / (f1 - f0)
      return v0 + (v1 - v0) * t
    end
    i = i + 1
  end
  return keys[#keys][2]
end

local function popup_obj(path)
  return display_object(path)
end

-- popupcomposition is also the save-station question.
-- The label text getter stays "" even while a sentence is on screen, so a
-- snapshot of it is blank and writing that snapshot back clears the save box.
-- When the warp prompt is fully down, put this sentence back and open the
-- panel. The close pose leaves the panel at scale 0.01 on a white background.
local SAVE_POPUP_TEXT = "Save your progress?|Hold "
  .. string.char(225, 160, 134)
  .. " and "
  .. string.char(225, 160, 135)
  .. " while selecting {c6}Cancel{c0}|to warp to the starting location."

local function set_popup_label(path, text, white)
  local obj = popup_obj(path)
  if obj == nil or not (GUI and GUI.SetProperties) then
    return
  end
  if GUI.SetLabelText then
    pcall(GUI.SetLabelText, obj, text)
  end
  local props = { Visible = true, Enabled = true, ColorA = 1 }
  if white then
    props.ColorR = 1
    props.ColorG = 1
    props.ColorB = 1
  end
  pcall(GUI.SetProperties, obj, props)
end

local function restore_popup_text()
  if not (GUI and GUI.SetProperties) then
    return
  end
  set_popup_label("popupcomposition.Panel.MessageText", SAVE_POPUP_TEXT, true)
  set_popup_label("popupcomposition.Panel.PressAText", "#GUI_GENERAL_LABEL_ACCEPT", false)
  set_popup_label("popupcomposition.Panel.Option1Text", "#GUI_GENERAL_LABEL_CANCEL", false)
  local panel = popup_obj("popupcomposition.Panel")
  if panel then
    pcall(GUI.SetProperties, panel, { ScaleX = 0.999, ScaleY = 0.999, ColorA = 1 })
  end
  local back = popup_obj("popupcomposition.Panel.MessageBackground")
  if back then
    pcall(GUI.SetProperties, back, {
      ColorR = 0.02745,
      ColorG = 0.09020,
      ColorB = 0.13333,
      ColorA = 0.90196,
    })
  end
end

function ApStationWarp.ApplyPopupFrame(kind, frame)
  if not (GUI and GUI.SetProperties) then
    return
  end
  local opening = kind ~= "close"
  local sx = popup_lerp(opening and POPUP_OPEN_X or POPUP_CLOSE_X, frame)
  local sy = popup_lerp(opening and POPUP_OPEN_Y or POPUP_CLOSE_Y, frame)
  local bg = opening and POPUP_BG_OPEN or POPUP_BG_CLOSE
  local panel = popup_obj("popupcomposition.Panel")
  if panel then
    pcall(GUI.SetProperties, panel, { ScaleX = sx, ScaleY = sy, ColorA = 1 })
  end
  local back = popup_obj("popupcomposition.Panel.MessageBackground")
  if back then
    pcall(GUI.SetProperties, back, {
      ColorR = popup_lerp(bg.R, frame),
      ColorG = popup_lerp(bg.G, frame),
      ColorB = popup_lerp(bg.B, frame),
      ColorA = popup_lerp(bg.A, frame),
    })
  end
  local show_text = opening and frame >= POPUP_FRAMES
  local show_cancel = show_text and not ApStationWarp._popup_ok
  for _, path in ipairs({
    "popupcomposition.Panel.MessageText",
    "popupcomposition.Panel.PressAText",
  }) do
    local label = popup_obj(path)
    if label then
      pcall(GUI.SetProperties, label, { Visible = show_text, Enabled = show_text })
    end
  end
  local cancel = popup_obj("popupcomposition.Panel.Option1Text")
  if cancel then
    pcall(GUI.SetProperties, cancel, { Visible = show_cancel, Enabled = show_cancel })
  end
  local opt2 = popup_obj("popupcomposition.Panel.Option2Text")
  if opt2 then
    pcall(GUI.SetProperties, opt2, { Visible = false, Enabled = false })
  end
end

function ApStationWarp.AdvancePopupAnim()
  local anim = ApStationWarp._anim
  if anim == nil then
    return
  end
  -- GuiTick and the debug-input hook both call Tick, about 1.5 times per
  -- displayed frame. Hold each authored frame for 1.5 ticks so the 15-frame
  -- open and close last about a quarter of a second.
  anim.acc = (anim.acc or 0) + 1
  if anim.acc < 1.5 then
    return
  end
  anim.acc = anim.acc - 1.5
  anim.frame = anim.frame + 1
  if anim.frame > POPUP_FRAMES then
    anim.frame = POPUP_FRAMES
  end
  ApStationWarp.ApplyPopupFrame(anim.kind, anim.frame)
  if anim.frame < POPUP_FRAMES then
    return
  end
  ApStationWarp._anim = nil
  if anim.kind == "close" then
    local entry = ApStationWarp._warp_entry
    ApStationWarp._warp_entry = nil
    ApStationWarp.ForceHideNativePopup()
    if entry ~= nil then
      ApStationWarp.WarpTo(entry)
    end
  end
end

function ApStationWarp.ShowNativePopup(text)
  if not (GUI and GUI.SetProperties and GUI.SetLabelText) then
    return false
  end
  local msg = display_object("popupcomposition.Panel.MessageText")
  local pop = display_object("popupcomposition")
  if msg == nil or pop == nil then
    return false
  end
  pcall(GUI.SetProperties, msg, { Visible = false })
  pcall(GUI.SetLabelText, msg, text)
  local press = display_object("popupcomposition.Panel.PressAText")
  if press then
    pcall(GUI.SetProperties, press, { Visible = false })
    -- #GUI_AP_STATION_OK is "OK" with the same A-button logo as ACCEPT.
    -- A plain "OK" draws the word with no button icon.
    pcall(GUI.SetLabelText, press, ApStationWarp._popup_ok and "#GUI_AP_STATION_OK" or "#GUI_GENERAL_LABEL_ACCEPT")
  end
  local cancel = display_object("popupcomposition.Panel.Option1Text")
  if cancel and not ApStationWarp._popup_ok then
    pcall(GUI.SetLabelText, cancel, "#GUI_GENERAL_LABEL_CANCEL")
  end
  local opt2 = display_object("popupcomposition.Panel.Option2Text")
  if opt2 then
    pcall(GUI.SetProperties, opt2, { Visible = false, Enabled = false })
  end
  pcall(GUI.SetProperties, pop, { Enabled = true, Visible = true, Depth = 50 })
  -- popupcomposition is shared with GUI.ShowMessage (the Archipelago start box).
  -- Only a prompt we opened may be hidden later.
  ApStationWarp._owns_popup = true
  ApStationWarp._popup_closing = 0
  ApStationWarp._anim = { kind = "open", frame = 0 }
  ApStationWarp.ApplyPopupFrame("open", 0)
  play_ui_sound("hud_bigwindow_open")
  return true
end

function ApStationWarp.HideNativePopup(sound_name)
  local pop = display_object("popupcomposition")
  if pop == nil or not (GUI and GUI.SetProperties) then
    return
  end
  pcall(GUI.SetProperties, pop, { Enabled = true, Visible = true, Depth = 50 })
  ApStationWarp._popup_closing = 0
  ApStationWarp._anim = { kind = "close", frame = 0 }
  -- B closes the pause map. Ignore it for 0.7s from the start of this close.
  ApStationWarp._b_lock_ticks = B_LOCK_TICKS
  ApStationWarp.ApplyPopupFrame("close", 0)
  play_ui_sound("hud_bigwindow_close")
  play_ui_sound(sound_name)
end

function ApStationWarp.ForceHideNativePopup()
  if ApStationWarp._anim ~= nil then
    return
  end
  if not ApStationWarp._owns_popup then
    return
  end
  local pop = display_object("popupcomposition")
  if pop and GUI and GUI.SetProperties then
    pcall(GUI.SetProperties, pop, { Enabled = false, Visible = false })
  end
  ApStationWarp._popup_closing = 0
  ApStationWarp._owns_popup = false
  restore_popup_text()
end

local function object_enabled(obj)
  if obj == nil or type(obj._Enabled_GetterFunction) ~= "function" then
    return false
  end
  local ok, value = pcall(function()
    return obj:_Enabled_GetterFunction()
  end)
  return ok and value == true
end

function ApStationWarp.HideBox()
  local panel = ApStationWarp._box_panel
  if panel and panel.SetProperties then
    pcall(function()
      panel:SetProperties({ Visible = false, Enabled = false })
    end)
  end
  local box = ApStationWarp._box
  if box and box.Hide then
    pcall(function()
      box:Hide()
    end)
  end
  -- Hide() can leave the fullscreen GUILib root enabled. That root sits on
  -- the pause map and eats the stick, so a later A press only places a marker.
  if box and box.root and GUI and GUI.SetProperties then
    pcall(GUI.SetProperties, box.root, { Enabled = false, Visible = false })
    if box.main then
      pcall(GUI.SetProperties, box.main, { Enabled = false, Visible = false })
    end
  end
end

function ApStationWarp.ShowBox(text)
  if type(GUILib) ~= "table" or not GUI then
    return false, "no-guilib"
  end
  if ApStationWarp._box_panel == nil then
    local parent = display_object("IngameMenuRoot")
    local ok, ui = pcall(GUILib, "ApStationWarpBox", parent)
    if not ok or ui == nil then
      return false, ui
    end
    local ok_panel, panel = pcall(function()
      return ui:AddPanel("Box", {
        X = "0.27",
        Y = "0.36",
        SizeX = "0.46",
        SizeY = "0.18",
        Enabled = true,
        Visible = false,
      })
    end)
    if not ok_panel or panel == nil then
      return false, panel
    end
    panel:AddLabel("Prompt", text, {
      X = "0.02",
      Y = "0.02",
      SizeX = "0.42",
      SizeY = "0.08",
      Font = "digital_hefty",
      TextAlignment = "Centered",
      TextVerticalAlignment = "Centered",
      ScaleX = "0.62",
      ScaleY = "0.62",
      Enabled = true,
      Visible = true,
    })
    panel:AddLabel("Hint", "A  Accept      B  Cancel", {
      X = "0.02",
      Y = "0.09",
      SizeX = "0.42",
      SizeY = "0.05",
      Font = "digital_hefty",
      TextAlignment = "Centered",
      TextVerticalAlignment = "Centered",
      ScaleX = "0.48",
      ScaleY = "0.48",
      Enabled = true,
      Visible = true,
    })
    pcall(function() ui:Show() end)
    ApStationWarp._box = ui
    ApStationWarp._box_panel = panel
  else
    local prompt = ApStationWarp._box_panel:Get("Prompt")
    if prompt and prompt.SetText then
      pcall(function() prompt:SetText(text) end)
    end
    if ApStationWarp._box and ApStationWarp._box.Show then
      pcall(function() ApStationWarp._box:Show() end)
    end
  end
  pcall(function()
    ApStationWarp._box_panel:SetProperties({ Visible = true, Enabled = true })
  end)
  return true, "shown"
end

local function open_prompt(entry)
  if not ApStationWarp.ReachAllows(entry) then
    log("reach reject " .. tostring(entry and entry.scenario))
    return
  end
  local offer = ApStationWarp.OfferWarp(entry)
  ApStationWarp._popup_ok = not offer
  local text
  if offer then
    local noun = KIND_NOUN[entry.kind] or "station"
    text = "Warp to this " .. noun .. "?"
    ApStationWarp.pending = entry
  else
    text = "You haven't saved here yet"
    ApStationWarp.pending = nil
  end
  ApStationWarp.prompt_open = true
  if ApStationWarp.HideBox then
    ApStationWarp.HideBox()
  end
  if GUI and GUI.FlushInput then
    pcall(GUI.FlushInput)
  end
  local shown, err = ApStationWarp.ShowNativePopup(text)
  if not shown then
    shown, err = ApStationWarp.ShowBox(text)
  end
  if not shown then
    ApStationWarp.prompt_open = false
    ApStationWarp.pending = nil
    ApStationWarp.HideBox()
    log("prompt box failed: " .. tostring(err))
    return
  end
  log(string.format(
    "prompt %s %s",
    tostring(entry.area),
    tostring(entry.scenario)
  ))
end

local function child_text(root, ...)
  local obj = root
  for i = 1, select("#", ...) do
    obj = find_child(obj, select(i, ...))
    if obj == nil then
      return nil
    end
  end
  return text_of(obj)
end

local function probe_once(inspector, header, scenario, x, y, source)
  ApStationWarp.probe_tries = (ApStationWarp.probe_tries or 0) + 1
  local useful = (type(inspector) == "string" and inspector ~= "") or x ~= nil
  if not useful and ApStationWarp.probe_tries < 45 then
    return
  end
  if ApStationWarp.did_probe then
    return
  end
  ApStationWarp.did_probe = true
  log(string.format(
    "probe label=%q header=%q scenario=%s view=%s,%s via=%s",
    tostring(inspector),
    tostring(header),
    tostring(scenario),
    tostring(x),
    tostring(y),
    tostring(source)
  ))
end

function ApStationWarp.TryRemoveMarker(arg)
  if arg == nil or arg == ApStationWarp._box or arg == ApStationWarp._box_panel then
    return
  end
  if type(arg) ~= "table" and type(arg) ~= "userdata" then
    return
  end
  for _, name in ipairs({ "Remove", "Delete" }) do
    local ok, fn = pcall(function()
      return arg[name]
    end)
    if ok and type(fn) == "function" then
      pcall(fn, arg)
    end
  end
end

local function marker_point(arg)
  local x, y = xy_of(arg)
  local wx, wy = world_xy(x, y)
  if wx ~= nil then
    return wx, wy
  end
  if type(arg) ~= "table" then
    return nil, nil
  end
  for _, key in ipairs({ "vPos", "pos", "position", "vPosition" }) do
    local child = arg[key]
    if child ~= nil then
      x, y = xy_of(child)
      wx, wy = world_xy(x, y)
      if wx ~= nil then
        return wx, wy
      end
    end
  end
  return nil, nil
end

local function inspector_label()
  local root = map_root()
  if root == nil then
    return nil
  end
  local content = find_child(root, "Content")
  local inspector = find_child(content, "Inspector")
  local label = find_child(inspector, "Inspector-Label")
  if label == nil or not flag_on(label, "Visible") then
    return nil
  end
  return text_of(label)
end

local function header_scenario()
  local root = map_root()
  if root == nil then
    return nil
  end
  return scenario_from_header(child_text(root, "Content", "Header-C-Label"))
end

local function plain_label(text)
  if type(text) ~= "string" then
    return nil
  end
  local plain = string.gsub(text, "{c%d+}", "")
  if plain == "" then
    return nil
  end
  return plain
end

local function longest_area_matches(text, scenario)
  local upper = string.upper(plain_label(text) or "")
  if upper == "" then
    return {}
  end
  local best_len = 0
  local matches = {}
  for _, entry in ipairs(ApStationWarp.stations or {}) do
    if scenario == nil or entry.scenario == scenario then
      local area = string.upper(entry.area or "")
      if area ~= "" and string.find(upper, area, 1, true) and #area >= best_len then
        if #area > best_len then
          matches = {}
          best_len = #area
        end
        matches[#matches + 1] = entry
      end
    end
  end
  return matches
end

-- The pause map writes the snapped icon's name into Inspector-Label.
-- That label is the lock. Cursor coordinates are only a tiebreaker.
local function entry_from_inspector()
  local text = inspector_label()
  text = plain_label(text)
  if text == nil then
    return nil, nil
  end
  local scenario = header_scenario() or current_scenario()
  local matches = longest_area_matches(text, scenario)
  if #matches == 0 and scenario ~= nil then
    matches = longest_area_matches(text, nil)
  end
  local kind = kind_from_label(text)
  if #matches == 0 and kind ~= nil then
    for _, entry in ipairs(ApStationWarp.stations or {}) do
      if entry.kind == kind and (scenario == nil or entry.scenario == scenario) then
        matches[#matches + 1] = entry
      end
    end
  end
  if #matches == 1 then
    if not ApStationWarp.ReachAllows(matches[1]) then
      return nil, nil
    end
    return matches[1], 0
  end
  if #matches == 0 then
    return nil, nil
  end
  local points = view_points()
  local px, py = nil, nil
  if points[1] ~= nil then
    px, py = points[1][1], points[1][2]
  end
  if px == nil then
    return nil, nil
  end
  local best, best_d = nil, nil
  for i = 1, #matches do
    local entry = matches[i]
    local dx = entry.x - px
    local dy = entry.y - py
    local d2 = dx * dx + dy * dy
    if best_d == nil or d2 < best_d then
      best = entry
      best_d = d2
    end
  end
  if best == nil or best_d == nil or not ApStationWarp.ReachAllows(best) then
    return nil, nil
  end
  return best, math.sqrt(best_d)
end

local function hovered_station()
  local labeled, label_dist = entry_from_inspector()
  if labeled ~= nil then
    local points = view_points()
    local x, y = nil, nil
    if points[1] ~= nil then
      x, y = points[1][1], points[1][2]
    end
    return labeled, label_dist, x, y
  end
  local scenario = header_scenario() or current_scenario()
  local points = view_points()
  for i = 1, #points do
    local entry, dist = nearest_locked(scenario, points[i][1], points[i][2])
    if entry ~= nil then
      return entry, dist, points[i][1], points[i][2]
    end
  end
  local x, y = nil, nil
  if points[1] ~= nil then
    x, y = points[1][1], points[1][2]
  end
  return nil, nil, x, y
end

function ApStationWarp.OnMarkerCreated(arg)
  if not ApStationWarp.IsEnabled() then
    return
  end
  if not ApStationWarp._logged_marker then
    ApStationWarp._logged_marker = true
    local extra = ""
    if type(arg) == "table" then
      local keys = {}
      local ok_pairs = pcall(function()
        for key, _ in pairs(arg) do
          keys[#keys + 1] = tostring(key)
          if #keys >= 8 then
            break
          end
        end
      end)
      if ok_pairs then
        extra = " keys=" .. table.concat(keys, ",")
      end
    elseif type(arg) == "number" or type(arg) == "string" then
      extra = " v=" .. tostring(arg)
    end
    log("marker " .. type(arg) .. extra)
  end
  if not ApStationWarp.block_marker then
    return
  end
  pcall(ApStationWarp.TryRemoveMarker, arg)
  pcall(ApStationWarp.BlockMarkerOpen)
  if ApStationWarp.prompt_open then
    return
  end
  local entry, dist, x, y = hovered_station()
  if entry == nil then
    local scenario = current_scenario()
    x, y = marker_point(arg)
    entry, dist = nearest_locked(scenario, x, y)
  end
  if entry == nil then
    return
  end
  -- This A press is the one that tried to place the marker. Do not also accept.
  ApStationWarp.a_was = true
  log(string.format("marker-hover %s dist=%.0f", tostring(entry.area), dist or -1))
  open_prompt(entry)
end

function ApStationWarp.Tick()
  if not ApStationWarp.IsEnabled() then
    return
  end
  -- Script load used to touch the marker dialog on the first tick and crash.
  -- Leave those frames alone. The pause map is not open yet.
  ApStationWarp._boot_ticks = (ApStationWarp._boot_ticks or 0) + 1
  if ApStationWarp._boot_ticks < 90 then
    return
  end
  local b_lock = (ApStationWarp._b_lock_ticks or 0) > 0
  if b_lock then
    ApStationWarp._b_lock_ticks = ApStationWarp._b_lock_ticks - 1
  end
  if ApStationWarp.AdvancePopupAnim then
    ApStationWarp.AdvancePopupAnim()
  end
  pcall(ApStationWarp.SyncSpawn)

  local open = false
  local ok_open, result = pcall(map_open)
  if ok_open then
    open = result and true or false
  end
  if not open and (ApStationWarp.prompt_open or (ApStationWarp._hold_map or 0) > 0) then
    ApStationWarp.HoldMapOpen()
    local ok_again, opened = pcall(map_open)
    if ok_again and opened then
      open = true
    end
  end
  if not open then
    if ApStationWarp.prompt_open or ApStationWarp._anim ~= nil then
      -- Opening popupcomposition can make the map page look closed for a tick.
      -- Keep a warp box we opened. GUI.ShowMessage is left alone because we
      -- do not own that popup.
      ApStationWarp.HoldMapOpen()
      open = true
    else
      -- B is still ignored for a short time after the warp prompt starts closing,
      -- even if the map page flickers closed.
      if b_lock and (btest(pad_mask(), 2) or inputs("B")) then
        if GUI and GUI.FlushInput then
          pcall(GUI.FlushInput)
        end
        ApStationWarp.HoldMapOpen()
        ApStationWarp.b_was = true
        ApStationWarp._status = "b-lock"
        return
      end
      -- The map page stays Visible, and the cursor stays on the last station,
      -- after unpausing. Enabled is off in gameplay, so this branch runs and
      -- Y must not open a prompt from that leftover lock.
      if ApStationWarp._owns_popup and ApStationWarp.ForceHideNativePopup then
        ApStationWarp.ForceHideNativePopup()
      end
      ApStationWarp.a_was = false
      ApStationWarp.b_was = false
      ApStationWarp.y_was = false
      ApStationWarp._lock = nil
      ApStationWarp._status = "map-closed"
      return
    end
  end
  if (ApStationWarp._hold_map or 0) > 0 then
    ApStationWarp._hold_map = ApStationWarp._hold_map - 1
    ApStationWarp.HoldMapOpen()
  end

  if ApStationWarp.prompt_open then
    -- The save-station window stays up while the question is on screen.
    local pop = display_object("popupcomposition")
    if pop and ApStationWarp._owns_popup and GUI and GUI.SetProperties then
      pcall(GUI.SetProperties, pop, { Enabled = true, Visible = true, Depth = 50 })
    end
  elseif (ApStationWarp._popup_closing or 0) > 0 then
    ApStationWarp._popup_closing = ApStationWarp._popup_closing - 1
    if ApStationWarp._popup_closing <= 0 and ApStationWarp.ForceHideNativePopup then
      ApStationWarp.ForceHideNativePopup()
    end
  end
  if ApStationWarp.block_marker then
    pcall(ApStationWarp.BlockMarkerOpen)
  end
  local box = ApStationWarp._box
  if not ApStationWarp.prompt_open and box and (object_enabled(box.root) or object_enabled(box.main)) then
    ApStationWarp.HideBox()
  end
  local entry, dist, x, y = hovered_station()
  local mask = pad_mask()
  ApStationWarp._pad = mask
  ApStationWarp._lock = entry and entry.area or nil
  ApStationWarp._status = string.format(
    "view %s %s pad=%s lock=%s",
    tostring(x),
    tostring(y),
    tostring(mask),
    tostring(entry and entry.area or "-")
  )

  local a_down = btest(mask, 1) or inputs("A")
  local b_down = btest(mask, 2) or inputs("B")
  -- Switch Y is bit 3. SQUARE is the debug-pad name for that same face button.
  local y_down = btest(mask, 8) or inputs("Y") or inputs("SQUARE")
  local a_pressed = a_down and not ApStationWarp.a_was
  local b_pressed = b_down and not ApStationWarp.b_was
  local y_pressed = y_down and not ApStationWarp.y_was
  ApStationWarp.a_was = a_down
  ApStationWarp.b_was = b_down
  ApStationWarp.y_was = y_down
  local closing = ApStationWarp._anim ~= nil and ApStationWarp._anim.kind == "close"
  if closing then
    -- The confirm press already started the close. Further A/B/Y must not
    -- reach the pause map until that animation finishes.
    if GUI and GUI.FlushInput then
      pcall(GUI.FlushInput)
    end
    ApStationWarp.HoldMapOpen()
    ApStationWarp._status = "popup-closing"
    return
  end
  if b_lock and b_down then
    -- 0.7s from the start of the close, not only while the animation plays.
    if GUI and GUI.FlushInput then
      pcall(GUI.FlushInput)
    end
    ApStationWarp.HoldMapOpen()
    ApStationWarp.b_was = true
    ApStationWarp._status = "b-lock"
    return
  end
  if ApStationWarp.prompt_open then
    -- Eat the press after we sample it so the pause map does not treat B as Close.
    if GUI and GUI.FlushInput then
      pcall(GUI.FlushInput)
    end
    ApStationWarp.HoldMapOpen()
    ApStationWarp._status = "prompt-up"
    if b_pressed then
      ApStationWarp_OnDecline()
      ApStationWarp._status = "cancelled"
      return
    end
    if a_pressed then
      ApStationWarp_OnAccept()
      ApStationWarp._status = "accepted"
    end
    return
  end
  -- A stays on world-map navigation and the marker list.
  -- Y opens the warp prompt only while this pause map is actually on screen.
  -- A station the cursor was sitting on stays in memory after unpausing, and
  -- Y during gameplay must not turn that into a prompt.
  local map_visible = false
  local ok_visible, visible_now = pcall(map_open)
  if ok_visible then
    map_visible = visible_now and true or false
  end
  if not map_visible or not y_pressed or entry == nil then
    if y_pressed and map_visible then
      ApStationWarp._status = "y-idle"
    end
    return
  end
  if GUI and GUI.FlushInput then
    pcall(GUI.FlushInput)
  end
  log(string.format("hover %s dist=%.0f", tostring(entry.area), dist or -1))
  ApStationWarp._status = "prompt " .. tostring(entry.area)
  open_prompt(entry)
end

function ApStationWarp.GuiTick()
  pcall(ApStationWarp.Tick)
  if ApStationWarp.IsEnabled() and Game and Game.AddGUISF then
    Game.AddGUISF(0, "ApStationWarp.GuiTick", "")
  end
end

function ApStationWarp.Install()
  if not ApStationWarp.IsEnabled() then
    log("Install skipped (station map warp off)")
    return
  end
  build_index()
  ApStationWarp.LoadVisited()
  log("modes " .. ApStationWarp.Requirement() .. " / " .. ApStationWarp.Reach())

  if ApStationWarp.did_install then
    pcall(ApStationWarp.SyncSpawn)
    pcall(ApStationWarp.HookMarker)
    if not ApStationWarp._gui_bound and Game and Game.AddGUISF then
      ApStationWarp._gui_bound = true
      Game.AddGUISF(0, "ApStationWarp.GuiTick", "")
    end
    return
  end
  if not Scenario or type(Scenario.CheckDebugInputs) ~= "function" then
    log("Install deferred")
    if Game and Game.AddSF then
      Game.AddSF(0.25, "ApStationWarp.Install", "")
    end
    return
  end

  ApStationWarp.did_install = true
  if not ApStationWarp._gui_bound and Game and Game.AddGUISF then
    ApStationWarp._gui_bound = true
    Game.AddGUISF(0, "ApStationWarp.GuiTick", "")
  end

  local orig_debug = Scenario.CheckDebugInputs
  Scenario.CheckDebugInputs = function(...)
    pcall(ApStationWarp.Tick)
    return orig_debug(...)
  end

  if type(Scenario.CheckWarpToStart) == "function" then
    local orig_warp = Scenario.CheckWarpToStart
    Scenario.CheckWarpToStart = function(actor)
      local name = nil
      if actor ~= nil then
        name = actor.sName or actor
      end
      if type(name) == "string" and is_station_usable(name) then
        pcall(ApStationWarp.NoteUsable, name)
      end
      return orig_warp(actor)
    end
  else
    log("WARN: Scenario.CheckWarpToStart missing")
  end

  if type(Scenario.OnLoadScenarioFinished) == "function" then
    local orig_onload = Scenario.OnLoadScenarioFinished
    Scenario.OnLoadScenarioFinished = function(...)
      local result = orig_onload(...)
      ApStationWarp.prompt_open = false
      ApStationWarp.pending = nil
      ApStationWarp.a_was = false
      ApStationWarp.b_was = false
      ApStationWarp.y_was = false
      ApStationWarp.seen_start = nil
      ApStationWarp.seen_scenario = nil
      pcall(ApStationWarp.LoadVisited)
      pcall(ApStationWarp.SyncSpawn)
      return result
    end
  end

  pcall(ApStationWarp.HookMarker)
  pcall(ApStationWarp.SyncSpawn)
  log("Install complete (pause map A on a locked Save/Map/Network station)")
end

function ApStationWarp.HookMarker()
  if type(guicallbacks) ~= "table" or ApStationWarp._marker_hooked then
    return
  end
  ApStationWarp._marker_hooked = true
  local prev = guicallbacks.OnMinimapCustomMarkCreated
  guicallbacks.OnMinimapCustomMarkCreated = function(arg)
    pcall(ApStationWarp.OnMarkerCreated, arg)
    if type(prev) == "function" then
      return prev(arg)
    end
  end
end

if ApStationWarp.IsEnabled() and not ApStationWarp._gui_bound and Game and Game.AddGUISF then
  if not ApStationWarp.stations then
    build_index()
  end
  ApStationWarp._gui_bound = true
  Game.AddGUISF(0, "ApStationWarp.GuiTick", "")
end

if ApStationWarp.IsEnabled() then
  pcall(ApStationWarp.HookMarker)
end
