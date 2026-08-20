# Metroid Bread for Archipelago

## Install the world

1. Get `metroid_bread.apworld`.
2. Copy it into Archipelago’s **`custom_worlds`** folder.
3. Restart Archipelago (Launcher / Generate).

The client Hub lives inside this world package (and inside the `.apworld`).

**Updates:** Hub (startup check + **Check for updates** in the Log toolbar) and the Hub Setup Wizard can download a newer `metroid_bread.apworld` from [GitHub Releases](https://github.com/Dummydud3/metroid-dread-apworld/releases) when remote `world_version` is ahead of local. You are always prompted before download. Builds from *before* this feature still need one manual install of a release that includes the updater.

## Generate / play

1. Add a YAML with `game: Metroid Bread` (or use the Archipelago host/YAML UI).
2. Generate as usual and host the multiworld.
3. Open the **Metroid Bread Client** (below), connect, patch, and play.

RemoteLua TCP details (listen vs connect, passive retry): see [docs/remote_lua_connection.md](docs/remote_lua_connection.md).

## Launch the client

Any of these:

1. **Archipelago Launcher** → **Metroid Bread Client**
2. Open an **`archipelago://`** room link → pick **Metroid Bread Client** when asked
3. **Direct Hub** (dev / extracted tree): run `dread-client-app/Launch_Dread_Client.bat`

### Hub Setup Wizard

If Node/npm/Hub are missing or Hub launch fails, a **Setup Wizard** opens first (tkinter) instead of silently falling back to the Kivy client:

- Checklist for Node, npm, Hub app, Electron, and Client Python
- **Install Node 24** / **Install Python 3.12** — downloads portable toolchains into `custom_worlds/_metroid_bread_runtime/tools/`
- **Fix / refresh Electron** — runs the existing npm/Electron repair path
- **Check for updates** — optional GitHub Releases apworld update (prompt before download)
- **Launch Hub** when prerequisites are green
- Red **Just open Kivy version** (top-right) — escape hatch to the Python client

Healthy Hub installs skip the wizard. Managed Node must be major **18–24** (Node **≥25** is refused for Electron).

First Hub launch may still install Electron deps via npm when needed.

If the room has a password, the URI/client may prompt you for it.
