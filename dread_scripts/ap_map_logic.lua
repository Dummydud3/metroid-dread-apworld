ApMapLogic = ApMapLogic or { rows = {}, snap = 800, _bound = false }

local ROOT = "IngameMenuRoot.mapmenucomposition"
local TIPS = {
  ROOT .. ".Content.Navigation.ListComposition.Menucontrols-Move",
  ROOT .. ".Content.Navigation.ListComposition.Menucontrols-Zoom",
  ROOT .. ".Content.Navigation.ListComposition.Menucontrols-Recenter",
  ROOT .. ".Content.Navigation.ListComposition.Menucontrols-FastMode",
}
-- Keep the map layout and right-side hints; change only the four tip strings.
local SHOW = {
  ROOT .. ".Content.Navigation",
  ROOT .. ".Content.Navigation.ListComposition",
  ROOT .. ".Content.Navigation.Navigation-Header",
  ROOT .. ".Content.Navigation.Navigation-Header.HeaderBackground",
  ROOT .. ".Content.Navigation.Navigation-Header.Navigation-Label",
  ROOT .. ".Content.Navigation.Navigation-Label",
  ROOT .. ".Content.Navigation.Navigation-Label_Close",
  ROOT .. ".Content.GlobalMap",
  ROOT .. ".Content.GlobalMap.GlobalMap-Label",
  ROOT .. ".Content.GlobalMap.HeaderBackground",
  ROOT .. ".CLabelHighlightIcons",
  ROOT .. ".CLabelAInput",
}
local VANILLA = {
  { ROOT .. ".Content.Navigation.Navigation-Header.Navigation-Label", "MAP CONTROLS" },
  { ROOT .. ".Content.Navigation.Navigation-Label", "MAP CONTROLS" },
  { ROOT .. ".Content.Navigation.Navigation-Label_Close", "MAP CONTROLS" },
  { ROOT .. ".Content.GlobalMap.GlobalMap-Label", "GLOBAL MAP" },
  { ROOT .. ".CLabelHighlightIcons", "HIGHLIGHT ICONS" },
  { ROOT .. ".CLabelAInput", "PLACE MARKER" },
}

local function getter(obj, name)
  if obj == nil then return nil end
  local ok, fn = pcall(function() return obj["_" .. name .. "_GetterFunction"] end)
  if not ok or type(fn) ~= "function" then return nil end
  local okv, value = pcall(fn, obj)
  if okv then return value end
  return nil
end

local function map_open()
  local ok, root = pcall(GUI.GetDisplayObject, "IngameMenuRoot.mapmenucomposition")
  if not ok or root == nil then return false end
  return getter(root, "Enabled") == true and getter(root, "Visible") == true
end

local function world_xy(x, y)
  if type(x) ~= "number" or type(y) ~= "number" or x ~= x or y ~= y then return nil, nil end
  if math.abs(x) > 80000 or math.abs(y) > 80000 then return nil, nil end
  if math.abs(x) < 1 and math.abs(y) < 1 then return nil, nil end
  return x, y
end

local function player_xy()
  local ok, player = pcall(Game.GetPlayer)
  if not ok or player == nil or player.vPos == nil then return nil, nil end
  local pos = player.vPos
  local mt = debug.getregistry()["base::math::CVector3D"]
  if mt == nil then return nil, nil end
  local old = debug.getmetatable(pos)
  debug.setmetatable(pos, mt)
  local x, y = tonumber(pos.x), tonumber(pos.y)
  debug.setmetatable(pos, old)
  return world_xy(x, y)
end

local function read_view()
  if OdrMap and OdrMap.ReadU64 and OdrMap.ReadFloatsAbs then
    local ok, mgr = pcall(Game.GetMinimapManager)
    if ok and mgr ~= nil then
      local hex = OdrMap.ReadU64(mgr, 0x38)
      if type(hex) == "string" then
        local rows = OdrMap.ReadFloatsAbs(hex, 0x560, 2)
        if type(rows) == "table" then
          local x, y = world_xy(rows[1], rows[2])
          if x ~= nil then return x, y end
        end
      end
    end
  end
  -- Use Samus's position until the map cursor is ready.
  return player_xy()
end

local function real_obj(path)
  local ok, obj = pcall(GUI.GetDisplayObject, path)
  if not ok or obj == nil then return nil end
  local okf, fn = pcall(function() return obj._Enabled_GetterFunction end)
  if not okf or type(fn) ~= "function" then return nil end
  return obj
end

local function show_obj(path)
  local obj = real_obj(path)
  if obj == nil then return end
  pcall(GUI.SetProperties, obj, { Visible = true, Enabled = true })
end

local function tip_scale(text)
  -- Shrink lines longer than the usual 21-character label width.
  -- Keep the text inside the tip box.
  local n = #(text or "")
  -- SetProperties ignores scale 1, so use a value just below it.
  if n <= 21 then return 0.999 end
  local scale = 21 / n
  if scale < 0.65 then scale = 0.65 end
  return scale
end

local function set_text(path, text, scale)
  local obj = real_obj(path)
  if obj == nil then return end
  text = text or ""
  if scale == nil or scale == 1 then scale = 0.999 end
  ApMapLogic._last = ApMapLogic._last or {}
  -- Hide and show the label to refresh its text.
  if ApMapLogic._last[path] ~= text then
    pcall(GUI.SetProperties, obj, { Visible = false })
    if GUI.SetLabelText then pcall(GUI.SetLabelText, obj, text) end
    ApMapLogic._last[path] = text
  end
  pcall(GUI.SetProperties, obj, {
    Text = text,
    Visible = true,
    Enabled = true,
    ScaleX = scale,
    ScaleY = scale,
  })
end

function ApMapLogic.RestoreChrome()
  for _, path in ipairs(SHOW) do
    show_obj(path)
  end
  for _, path in ipairs(TIPS) do
    show_obj(path)
  end
  for _, item in ipairs(VANILLA) do
    set_text(item[1], item[2], 1)
  end
end

function ApMapLogic.Apply(lines)
  lines = lines or {}
  ApMapLogic.RestoreChrome()
  for i, path in ipairs(TIPS) do
    local text = lines[i]
    if type(text) ~= "string" then text = "" end
    set_text(path, text, tip_scale(text))
  end
end

function ApMapLogic.Nearest(scenario, x, y)
  local best, best_d = nil, nil
  local limit = (ApMapLogic.snap or 800) ^ 2
  for _, row in ipairs(ApMapLogic.rows or {}) do
    if row.s == scenario then
      local dx, dy = row.x - x, row.y - y
      local d2 = dx * dx + dy * dy
      if d2 <= limit and (best_d == nil or d2 < best_d) then
        best, best_d = row, d2
      end
    end
  end
  return best
end

function ApMapLogic.Tick()
  if not map_open() then
    ApMapLogic._status = "map-closed"
    return
  end
  local x, y = read_view()
  if x == nil then
    ApMapLogic.Apply({})
    ApMapLogic._status = "no-cursor"
    return
  end
  local scenario = nil
  pcall(function() scenario = Game.GetScenarioID() end)
  local row = ApMapLogic.Nearest(scenario, x, y)
  if row == nil then
    ApMapLogic.Apply({})
    ApMapLogic._status = string.format("empty %.0f %.0f", x, y)
    return
  end
  local lines = row.t
  if type(lines) ~= "table" or #lines == 0 then
    lines = { "No abilities" }
  elseif #lines > #TIPS then
    local packed = {}
    local per = math.ceil(#lines / #TIPS)
    local i = 1
    while i <= #lines and #packed < #TIPS do
      local parts = {}
      for k = 0, per - 1 do
        local item = lines[i + k]
        if item then parts[#parts + 1] = item end
      end
      packed[#packed + 1] = table.concat(parts, ", ")
      i = i + per
    end
    lines = packed
  end
  ApMapLogic.Apply(lines)
  ApMapLogic._status = string.format("hover %s", tostring(row.area or ""))
end

function ApMapLogic.GuiTick()
  pcall(ApMapLogic.Tick)
  if Game and Game.AddGUISF then
    Game.AddGUISF(0, "ApMapLogic.GuiTick", "")
  end
end

if not ApMapLogic._bound and Game and Game.AddGUISF then
  ApMapLogic._bound = true
  Game.AddGUISF(0, "ApMapLogic.GuiTick", "")
end
return "logic-tick"
