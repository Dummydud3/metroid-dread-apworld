Game.LogWarn(0, "Loading randomizer_powerup.lua...")

RandomizerPowerup = {}
function RandomizerPowerup.main()
end

RandomizerPowerup.tProgressiveModels = {}

RandomizerPowerup.Self = nil

function RandomizerPowerup.SetItemAmount(item_id, quantity)
    if type(quantity) == "string" then
        quantity = RandomizerPowerup.GetItemAmount(quantity)
    end
    Game.SetItemAmount(Game.GetPlayerName(), item_id, quantity)
end
function RandomizerPowerup.GetItemAmount(item_id)
    return Game.GetItemAmount(Game.GetPlayerName(), item_id)
end
function RandomizerPowerup.HasItem(item_id)
    return RandomizerPowerup.GetItemAmount(item_id) > 0
end
function RandomizerPowerup.IncreaseItemAmount(item_id, quantity, capacity)
    local target = RandomizerPowerup.GetItemAmount(item_id) + quantity
    if capacity ~= nil then
        if type(capacity) == "string" then
            capacity = RandomizerPowerup.GetItemAmount(capacity)
        end
        target = math.min(target, capacity)
    end
    target = math.max(target, 0)
    RandomizerPowerup.SetItemAmount(item_id, target)
end

function RandomizerPowerup.PropertyForLocation(locationIdentifier)
    return "Location_Collected_" .. locationIdentifier
end

function RandomizerPowerup.MarkLocationCollected(locationIdentifier)
    local playerSection = Game.GetPlayerBlackboardSectionName()
    local propName = RandomizerPowerup.PropertyForLocation(locationIdentifier)
    Game.LogWarn(0, propName)
    if playerSection ~= nil then
        Blackboard.SetProp(playerSection, propName, "b", true)
    end
    local pickupIndex = nil
    if RL and RL.BossPickupIndexByLocation then
        pickupIndex = RL.BossPickupIndexByLocation[locationIdentifier]
    end
    if pickupIndex ~= nil then
        Game.LogWarn(0, "AP_CHECK: boss/EMMI pickup index " .. tostring(pickupIndex))
        if RL and RL.SendApLog then
            RL.SendApLog("AP_CHECK: boss/EMMI marked " .. locationIdentifier .. " (pickup index " .. tostring(pickupIndex) .. ")")
        end
    end
    -- Boss/EMMI death callbacks often run outside INGAME; push bitfield anyway.
    if RL and RL.GetCollectedIndicesAndSend then
        pcall(RL.GetCollectedIndicesAndSend)
        Game.AddSF(0.05, "RL.GetCollectedIndicesAndSend", "")
        Game.AddSF(1.0, "RL.GetCollectedIndicesAndSend", "")
        Game.AddSF(3.0, "RL.GetCollectedIndicesAndSend", "")
    end
end

function RandomizerPowerup.IncrementInventoryIndex()
    local playerSection = Game.GetPlayerBlackboardSectionName()
    local propName = "InventoryIndex"
    local currentIndex = Blackboard.GetProp(playerSection, propName) or 0
    currentIndex = currentIndex + 1
    Blackboard.SetProp(playerSection, propName, "f", currentIndex)
end

-- Stub for missing Randovania functions to prevent crashes
if not Scenario then Scenario = {} end
if not Scenario.UpdateHudDnaCount then
    function Scenario.UpdateHudDnaCount()
        -- Stub for Archipelago (DNA counter not used)
    end
end
if not Game.UpdateHudDnaCount then
    function Game.UpdateHudDnaCount()
        -- Stub for Archipelago (DNA counter not used)
    end
end

function RandomizerPowerup.OnPickedUp(actor, resources)
    RandomizerPowerup.Self = actor
    local name = "Boss"
    if actor ~= nil then
        name = actor.sName
        RandomizerPowerup.MarkLocationCollected(string.format("%s_%s", Scenario.CurrentScenarioID, name))
    end

    Game.LogWarn(0, "Collected pickup: " .. name)
    local granted = RandomizerPowerup.HandlePickupResources(resources)

    for _, resource in ipairs(granted) do
        RandomizerPowerup.IncreaseEnergy(resource)
        RandomizerPowerup.IncreaseAmmo(resource)
        RandomizerPowerup.CheckArtifacts(resource)
    end

    RandomizerPowerup.ApplyTunableChanges()
    RandomizerPowerup.UpdateWeapons()
    
    -- Removed calls to functions that may not exist in Archipelago context
    -- Scenario.UpdateProgressiveItemModels()
    -- Scenario.UpdateBlastShields()
    
    RandomizerPowerup.IncrementInventoryIndex()
    
    -- Call RL.UpdateRDVClient if it exists
    if RL and RL.UpdateRDVClient then
        RL.UpdateRDVClient(false)
    end
    
    return granted
end

function RandomizerPowerup.DisableInput()
    -- items with unique inputs (Speed Booster, Phantom Cloak) require disabling and re-enabling inputs to work properly
    local oPlayer = Game.GetPlayer()
    if oPlayer ~= nil then
        oPlayer.INPUT:IgnoreInput(true, false, "PickupObtained")
    end
    Game.AddSF(0.1, "RandomizerPowerup.RecoverInput", "")
end
function RandomizerPowerup.RecoverInput()
    local oPlayer = Game.GetPlayer()
    if oPlayer ~= nil then
        oPlayer.INPUT:IgnoreInput(false, false, "PickupObtained")
    end
end

function RandomizerPowerup.HandlePickupResources(progression)
    progression = progression or {}

    local alwaysGrant = false

    if #progression == 0 then
        return {}
    elseif #progression == 1 then
        alwaysGrant = true
    end

    Game.LogWarn(0, "Resources:")
    for _, resource_list in ipairs(progression) do
        local data = " - "
        for _, resource in ipairs(resource_list) do
            data = data .. resource.item_id .. " (" .. resource.quantity .. ") / "
        end
        Game.LogWarn(0, data)
    end

    -- For each progression stage, if the player does not have the FIRST item in that stage, the whole stage is granted
    for _, resource_list in ipairs(progression) do
        -- Check if we need to grant anything from this progression stage

        if #resource_list > 0 then
            local current = RandomizerPowerup.GetItemAmount(resource_list[1].item_id)
            local shouldGrant = alwaysGrant or current < resource_list[1].quantity

            if shouldGrant then
                for _, resource in ipairs(resource_list) do
                    Game.LogWarn(0, "Granting " .. resource.quantity .. " " .. resource.item_id)
                    RandomizerPowerup.IncreaseItemAmount(resource.item_id, resource.quantity)
                end

                return resource_list
            end
        end

        -- Otherwise, loop to next progression stage (or fall out of loop)
    end

    return {} -- nothing granted after final stage of progression is reached
end

function RandomizerPowerup.ChangeSuit()
    -- ordered by priority
    local suits = {
        {item = "ITEM_HYPER_SUIT", model = "Hyper"},
        {item = "ITEM_GRAVITY_SUIT", model = "Gravity"},
        {item = "ITEM_VARIA_SUIT", model = "Varia"},
    }
    local model_updater = Game.GetPlayer().MODELUPDATER
    for _, suit in ipairs(suits) do
        if suit.model == model_updater.sModelAlias then break end
        if RandomizerPowerup.HasItem(suit.item) then
            Game.AddPSF(0.1, RandomizerPowerup.Delayed_ChangeSuit, "s", suit.model)
            break
        end
    end
end

function RandomizerPowerup.Delayed_ChangeSuit(model)
    if fxcallbacks == nil then
        Game.LogWarn(0, "No fxcallbacks")
    elseif #fxcallbacks.lfxenabled > 0 then
        Game.LogWarn(0, "FX active, try again")
        Game.AddPSF(0.1, RandomizerPowerup.Delayed_ChangeSuit, "s", model)
        return
    end
    -- updating the model while VFX are active on the old model will cause a nullptr
    local model_updater = Game.GetPlayer().MODELUPDATER
    Game.LogWarn(0, "Updating suit to " .. model)
    model_updater.sModelAlias = model
end

MAX_ENERGY = 1499
function RandomizerPowerup.IncreaseEnergy(resource)
    -- No resource, quit
    if not resource then return end

    local item_id = resource.item_id

    -- Not etank or epart, quit
    if item_id ~= "ITEM_ENERGY_TANKS" and item_id ~= "ITEM_LIFE_SHARDS" then return end

    local energy = Init.fEnergyPerTank

    if item_id == "ITEM_LIFE_SHARDS" then
        local shards_amount = RandomizerPowerup.GetItemAmount(item_id)
        if Init.bImmediateEnergyParts then
            energy = Init.fEnergyPerPart
        elseif (shards_amount % 4) ~= 0 then
            -- only change energy every 4 parts if not immediate but change internal amount
            Game.GetPlayer().LIFE.fLifeShards = shards_amount
            return
        end
        -- remove all life shards as energy will be increased by following code
        RandomizerPowerup.SetItemAmount("ITEM_LIFE_SHARDS", 0)
        Game.GetPlayer().LIFE.fLifeShards = 0
    end

    Game.LogWarn(0, "Increasing player energy.")

    local new_max = RandomizerPowerup.GetItemAmount("ITEM_MAX_LIFE") + energy
    new_max = math.min(new_max, MAX_ENERGY)

    local new_current = new_max
    if item_id == "ITEM_LIFE_SHARDS" and Init.bImmediateEnergyParts then
        new_current = RandomizerPowerup.GetItemAmount("ITEM_CURRENT_LIFE") + energy
        new_current = math.min(new_current, new_max)
    end

    RandomizerPowerup.SetItemAmount("ITEM_MAX_LIFE", new_max)
    RandomizerPowerup.SetItemAmount("ITEM_CURRENT_LIFE", new_current)

    local life = Game.GetPlayer().LIFE
    life.fMaxLife = new_max
    life.fCurrentLife = new_current
end

function RandomizerPowerup.IncreaseAmmo(resource)
    if not resource then return end

    local current_id = nil

    if resource.item_id == "ITEM_WEAPON_POWER_BOMB_MAX" then
        current_id = "ITEM_WEAPON_POWER_BOMB_CURRENT"
    elseif resource.item_id == "ITEM_WEAPON_MISSILE_MAX" then
        current_id = "ITEM_WEAPON_MISSILE_CURRENT"
    end

    if current_id == nil then return end

    RandomizerPowerup.IncreaseItemAmount(current_id, resource.quantity, resource.item_id)
end

function RandomizerPowerup.GrantNextArtifact()
    -- Grant the first unowned ITEM_RANDO_ARTIFACT_N (N <= required DNA).
    -- Used for AP server /give DNA when artifact slot is not fixed upfront.
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

function RandomizerPowerup.CheckArtifacts(resource)
    if not resource then return end
    if not Init or Init.iNumRequiredArtifacts == 0 then return end
    if RandomizerPowerup.HasItem("ITEM_METROIDNIZATION") then return end

    if resource.item_id:find("ITEM_RANDO_ARTIFACT", 1, true) then
        if GUI and GUI.AddEmmyMissionLogEntry then
            GUI.AddEmmyMissionLogEntry("#MLOG_" .. resource.item_id)
        end
    end

    -- Use stub instead of missing function
    if Scenario and Scenario.UpdateHudDnaCount then
        Scenario.UpdateHudDnaCount()
    end

    -- check for all artifact items, which are numbered. if all are collected, grant metroidnization
    for i=1, Init.iNumRequiredArtifacts do
        if RandomizerPowerup.GetItemAmount("ITEM_RANDO_ARTIFACT_"..i) == 0 then return end
    end

    RandomizerPowerup.SetItemAmount("ITEM_METROIDNIZATION", 1)
end

function RandomizerPowerup.ShowArtifactMessage()
    if GUI and GUI.ShowMessage then
        GUI.ShowMessage("#RANDO_ARTIFACTS_ALL", true, "")
    end
end

local tItemTunableHandlers = {
    ["ITEM_UPGRADE_FLASH_SHIFT_CHAIN"] = function(quantity)
        -- # of chains after first - vanilla is 2. We set it to the number of items, and the "default" config starts with 2 items.
        Scenario.SetTunableValue("CTunableAbilityGhostAura", "iChainDashMax", quantity)
    end,
    ["ITEM_UPGRADE_SPEED_BOOST_CHARGE"] = function(quantity)
        -- Amount of time in seconds for SB to charge - vanilla is 1.5 seconds. Each upgrade reduces by 0.25 seconds.
        -- Cannot be <= 0 or else all hell breaks loose.
        -- SB activation is very buggy <= 0.5, so we clamp it a tiny bit higher.
        local chargeTime = math.max(0.55, 1.5 - quantity * 0.25)
        Scenario.SetTunableValue("CTunableAbilitySpeedBooster", "fTimeToActivate", chargeTime)
    end
}

function RandomizerPowerup.ApplyTunableChanges()
    Game.AddSF(0, "RandomizerPowerup._ApplyTunableChanges", "")
end

function RandomizerPowerup._ApplyTunableChanges()
    for item, handler in pairs(tItemTunableHandlers) do
        local totalQuantity = RandomizerPowerup.GetItemAmount(item)

        Game.LogWarn(0, "Calling tunable handler for " .. item .. " = " .. totalQuantity)

        handler(totalQuantity)
    end
end

function RandomizerPowerup.UpdateWeapons()
    RandomizerPowerup.UpdateBeams()
    RandomizerPowerup.UpdateMissiles()
    
    -- Force weapon refresh by cycling input
    Game.AddSF(0.15, "RandomizerPowerup.RefreshWeaponDisplay", "")
end

function RandomizerPowerup.RefreshWeaponDisplay()
    -- Force the game to refresh the weapon display
    -- This is done by briefly disabling and re-enabling player input
    local oPlayer = Game.GetPlayer()
    if oPlayer == nil then
        return
    end
    
    Game.LogWarn(0, "Refreshing weapon display")
    
    -- Disable input briefly
    if oPlayer.INPUT then
        oPlayer.INPUT:IgnoreInput(true, false, "WeaponRefresh")
    end
    
    -- Re-enable after a tiny delay
    Game.AddSF(0.05, "RandomizerPowerup._ReenableInputAfterWeaponRefresh", "")
end

function RandomizerPowerup._ReenableInputAfterWeaponRefresh()
    local oPlayer = Game.GetPlayer()
    if oPlayer and oPlayer.INPUT then
        oPlayer.INPUT:IgnoreInput(false, false, "WeaponRefresh")
        Game.LogWarn(0, "Weapon display refreshed")
    end
end

function RandomizerPowerup.BeamsState()
    return {
        power = RandomizerPowerup.HasItem("ITEM_WEAPON_POWER_BEAM"),
        wide = RandomizerPowerup.HasItem("ITEM_WEAPON_WIDE_BEAM"),
        plasma = RandomizerPowerup.HasItem("ITEM_WEAPON_PLASMA_BEAM"),
        wave = RandomizerPowerup.HasItem("ITEM_WEAPON_WAVE_BEAM"),
    }
end

function RandomizerPowerup.MissileState()
    return {
        missile = RandomizerPowerup.HasItem("ITEM_WEAPON_MISSILE_LAUNCHER"),
        super = RandomizerPowerup.HasItem("ITEM_WEAPON_SUPER_MISSILE"),
        ice = RandomizerPowerup.HasItem("ITEM_WEAPON_ICE_MISSILE"),
    }
end

function RandomizerPowerup.UpdateBeams()
    RandomizerPowerup._UpdateBeams(RandomizerPowerup.BeamsState())
end

function RandomizerPowerup.UpdateMissiles()
    RandomizerPowerup._UpdateMissiles(RandomizerPowerup.MissileState())
end

function RandomizerPowerup._UpdateBeams(beams)
    if not beams.power then return nil end

    local offset = 60
    local plasma_damage = 50
    local wave_damage = 80
    if not beams.wide then
        offset = 0
        plasma_damage = plasma_damage / 3
        wave_damage = wave_damage / 3
    end
    if not beams.plasma then
        wave_damage = wave_damage / 2
    end
    Scenario.SetTunableValue("CTunableWideBeam", "fPerpendicularOffsetSize", offset)
    Scenario.SetTunableValue("CTunablePlasmaBeam", "fDamageAmount", plasma_damage)
    Scenario.SetTunableValue("CTunableWaveBeam", "fDamageAmount", wave_damage)

    local weapon_id = nil
    if beams.wide and beams.plasma and beams.wave then
        weapon_id = "ITEM_WEAPON_WIDE_PLASMA_WAVE_BEAM"
    elseif beams.plasma and beams.wave then
        weapon_id = "ITEM_WEAPON_PLASMA_WAVE_BEAM"
    elseif beams.wide and beams.wave then
        weapon_id = "ITEM_WEAPON_WIDE_WAVE_BEAM"
    elseif beams.wide and beams.plasma then
        weapon_id = "ITEM_WEAPON_WIDE_PLASMA_BEAM"
    elseif beams.wave then
        weapon_id = "ITEM_WEAPON_SOLO_WAVE_BEAM"
    elseif beams.plasma then
        weapon_id = "ITEM_WEAPON_SOLO_PLASMA_BEAM"
    elseif beams.wide then
        weapon_id = "ITEM_WEAPON_SOLO_WIDE_BEAM"
    else
        weapon_id = "ITEM_WEAPON_POWER_BEAM"
    end
    
    -- Log which beam combination we're activating
    Game.LogWarn(0, "Beam state updated to: " .. weapon_id)
    Game.LogWarn(0, "  Wide: " .. tostring(beams.wide) .. ", Plasma: " .. tostring(beams.plasma) .. ", Wave: " .. tostring(beams.wave))
    
    return weapon_id
end

function RandomizerPowerup._UpdateMissiles(missiles)
    -- don't give any missiles without launcher
    if not missiles.missile then return nil end

    local ice_damage = 400
    if not missiles.super then
        ice_damage = ice_damage / 3
    end
    Scenario.SetTunableValue("CTunableIceMissile", "fDamageAmount", ice_damage)

    if missiles.super and missiles.ice then
        return "ITEM_WEAPON_SUPER_ICE_MISSILE"
    end
    if missiles.ice then
        return "ITEM_WEAPON_SOLO_ICE_MISSILE"
    end
    if missiles.super then
        return "ITEM_WEAPON_SOLO_SUPER_MISSILE"
    end

    return "ITEM_WEAPON_MISSILE_LAUNCHER"
end

-- Main PBs
RandomizerPowerBomb = {}
setmetatable(RandomizerPowerBomb, {__index = RandomizerPowerup})
function RandomizerPowerBomb.OnPickedUp(actor, progression)
    progression = progression or {{{ item_id = "ITEM_WEAPON_POWER_BOMB_MAX", quantity = 0 }}}
    RandomizerPowerup.OnPickedUp(actor, progression)
end

-- Flash Shift: Require Main OFF → first chain unlock also grants Ghost Aura.
-- Require Main ON → upgrades only stack chains (AP_FLASH_SHIFT_REQUIRES_MAIN).
AP_FLASH_SHIFT_REQUIRES_MAIN = AP_FLASH_SHIFT_REQUIRES_MAIN or false

local function ap_flash_shift_requires_main()
    if RL and RL.FlashShiftRequiresMain ~= nil then
        return RL.FlashShiftRequiresMain and true or false
    end
    return AP_FLASH_SHIFT_REQUIRES_MAIN and true or false
end

if not RandomizerPowerup._APFlashUpgradeHooked then
    RandomizerPowerup._APFlashUpgradeHooked = true
    local _APIncreaseItemAmount = RandomizerPowerup.IncreaseItemAmount
    function RandomizerPowerup.IncreaseItemAmount(item_id, quantity, capacity)
        if item_id == "ITEM_UPGRADE_FLASH_SHIFT_CHAIN" and quantity and quantity > 0 then
            if not RandomizerPowerup.HasItem("ITEM_GHOST_AURA") and not ap_flash_shift_requires_main() then
                RandomizerPowerup.SetItemAmount("ITEM_GHOST_AURA", 1)
                Game.LogWarn(0, "Flash Shift Upgrade unlocked Flash Shift (ITEM_GHOST_AURA)")
                quantity = 0
            end
        end
        return _APIncreaseItemAmount(item_id, quantity, capacity)
    end
end

-- Flash Shift
RandomizerFlashShift = {}
setmetatable(RandomizerFlashShift, {__index = RandomizerPowerup})
-- Flash Shift Upgrade (progressive stack) — not in stock ODR; required for AP remote grants.
RandomizerFlashShiftUpgrade = {}
setmetatable(RandomizerFlashShiftUpgrade, {__index = RandomizerPowerup})
function RandomizerFlashShiftUpgrade.OnPickedUp(actor, progression)
    progression = progression or {{{item_id = "ITEM_UPGRADE_FLASH_SHIFT_CHAIN", quantity = 1}}}
    local first = not RandomizerPowerup.HasItem("ITEM_GHOST_AURA")
    if first and not ap_flash_shift_requires_main() then
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

function RandomizerPowerup.ToggleInputsOnPickedUp(actor, progression, item, SFs)
    SFs = SFs or {}
    local has_item_already = RandomizerPowerup.HasItem(item)
    RandomizerPowerup.OnPickedUp(actor, progression)
    if not has_item_already then
        RandomizerPowerup.DisableInput()
        for _, SF in ipairs(SFs) do
            Game.AddSF(SF[1], SF[2], SF[3])
        end
    end
end

RandomizerPhantomCloak = {}
setmetatable(RandomizerPhantomCloak, {__index = RandomizerPowerup})
function RandomizerPhantomCloak.OnPickedUp(actor, progression)
    RandomizerPowerup.ToggleInputsOnPickedUp(
        actor, progression, "ITEM_OPTIC_CAMOUFLAGE", {
            {0.101, "RandomizerPhantomCloak.Deactivate", ""}
        }
    )
end

function RandomizerPhantomCloak.Deactivate()
    -- prevent the pickup from trying to kill you
    Game.GetPlayer().SPECIALENERGY:Fill()
end

RandomizerSpeedBooster = {}
setmetatable(RandomizerSpeedBooster, {__index = RandomizerPowerup})
function RandomizerSpeedBooster.OnPickedUp(actor, progression)
    RandomizerPowerup.ToggleInputsOnPickedUp(
        actor, progression, "ITEM_SPEED_BOOSTER"
    )
end

RandomizerStormMissile = {}
setmetatable(RandomizerStormMissile, {__index = RandomizerPowerup})
function RandomizerStormMissile.OnPickedUp(actor, progression)
    progression = progression or {{{item_id = "ITEM_MULTILOCKON", quantity = 1}}}
    if RandomizerPowerup.HasItem("ITEM_WEAPON_MISSILE_LAUNCHER") then
        table.insert(progression[1], 1, {item_id = "ITEM_WEAPON_STORM_MISSILE", quantity = 1})
    end

    RandomizerPowerup.ToggleInputsOnPickedUp(
        actor, progression, "ITEM_MULTILOCKON"
    )
end

RandomizerEnergyPart = {}
setmetatable(RandomizerEnergyPart, {__index = RandomizerPowerup})
function RandomizerEnergyPart.OnPickedUp(actor, progression)
    Game.LogWarn(0, "RandomizerEnergyPart " .. type(progression))
    if not Init.bImmediateEnergyParts and actor then
        name = actor.sName
        RandomizerPowerup.MarkLocationCollected(string.format("%s_%s", Scenario.CurrentScenarioID, name))
    else
        progression = progression or {{{ item_id = "ITEM_LIFE_SHARDS", quantity = 1 }}}
        RandomizerPowerup.OnPickedUp(actor, progression)
    end
end

local function pick_up_beam(beam, actor, progression)
    progression = progression or {{{item_id = "ITEM_WEAPON_" .. beam:upper() .. "_BEAM", quantity = 1}}}
    local beams = RandomizerPowerup.BeamsState()
    if #progression == 1 then
        beams[beam] = true
        local to_grant = RandomizerPowerup._UpdateBeams(beams)
        if to_grant ~= nil then
            table.insert(progression[1], 1, {item_id = to_grant, quantity = 1})
        end
    else
        -- progressive beams
        progression = {
            {
                {item_id = "ITEM_WEAPON_SOLO_WIDE_BEAM", quantity = 1},
                {item_id = "ITEM_WEAPON_WIDE_BEAM", quantity = 1,}
            },
            {
                {item_id = "ITEM_WEAPON_WIDE_PLASMA_BEAM", quantity = 1},
                {item_id = "ITEM_WEAPON_PLASMA_BEAM", quantity = 1},
            },
            {
                {item_id = "ITEM_WEAPON_WIDE_PLASMA_WAVE_BEAM", quantity = 1},
                {item_id = "ITEM_WEAPON_WAVE_BEAM", quantity = 1},
            }
        }
        Game.AddSF(0.1, "RandomizerPowerup.UpdateBeams", "")
    end

    return RandomizerPowerup.OnPickedUp(actor, progression)
end

RandomizerPowerBeam = {}
setmetatable(RandomizerPowerBeam, {__index = RandomizerPowerup})
function RandomizerPowerBeam.OnPickedUp(actor, progression)
    return pick_up_beam("power", actor, progression)
end

RandomizerWideBeam = {}
setmetatable(RandomizerWideBeam, {__index = RandomizerPowerup})
function RandomizerWideBeam.OnPickedUp(actor, progression)
    return pick_up_beam("wide", actor, progression)
end

RandomizerPlasmaBeam = {}
setmetatable(RandomizerPlasmaBeam, {__index = RandomizerPowerup})
function RandomizerPlasmaBeam.OnPickedUp(actor, progression)
    return pick_up_beam("plasma", actor, progression)
end

RandomizerWaveBeam = {}
setmetatable(RandomizerWaveBeam, {__index = RandomizerPowerup})
function RandomizerWaveBeam.OnPickedUp(actor, progression)
    return pick_up_beam("wave", actor, progression)
end

local function pick_up_missile(id, item, actor, progression)
    progression = progression or {{{item_id = item, quantity = 1}}}
    local missiles = RandomizerPowerup.MissileState()
    if #progression == 1 then
        missiles[id] = true
        local to_grant = RandomizerPowerup._UpdateMissiles(missiles)
        if to_grant ~= nil then
            table.insert(progression[1], 1, {item_id = to_grant, quantity = 1})
        end
    else
        -- progressive missiles
        progression = {
            {
                {item_id = "ITEM_WEAPON_SOLO_SUPER_MISSILE", quantity = 1},
                {item_id = "ITEM_WEAPON_SUPER_MISSILE", quantity = 1,}
            },
            {
                {item_id = "ITEM_WEAPON_SUPER_ICE_MISSILE", quantity = 1},
                {item_id = "ITEM_WEAPON_ICE_MISSILE", quantity = 1},
            },
        }
        Game.AddSF(0.1, "RandomizerPowerup.UpdateMissiles", "")
    end

    return RandomizerPowerup.OnPickedUp(actor, progression)
end

RandomizerMissileLauncher = {}
setmetatable(RandomizerMissileLauncher, {__index = RandomizerPowerup})
function RandomizerMissileLauncher.OnPickedUp(actor, progression)
    return pick_up_missile("missile", "ITEM_WEAPON_MISSILE_LAUNCHER", actor, progression)
end

RandomizerSuperMissile = {}
setmetatable(RandomizerSuperMissile, {__index = RandomizerPowerup})
function RandomizerSuperMissile.OnPickedUp(actor, progression)
    return pick_up_missile("super", "ITEM_WEAPON_SUPER_MISSILE", actor, progression)
end

RandomizerIceMissile = {}
setmetatable(RandomizerIceMissile, {__index = RandomizerPowerup})
function RandomizerIceMissile.OnPickedUp(actor, progression)
    return pick_up_missile("ice", "ITEM_WEAPON_ICE_MISSILE", actor, progression)
end

-- DeathLink detection is installed by the AP client bootstrap (RL.InstallDeathHook /
-- RL.ScheduleDeathCheck). Do not use anonymous Game.AddSF callbacks here — exlaunch
-- only reliably schedules named global functions like "RL.ScheduleDeathCheck".
