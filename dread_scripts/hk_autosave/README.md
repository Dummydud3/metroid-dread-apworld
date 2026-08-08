# HK Autosave (shipped with every Dread direct patch)

Companion to `AP_DREAD_HK_AUTOSAVE_HANDOFF.md` (md modding).

`dread_direct_patch.finalize_mod()` always:

1. Registers these scripts in TOC + `system.pkg` as `system/scripts/<name>.lc`
2. Patches ODR `system/scripts/scenario.lc` to `DoFile` them and call `HkAutosave.Install()`

| File | Role |
|---|---|
| `progress_keeper.lua` | ProgressStore + RespawnAnchor + death/load reinject |
| `actor_consistency.lua` | Hide collected pickups / refresh shields after reinject |
| `scenario_hooks_hk_autosave.lua` | Wire InitScenario / OnLoadScenarioFinished / save stations |
| `progress_sections.json` | Schema reference (not loaded by the game) |

AP remote grants call `HkAutosave.OnRemoteItemGranted()` from `RL.ConfirmPickup` in `dread_client_bridge.py`.
