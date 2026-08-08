# Dread Scripts for Archipelago

This directory contains Lua scripts from Randovania's `open-dread-rando` project that are needed for proper item granting in Archipelago.

## Files

### randomizer_powerup.lua
- **Source**: https://github.com/randovania/open-dread-rando/blob/main/src/open_dread_rando/files/randomizer_powerup.lua
- **Purpose**: Provides the `RandomizerPowerup.OnPickedUp()` function and related item granting logic
- **Modifications**: 
  - Added stub functions for `Scenario.UpdateHudDnaCount()` and `Game.UpdateHudDnaCount()` to prevent crashes (Archipelago doesn't use DNA counter)
  - Made calls to `Scenario.UpdateProgressiveItemModels()` and `Scenario.UpdateBlastShields()` conditional
  - Added safety checks for missing `Init`, `GUI`, and other Randovania-specific objects

### gen_map_icon_actors.py / rebuild_map_icon_keys.py
- **Purpose**: keep `MAP_ICON_ItemCustom{n}` numbering in sync with open-dread-rando.
- `gen_map_icon_actors.py <extracted_romfs>` regenerates `dread_map_icon_actors.json`,
  the per-scenario list of vanilla minimap `items` actors. ODR only assigns an
  `ItemCustom{n}` to a pickup whose map actor is in that list, so pickups like
  `ItemSphere_ChargeBeam` consume no number. Only needs re-running if Nintendo ships
  a map-data change or ODR changes `patch_minimap_icon`. Requires ODR's interpreter.
- `rebuild_map_icon_keys.py [mod_root]` repairs an already-installed mod's
  `map_icon_keys.json` from its `patcher.json`, without re-patching. Use it when a
  seed was patched with a pre-v3 sidecar (map labels showing another check's
  in/out-of-logic state or item name).

## Usage

These scripts should be included in the patcher output (`patcher.json`) under the `game_patches` section, so they get copied to:
```
romfs/actors/items/randomizer_powerup/scripts/randomizer_powerup.lua
```

This allows the Archipelago client to use `RandomizerPowerup.OnPickedUp()` for proper item granting with animations and visual feedback, rather than just setting Blackboard values.

## Integration with ap_to_patcher.py

The `ap_to_patcher.py` script should be modified to:
1. Read this `randomizer_powerup.lua` file
2. Include it in the generated `patcher.json` with the correct path
3. Ensure it's packaged with every Archipelago seed export

## License

These files are from the Randovania project, which is licensed under GPL-3.0.
