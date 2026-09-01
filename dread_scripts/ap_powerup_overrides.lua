-- Archipelago overrides appended after open-dread-rando's generated randomizer_powerup.
-- Redefines only what AP needs so progressive/boss pickup classes from ODR remain intact.

-- All Bosses: DNA CheckArtifacts must not unlock Itorash; the AP client grants
-- ITEM_METROIDNIZATION only when every non-RB boss is beaten (and DNA, if any).
AP_ALL_BOSSES_GATE = AP_ALL_BOSSES_GATE or false

local function ap_all_bosses_gate()
    if RL and RL.AllBossesGate ~= nil then
        return RL.AllBossesGate and true or false
    end
    return AP_ALL_BOSSES_GATE and true or false
end

function RandomizerPowerup.CheckArtifacts(resource)
    if not resource then return end
    if not Init or Init.iNumRequiredArtifacts == 0 then return end
    if RandomizerPowerup.HasItem("ITEM_METROIDNIZATION") then return end

    if resource.item_id:find("ITEM_RANDO_ARTIFACT", 1, true) then
        if GUI and GUI.AddEmmyMissionLogEntry then
            GUI.AddEmmyMissionLogEntry("#MLOG_" .. resource.item_id)
        end
    end

    if Scenario and Scenario.UpdateHudDnaCount then
        Scenario.UpdateHudDnaCount()
    end

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

-- Remote AP DNA (format_dna_receive_lua / /give). Stock ODR has no GrantNextArtifact;
-- without this, server DNA shows the popup but never increments the HUD counter.
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
            if Scenario and Scenario.UpdateHudDnaCount then
                Scenario.UpdateHudDnaCount()
            end
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

    -- Boss/EMMI wrappers call this with scenario_callback keys (actor is nil in OnPickedUp).
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

    -- Boss/EMMI death callbacks often run outside INGAME; push bitfield immediately
    -- (AddSF alone can be dropped mid-cutscene) and retry after the cutscene.
    if RL and RL.GetCollectedIndicesAndSend then
        pcall(RL.GetCollectedIndicesAndSend)
        Game.AddSF(0.05, "RL.GetCollectedIndicesAndSend", "")
        Game.AddSF(1.0, "RL.GetCollectedIndicesAndSend", "")
        Game.AddSF(3.0, "RL.GetCollectedIndicesAndSend", "")
    end
end

-- Progressive Flash Shift Upgrade: unlock Ghost Aura on first pickup when
-- Require Main Item is OFF. When Require Main is ON, upgrades only add chains.
-- AP_FLASH_SHIFT_REQUIRES_MAIN is set by finalize_mod / client from seed options.
AP_FLASH_SHIFT_REQUIRES_MAIN = AP_FLASH_SHIFT_REQUIRES_MAIN or false

local function ap_flash_shift_requires_main()
    if RL and RL.FlashShiftRequiresMain ~= nil then
        return RL.FlashShiftRequiresMain and true or false
    end
    return AP_FLASH_SHIFT_REQUIRES_MAIN and true or false
end

-- Mirror of randomizer_powerup.lua Flash Shift Upgrade (progressive first = ability only).
if not RandomizerPowerup._APFlashUpgradeHooked then
    RandomizerPowerup._APFlashUpgradeHooked = true
    local _APIncreaseItemAmount = RandomizerPowerup.IncreaseItemAmount
    function RandomizerPowerup.IncreaseItemAmount(item_id, quantity, capacity)
        if item_id == "ITEM_UPGRADE_FLASH_SHIFT_CHAIN" and quantity and quantity > 0 then
            if RandomizerPowerup._APFlashFirstUnlock then
                quantity = 0
            elseif not RandomizerPowerup.HasItem("ITEM_GHOST_AURA") and not ap_flash_shift_requires_main() then
                RandomizerPowerup.SetItemAmount("ITEM_GHOST_AURA", 1)
                Game.LogWarn(0, "Flash Shift Upgrade unlocked Flash Shift (ITEM_GHOST_AURA)")
                quantity = 0
            end
        end
        return _APIncreaseItemAmount(item_id, quantity, capacity)
    end
end

RandomizerFlashShiftUpgrade = {}
setmetatable(RandomizerFlashShiftUpgrade, {__index = RandomizerPowerup})
function RandomizerFlashShiftUpgrade.OnPickedUp(actor, progression)
    progression = progression or {{{item_id = "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", quantity = 1}}}
    local first = not RandomizerPowerup.HasItem("ITEM_GHOST_AURA")
    RandomizerPowerup._APFlashFirstUnlock = false
    if first and not ap_flash_shift_requires_main() then
        for _, resource_list in ipairs(progression) do
            for _, resource in ipairs(resource_list) do
                if resource.item_id == "ITEM_UPGRADE_FLASH_SHIFT_CHAIN" then
                    resource.quantity = 0
                end
            end
        end
        RandomizerPowerup.SetItemAmount("ITEM_GHOST_AURA", 1)
        RandomizerPowerup._APFlashFirstUnlock = true
        Game.LogWarn(0, "Flash Shift Upgrade unlocked Flash Shift (ITEM_GHOST_AURA)")
    elseif first and ap_flash_shift_requires_main() then
        Game.LogWarn(0, "Flash Shift Upgrade stacked (waiting for main Flash Shift)")
    end
    RandomizerPowerup.OnPickedUp(actor, progression)
    RandomizerPowerup._APFlashFirstUnlock = false
end

-- Main Flash Shift: do not strip chains when inventory still has 0
-- (lets AP catch up after a Ghost-only local grant).
function RandomizerFlashShift.OnPickedUp(actor, progression)
    progression = progression or {{{item_id = "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", quantity = 0}}}

    local hasFlashShift = RandomizerPowerup.HasItem("ITEM_GHOST_AURA")
    local currentChains = RandomizerPowerup.GetItemAmount("ITEM_UPGRADE_FLASH_SHIFT_CHAIN") or 0

    for _, resource_list in ipairs(progression) do
        for _, resource in ipairs(resource_list) do
            if resource.item_id == "ITEM_UPGRADE_FLASH_SHIFT_CHAIN" and hasFlashShift and currentChains > 0 then
                -- Duplicate Flash Shift main item only: do not stack more chains
                resource.quantity = 0
            end
        end
    end

    RandomizerPowerup.OnPickedUp(actor, progression)
end
