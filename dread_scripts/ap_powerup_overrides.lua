-- Add AP changes after ODR's generated powerup script.

-- For All Bosses, let the AP client unlock Itorash after checking bosses.
AP_ALL_BOSSES_GATE = AP_ALL_BOSSES_GATE or false

local function ap_all_bosses_gate()
    if RL and RL.AllBossesGate ~= nil then
        return RL.AllBossesGate and true or false
    end
    return AP_ALL_BOSSES_GATE and true or false
end

-- Keep DNA HUD errors from stopping an item grant.
local function ap_ensure_hud_dna_wrapped()
    if not Scenario or type(Scenario.UpdateHudDnaCount) ~= "function" then
        return
    end
    if Scenario._APHudDnaWrapped then
        return
    end
    Scenario._APHudDnaWrapped = true
    local _ap_orig_update_hud_dna = Scenario.UpdateHudDnaCount
    function Scenario.UpdateHudDnaCount()
        local label = Scenario.DnaCountLabel
        if label == nil then
            return
        end
        if Exists and not Exists(label) then
            return
        end
        if not Init or not Init.iNumRequiredArtifacts or Init.iNumRequiredArtifacts <= 0 then
            return
        end
        return _ap_orig_update_hud_dna()
    end
end

local function ap_update_hud_dna()
    ap_ensure_hud_dna_wrapped()
    if not Scenario or type(Scenario.UpdateHudDnaCount) ~= "function" then
        return
    end
    local ok, err = pcall(Scenario.UpdateHudDnaCount)
    if not ok then
        Game.LogWarn(0, "UpdateHudDnaCount failed: " .. tostring(err))
        if RL and RL.SendApLog then
            RL.SendApLog("AP_DNA_HUD_FAIL: " .. tostring(err))
        end
    end
end

function RandomizerPowerup.CheckArtifacts(resource)
    if not resource then return end
    if not Init or Init.iNumRequiredArtifacts == 0 then return end
    if RandomizerPowerup.HasItem("ITEM_METROIDNIZATION") then return end

    if resource.item_id:find("ITEM_RANDO_ARTIFACT", 1, true) then
        if GUI and GUI.AddEmmyMissionLogEntry then
            pcall(GUI.AddEmmyMissionLogEntry, "#MLOG_" .. resource.item_id)
        end
    end

    ap_update_hud_dna()

    for i = 1, Init.iNumRequiredArtifacts do
        if RandomizerPowerup.GetItemAmount("ITEM_RANDO_ARTIFACT_" .. i) == 0 then
            return
        end
    end

    if ap_all_bosses_gate() then
        Game.LogWarn(0, "CheckArtifacts: DNA complete; Metroidnization deferred (All Bosses)")
        if RL and RL.SendApLog then
            RL.SendApLog("AP_ALL_BOSSES: DNA complete; waiting for bosses before Metroidnization")
        end
        return
    end

    RandomizerPowerup.SetItemAmount("ITEM_METROIDNIZATION", 1)
end

-- Add the GrantNextArtifact helper used by remote DNA grants.
function RandomizerPowerup.GrantNextArtifact()
    if not Init or not Init.iNumRequiredArtifacts or Init.iNumRequiredArtifacts == 0 then
        Game.LogWarn(0, "GrantNextArtifact: DNA gate disabled (iNumRequiredArtifacts=0)")
        return nil
    end
    for i = 1, Init.iNumRequiredArtifacts do
        local artifact_id = "ITEM_RANDO_ARTIFACT_" .. i
        if RandomizerPowerup.GetItemAmount(artifact_id) == 0 then
            Game.LogWarn(0, "GrantNextArtifact: granting " .. artifact_id)
            RandomizerPowerup.IncreaseItemAmount(artifact_id, 1)
            local resource = {item_id = artifact_id, quantity = 1}
            RandomizerPowerup.CheckArtifacts(resource)
            ap_update_hud_dna()
            return resource
        end
    end
    Game.LogWarn(0, "GrantNextArtifact: all required artifacts already owned")
    return nil
end

function RandomizerPowerup.MarkLocationCollected(locationIdentifier)
    local playerSection = Game.GetPlayerBlackboardSectionName()
    local propName = RandomizerPowerup.PropertyForLocation(locationIdentifier)
    Game.LogWarn(0, propName)
    if playerSection ~= nil then
        Blackboard.SetProp(playerSection, propName, "b", true)
    end
    if ApLoadingTips and type(ApLoadingTips.NotifyCheckCollected) == "function" then
        pcall(ApLoadingTips.NotifyCheckCollected, locationIdentifier)
    end

    -- Use callback names for boss pickups when no actor is provided.
    local pickupIndex = nil
    if RL and RL.BossPickupIndexByLocation then
        pickupIndex = RL.BossPickupIndexByLocation[locationIdentifier]
    end
    local msg
    if pickupIndex ~= nil then
        msg = string.format(
            "AP_CHECK: boss/EMMI marked %s (pickup index %d) — syncing LocationChecks",
            locationIdentifier,
            pickupIndex
        )
    else
        msg = "AP_CHECK: marked " .. tostring(locationIdentifier)
    end
    Game.LogWarn(0, msg)
    if RL and RL.SendApLog then
        RL.SendApLog(msg)
    end

    -- Send pickup flags even when boss callbacks run outside INGAME.
    if RL and RL.GetCollectedIndicesAndSend then
        pcall(RL.GetCollectedIndicesAndSend)
        Game.AddSF(0.05, "RL.GetCollectedIndicesAndSend", "")
        Game.AddSF(1.0, "RL.GetCollectedIndicesAndSend", "")
        Game.AddSF(3.0, "RL.GetCollectedIndicesAndSend", "")
    end
end

-- Unlock Ghost Aura on the first progressive Flash Shift Upgrade when needed.
AP_FLASH_SHIFT_REQUIRES_MAIN = AP_FLASH_SHIFT_REQUIRES_MAIN or false

local function ap_flash_shift_requires_main()
    if RL and RL.FlashShiftRequiresMain ~= nil then
        return RL.FlashShiftRequiresMain and true or false
    end
    return AP_FLASH_SHIFT_REQUIRES_MAIN and true or false
end

local function ap_unlock_flash_shift_from_upgrade()
    if RandomizerPowerup.HasItem("ITEM_GHOST_AURA") then
        return false
    end
    if ap_flash_shift_requires_main() then
        return false
    end
    RandomizerPowerup.SetItemAmount("ITEM_GHOST_AURA", 1)
    Game.LogWarn(0, "Flash Shift Upgrade unlocked Flash Shift (ITEM_GHOST_AURA)")
    -- Refresh controls so new abilities work without reloading.
    if RandomizerPowerup.DisableInput then
        RandomizerPowerup.DisableInput()
    end
    return true
end

-- Match the local progressive Flash Shift grant behavior.
if not RandomizerPowerup._APFlashUpgradeHooked then
    RandomizerPowerup._APFlashUpgradeHooked = true
    local _APIncreaseItemAmount = RandomizerPowerup.IncreaseItemAmount
    function RandomizerPowerup.IncreaseItemAmount(item_id, quantity, capacity)
        if item_id == "ITEM_UPGRADE_FLASH_SHIFT_CHAIN" and quantity and quantity > 0 then
            -- Local pickups use RandomizerPowerup rather than SPECIFIC_CLASSES.
            ap_unlock_flash_shift_from_upgrade()
        end
        return _APIncreaseItemAmount(item_id, quantity, capacity)
    end
end

RandomizerFlashShiftUpgrade = {}
setmetatable(RandomizerFlashShiftUpgrade, {__index = RandomizerPowerup})
function RandomizerFlashShiftUpgrade.OnPickedUp(actor, progression)
    progression = progression or {{{item_id = "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", quantity = 1}}}
    local first = not RandomizerPowerup.HasItem("ITEM_GHOST_AURA")
    if first and not ap_flash_shift_requires_main() then
        ap_unlock_flash_shift_from_upgrade()
    elseif first and ap_flash_shift_requires_main() then
        Game.LogWarn(0, "Flash Shift Upgrade stacked (waiting for main Flash Shift)")
    end
    RandomizerPowerup.OnPickedUp(actor, progression)
end

-- Keep existing Flash Shift chains while the inventory is still updating.
function RandomizerFlashShift.OnPickedUp(actor, progression)
    progression = progression or {{{item_id = "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", quantity = 0}}}

    local hasFlashShift = RandomizerPowerup.HasItem("ITEM_GHOST_AURA")
    local currentChains = RandomizerPowerup.GetItemAmount("ITEM_UPGRADE_FLASH_SHIFT_CHAIN") or 0

    for _, resource_list in ipairs(progression) do
        for _, resource in ipairs(resource_list) do
            if resource.item_id == "ITEM_UPGRADE_FLASH_SHIFT_CHAIN" and hasFlashShift and currentChains > 0 then
                -- Do not add more chains for a duplicate main Flash Shift item.
                resource.quantity = 0
            end
        end
    end

    RandomizerPowerup.OnPickedUp(actor, progression)
end
