
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import urllib.parse
import zipfile
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple

logger = logging.getLogger("MetroidDread.HubLauncher")

ELECTRON_REINSTALL_MARKERS = (
    "Electron failed to install correctly",
    "please delete node_modules/electron",
    "try installing again",
)

HUB_DIR_NAME = "dread-client-app"
CONFIG_NAME = "dread_client_ui_config.json"
CLIENT_SCRIPT_NAME = "MetroidDreadClient.py"
# When the world is loaded from a .apworld zip, Hub assets are not real files.
# Extract under custom_worlds so npm/Electron can run from a writable tree.
# Leading underscore: Archipelago skips "_*" entries under custom_worlds as worlds.
RUNTIME_WORLD_DIRNAME = "_metroid_dread_runtime"
APWORLD_STAMP_NAME = ".apworld_hub_source"
# Bump when extract layout changes so stale runtime trees are refreshed.
APWORLD_EXTRACT_LAYOUT = "world-pkg-v11"
WORLD_ZIP_PREFIX = "metroid_dread/"
HUB_ZIP_PREFIX = "metroid_dread/dread-client-app/"
# Paths inside the apworld that must never be extracted (bloat / not usable from zip).
_EXTRACT_SKIP_PREFIXES = (
    "metroid_dread/dread-client-app/node_modules/",
    "metroid_dread/node_modules/",
    "metroid_dread/.git/",
    "metroid_dread/dread-client-app/.git/",
)
_EXTRACT_SKIP_PARTS = ("/__pycache__/", "/.pytest_cache/", "/.mypy_cache/")


def electron_relative_binary(platform: Optional[str] = None) -> str:
    """Relative path of the Electron binary inside node_modules/electron/dist."""
    plat = platform or sys.platform
    if plat == "darwin":
        return "Electron.app/Contents/MacOS/Electron"
    if plat in ("win32", "cygwin", "msys"):
        return "electron.exe"
    return "electron"


def is_electron_reinstall_error(text: str) -> bool:
    """True if stderr/stdout matches Electron's incomplete-install message."""
    if not text:
        return False
    lowered = text.lower()
    return all(marker.lower() in lowered for marker in (
        "electron failed to install correctly",
        "node_modules/electron",
    )) or (
        "please delete node_modules/electron" in lowered
        and "installing again" in lowered
    )


def electron_package_dir(hub_dir: Path) -> Path:
    return Path(hub_dir) / "node_modules" / "electron"


def electron_is_healthy(hub_dir: Path, platform: Optional[str] = None) -> bool:
    """
    Return True when the Electron npm package has a usable platform binary.

    Mirrors electron/index.js: path.txt must exist and point at a real file under dist/.
    """
    pkg = electron_package_dir(hub_dir)
    path_txt = pkg / "path.txt"
    if not path_txt.is_file():
        return False
    try:
        rel = path_txt.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not rel:
        return False
    binary = pkg / "dist" / rel
    if binary.is_file():
        return True
    # Some installs omit path.txt content sync; accept expected platform binary.
    expected = pkg / "dist" / electron_relative_binary(platform)
    return expected.is_file()


def hub_deps_installed(hub_dir: Path) -> bool:
    """True when node_modules looks present enough to attempt a start."""
    hub = Path(hub_dir)
    return (hub / "node_modules").is_dir() and (hub / "package.json").is_file()


def find_npm() -> Optional[str]:
    """Locate npm (npm.cmd / npm.exe on Windows)."""
    for name in ("npm", "npm.cmd", "npm.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def find_node() -> Optional[str]:
    for name in ("node", "node.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def world_package_dir() -> Path:
    """Directory of this world package (canonical Hub + client home)."""
    return Path(__file__).resolve().parent


def find_containing_apworld(start: Optional[Path] = None) -> Optional[Path]:
    here = Path(start) if start is not None else Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if candidate.suffix.lower() == ".apworld" and candidate.is_file():
            return candidate
    # Walk string form in case resolve() collapsed oddly
    parts = list(here.parts)
    for i, part in enumerate(parts):
        if part.lower().endswith(".apworld"):
            zipped = Path(*parts[: i + 1])
            if zipped.is_file():
                return zipped
    return None


def runtime_world_dir() -> Path:
    """Writable folder for Hub extracted from a .apworld."""
    try:
        from Utils import user_path

        return Path(user_path("custom_worlds", RUNTIME_WORLD_DIRNAME))
    except Exception:
        pass
    try:
        from Utils import local_path

        return Path(local_path()) / "custom_worlds" / RUNTIME_WORLD_DIRNAME
    except Exception:
        return Path.cwd() / "custom_worlds" / RUNTIME_WORLD_DIRNAME


def _apworld_stamp(apworld: Path) -> str:
    st = apworld.stat()
    return f"{apworld.resolve()}|{st.st_mtime_ns}|{st.st_size}|{APWORLD_EXTRACT_LAYOUT}"


def _should_skip_apworld_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if any(normalized.startswith(prefix) for prefix in _EXTRACT_SKIP_PREFIXES):
        return True
    if any(part in normalized for part in _EXTRACT_SKIP_PARTS):
        return True
    return False


def runtime_tree_ready(dest_world: Path) -> bool:
    """True when extracted runtime has Hub + MetroidDreadClient.py (Hub's WORLD_DIR layout)."""
    dest_hub = dest_world / HUB_DIR_NAME
    return (
        (dest_hub / "package.json").is_file()
        and (dest_hub / "main.js").is_file()
        and (dest_hub / "room_info_gate.js").is_file()
        and (dest_world / CLIENT_SCRIPT_NAME).is_file()
    )


def _extract_apworld_members(
    apworld: Path,
    dest_world: Path,
    *,
    include_hub: bool,
    skip_existing_configs: bool = True,
) -> int:
    """Extract metroid_dread/* members into dest_world. Returns file count."""
    preserved = set()
    if skip_existing_configs:
        for cfg_name in (CONFIG_NAME, "dread_direct_patch_config.json"):
            if (dest_world / cfg_name).is_file():
                preserved.add(cfg_name)

    world_prefix = WORLD_ZIP_PREFIX
    hub_rel_prefix = f"{HUB_DIR_NAME}/"
    extracted = 0
    with zipfile.ZipFile(apworld, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name.startswith(world_prefix) or name.endswith("/"):
                continue
            if _should_skip_apworld_member(name):
                continue
            rel = name[len(world_prefix) :]
            if not rel:
                continue
            if not include_hub and rel.startswith(hub_rel_prefix):
                continue
            if rel in preserved:
                continue
            target = dest_world / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            extracted += 1
    return extracted


def materialize_hub_from_apworld(apworld: Path, dest_world: Path) -> Path:
    """
    Extract the metroid_dread world package from the apworld into dest_world.

    Layout matches source worlds/metroid_dread/:
      dest_world/MetroidDreadClient.py
      dest_world/dread_direct_patch.py
      dest_world/dread-client-app/{package.json,main.js,...}

    Preserves an existing dread-client-app/node_modules/ tree across refreshes.
    Never extracts node_modules from the zip.
    """
    dest_hub = dest_world / HUB_DIR_NAME
    stamp_path = dest_world / APWORLD_STAMP_NAME
    stamp = _apworld_stamp(apworld)
    if runtime_tree_ready(dest_world) and stamp_path.is_file():
        try:
            if stamp_path.read_text(encoding="utf-8").strip() == stamp:
                return dest_hub
        except OSError:
            pass

    dest_world.mkdir(parents=True, exist_ok=True)
    hub_ok = (dest_hub / "package.json").is_file() and (dest_hub / "main.js").is_file()
    client_ok = (dest_world / CLIENT_SCRIPT_NAME).is_file()

    # Fast path: Hub already on disk (possibly with locked node_modules) but the
    # older hub-only extract omitted MetroidDreadClient.py — fill world files only.
    if hub_ok and not client_ok:
        logger.info(
            "Completing runtime world files from %s → %s (Hub already present)",
            apworld,
            dest_world,
        )
        extracted = _extract_apworld_members(
            apworld, dest_world, include_hub=False, skip_existing_configs=True
        )
        if not (dest_world / CLIENT_SCRIPT_NAME).is_file():
            raise FileNotFoundError(
                f"apworld {apworld} is missing {CLIENT_SCRIPT_NAME} "
                f"(extracted {extracted} non-Hub files into {dest_world})."
            )
        stamp_path.write_text(stamp, encoding="utf-8")
        return dest_hub

    logger.info(
        "Extracting Metroid Dread world+Hub from %s → %s", apworld, dest_world
    )

    # Park node_modules so a refresh does not force a full reinstall.
    parked_modules: Optional[Path] = None
    modules = dest_hub / "node_modules"
    if modules.is_dir():
        parked_modules = dest_world / ".node_modules_preserve"
        if parked_modules.exists():
            shutil.rmtree(parked_modules, ignore_errors=True)
        try:
            modules.rename(parked_modules)
        except OSError as exc:
            logger.warning(
                "Could not park node_modules (%s); leaving Hub tree in place and "
                "extracting world scripts beside it",
                exc,
            )
            extracted = _extract_apworld_members(
                apworld, dest_world, include_hub=False, skip_existing_configs=True
            )
            if not runtime_tree_ready(dest_world):
                raise FileNotFoundError(
                    f"Could not refresh Hub (node_modules locked) and runtime is incomplete "
                    f"at {dest_world} (extracted {extracted} files). Close Dread Client Hub "
                    f"and retry."
                ) from exc
            stamp_path.write_text(stamp, encoding="utf-8")
            return dest_hub

    # Preserve user UI/patch configs across refresh (do not clobber with zip defaults).
    preserved_configs: dict[str, bytes] = {}
    for cfg_name in (CONFIG_NAME, "dread_direct_patch_config.json"):
        cfg_path = dest_world / cfg_name
        if cfg_path.is_file():
            try:
                preserved_configs[cfg_name] = cfg_path.read_bytes()
            except OSError:
                pass

    # Clear previous Hub extract (world scripts overwritten in place below).
    if dest_hub.exists():
        shutil.rmtree(dest_hub, ignore_errors=True)

    extracted = _extract_apworld_members(
        apworld, dest_world, include_hub=True, skip_existing_configs=True
    )

    for cfg_name, data in preserved_configs.items():
        try:
            (dest_world / cfg_name).write_bytes(data)
        except OSError as exc:
            logger.debug("Could not restore %s: %s", cfg_name, exc)

    if not runtime_tree_ready(dest_world):
        raise FileNotFoundError(
            f"apworld {apworld} is missing Hub and/or {CLIENT_SCRIPT_NAME} "
            f"(extracted {extracted} files into {dest_world}). "
            f"Rebuild/reinstall metroid_dread.apworld with client + dread-client-app sources."
        )

    if parked_modules and parked_modules.is_dir():
        if modules.exists():
            shutil.rmtree(modules, ignore_errors=True)
        modules.parent.mkdir(parents=True, exist_ok=True)
        parked_modules.rename(modules)

    stamp_path.write_text(stamp, encoding="utf-8")
    return dest_hub


def materialize_hub_if_needed() -> Optional[Path]:
    """
    When this module is loaded from a .apworld, extract Hub to a writable folder.

    No-op (returns None) for folder/source installs — callers should search
    colocated paths first.
    """
    world = world_package_dir()
    colocated = world / HUB_DIR_NAME
    if (colocated / "package.json").is_file() and (colocated / "main.js").is_file():
        return colocated

    apworld = find_containing_apworld()
    if apworld is None:
        return None
    try:
        return materialize_hub_from_apworld(apworld, runtime_world_dir())
    except Exception as exc:
        logger.warning("Failed to materialize Hub from apworld: %s", exc)
        return None


# Back-compat alias
def ensure_runtime_hub(extra_roots: Optional[Iterable[Path]] = None) -> Optional[Path]:
    return materialize_hub_if_needed()


def candidate_hub_parents(extra: Optional[Iterable[Path]] = None) -> list[Path]:
    """
    Folders that may directly contain dread-client-app/.

    Preferred: worlds/metroid_dread (colocated). Also accept legacy AP-root
    layout and portable DreadClient packages for one release cycle.
    """
    roots: list[Path] = []
    seen: set[Path] = set()

    def add(path: Optional[Path]) -> None:
        if path is None:
            return
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(resolved)

    if extra:
        for item in extra:
            add(Path(item))

    # Prefer extracted runtime Hub when the world lives inside a .apworld zip.
    add(runtime_world_dir())

    world = world_package_dir()
    add(world)  # canonical: worlds/metroid_dread/dread-client-app
    add(Path.cwd())
    add(world.parents[1])  # Archipelago / portable root (legacy hub location)
    add(world.parent)  # worlds/ (custom apworld extract)

    try:
        from Utils import local_path
        add(Path(local_path()))
        add(Path(local_path()) / "worlds" / "metroid_dread")
        add(Path(local_path()) / "custom_worlds" / RUNTIME_WORLD_DIRNAME)
    except Exception:
        pass

    try:
        from Utils import user_path
        add(Path(user_path("custom_worlds", RUNTIME_WORLD_DIRNAME)))
    except Exception:
        pass

    # Portable dist next to this tree, or common build outputs.
    here = Path(__file__).resolve()
    for parent in here.parents:
        add(parent / "build" / "dread_dist" / "DreadClient_fresh" / "worlds" / "metroid_dread")
        add(parent / "build" / "dread_dist" / "DreadClient_fresh")
        add(parent / "build" / "dread_dist" / "DreadClient" / "worlds" / "metroid_dread")
        add(parent / "build" / "dread_dist" / "DreadClient")
        add(parent)

    return roots


# Back-compat name used by tests / callers.
def candidate_ap_roots(extra: Optional[Iterable[Path]] = None) -> list[Path]:
    return candidate_hub_parents(extra)


def _hub_at(root: Path) -> Optional[Path]:
    """Return dread-client-app under root (or nested world layouts) when valid."""
    try:
        resolved_root = root.resolve()
    except OSError:
        resolved_root = root
    for hub in (
        resolved_root / HUB_DIR_NAME,
        resolved_root / "metroid_dread" / HUB_DIR_NAME,
        resolved_root / "worlds" / "metroid_dread" / HUB_DIR_NAME,
    ):
        if (hub / "package.json").is_file() and (hub / "main.js").is_file():
            return hub.resolve()
    return None


def find_hub_dir(extra_roots: Optional[Iterable[Path]] = None) -> Optional[Path]:
    """Locate dread-client-app with package.json + main.js (extract from apworld if needed)."""
    # Explicit overrides / unit tests win so a colocated source Hub cannot shadow them.
    if extra_roots:
        for root in extra_roots:
            found = _hub_at(Path(root))
            if found is not None:
                return found

    # Folder install → colocated Hub. .apworld install → extract/refresh runtime Hub.
    materialized = materialize_hub_if_needed()
    if materialized is not None:
        return materialized.resolve()

    for root in candidate_hub_parents():
        found = _hub_at(root)
        if found is not None:
            return found
    return None


def find_world_dir_for_hub(hub_dir: Path) -> Path:
    """Parent of dread-client-app is the world package (configs + client scripts)."""
    return Path(hub_dir).resolve().parent


def find_ap_root_for_hub(hub_dir: Path) -> Path:
    """
    Archipelago import root (contains CommonClient.py + Options.py).

    Hub itself lives under worlds/metroid_dread/; climb until a real filesystem root
    is found. Runtime extracts under custom_worlds/_metroid_dread_runtime fall back
    to the bundled ``ap_core/`` when the nearby install is frozen-only.
    """
    world = find_world_dir_for_hub(hub_dir)
    try:
        import dread_paths

        return dread_paths.resolve_ap_root(world)
    except Exception:
        pass

    for key in ("DREAD_HUB_AP_ROOT", "ARCHIPELAGO_ROOT"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            candidate = Path(raw).expanduser()
            if (candidate / "CommonClient.py").is_file():
                return candidate.resolve()

    for parent in [world, *world.parents]:
        if (parent / "CommonClient.py").is_file() and parent.name.lower() != "ap_core":
            return parent.resolve()

    # Infer from saved Hub config paths (games_folder / yaml often point at source).
    cfg_path = world / CONFIG_NAME
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cfg = {}
        for key in ("games_folder", "yaml_path", "base_rom_path"):
            raw = cfg.get(key)
            if not raw:
                continue
            cur = Path(str(raw)).expanduser()
            for parent in [cur, *cur.parents]:
                if (parent / "CommonClient.py").is_file() and parent.name.lower() != "ap_core":
                    return parent.resolve()

    bundled = world / "ap_core"
    if (bundled / "CommonClient.py").is_file():
        return bundled.resolve()

    try:
        from Utils import local_path

        local = Path(local_path())
        if (local / "CommonClient.py").is_file():
            return local.resolve()
    except Exception:
        pass

    # Fallback: conventional worlds/metroid_dread → repo root
    return world.parents[1] if len(world.parents) >= 2 else world


def normalize_uri_password(password: Optional[str]) -> Optional[str]:
    """
    Archipelago WebHost often encodes an empty password as the literal 'None'.

    Returns:
      None  — password not provided (leave existing config alone)
      ""    — explicitly no password (clear stored password)
      str   — real password
    """
    if password is None:
        return None
    text = urllib.parse.unquote(str(password)).strip()
    if text.lower() in ("", "none", "null"):
        return ""
    return text


def parse_archipelago_uri(url: str) -> dict:
    """Parse archipelago://slot:pass@host:port?game=...&room=... into connect fields."""
    info: dict = {
        "server": None,
        "slot": None,
        "password": None,
        "game": None,
        "room": None,
        "url": url,
        "auto_connect": True,
    }
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "archipelago":
        return info
    host = parsed.hostname or ""
    port = parsed.port
    if host:
        info["server"] = f"{host}:{port}" if port else host
    if parsed.username:
        info["slot"] = urllib.parse.unquote(parsed.username)
    # password may be "" or the literal "None" from WebHost
    if parsed.password is not None or (
        parsed.netloc and "@" in parsed.netloc and ":" in parsed.netloc.split("@", 1)[0]
    ):
        # urlparse yields password="None" for …:None@host
        info["password"] = normalize_uri_password(
            parsed.password if parsed.password is not None else ""
        )
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("game"):
        info["game"] = query["game"][0]
    if query.get("room"):
        info["room"] = query["room"][0]
    return info


def parse_launcher_connect_args(args: Sequence[str]) -> dict:
    """
    Extract connect info from Archipelago Launcher passthrough args.

    Supports:
      archipelago://slot:pass@host:port?game=Metroid%20Dread&room=...
      --connect host:port --name slot --password pass --dread-ip ip
    """
    info: dict = {
        "server": None,
        "slot": None,
        "password": None,
        "dread_ip": None,
        "game": None,
        "room": None,
        "url": None,
        "auto_connect": False,
        "raw": list(args),
    }
    argv = list(args)
    i = 0
    while i < len(argv):
        token = argv[i]
        if isinstance(token, str) and token.startswith("archipelago://"):
            parsed = parse_archipelago_uri(token)
            for key in ("server", "slot", "password", "game", "room", "url", "auto_connect"):
                if parsed.get(key) is not None:
                    info[key] = parsed[key]
            if parsed.get("auto_connect"):
                info["auto_connect"] = True
            i += 1
            continue
        if token in ("--connect", "--name", "--password", "--dread-ip", "--game", "--room") and i + 1 < len(argv):
            key = {
                "--connect": "server",
                "--name": "slot",
                "--password": "password",
                "--dread-ip": "dread_ip",
                "--game": "game",
                "--room": "room",
            }[token]
            value = argv[i + 1]
            if key == "password":
                value = normalize_uri_password(value)
            info[key] = value
            i += 2
            continue
        if token == "--auto-connect":
            info["auto_connect"] = True
            i += 1
            continue
        i += 1
    return info


def apply_connect_prefills(world_or_ap_root: Path, connect: Mapping) -> Path:
    """Merge launcher connect fields into dread_client_ui_config.json for Hub UI."""
    base = Path(world_or_ap_root)
    world = world_package_dir()
    try:
        base_res = base.resolve()
        world_res = world.resolve()
    except OSError:
        base_res, world_res = base, world

    # Write beside the Hub when the caller passed the world package, or when they
    # passed the Archipelago/portable root that contains this world.
    if (base / HUB_DIR_NAME / "package.json").is_file() or base_res == world_res:
        cfg_path = base / CONFIG_NAME
    elif (base / "CommonClient.py").is_file() and (world / HUB_DIR_NAME / "package.json").is_file():
        cfg_path = world / CONFIG_NAME
    else:
        cfg_path = base / CONFIG_NAME

    cfg: dict = {}
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cfg = {}
    changed = False
    if connect.get("server"):
        server = str(connect["server"]).replace("ws://", "").replace("wss://", "")
        if server.startswith("archipelago://"):
            # leave full URI handling to Hub normalize; strip scheme if bare
            pass
        cfg["server"] = server
        changed = True
    if connect.get("slot"):
        cfg["slot"] = str(connect["slot"])
        changed = True
    if connect.get("password") is not None:
        # "" means explicitly clear (URI password was None/empty)
        cfg["password"] = str(connect["password"])
        changed = True
    if connect.get("dread_ip"):
        cfg["dread_ip"] = str(connect["dread_ip"])
        changed = True
    if connect.get("room"):
        cfg["room_id"] = str(connect["room"])
        changed = True
    if connect.get("game"):
        cfg["game"] = str(connect["game"])
        changed = True
    if connect.get("url"):
        cfg["launcher_uri"] = str(connect["url"])
        changed = True
    if connect.get("auto_connect"):
        cfg["auto_connect_ap"] = True
        cfg["hub_stage"] = "connect"
        changed = True
    if changed:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg_path


def hub_env_from_connect(
    connect: Mapping,
    base: Optional[Mapping[str, str]] = None,
    *,
    hub_dir: Optional[Path] = None,
) -> dict:
    env = dict(base or os.environ)
    env.setdefault("SKIP_REQUIREMENTS_UPDATE", "1")
    if connect.get("server"):
        env["DREAD_HUB_CONNECT"] = str(connect["server"])
    if connect.get("slot"):
        env["DREAD_HUB_SLOT"] = str(connect["slot"])
    if connect.get("password") is not None:
        env["DREAD_HUB_PASSWORD"] = str(connect["password"])
    if connect.get("dread_ip"):
        env["DREAD_HUB_DREAD_IP"] = str(connect["dread_ip"])
    if connect.get("url"):
        env["DREAD_HUB_URL"] = str(connect["url"])
    if connect.get("room"):
        env["DREAD_HUB_ROOM"] = str(connect["room"])
    if connect.get("game"):
        env["DREAD_HUB_GAME"] = str(connect["game"])
    if connect.get("auto_connect"):
        env["DREAD_HUB_AUTO_CONNECT"] = "1"
    # Point Electron/system Python at a filesystem Archipelago import root.
    try:
        hub_path = Path(hub_dir) if hub_dir else find_hub_dir() or Path.cwd()
        world = find_world_dir_for_hub(hub_path)
        try:
            import dread_paths

            import_root, install_root = dread_paths.resolve_ap_roots(world)
        except Exception:
            import_root = find_ap_root_for_hub(hub_path)
            install_root = import_root
            try:
                import dread_paths as _dp

                frozen = _dp.resolve_frozen_install_root(world)
                if frozen is not None:
                    install_root = frozen
            except Exception:
                pass
        if import_root is not None and (Path(import_root) / "CommonClient.py").is_file():
            env["DREAD_HUB_AP_ROOT"] = str(Path(import_root).resolve())
        if install_root is not None:
            env["DREAD_HUB_INSTALL_ROOT"] = str(Path(install_root).resolve())
        env["DREAD_HUB_WORLD_DIR"] = str(world.resolve())
    except Exception as exc:
        logger.debug("Could not resolve DREAD_HUB_AP_ROOT: %s", exc)
    return env


def remove_electron_package(hub_dir: Path) -> None:
    """Delete corrupted node_modules/electron so npm can reinstall the binary."""
    pkg = electron_package_dir(hub_dir)
    if pkg.exists():
        logger.info("Removing incomplete Electron package at %s", pkg)
        shutil.rmtree(pkg, ignore_errors=True)


def run_npm(hub_dir: Path, npm_args: Sequence[str], *, env: Optional[Mapping[str, str]] = None) -> subprocess.CompletedProcess:
    npm = find_npm()
    if not npm:
        raise RuntimeError(
            "Node.js / npm not found. Install Node.js LTS from https://nodejs.org "
            "or use the Python Metroid Dread client."
        )
    merged = dict(env or os.environ)
    # Ensure electron postinstall downloads the platform binary.
    merged.pop("ELECTRON_SKIP_BINARY_DOWNLOAD", None)
    logger.info("Running: %s %s (cwd=%s)", npm, " ".join(npm_args), hub_dir)
    return subprocess.run(
        [npm, *npm_args],
        cwd=str(hub_dir),
        env=merged,
        capture_output=True,
        text=True,
        shell=False,
    )


def ensure_hub_packages(hub_dir: Path, *, force_reinstall_electron: bool = False) -> bool:
    """
    Download/install Hub npm deps when missing; repair Electron when unhealthy.

    Returns True if an install/repair was performed.
    """
    hub = Path(hub_dir)
    repaired = False

    if force_reinstall_electron or (hub_deps_installed(hub) and not electron_is_healthy(hub)):
        remove_electron_package(hub)
        repaired = True

    need_install = (
        force_reinstall_electron
        or not hub_deps_installed(hub)
        or not electron_is_healthy(hub)
        or not (hub / "node_modules" / "adm-zip").is_dir()
    )
    if not need_install:
        return False

    logger.info("Installing / repairing Dread Client Hub npm packages...")
    result = run_npm(hub, ["install"])
    if result.returncode != 0:
        combined = f"{result.stdout or ''}\n{result.stderr or ''}"
        raise RuntimeError(
            "npm install failed for Dread Client Hub.\n"
            f"{combined.strip() or f'exit {result.returncode}'}"
        )

    # Explicit electron rebuild if still missing after npm install (devDependency edge cases).
    if not electron_is_healthy(hub):
        logger.info("Electron binary still missing; installing electron package explicitly...")
        remove_electron_package(hub)
        result = run_npm(hub, ["install", "electron", "--save-dev"])
        if result.returncode != 0 or not electron_is_healthy(hub):
            combined = f"{result.stdout or ''}\n{result.stderr or ''}"
            raise RuntimeError(
                "Electron failed to install correctly after repair.\n"
                f"{combined.strip()}"
            )
        repaired = True

    return True or repaired


def _combined_output(proc: subprocess.CompletedProcess) -> str:
    return f"{proc.stdout or ''}\n{proc.stderr or ''}"


def probe_electron_load(hub_dir: Path, *, env: Optional[Mapping[str, str]] = None) -> Tuple[bool, str]:
    """
    Require('electron') the same way `npm start` does — catches missing path.txt
    without starting the full Hub window. No network.
    """
    node = find_node()
    if not node:
        return False, "node not found"
    merged = dict(env or os.environ)
    # Resolve the electron package entry (throws the reinstall Error when broken).
    script = (
        "try {"
        "  require('electron');"
        "  process.exit(0);"
        "} catch (e) {"
        "  console.error(String(e && e.message ? e.message : e));"
        "  process.exit(1);"
        "}"
    )
    proc = subprocess.run(
        [node, "-e", script],
        cwd=str(hub_dir),
        env=merged,
        capture_output=True,
        text=True,
    )
    output = _combined_output(proc)
    return proc.returncode == 0, output


def start_hub_process(
    hub_dir: Path,
    *,
    env: Optional[MutableMapping[str, str]] = None,
    wait: bool = True,
) -> int:
    """
    Start the Electron Hub via `npm start`.

    Does not capture stdout/stderr (GUI apps can fill pipes and deadlock).
    Preflight health/repair is handled by launch_hub_with_repair().
    """
    npm = find_npm()
    if not npm:
        raise RuntimeError("npm not found")

    merged = dict(env or os.environ)
    merged.setdefault("SKIP_REQUIREMENTS_UPDATE", "1")

    if not wait:
        subprocess.Popen(
            [npm, "start"],
            cwd=str(hub_dir),
            env=merged,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        return 0

    proc = subprocess.run(
        [npm, "start"],
        cwd=str(hub_dir),
        env=merged,
        shell=False,
    )
    return proc.returncode


def ensure_system_client_python_deps(world_dir: Optional[Path] = None) -> str:
    """
    Install Hub client packages (websockets, etc.) for the Hub-spawned Python.

    Archipelago Launcher / Text Client use a bundled interpreter that already
    has deps; Hub spawns host Python with SKIP_REQUIREMENTS_UPDATE=1, so those
    packages must be installed separately. On Linux, ensure_client_deps uses a
    local ``_metroid_dread_venv`` (never systemwide / ``pip install --user``).
    Raises RuntimeError with a clear user-facing message on failure.
    """
    world = Path(world_dir) if world_dir else world_package_dir()
    try:
        from ensure_client_deps import ensure_client_deps_or_raise
    except ImportError:
        # When loaded from a .apworld before extract, import from materialized world.
        import importlib.util

        script = world / "ensure_client_deps.py"
        if not script.is_file():
            runtime = runtime_world_dir() / "ensure_client_deps.py"
            script = runtime if runtime.is_file() else script
        if not script.is_file():
            raise RuntimeError(
                "ensure_client_deps.py missing from the Metroid Dread world package.\n"
                "Reinstall/update metroid_dread.apworld, then try again."
            )
        spec = importlib.util.spec_from_file_location("ensure_client_deps", script)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load {script}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ensure_client_deps_or_raise = mod.ensure_client_deps_or_raise

    msg = ensure_client_deps_or_raise(world=world)
    logger.info("%s", msg.splitlines()[0] if msg else "client deps ok")
    return msg


def launch_hub_with_repair(
    hub_dir: Path,
    *,
    env: Optional[MutableMapping[str, str]] = None,
    wait: bool = True,
) -> int:
    """
    Ensure packages, probe Electron, auto-repair once if needed, then start Hub.
    """
    ensure_hub_packages(hub_dir)

    ok, probe_out = probe_electron_load(hub_dir, env=env)
    if not ok or not electron_is_healthy(hub_dir):
        logger.warning(
            "Electron install looks broken (%s); deleting node_modules/electron and reinstalling...",
            (probe_out or "unhealthy binary").strip().splitlines()[:1],
        )
        ensure_hub_packages(hub_dir, force_reinstall_electron=True)
        ok, probe_out = probe_electron_load(hub_dir, env=env)
        if not ok or not electron_is_healthy(hub_dir):
            raise RuntimeError(
                "Electron still failed after automatic repair.\n"
                + (probe_out.strip() or "electron binary missing")
            )

    return start_hub_process(hub_dir, env=env, wait=wait)


def ensure_filesystem_world_dir() -> Path:
    """
    Return a real on-disk world package directory.

    When the launcher is loaded from a ``.apworld`` zip, Path(__file__) looks like
    ``…/metroid_dread.apworld/metroid_dread`` but is not a directory — reading
    ``Items.py`` then raises NotADirectoryError. Extract to
    ``custom_worlds/_metroid_dread_runtime`` first (same tree Hub uses).
    """
    world = world_package_dir()
    if (world / CLIENT_SCRIPT_NAME).is_file() and (world / "Items.py").is_file():
        return world

    apworld = find_containing_apworld()
    if apworld is None:
        return world

    dest = runtime_world_dir()
    try:
        materialize_hub_from_apworld(apworld, dest)
    except Exception as exc:
        logger.warning(
            "Failed to extract world from %s for Python client fallback: %s",
            apworld,
            exc,
        )
        return world
    if (dest / CLIENT_SCRIPT_NAME).is_file():
        logger.info("Using extracted apworld runtime for Python client: %s", dest)
        os.environ["DREAD_HUB_WORLD_DIR"] = str(dest.resolve())
        return dest
    return world


def _load_metroid_dread_client_module(world: Optional[Path] = None):
    """
    Load MetroidDreadClient from a real file path, or via zipimport / package import
    when the world lives inside a .apworld.
    """
    import importlib
    import importlib.util

    bases: list[Path] = []
    if world is not None:
        bases.append(world)
    runtime = runtime_world_dir()
    if runtime not in bases:
        bases.append(runtime)
    pkg_world = world_package_dir()
    if pkg_world not in bases:
        bases.append(pkg_world)

    for base in bases:
        client_path = base / CLIENT_SCRIPT_NAME
        if not client_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("metroid_dread_client_impl", client_path)
        if spec is None or spec.loader is None:
            continue
        mdc = importlib.util.module_from_spec(spec)
        # dataclasses + from __future__ import annotations looks up cls.__module__
        # in sys.modules; omit this and @dataclass raises AttributeError on None.
        sys.modules[spec.name] = mdc
        spec.loader.exec_module(mdc)
        return mdc

    apworld = find_containing_apworld()
    if apworld is not None:
        # zipimport can load the submodule without reading a bare filesystem path.
        try:
            return importlib.import_module("worlds.metroid_dread.MetroidDreadClient")
        except Exception as exc:
            logger.warning("zipimport of MetroidDreadClient failed (%s); trying zip read", exc)
            import types

            member = "metroid_dread/MetroidDreadClient.py"
            with zipfile.ZipFile(apworld, "r") as zf:
                source = zf.read(member)
            mod = types.ModuleType("metroid_dread_client_impl")
            mod.__file__ = str(apworld / member)
            sys.modules[mod.__name__] = mod
            exec(compile(source, mod.__file__, "exec"), mod.__dict__)
            return mod

    raise ImportError(
        f"Cannot load MetroidDreadClient (tried {[str(b) for b in bases]})"
    )


def launch_python_client(args: Sequence[str]) -> None:
    """Fallback: run MetroidDreadClient in-process (used inside launcher subprocess)."""
    import asyncio

    # Prefer a real extracted folder over zipimport fake paths (Items.py reads).
    world = ensure_filesystem_world_dir()
    # Prefer env / CommonClient climb — runtime parents[1] is often a frozen install
    # and must not put world Options.py ahead of Archipelago Options.
    using_ap_core = False
    try:
        import dread_paths

        # Point WORLD_DIR helpers at the extracted tree when we just materialized it.
        if world != world_package_dir():
            dread_paths.WORLD_DIR = world.resolve()
            dread_paths.ROOT = dread_paths.WORLD_DIR
        dread_paths.ensure_import_paths()
        ap_root = dread_paths.AP_ROOT
        using_ap_core = ap_root.name.lower() == "ap_core"
    except Exception:
        ap_root = find_ap_root_for_hub(world / HUB_DIR_NAME)
        using_ap_core = Path(ap_root).name.lower() == "ap_core"
        for path in (str(world), str(ap_root)):
            if path in sys.path:
                sys.path.remove(path)
            sys.path.insert(0, path)

    # Source installs may fetch deps; ap_core ships for frozen Hub and must not
    # trigger ModuleUpdate against the full AP requirements (kivy/kivymd git, etc.).
    # Still ensure the small client set (websockets, …) into system Python when
    # Hub would have used it — and into this interpreter for in-process fallback.
    if using_ap_core:
        os.environ.setdefault("SKIP_REQUIREMENTS_UPDATE", "1")
        try:
            ensure_system_client_python_deps(world)
        except RuntimeError as dep_exc:
            # In-process fallback under Launcher's Python may already have deps;
            # only hard-fail when this interpreter is also missing them.
            try:
                from ensure_client_deps import local_modules_present

                local_missing = local_modules_present()
            except Exception:
                local_missing = ["websockets"]
            if local_missing:
                raise RuntimeError(
                    f"{dep_exc}\n\n"
                    f"Also missing in this Python: {', '.join(local_missing)}"
                ) from dep_exc
            logger.warning(
                "System Python client deps unavailable (%s); continuing with "
                "in-process packages.",
                dep_exc,
            )
    else:
        os.environ.pop("SKIP_REQUIREMENTS_UPDATE", None)
        try:
            import ModuleUpdate
            ModuleUpdate.update(yes=True)
        except Exception as exc:
            logger.warning("ModuleUpdate skipped/failed: %s", exc)
        try:
            ensure_system_client_python_deps(world)
        except RuntimeError as dep_exc:
            logger.warning("ensure_client_deps: %s", dep_exc)

    # Prefer filesystem load from extracted runtime; zipimport only as last resort.
    mdc = _load_metroid_dread_client_module(world)
    main = mdc.main
    get_base_parser = mdc.get_base_parser

    from CommonClient import handle_url_arg

    parser = get_base_parser(description="Metroid Dread Client for Archipelago")
    parser.add_argument("--dread-ip", default="127.0.0.1",
                        help="IP address of Ryujinx running Dread")
    parser.add_argument("--name", default=None, help="Slot name to connect as")
    parser.add_argument("--electron", action="store_true")
    parser.add_argument("--auto-dread", action="store_true")
    parser.add_argument("--no-auto-dread", action="store_true")
    parser.add_argument("url", nargs="?", help="archipelago:// connection url")
    parsed = parser.parse_args(list(args))
    # Prefer our URI parser: host:port only (CommonClient leaves userinfo in netloc).
    connect = parse_launcher_connect_args(args)
    if connect.get("url"):
        parsed.url = connect["url"]
        if connect.get("server"):
            parsed.connect = connect["server"]
        if connect.get("slot"):
            parsed.name = connect["slot"]
        if connect.get("password") is not None:
            parsed.password = connect["password"] or None
    else:
        parsed = handle_url_arg(parsed, parser=parser)
    if connect.get("dread_ip"):
        parsed.dread_ip = connect["dread_ip"]
    asyncio.run(main(parsed))


def launch_hub_or_fallback(args: Sequence[str] = (), *, wait: bool = True) -> str:
    """
    Preferred entry: Hub when possible, else Python client.

    Returns which path was used: "hub" or "python".
    """
    connect = parse_launcher_connect_args(args)
    hub = find_hub_dir()
    npm = find_npm()
    node = find_node()

    if hub and npm and node:
        world_dir = find_world_dir_for_hub(hub)
        try:
            apply_connect_prefills(world_dir, connect)
            env = hub_env_from_connect(connect, hub_dir=hub)
            ap_root = env.get("DREAD_HUB_AP_ROOT")
            install_root = env.get("DREAD_HUB_INSTALL_ROOT")
            if ap_root:
                logger.info("Hub Archipelago import root (CommonClient): %s", ap_root)
                if install_root and install_root != ap_root:
                    logger.info("Hub Archipelago install root: %s", install_root)
            else:
                logger.warning(
                    "No filesystem CommonClient.py found for Hub — ensure "
                    "metroid_dread/ap_core is present, or set DREAD_HUB_AP_ROOT."
                )
            # Install websockets/etc. into system Python before Hub can spawn it.
            # Soft-fail: Hub Connect re-checks and surfaces pythonMissingError / pip text.
            try:
                ensure_system_client_python_deps(world_dir)
            except RuntimeError as dep_exc:
                logger.error(
                    "Could not ensure Hub client Python packages before launch:\n%s",
                    dep_exc,
                )
            logger.info("Launching Dread Client Hub from %s", hub)
            # After a successful start, do not fall back to Python just because
            # Electron returned a non-zero code on window close.
            launch_hub_with_repair(hub, env=env, wait=wait)
            return "hub"
        except Exception as exc:
            logger.warning("Hub launch failed (%s); falling back to Python client", exc)
    else:
        reasons = []
        if not hub:
            reasons.append("dread-client-app not found")
        if not node:
            reasons.append("node not found")
        if not npm:
            reasons.append("npm not found")
        logger.info("Using Python Metroid Dread client (%s)", ", ".join(reasons) or "fallback")

    launch_python_client(args)
    return "python"
