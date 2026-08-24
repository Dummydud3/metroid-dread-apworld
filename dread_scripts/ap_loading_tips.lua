-- ApLoadingTips: pin ForcedTooltip for Continue / New Game + /tip_force probe.
--
-- Retail SetForcedTooltip @0x1054d10 is a stub; GetForcedTooltip always pushed "".
-- With open-dread-rando-exlaunch OdrTip (tip_hooks), Set/Get are live and
-- SetLoadingMode re-applies tip caption to LOADING+0x68 after the retail clear.
--
-- OdrTip 0.5.2: live tip text overrides + controllable carousel order
-- (default count 1 = CONNECT CLIENT first).
--   InstallHooks seeds Metroid Bread TITLE||BODY defaults (visible before client).
--   Default carousel order is hardcoded sequential 0,1,2,3,4 (not random).
--   OdrTip.SetTipText(0-4, "TITLE||BODY") / SetTipTextByKey / ApLoadingTips.SetTipText
--   OdrTip.GetTipText(0-4) / ApLoadingTips.GetTipText / RL.GetTipText
--   ClearTipText / empty SetTipText restore defaults (not empty / BTXT).
--   OdrTip.SetTipOrder({0,1,2,3,4}) / ApLoadingTips.SetTipOrder — carousel slot order.
--   OdrTip.SetTipCount(N) / ApLoadingTips.SetTipCount — how many tips (1–5).
--   Client: /tip_set 0 {c6}LIVE{c7}||runtime override works.
--   Client: /tip_get 0   (omit slot to dump 0–4)
--   Client: /tip_order 0 1 2 3 4
--   Client: /tip_count 2
--
-- Continue pin: SetForcedTooltip ONLY via LoadGame / OnLoadScenarioRequest /
-- StartPrologue / LoadProfile wraps. Do NOT wrap ShowLoadingScreen / Hide /
-- SetLoadingScreen — that caused heavy CHADO flicker.
-- OnLoadScenarioRequest: ForceNextTip AFTER orig (orig → SetScenarioLoadingScreen
-- → ShowLoadingScreen). Pinning before Show made TipRefresh soft-fail with no
-- PoolBuild; death Continue never hits SetLoadingMode to retry (0.5.9 log).
-- /tip_force stays AddSF-scheduled dialogue + optional chrome probe.

ApLoadingTips = ApLoadingTips or {
  enabled = true,
  did_install = false,
  wrap_count = 0,
  force_count = 0,
  _armed = false,
  _orig = {},
  _fallback_loc = "#TIP_000_GENERAL_PARKOUR_000",
  _last_readback = "",
  _forced_writable = false,
  _forced_dead = true, -- flipped false when Set readback sticks (OdrTip / future)
  _msg_path = "",
  _chrome_secs = 3.0,
  _pending_tip = nil,
  _deathlink_tip = nil, -- TITLE||BODY; re-pin on checkpoint LoadGame after game-over
}

local function log(msg)
  local line = "[ApLoadingTips] " .. tostring(msg)
  if Game and Game.LogWarn then
    Game.LogWarn(0, line)
  end
  local ap = "AP_TIP: " .. tostring(msg)
  if RL and type(RL.SendApLog) == "function" then
    pcall(RL.SendApLog, ap)
  elseif RL and type(RL.SendLog) == "function" then
    pcall(RL.SendLog, ap)
  elseif RemoteLua and type(RemoteLua.SendLog) == "function" then
    pcall(RemoteLua.SendLog, ap)
  end
end

local function tip_display(cur)
  if cur == nil then
    return ""
  end
  cur = tostring(cur)
  if #cur < 2 then
    return cur
  end
  return cur:sub(2)
end

local function tip_is_empty(cur)
  local d = tip_display(cur)
  return d == nil or d == "" or d == "None"
end

local function odr_tip_live()
  return type(OdrTip) == "table" and OdrTip.Ready and true or false
end

--- ForcedTooltip diagnosis + optional pin. With OdrTip subsdk9, readback should stick.
function ApLoadingTips.ApplyForcedTooltip(want)
  want = want or ApLoadingTips._fallback_loc
  local odr = odr_tip_live()

  if type(Game) ~= "table" or type(Game.GetForcedTooltip) ~= "function" then
    log("ApplyForced: GetForcedTooltip missing (dead)")
    ApLoadingTips._forced_dead = true
    ApLoadingTips._forced_writable = false
    ApLoadingTips._last_readback = ""
    return ""
  end

  if type(Game.SetForcedTooltip) == "function" and want ~= nil and want ~= "" then
    local ok_set, ret = pcall(Game.SetForcedTooltip, want)
    local ok2, after = pcall(function()
      return Game.GetForcedTooltip()
    end)
    local after_s = (ok2 and after ~= nil) and tostring(after) or ""
    if odr and type(OdrTip.ApplyToLoadingObject) == "function" then
      pcall(OdrTip.ApplyToLoadingObject)
    end
    log(
      "ApplyForced want="
        .. tostring(want)
        .. " ok_set="
        .. tostring(ok_set)
        .. " set_ret="
        .. tostring(ret)
        .. " readback='"
        .. after_s
        .. "' odr_tip="
        .. tostring(odr)
    )
    if not tip_is_empty(after_s) then
      ApLoadingTips._forced_writable = true
      ApLoadingTips._forced_dead = false
      ApLoadingTips._last_readback = after_s
      return after_s
    end
    ApLoadingTips._last_readback = after_s
  else
    local ok, a = pcall(function()
      return Game.GetForcedTooltip()
    end)
    ApLoadingTips._last_readback = (ok and a ~= nil) and tostring(a) or ""
  end

  ApLoadingTips._forced_writable = false
  ApLoadingTips._forced_dead = true
  return ApLoadingTips._last_readback or ""
end

--- Pin tip id into OdrTip ForcedTooltip slot (no Show/Hide). Cheap; safe to call often.
function ApLoadingTips.ForceNextTip(reason)
  if not ApLoadingTips.enabled then
    return false
  end
  -- Re-apply DeathLink tip pin on checkpoint / scenario load so TipRefresh
  -- after game-over A sees count=1 DEATHLINK (not a later main-menu Continue).
  if ApLoadingTips._deathlink_tip ~= nil and ApLoadingTips._deathlink_tip ~= "" then
    pcall(ApLoadingTips.ApplyDeathLinkTipPin, reason or "ForceNextTip")
  end
  -- Without OdrTip, SetForcedTooltip is a stub — skip spam on Continue.
  if not odr_tip_live() and (ApLoadingTips._forced_dead or ApLoadingTips._forced_writable == false) then
    return false
  end
  local got = ApLoadingTips.ApplyForcedTooltip(nil)
  ApLoadingTips.force_count = (ApLoadingTips.force_count or 0) + 1
  if not tip_is_empty(got) then
    ApLoadingTips._armed = true
    log(
      "ForcedTooltip pinned '"
        .. got
        .. "' reason="
        .. tostring(reason or "?")
        .. " n="
        .. tostring(ApLoadingTips.force_count)
    )
    return true
  end
  return false
end

--- Remember DeathLink tip text for LoadGame("checkpoint") / OnLoad re-pin.
function ApLoadingTips.ArmDeathLinkTip(tip)
  tip = tip ~= nil and tostring(tip) or ""
  if tip == "" then
    ApLoadingTips._deathlink_tip = nil
    return false
  end
  ApLoadingTips._deathlink_tip = tip
  log("ArmDeathLinkTip len=" .. tostring(#tip))
  return true
end

function ApLoadingTips.ClearDeathLinkTip()
  ApLoadingTips._deathlink_tip = nil
end

--- Store tip 0 + count=1 again (OdrTip ArmCarouselRefresh) before ForceNextTip.
function ApLoadingTips.ApplyDeathLinkTipPin(reason)
  local tip = ApLoadingTips._deathlink_tip
  if tip == nil or tip == "" then
    return false
  end
  local ok = false
  if type(OdrTip) == "table" and type(OdrTip.SetTipText) == "function" then
    local call_ok, set_ok = pcall(OdrTip.SetTipText, 0, tip)
    ok = call_ok and set_ok and true or false
    if type(OdrTip.SetTipCount) == "function" then
      pcall(OdrTip.SetTipCount, 1)
    end
    if type(OdrTip.SetTipOrder) == "function" then
      pcall(OdrTip.SetTipOrder, { 0, 1, 2, 3, 4 })
    end
  end
  log(
    "DeathLinkTip re-pin ok="
      .. tostring(ok)
      .. " reason="
      .. tostring(reason or "?")
  )
  -- One-shot: clear after the checkpoint load that consumes it.
  ApLoadingTips._deathlink_tip = nil
  return ok
end

function ApLoadingTips.ClearArm()
  ApLoadingTips._armed = false
end

--- Try to put unmistakable text on screen. #TIP_* alone is often invisible in ShowMessage.
function ApLoadingTips.ShowTipMessage(tip_loc)
  tip_loc = tip_loc or ApLoadingTips._fallback_loc
  if type(tip_loc) ~= "string" then
    tip_loc = ApLoadingTips._fallback_loc
  end
  local keyed = tip_loc
  if keyed:sub(1, 1) ~= "#" then
    keyed = "#" .. keyed
  end
  ApLoadingTips._msg_path = "none"

  -- Unmistakable raw dialogue (localization keys like #TIP_* often no-op in ShowMessage).
  local raw = (
    "AP TIP FORCE|"
    .. "PARKOUR: vault over one-block terrain while running.|"
    .. "key="
    .. keyed
  )

  if not (GUI and type(GUI.ShowMessage) == "function") then
    log("ShowTipMessage FAIL no GUI.ShowMessage")
    return false
  end

  -- 1) Raw 4-arg form used by EmmyAbilityObtained / ODR item popups.
  local ok, err = pcall(GUI.ShowMessage, raw, true, "", false)
  log("ShowTipMessage raw4 ok=" .. tostring(ok) .. " err=" .. tostring(err))
  if ok then
    ApLoadingTips._msg_path = "ShowMessage-raw4"
    return true
  end

  -- 2) Raw 3-arg (ap_warp style).
  ok, err = pcall(GUI.ShowMessage, raw, true, "")
  log("ShowTipMessage raw3 ok=" .. tostring(ok) .. " err=" .. tostring(err))
  if ok then
    ApLoadingTips._msg_path = "ShowMessage-raw3"
    return true
  end

  -- 3) Localized tip key (may be a silent no-op for TIP_* bank).
  ok, err = pcall(GUI.ShowMessage, keyed, true, "", false)
  log("ShowTipMessage key4 " .. keyed .. " ok=" .. tostring(ok) .. " err=" .. tostring(err))
  if ok then
    ApLoadingTips._msg_path = "ShowMessage-key4"
    -- Still schedule HUD — key path often returns ok with nothing visible.
  end

  -- 4) HUD label toast on iconshudcomposition (death-counter style).
  local hud_ok = ApLoadingTips.ShowHudToast(
    "AP TIP: PARKOUR vault over 1-block terrain (" .. keyed .. ")"
  )
  if hud_ok then
    ApLoadingTips._msg_path = (ApLoadingTips._msg_path ~= "none" and (ApLoadingTips._msg_path .. "+hud") or "hud")
    return true
  end

  if ApLoadingTips._msg_path ~= "none" then
    return true
  end
  log("ShowTipMessage: all paths failed or likely no-op")
  return false
end

function ApLoadingTips.ShowHudToast(text)
  if not (GUI and type(GUI.GetDisplayObject) == "function") then
    return false
  end
  local ok_hud, hud = pcall(GUI.GetDisplayObject, "IngameMenuRoot.iconshudcomposition")
  if not ok_hud or hud == nil then
    log("ShowHudToast: no iconshudcomposition")
    return false
  end

  -- Reuse or create a simple label child.
  local label = nil
  if type(hud.FindChild) == "function" then
    local ok_f, child = pcall(hud.FindChild, hud, "ApTipForceLabel")
    if ok_f then
      label = child
    end
  end
  if label == nil and type(GUI.CreateDisplayObject) == "function" then
    local ok_c, created = pcall(
      GUI.CreateDisplayObject,
      hud,
      "ApTipForceLabel",
      "CLabel",
      {
        X = 0.08,
        Y = 0.82,
        SizeX = 0.84,
        SizeY = 0.08,
        Font = "digital_medium",
        TextAlignment = "Centered",
        Autosize = false,
        ColorR = 1.0,
        ColorG = 0.95,
        ColorB = 0.2,
      }
    )
    if ok_c then
      label = created
    end
  end
  if label == nil and type(GUI.CreateDisplayObjectEx) == "function" then
    local ok_c, created = pcall(GUI.CreateDisplayObjectEx, "ApTipForceLabel", "CLabel", {
      X = 0.08,
      Y = 0.82,
      SizeX = 0.84,
      SizeY = 0.08,
      Font = "digital_medium",
    })
    if ok_c and created and type(hud.AddChild) == "function" then
      pcall(hud.AddChild, hud, created)
      label = created
    elseif ok_c then
      label = created
    end
  end
  if label == nil then
    log("ShowHudToast: could not create/find label")
    return false
  end

  if type(GUI.SetLabelText) == "function" then
    local ok_t, err_t = pcall(GUI.SetLabelText, label, tostring(text))
    log("ShowHudToast SetLabelText ok=" .. tostring(ok_t) .. " err=" .. tostring(err_t))
    if not ok_t then
      return false
    end
  elseif type(GUI.SetProperties) == "function" then
    pcall(GUI.SetProperties, label, { Text = tostring(text), Visible = true })
  else
    return false
  end
  if type(GUI.SetProperties) == "function" then
    pcall(GUI.SetProperties, label, { Visible = true, Enabled = true })
  end
  -- Auto-clear after a few seconds.
  if Game and Game.AddSF then
    pcall(Game.AddSF, 6.0, "ApLoadingTips.ClearHudToast", "")
  end
  return true
end

function ApLoadingTips.ClearHudToast()
  if not (GUI and GUI.GetDisplayObject) then
    return
  end
  local ok_hud, hud = pcall(GUI.GetDisplayObject, "IngameMenuRoot.iconshudcomposition")
  if not ok_hud or hud == nil or type(hud.FindChild) ~= "function" then
    return
  end
  local ok_f, label = pcall(hud.FindChild, hud, "ApTipForceLabel")
  if ok_f and label and GUI.SetProperties then
    pcall(GUI.SetProperties, label, { Visible = false })
  end
end

--- Deferred CHADO flash — MUST NOT run inside Remote Lua EXEC (blocks reply → TimeoutError).
function ApLoadingTips.ProbeChromeShow()
  local seconds = tonumber(ApLoadingTips._chrome_secs) or 3.0
  local show_status = "skipped-chrome"
  local ok_chrome, chrome_err = pcall(function()
    if type(Game.SetLoadingScreen) == "function" then
      pcall(Game.SetLoadingScreen, true)
    end
    if type(loadingscreen) == "table" and loadingscreen.oGUIRoot ~= nil then
      local show = ApLoadingTips._orig["ShowLoadingScreen"] or loadingscreen.ShowLoadingScreen
      if type(show) == "function" then
        local ok_show, err_show = pcall(show)
        if ok_show then
          show_status = "show-ok"
          if Game.AddSF then
            pcall(Game.AddSF, seconds, "ApLoadingTips.ProbeHide", "")
          end
        else
          show_status = "show-fail"
          log("ProbeChromeShow err=" .. tostring(err_show))
          if type(Game.SetLoadingScreen) == "function" then
            pcall(Game.SetLoadingScreen, false)
          end
        end
      else
        show_status = "no-Show-fn"
      end
    else
      show_status = "no-loadingscreen"
      if Game.AddSF then
        pcall(Game.AddSF, seconds, "ApLoadingTips.ProbeHideNative", "")
      end
    end
  end)
  if not ok_chrome then
    show_status = "chrome-err"
    log("ProbeChromeShow chrome err=" .. tostring(chrome_err))
  end
  log("ProbeChromeShow status=" .. show_status)
  return show_status
end

--- Fast probe: diagnose Forced, schedule visible message + chrome, return NOW.
--- Never call GUI.ShowMessage inline — it is modal and blocks EXEC → TimeoutError.
function ApLoadingTips.ProbeShow(tip_id, seconds, also_message)
  tip_id = tip_id or ApLoadingTips._fallback_loc
  seconds = tonumber(seconds) or 3.0
  ApLoadingTips._chrome_secs = seconds
  ApLoadingTips._pending_tip = tip_id
  if also_message == nil then
    also_message = true
  end
  ApLoadingTips.ClearArm()

  local got = ""
  local ok_apply, apply_err = pcall(function()
    got = ApLoadingTips.ApplyForcedTooltip(tip_id) or ""
  end)
  if not ok_apply then
    log("ProbeShow ApplyForced err=" .. tostring(apply_err))
    got = ""
  end

  local msg = "skipped"
  if also_message then
    if Game and type(Game.AddSF) == "function" then
      local ok_sf, err_sf = pcall(Game.AddSF, 0.05, "ApLoadingTips.ProbeShowMessage", "")
      if ok_sf then
        msg = "scheduled"
        ApLoadingTips._msg_path = "scheduled"
      else
        msg = "schedule-fail"
        log("ProbeShow AddSF msg err=" .. tostring(err_sf))
      end
    else
      -- Last resort (may block EXEC): call directly.
      local okm = ApLoadingTips.ShowTipMessage(tip_id)
      msg = okm and "inline" or "inline-fail"
    end
  end

  local chrome = "scheduled"
  if Game and type(Game.AddSF) == "function" then
    local ok_sf, err_sf = pcall(Game.AddSF, 0.35, "ApLoadingTips.ProbeChromeShow", "")
    if not ok_sf then
      chrome = "schedule-fail"
      log("ProbeShow AddSF chrome err=" .. tostring(err_sf))
    end
  else
    chrome = "no-AddSF"
  end

  return (
    "readback="
      .. tostring(got)
      .. ";writable="
      .. tostring(ApLoadingTips._forced_writable)
      .. ";forced_dead="
      .. tostring(ApLoadingTips._forced_dead)
      .. ";chrome="
      .. chrome
      .. ";msg="
      .. tostring(msg)
      .. ";msg_path="
      .. tostring(ApLoadingTips._msg_path or "")
  )
end

function ApLoadingTips.ProbeShowMessage()
  local tip = ApLoadingTips._pending_tip or ApLoadingTips._fallback_loc
  local ok = ApLoadingTips.ShowTipMessage(tip)
  log("ProbeShowMessage done ok=" .. tostring(ok) .. " path=" .. tostring(ApLoadingTips._msg_path))
  return ok
end

function ApLoadingTips.ProbeHideNative()
  if Game and type(Game.SetLoadingScreen) == "function" then
    pcall(Game.SetLoadingScreen, false)
  end
  ApLoadingTips.ClearArm()
end

function ApLoadingTips.ProbeHide()
  if loadingscreen and type(loadingscreen.HideLoadingScreen) == "function" then
    local hide = ApLoadingTips._orig["HideLoadingScreen"] or loadingscreen.HideLoadingScreen
    pcall(hide)
  end
  ApLoadingTips.ProbeHideNative()
end

--- Pin-only Game.* wrap: SetForcedTooltip then call original (no Show/Hide thrash).
local function wrap_game_fn(name, reason)
  if type(Game) ~= "table" or type(Game[name]) ~= "function" then
    return false
  end
  local key = "Game." .. name
  if ApLoadingTips._orig[key] ~= nil then
    return true
  end
  local orig = Game[name]
  ApLoadingTips._orig[key] = orig
  Game[name] = function(...)
    pcall(ApLoadingTips.ForceNextTip, reason or name)
    return orig(...)
  end
  ApLoadingTips.wrap_count = (ApLoadingTips.wrap_count or 0) + 1
  return true
end

local function wrap_on_load_scenario()
  if type(guicallbacks) ~= "table" or type(guicallbacks.OnLoadScenarioRequest) ~= "function" then
    return false
  end
  if ApLoadingTips._orig["OnLoadScenarioRequest"] ~= nil then
    return true
  end
  local orig = guicallbacks.OnLoadScenarioRequest
  ApLoadingTips._orig["OnLoadScenarioRequest"] = orig
  guicallbacks.OnLoadScenarioRequest = function(...)
    -- Show loading chrome first, then pin/ForceRefresh. Pre-Show TipRefresh
    -- no-ops (0.5.9 soft-fail); death checkpoint never calls SetLoadingMode.
    orig(...)
    pcall(ApLoadingTips.ForceNextTip, "OnLoadScenarioRequest")
  end
  ApLoadingTips.wrap_count = (ApLoadingTips.wrap_count or 0) + 1
  return true
end

--- Restore any previously installed wraps (Show/Hide thrashers from older scripts + pin wraps).
function ApLoadingTips.UninstallLoadWraps()
  local restored = 0
  if type(loadingscreen) == "table" then
    for _, name in ipairs({
      "ShowLoadingScreen",
      "HideLoadingScreen",
      "SetScenarioLoadingScreen",
      "SetCutsceneLoadingScreen",
      "SetMainMenuLoadingScreen",
    }) do
      local orig = ApLoadingTips._orig[name]
      if orig ~= nil and loadingscreen[name] ~= orig then
        loadingscreen[name] = orig
        restored = restored + 1
      end
      ApLoadingTips._orig[name] = nil
    end
  end
  if type(guicallbacks) == "table" then
    local orig = ApLoadingTips._orig["OnLoadScenarioRequest"]
    if orig ~= nil and guicallbacks.OnLoadScenarioRequest ~= orig then
      guicallbacks.OnLoadScenarioRequest = orig
      restored = restored + 1
    end
    ApLoadingTips._orig["OnLoadScenarioRequest"] = nil
  end
  if type(Game) == "table" then
    for _, name in ipairs({
      "LoadGame",
      "LoadGameFromCheckpoint",
      "LoadScenario",
      "StartPrologue",
      "LoadProfile",
    }) do
      local key = "Game." .. name
      local orig = ApLoadingTips._orig[key]
      if orig ~= nil and Game[name] ~= orig then
        Game[name] = orig
        restored = restored + 1
      end
      ApLoadingTips._orig[key] = nil
    end
  end
  ApLoadingTips.wrap_count = 0
  return restored
end

--- Runtime tip caption override (OdrTip 0.5.0 GetLocalized side table).
--- text shape: TITLE||BODY with optional {c6}/{c7}/{c0}. Empty text clears.
--- indexOrKey: 0–4, or key TIP_* / #TIP_* / AP_TIP_N.
function ApLoadingTips.SetTipText(indexOrKey, text)
  if type(OdrTip) ~= "table" then
    log("SetTipText: OdrTip missing")
    return false, "no-odrtip"
  end
  text = text ~= nil and tostring(text) or ""
  local ok, reason
  if type(indexOrKey) == "number" and type(OdrTip.SetTipText) == "function" then
    ok, reason = OdrTip.SetTipText(indexOrKey, text)
  elseif type(OdrTip.SetTipTextByKey) == "function" then
    ok, reason = OdrTip.SetTipTextByKey(tostring(indexOrKey), text)
  else
    log("SetTipText: no SetTipText API ver=" .. tostring(OdrTip.Version))
    return false, "no-api"
  end
  log(
    "SetTipText slot="
      .. tostring(indexOrKey)
      .. " ok="
      .. tostring(ok)
      .. " reason="
      .. tostring(reason)
      .. " len="
      .. tostring(#text)
  )
  return ok and true or false, reason
end

--- Read current tip override (OdrTip GetTipText). Returns text, key|reason.
function ApLoadingTips.GetTipText(indexOrKey)
  if type(OdrTip) ~= "table" or type(OdrTip.GetTipText) ~= "function" then
    return nil, "no-odrtip"
  end
  return OdrTip.GetTipText(indexOrKey)
end

--- Carousel display order: order[i] = tip id 0–4 for slot i (permutation).
function ApLoadingTips.SetTipOrder(order)
  if type(OdrTip) ~= "table" or type(OdrTip.SetTipOrder) ~= "function" then
    log("SetTipOrder: OdrTip.SetTipOrder missing ver=" .. tostring(OdrTip and OdrTip.Version))
    return false, "no-api"
  end
  if type(order) ~= "table" then
    return false, "bad-args"
  end
  local ok, reason = OdrTip.SetTipOrder(order)
  log(
    "SetTipOrder ok="
      .. tostring(ok)
      .. " reason="
      .. tostring(reason)
      .. " order="
      .. tostring(order[1])
      .. ","
      .. tostring(order[2])
      .. ","
      .. tostring(order[3])
      .. ","
      .. tostring(order[4])
      .. ","
      .. tostring(order[5])
  )
  return ok and true or false, reason
end

function ApLoadingTips.GetTipOrder()
  if type(OdrTip) ~= "table" or type(OdrTip.GetTipOrder) ~= "function" then
    return nil, "no-api"
  end
  return OdrTip.GetTipOrder()
end

--- How many ordered tips the carousel holds (1–5). Composes with SetTipOrder.
function ApLoadingTips.SetTipCount(n)
  if type(OdrTip) ~= "table" or type(OdrTip.SetTipCount) ~= "function" then
    log("SetTipCount: OdrTip.SetTipCount missing ver=" .. tostring(OdrTip and OdrTip.Version))
    return false, "no-api"
  end
  local ok, reason = OdrTip.SetTipCount(tonumber(n) or -1)
  log(
    "SetTipCount n="
      .. tostring(n)
      .. " ok="
      .. tostring(ok)
      .. " reason="
      .. tostring(reason)
  )
  return ok and true or false, reason
end

function ApLoadingTips.GetTipCount()
  if type(OdrTip) ~= "table" or type(OdrTip.GetTipCount) ~= "function" then
    return nil, "no-api"
  end
  return OdrTip.GetTipCount()
end

--- Remote Lua helper: RL.SetTipText / GetTipText / SetTipOrder / SetTipCount when RL exists.
function ApLoadingTips.InstallRemoteTipHelper()
  if type(RL) ~= "table" then
    return false
  end
  RL.SetTipText = function(indexOrKey, text)
    return ApLoadingTips.SetTipText(indexOrKey, text)
  end
  RL.GetTipText = function(indexOrKey)
    return ApLoadingTips.GetTipText(indexOrKey)
  end
  RL.SetTipOrder = function(order)
    return ApLoadingTips.SetTipOrder(order)
  end
  RL.GetTipOrder = function()
    return ApLoadingTips.GetTipOrder()
  end
  RL.SetTipCount = function(n)
    return ApLoadingTips.SetTipCount(n)
  end
  RL.GetTipCount = function()
    return ApLoadingTips.GetTipCount()
  end
  return true
end

function ApLoadingTips.Install()
  -- Strip any Show/Hide / old wraps, then install pin-only load hooks.
  local restored = ApLoadingTips.UninstallLoadWraps()
  ApLoadingTips.did_install = true
  ApLoadingTips.wrap_count = 0
  pcall(ApLoadingTips.InstallRemoteTipHelper)

  wrap_game_fn("LoadGame", "LoadGame")
  wrap_game_fn("LoadGameFromCheckpoint", "LoadGameFromCheckpoint")
  wrap_game_fn("LoadScenario", "LoadScenario")
  wrap_game_fn("StartPrologue", "StartPrologue")
  wrap_game_fn("LoadProfile", "LoadProfile")
  wrap_on_load_scenario()

  -- Early pin so OdrTip slot is filled before first Continue SetLoadingMode.
  local pinned = false
  if odr_tip_live() then
    pinned = ApLoadingTips.ForceNextTip("Install")
  end

  local odr_ver = ""
  if type(OdrTip) == "table" then
    odr_ver = tostring(OdrTip.Version or "?")
      .. " ready="
      .. tostring(OdrTip.Ready)
  end
  log(
    "Install: pin wraps; restored="
      .. tostring(restored)
      .. " wrap_count="
      .. tostring(ApLoadingTips.wrap_count)
      .. " pinned="
      .. tostring(pinned)
      .. " OdrTip="
      .. odr_ver
  )
  return ApLoadingTips.wrap_count
end

if Game and Game.AddSF then
  Game.AddSF(0.25, "ApLoadingTips.Install", "")
else
  ApLoadingTips.Install()
end
