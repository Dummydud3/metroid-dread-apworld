"""
Launch the Metroid Dread Client Hub (Electron) from Archipelago Launcher.

Cross-platform:
  - Ensures npm packages are installed when missing
  - Detects / repairs the common incomplete Electron binary install
    ("please delete node_modules/electron and try installing again")
  - Falls back to the Python MetroidDreadClient when Hub cannot start
    (no Node/npm, repeated Electron failure, missing Hub tree)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import urllib.parse
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


def candidate_ap_roots(extra: Optional[Iterable[Path]] = None) -> list[Path]:
    """Likely Archipelago / DreadClient package roots containing dread-client-app."""
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

    add(Path.cwd())
    add(Path(__file__).resolve().parents[2])  # .../worlds/metroid_dread -> repo root
    add(Path(__file__).resolve().parents[1])  # worlds/ (apworld layout)

    try:
        from Utils import local_path
        add(Path(local_path()))
    except Exception:
        pass

    # Portable dist next to this tree, or common build outputs.
    here = Path(__file__).resolve()
    for parent in here.parents:
        add(parent / "build" / "dread_dist" / "DreadClient_fresh")
        add(parent / "build" / "dread_dist" / "DreadClient")
        add(parent)

    return roots


def find_hub_dir(extra_roots: Optional[Iterable[Path]] = None) -> Optional[Path]:
    """Locate dread-client-app with package.json + main.js."""
    for root in candidate_ap_roots(extra_roots):
        hub = root / HUB_DIR_NAME
        if (hub / "package.json").is_file() and (hub / "main.js").is_file():
            return hub
        # apworld may ship hub beside the world package
        hub = root / "metroid_dread" / HUB_DIR_NAME
        if (hub / "package.json").is_file() and (hub / "main.js").is_file():
            return hub
    return None


def find_ap_root_for_hub(hub_dir: Path) -> Path:
    """Parent of dread-client-app is the package / Archipelago root."""
    return Path(hub_dir).resolve().parent


def parse_launcher_connect_args(args: Sequence[str]) -> dict:
    """
    Extract connect info from Archipelago Launcher passthrough args.

    Supports:
      archipelago://slot:pass@host:port?game=Metroid%20Dread
      --connect host:port --name slot --password pass --dread-ip ip
    """
    info: dict = {
        "server": None,
        "slot": None,
        "password": None,
        "dread_ip": None,
        "url": None,
        "raw": list(args),
    }
    argv = list(args)
    i = 0
    while i < len(argv):
        token = argv[i]
        if isinstance(token, str) and token.startswith("archipelago://"):
            info["url"] = token
            parsed = urllib.parse.urlparse(token)
            if parsed.netloc:
                # urlparse puts user:pass@host:port in netloc; hostname/port helpers vary
                host = parsed.hostname or ""
                port = parsed.port
                if host:
                    info["server"] = f"{host}:{port}" if port else host
                if parsed.username:
                    info["slot"] = urllib.parse.unquote(parsed.username)
                if parsed.password is not None:
                    info["password"] = urllib.parse.unquote(parsed.password)
            i += 1
            continue
        if token in ("--connect", "--name", "--password", "--dread-ip") and i + 1 < len(argv):
            key = {
                "--connect": "server",
                "--name": "slot",
                "--password": "password",
                "--dread-ip": "dread_ip",
            }[token]
            info[key] = argv[i + 1]
            i += 2
            continue
        i += 1
    return info


def apply_connect_prefills(ap_root: Path, connect: Mapping) -> Path:
    """Merge launcher connect fields into dread_client_ui_config.json for Hub UI."""
    cfg_path = Path(ap_root) / CONFIG_NAME
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
    if connect.get("password") is not None and connect.get("password") != "":
        cfg["password"] = str(connect["password"])
        changed = True
    if connect.get("dread_ip"):
        cfg["dread_ip"] = str(connect["dread_ip"])
        changed = True
    if changed:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg_path


def hub_env_from_connect(connect: Mapping, base: Optional[Mapping[str, str]] = None) -> dict:
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


def launch_python_client(args: Sequence[str]) -> None:
    """Fallback: run MetroidDreadClient in-process (used inside launcher subprocess)."""
    import asyncio

    # Allow ModuleUpdate to fetch Python deps when missing (non-frozen source installs).
    os.environ.pop("SKIP_REQUIREMENTS_UPDATE", None)
    try:
        import ModuleUpdate
        ModuleUpdate.update(yes=True)
    except Exception as exc:
        logger.warning("ModuleUpdate skipped/failed: %s", exc)

    from MetroidDreadClient import main, get_base_parser
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
    parsed = handle_url_arg(parsed, parser=parser)
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
        ap_root = find_ap_root_for_hub(hub)
        try:
            apply_connect_prefills(ap_root, connect)
            env = hub_env_from_connect(connect)
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
