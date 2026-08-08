# Metroid Dread for Archipelago

## Install the world

1. Get `metroid_dread.apworld`.
2. Copy it into Archipelago’s **`custom_worlds`** folder.
3. Restart Archipelago (Launcher / Generate).

The client Hub lives inside this world package (and inside the `.apworld`).

## Generate / play

1. Add a YAML with `game: Metroid Dread` (or use the Archipelago host/YAML UI).
2. Generate as usual and host the multiworld.
3. Open the **Metroid Dread Client** (below), connect, patch, and play.

## Launch the client

Any of these:

1. **Archipelago Launcher** → **Metroid Dread Client**
2. Open an **`archipelago://`** room link → pick **Metroid Dread Client** when asked
3. **Direct Hub** (dev / extracted tree): run `dread-client-app/Launch_Dread_Client.bat`

First launch may install Electron deps via npm if they are missing (needs Node.js).

If the room has a password, the URI/client may prompt you for it.
