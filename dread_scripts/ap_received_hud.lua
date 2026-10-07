-- Show received items on the room-name bar at the bottom right.
-- Align text to the right so long item names stay on screen.
ApReceivedHud = ApReceivedHud or {
  _wrapped = false,
}

local WIDTH = 0.46
local RIGHT_MARGIN = 0.02
local BAR_X = 1 - RIGHT_MARGIN - WIDTH
local BAR_Y = 0.905

function ApReceivedHud.Init()
  if ApReceivedHud.ui then
    pcall(function() ApReceivedHud.ui:Destroy() end)
    ApReceivedHud.ui = nil
    ApReceivedHud.container = nil
    ApReceivedHud.label = nil
  end
  if type(GUILib) ~= "table" or not GUI or not GUI.GetDisplayObject then
    return false
  end
  local ok_hud, hud = pcall(GUI.GetDisplayObject, "IngameMenuRoot.iconshudcomposition")
  if not ok_hud or hud == nil then
    return false
  end
  local ui = GUILib("ApReceivedHud", hud)
  local container = ui:AddContainer("Content", {
    X = BAR_X,
    Y = BAR_Y,
    SizeX = WIDTH,
    SizeY = 0.06,
  })
  container:AddSprite("Background", "HUD_TILESET/BACKGROUND", {
    SizeX = WIDTH,
    SizeY = 0.06,
    FlipX = true,
  })
  -- Mirror the room-name bar's corner for the right side.
  container:AddSprite("Frame_top", "HUD_TILESET/FRAME_TOP", {
    X = WIDTH - 0.05,
    Y = -0.0005,
    SizeX = 0.05,
    SizeY = 0.015,
    FlipX = true,
    ColorR = 0.8773584961891174,
    ColorG = 0.8773584961891174,
    ColorB = 0.8773584961891174,
  })
  local label = container:AddLabel("ApReceivedHud_Text", "", {
    X = "0.008",
    Y = "0.01",
    SizeX = tostring(WIDTH - 0.016),
    SizeY = "0.04",
    Font = "digital_small",
    Autosize = false,
    TextAlignment = "Right",
    TextVerticalAlignment = "Centered",
  })
  ApReceivedHud.ui = ui
  ApReceivedHud.container = container
  ApReceivedHud.label = label
  ApReceivedHud.Fade("0.0", "0.01")
  return true
end

function ApReceivedHud.Fade(fade_val, fade_time)
  fade_time = fade_time or "0.5"
  local container = ApReceivedHud.container
  if not container then
    return
  end
  container:SetProperties({
    FadeColorR = "-1.0",
    FadeColorG = "-1.0",
    FadeColorB = "-1.0",
    FadeColorA = fade_val,
    FadeTime = fade_time,
  })
end

-- Show the message, then let it fade before writing the next one.
-- Use one message on the bar at a time.
local HOLD_SECONDS = 5.0
local FADE_OUT_SECONDS = 0.35
local GAP_AFTER_FADE = 0.2

ApReceivedHud._queue = ApReceivedHud._queue or {}

local function clear_sf(id)
  if id ~= nil and Game and Game.DelSFByID then
    pcall(Game.DelSFByID, id)
  end
end

function ApReceivedHud.Show(text)
  if not ApReceivedHud.label then
    ApReceivedHud.Init()
  end
  if not ApReceivedHud.label then
    return
  end
  ApReceivedHud.label:SetText(tostring(text or ""))
  ApReceivedHud.Fade("1.0", "0.15")
end

function ApReceivedHud.Hide()
  ApReceivedHud.Fade("0.0", tostring(FADE_OUT_SECONDS))
end

function ApReceivedHud.HideCenterPopup()
  if Scenario and Scenario.PopupLabel and GUI and GUI.SetProperties then
    pcall(GUI.SetProperties, Scenario.PopupLabel, { Visible = false })
  end
end

function ApReceivedHud.Enqueue(text)
  if text == nil then
    return
  end
  ApReceivedHud._queue[#ApReceivedHud._queue + 1] = tostring(text)
  if not ApReceivedHud._showing then
    ApReceivedHud.PresentNext()
  end
end

function ApReceivedHud.PresentNext()
  ApReceivedHud._gapId = nil
  if #ApReceivedHud._queue == 0 then
    ApReceivedHud._showing = false
    return
  end
  local text = table.remove(ApReceivedHud._queue, 1)
  ApReceivedHud._showing = true
  ApReceivedHud.Show(text)
  clear_sf(ApReceivedHud._holdId)
  ApReceivedHud._holdId = Game.AddGUISF(HOLD_SECONDS, "ApReceivedHud.BeginGap", "")
  -- Let the normal popup timer remove the message after five seconds.
  if ApReceivedHud._prev_show then
    ApReceivedHud._prev_show(text, HOLD_SECONDS)
  elseif Scenario then
    clear_sf(Scenario.hideSFID)
    Scenario.ShowingPopup = true
    Scenario.hideSFID = Game.AddGUISF(HOLD_SECONDS, "Scenario.HideAsyncPopup", "")
  end
  ApReceivedHud.HideCenterPopup()
end

function ApReceivedHud.BeginGap()
  ApReceivedHud._holdId = nil
  ApReceivedHud.Hide()
  clear_sf(ApReceivedHud._gapId)
  ApReceivedHud._gapId = Game.AddGUISF(FADE_OUT_SECONDS + GAP_AFTER_FADE, "ApReceivedHud.PresentNext", "")
end

function ApReceivedHud.Install()
  if not Scenario then
    return
  end
  -- Save the original functions once so reloading cannot wrap our own code.
  if not ApReceivedHud._wrapped and not ApReceivedHud._prev_show then
    ApReceivedHud._wrapped = true
    ApReceivedHud._prev_show = Scenario.ShowAsyncPopup
    ApReceivedHud._prev_hide = Scenario.HideAsyncPopup
    ApReceivedHud._prev_load = Scenario.OnLoadScenarioFinished
  end
  local prev_hide = ApReceivedHud._prev_hide
  local prev_load = ApReceivedHud._prev_load

  function Scenario.ShowAsyncPopup(text, time)
    ApReceivedHud.Enqueue(text)
    ApReceivedHud.HideCenterPopup()
  end

  if prev_hide then
    function Scenario.HideAsyncPopup()
      prev_hide()
      ApReceivedHud.HideCenterPopup()
    end
  end

  if prev_load then
    function Scenario.OnLoadScenarioFinished(...)
      prev_load(...)
      -- Create the HUD only after the scenario GUI is ready.
      -- Doing this during script loading crashes the game even inside pcall.
      ApReceivedHud.Init()
    end
  end
end
