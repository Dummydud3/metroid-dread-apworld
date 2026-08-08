-- Archipelago overrides appended after open-dread-rando's generated randomizer_powerup.
-- Redefines only what AP needs so progressive/boss pickup classes from ODR remain intact.

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

-- Progressive Flash Shift Upgrade: unlock Ghost Aura on first pickup (1 flash);
-- each later upgrade adds +1 chain (3rd pickup = vanilla 3, 7th = 7 uses).
RandomizerFlashShiftUpgrade = {}
setmetatable(RandomizerFlashShiftUpgrade, {__index = RandomizerPowerup})
function RandomizerFlashShiftUpgrade.OnPickedUp(actor, progression)
    progression = progression or {{{item_id = "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", quantity = 1}}}
    local first = not RandomizerPowerup.HasItem("ITEM_GHOST_AURA")
    if first then
        RandomizerPowerup.SetItemAmount("ITEM_GHOST_AURA", 1)
        Game.LogWarn(0, "Flash Shift Upgrade unlocked Flash Shift (ITEM_GHOST_AURA)")
        for _, resource_list in ipairs(progression) do
            for _, resource in ipairs(resource_list) do
                if resource.item_id == "ITEM_UPGRADE_FLASH_SHIFT_CHAIN" then
                    resource.quantity = 0
                end
            end
        end
    end
    RandomizerPowerup.OnPickedUp(actor, progression)
end

-- Progressive Flash Shift Upgrade: do not strip chains when inventory still has 0
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
