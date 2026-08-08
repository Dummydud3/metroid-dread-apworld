# `ap_core` — filesystem Archipelago import root for frozen installs

Official Archipelago Windows installs under `C:\ProgramData\Archipelago` are
**frozen**: `CommonClient` lives only as Python 3.13 `.pyc` inside
`lib/library.zip`. Hub launches the Metroid Dread client with **system Python**
(3.11–3.13), which cannot load those bytecodes.

This folder is a minimal loose-`.py` import surface (CommonClient, Utils,
NetUtils, Options, …) plus a stub `worlds/` package that exposes the Metroid
Dread datapackage. Path resolution prefers a real Archipelago source/portable
tree when present; otherwise it uses this `ap_core`.

Refresh from a matching Archipelago checkout:

```text
py -3.12 worlds/metroid_dread/tools/sync_ap_core.py
```

Do not point `Utils.local_path` here for user data — frozen install / ProgramData
remains the install root for `Players/`, `output/`, `host.yaml`, and logs.
