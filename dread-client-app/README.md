# Dread Client Hub

One app for Metroid Dread Archipelago: **YAML Editor** + **Client** (connect → patch → play).

## Install (recommended)

Double-click **`Install_Dread_Client_Hub.bat`** in the repo root (or in `dread-client-app/`).

The installer can:

- Install / update npm dependencies
- Create a **Desktop** shortcut
- Add the app to the **Start Menu** (`Programs → Dread Client Hub`)
- Optionally launch the hub when finished

Uninstall shortcuts anytime from **Start Menu → Dread Client Hub → Uninstall Dread Client Hub**, or:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File dread-client-app\Install_Dread_Client_Hub.ps1 -Uninstall
```

Silent install (no UI):

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File dread-client-app\Install_Dread_Client_Hub.ps1 -Silent
```

## Launch

After installing, use the Desktop / Start Menu shortcut (opens with no console window).

Or double-click either:

- `Launch_Dread_Client_UI.bat` (repo root), or
- `dread-client-app/Launch_Dread_Client.bat`

First run installs npm deps (Electron + adm-zip) if needed.

## Menu

Use **Menu** in the top-right:

| Section | Purpose |
|---------|---------|
| **YAML Editor** | Edit common Metroid Dread player options and save a YAML into `Players/` |
| **Client** | Connect → patch → play flow |

## Client flow

1. **Connect** — server address, optional password, slot name → **Connect**
2. On success the hub checks the slot is **Metroid Dread**, then **asks the Archipelago server** for your placements (`LocationScouts`) and builds seed data automatically — no local AP zip / spoiler import
3. **Patch** — set source path (`md rando` decompiled RomFS), Ryujinx mod output, hit **Patch!**
4. **Play** — status, chat, DeathLink, Map Tracker, and **Launch Ryujinx + Play**

Use **Re-download seed** on the patch screen (or `/download_patch` in the log) if the first download fails.

### Paths

- **Source path** — extracted/decompiled Dread RomFS (same as the old “md rando” folder)
- **Ryujinx output** — usually `%APPDATA%\Ryujinx\mods\contents\010093801237c000`
- **Ryujinx.exe** / **Dread ROM** — auto-detected when possible; browse if missing

### Patch progress

While patching you’ll see a progress bar, percent, and ETA. The log panel under the patcher is collapsed by default.

## Notes

- Close any Randovania Game Connection using port **6969** first.
- Use **Already patched — continue** to skip straight to the client screen.
