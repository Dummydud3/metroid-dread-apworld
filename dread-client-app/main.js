const { app, BrowserWindow, ipcMain, dialog, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const https = require("https");
const http = require("http");
const { spawn, spawnSync } = require("child_process");
const AdmZip = require("adm-zip");
const {
  normalizeUriPassword,
  parseConnectServerString,
  probeRoomInfo,
} = require("./room_info_gate");
const {
  formatPythonCmd,
  pythonMissingError,
  explainClientExit,
} = require("./client_exit");

// Hub lives at worlds/metroid_bread/dread-client-app — world package is parent.
const WORLD_DIR = path.resolve(__dirname, "..");
const AP_CORE_DIRNAME = "ap_core";

/** Strip UTF-8 BOM (`\uFEFF` / EF BB BF) so JSON.parse accepts Windows-saved files. */
function stripBom(text) {
  return String(text ?? "").replace(/^\uFEFF/, "");
}

function readJsonFile(filePath) {
  return JSON.parse(stripBom(fs.readFileSync(filePath, "utf8")));
}

/** UTF-8 without BOM (Node's default `utf8` write). */
function writeJsonFile(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf8");
}

function hasCommonClient(dir) {
  return Boolean(dir && fs.existsSync(path.join(dir, "CommonClient.py")));
}

function isFrozenApInstall(dir) {
  if (!dir || hasCommonClient(dir)) return false;
  if (!fs.existsSync(path.join(dir, "lib", "library.zip"))) return false;
  const markers = [
    "ArchipelagoLauncher.exe",
    "ArchipelagoGenerate.exe",
    "ArchipelagoServer.exe",
    "python313.dll",
    "python312.dll",
    "python311.dll",
    "manifest.json",
  ];
  return markers.some((name) => fs.existsSync(path.join(dir, name)));
}

function climbForCommonClient(startDir, { allowApCore = false } = {}) {
  let cur = path.resolve(startDir || "");
  for (let i = 0; i < 8; i++) {
    if (hasCommonClient(cur)) {
      const base = path.basename(cur).toLowerCase();
      if (allowApCore || base !== AP_CORE_DIRNAME) {
        return cur;
      }
    }
    const parent = path.dirname(cur);
    if (!parent || parent === cur) break;
    cur = parent;
  }
  return "";
}

function climbForFrozenInstall(startDir) {
  let cur = path.resolve(startDir || "");
  for (let i = 0; i < 8; i++) {
    if (isFrozenApInstall(cur)) return cur;
    const parent = path.dirname(cur);
    if (!parent || parent === cur) break;
    cur = parent;
  }
  return "";
}

function inferApRootFromWorldConfig(worldDir) {
  // Runtime extracts under ProgramData have no CommonClient nearby; saved Hub
  // paths (games_folder / yaml) often still point at a source checkout.
  try {
    const cfgPath = path.join(worldDir, "dread_client_ui_config.json");
    if (!fs.existsSync(cfgPath)) return "";
    const cfg = readJsonFile(cfgPath);
    for (const key of ["games_folder", "yaml_path", "base_rom_path"]) {
      const raw = cfg && cfg[key];
      if (!raw) continue;
      const found = climbForCommonClient(path.resolve(String(raw)));
      if (found) return found;
    }
  } catch (_) {
    /* ignore */
  }
  return "";
}

function bundledApCore(worldDir) {
  const core = path.join(worldDir, AP_CORE_DIRNAME);
  return hasCommonClient(core) ? core : "";
}

/**
 * Prefer install root from Hub env (source or frozen), then climb/infer/frozen.
 */
function resolveInstallCandidate(worldDir, { prefer = "" } = {}) {
  const envInstall = (process.env.DREAD_HUB_INSTALL_ROOT || "").trim();
  if (envInstall && fs.existsSync(envInstall)) {
    return path.resolve(envInstall);
  }
  if (prefer && fs.existsSync(prefer)) {
    return path.resolve(prefer);
  }
  const climbed = climbForCommonClient(worldDir);
  if (climbed) return climbed;
  const inferred = inferApRootFromWorldConfig(worldDir);
  if (inferred) return inferred;
  const frozen = climbForFrozenInstall(worldDir);
  if (frozen) return frozen;
  return "";
}

/**
 * Resolve import root (CommonClient.py) + install root (Players/output/host.yaml).
 *
 * Prefer world/ap_core for imports when present — MetroidBreadClient is built
 * against that API. A nearby full AP tree (e.g. D:\\Archipelago) is install-only
 * so an older CommonClient cannot break Connect (missing handle_url_arg, etc.).
 */
function resolveApRoots(worldDir) {
  const core = bundledApCore(worldDir);
  const envRoot = (
    process.env.DREAD_HUB_AP_ROOT ||
    process.env.ARCHIPELAGO_ROOT ||
    ""
  ).trim();

  if (envRoot && hasCommonClient(envRoot)) {
    const resolved = path.resolve(envRoot);
    if (path.basename(resolved).toLowerCase() === AP_CORE_DIRNAME) {
      const install = resolveInstallCandidate(worldDir) || resolved;
      return { importRoot: resolved, installRoot: install };
    }
    // Explicit non-ap_core AP root: still prefer bundled ap_core for imports
    // when Hub ships it (matches client); keep env root as install.
    if (core) {
      return { importRoot: core, installRoot: resolved };
    }
    return { importRoot: resolved, installRoot: resolved };
  }

  const install = resolveInstallCandidate(worldDir);
  if (core) {
    return {
      importRoot: core,
      installRoot: install || core,
    };
  }
  if (install && hasCommonClient(install)) {
    return { importRoot: install, installRoot: install };
  }

  // Conventional checkout: worlds/metroid_bread → repo root (may lack CommonClient
  // when Hub runs from custom_worlds/_metroid_bread_runtime next to a frozen install).
  const legacy = path.resolve(worldDir, "..", "..");
  const frozen = climbForFrozenInstall(worldDir);
  return {
    importRoot: legacy,
    installRoot: install || (frozen ? path.resolve(frozen) : legacy),
  };
}

const { importRoot: AP_ROOT, installRoot: INSTALL_ROOT } = resolveApRoots(WORLD_DIR);
const CONFIG_PATH = path.join(WORLD_DIR, "dread_client_ui_config.json");
const PATCH_CONFIG_PATH = path.join(WORLD_DIR, "dread_direct_patch_config.json");
const CLIENT_SCRIPT = path.join(WORLD_DIR, "MetroidBreadClient.py");
const PATCHER_SCRIPT = path.join(WORLD_DIR, "dread_direct_patch.py");
const CATALOG_PATH = path.join(__dirname, "tracker", "catalog.json");
const DEFAULT_OUTPUT_SCAN = path.join(INSTALL_ROOT, "output");
const EXTRACT_ROOT = path.join(INSTALL_ROOT, "output", "_patcher_extract");
const PLAYERS_DIR = path.join(INSTALL_ROOT, "Players");
const UI_PREFIX = "@@APUI@@";
const UI_LOG_PREFIX = "@@APLOG@@";
const UI_LOG_RE = /^@@APLOG@@(debug|normal)@@(.*)$/i;
const DREAD_TITLE_ID = "010093801237c000";

const DEFAULT_CONFIG = {
  server: "127.0.0.1:38281",
  slot: "DreadPlayer",
  password: "",
  dread_ip: "127.0.0.1",
  auto_connect_dread: true,
  base_rom_path: String.raw`C:\Users\dummy\Downloads\md rando`,
  output_path: path.join(
    process.env.APPDATA || "",
    "Ryujinx",
    "mods",
    "contents",
    DREAD_TITLE_ID
  ),
  ryujinx_output_path: path.join(
    process.env.APPDATA || "",
    "Ryujinx",
    "mods",
    "contents",
    DREAD_TITLE_ID
  ),
  atmosphere_output_path: "",
  mod_compatibility: "ryujinx",
  games_folder: DEFAULT_OUTPUT_SCAN,
  ryujinx_path: "",
  dread_rom_path: "",
  freesink: true,
  clean_output: false,
  yaml_path: path.join(PLAYERS_DIR, "dread_player.yaml"),
  hub_stage: "connect",
  // Hub Log panel: off = AP/normal only; on = full debug (@@APLOG@@debug@@…).
  debug_logs: false,
};

function normalizeModCompatibility(value) {
  const raw = String(value || "ryujinx").trim().toLowerCase();
  if (["atmosphere", "atmos", "cfw", "switch", "hardware"].includes(raw)) {
    return "atmosphere";
  }
  return "ryujinx";
}

function pythonSpawnEnv(extra = {}) {
  return {
    ...process.env,
    PYTHONUNBUFFERED: "1",
    PYTHONIOENCODING: "utf-8",
    PYTHONUTF8: "1",
    SKIP_REQUIREMENTS_UPDATE: "1",
    DREAD_HUB_AP_ROOT: AP_ROOT,
    DREAD_HUB_INSTALL_ROOT: INSTALL_ROOT,
    DREAD_HUB_WORLD_DIR: WORLD_DIR,
    // AP import root must precede WORLD_DIR — world Options.py would shadow AP Options.
    PYTHONPATH: [AP_ROOT, WORLD_DIR, process.env.PYTHONPATH || ""]
      .filter(Boolean)
      .join(path.delimiter),
    ...extra,
  };
}

let mainWindow = null;
let trackerWindow = null;
let clientProcess = null;
let patchProcess = null;
let latestStatus = null;
let preparedSeed = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1040,
    height: 860,
    minWidth: 780,
    minHeight: 660,
    backgroundColor: "#071016",
    title: "Metroid Bread Client Hub",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.on("closed", () => {
    mainWindow = null;
    stopClient();
    if (trackerWindow && !trackerWindow.isDestroyed()) {
      trackerWindow.close();
    }
  });
}

function loadPatchDefaults() {
  try {
    if (fs.existsSync(PATCH_CONFIG_PATH)) {
      return readJsonFile(PATCH_CONFIG_PATH);
    }
  } catch (err) {
    console.error("Failed to load patch config:", err);
  }
  return {};
}

function applyLauncherPrefill(cfg) {
  // Archipelago Launcher / hub_launcher.py can pass connect fields via env.
  const server = process.env.DREAD_HUB_CONNECT;
  const slot = process.env.DREAD_HUB_SLOT;
  const password = process.env.DREAD_HUB_PASSWORD;
  const dreadIp = process.env.DREAD_HUB_DREAD_IP;
  const url = process.env.DREAD_HUB_URL;
  const room = process.env.DREAD_HUB_ROOM;
  const game = process.env.DREAD_HUB_GAME;
  const autoConnect =
    process.env.DREAD_HUB_AUTO_CONNECT === "1" ||
    process.env.DREAD_HUB_AUTO_CONNECT === "true";

  if (server) {
    cfg.server = String(server).replace(/^wss?:\/\//i, "");
  }
  if (slot) {
    cfg.slot = String(slot);
  }
  if (password != null) {
    // Env always present as string when set; "" / None → clear stored password.
    cfg.password = normalizeUriPassword(password);
  }
  if (dreadIp) {
    cfg.dread_ip = String(dreadIp);
  }
  if (room) {
    cfg.room_id = String(room);
  }
  if (game) {
    cfg.game = String(game);
  }
  if (url && String(url).startsWith("archipelago://")) {
    cfg.launcher_uri = String(url);
    try {
      const parsed = new URL(String(url).replace(/^archipelago:/i, "http:"));
      const host = parsed.hostname;
      const port = parsed.port;
      if (host && !server) {
        cfg.server = port ? `${host}:${port}` : host;
      }
      if (parsed.username && !slot) {
        cfg.slot = decodeURIComponent(parsed.username);
      }
      if (parsed.password != null && password == null) {
        cfg.password = normalizeUriPassword(parsed.password);
      }
      const roomParam = parsed.searchParams.get("room");
      if (roomParam && !room) {
        cfg.room_id = roomParam;
      }
      const gameParam = parsed.searchParams.get("game");
      if (gameParam && !game) {
        cfg.game = gameParam;
      }
    } catch (err) {
      // ignore malformed URI; user can still type connect fields
    }
    cfg.auto_connect_ap = true;
  }
  if (autoConnect) {
    cfg.auto_connect_ap = true;
  }
  return cfg;
}

function migratePlaceholderDreadIp(cfg) {
  // Old sample/placeholder game IP; leave any other custom IP alone.
  if (String(cfg.dread_ip || "").trim() !== "1.2.3.4") {
    return false;
  }
  cfg.dread_ip = DEFAULT_CONFIG.dread_ip;
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const raw = readJsonFile(CONFIG_PATH);
      if (String(raw.dread_ip || "").trim() === "1.2.3.4") {
        raw.dread_ip = DEFAULT_CONFIG.dread_ip;
        writeJsonFile(CONFIG_PATH, raw);
      }
    }
  } catch (err) {
    console.error("Failed to migrate dread_ip placeholder:", err);
  }
  return true;
}

function loadConfig() {
  const patch = loadPatchDefaults();
  const cfg = {
    ...DEFAULT_CONFIG,
    base_rom_path: patch.base_rom_path || DEFAULT_CONFIG.base_rom_path,
    output_path: patch.output_path || DEFAULT_CONFIG.output_path,
    ryujinx_output_path:
      patch.ryujinx_output_path ||
      DEFAULT_CONFIG.ryujinx_output_path ||
      DEFAULT_CONFIG.output_path,
    atmosphere_output_path: patch.atmosphere_output_path || "",
    mod_compatibility: normalizeModCompatibility(
      patch.mod_compatibility || DEFAULT_CONFIG.mod_compatibility
    ),
    games_folder: patch.games_folder || DEFAULT_CONFIG.games_folder,
    freesink: patch.freesink != null ? Boolean(patch.freesink) : DEFAULT_CONFIG.freesink,
    clean_output: Boolean(patch.clean_output),
  };
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      Object.assign(cfg, readJsonFile(CONFIG_PATH));
    }
  } catch (err) {
    console.error("Failed to load config:", err);
  }
  migratePlaceholderDreadIp(cfg);
  applyLauncherPrefill(cfg);
  delete cfg.poptracker_path;
  cfg.mod_compatibility = normalizeModCompatibility(cfg.mod_compatibility);
  if (!cfg.ryujinx_output_path) {
    cfg.ryujinx_output_path =
      cfg.mod_compatibility === "ryujinx"
        ? cfg.output_path || DEFAULT_CONFIG.ryujinx_output_path
        : DEFAULT_CONFIG.ryujinx_output_path;
  }
  if (cfg.atmosphere_output_path == null) {
    cfg.atmosphere_output_path = "";
  }
  if (!cfg.output_path) {
    cfg.output_path =
      cfg.mod_compatibility === "atmosphere"
        ? cfg.atmosphere_output_path || ""
        : cfg.ryujinx_output_path || DEFAULT_CONFIG.output_path;
  }
  if (!cfg.ryujinx_path) {
    cfg.ryujinx_path = findRyujinxPath() || "";
  }
  if (!cfg.dread_rom_path) {
    cfg.dread_rom_path = findDreadRomPath(cfg) || "";
  }
  return cfg;
}

function saveConfig(partial) {
  const cfg = { ...loadConfig(), ...partial };
  delete cfg.poptracker_path;
  cfg.mod_compatibility = normalizeModCompatibility(cfg.mod_compatibility);
  if (cfg.mod_compatibility === "atmosphere") {
    if (cfg.output_path) cfg.atmosphere_output_path = cfg.output_path;
  } else if (cfg.output_path) {
    cfg.ryujinx_output_path = cfg.output_path;
  }
  writeJsonFile(CONFIG_PATH, cfg);

  // Keep patcher config in sync for CLI / legacy tools.
  try {
    const patchDefaults = loadPatchDefaults();
    const patchCfg = {
      ...patchDefaults,
      base_rom_path: cfg.base_rom_path,
      output_path: cfg.output_path,
      ryujinx_output_path:
        cfg.ryujinx_output_path || DEFAULT_CONFIG.ryujinx_output_path,
      atmosphere_output_path: cfg.atmosphere_output_path || "",
      mod_compatibility: cfg.mod_compatibility,
      player_name: cfg.slot || patchDefaults.player_name || "DreadPlayer",
      clean_output: Boolean(cfg.clean_output),
      freesink: Boolean(cfg.freesink),
      games_folder: cfg.games_folder || DEFAULT_OUTPUT_SCAN,
      // Frozen Hub / apworld ship exlaunch/deploy next to the world package.
      // Preserve an existing key; never drop it when rewriting patcher config.
      custom_exlaunch_deploy:
        patchDefaults.custom_exlaunch_deploy || "exlaunch/deploy",
    };
    writeJsonFile(PATCH_CONFIG_PATH, patchCfg);
  } catch (err) {
    console.error("Failed to sync patch config:", err);
  }
  return cfg;
}

let cachedPythonLauncher = null;
const ENSURE_CLIENT_DEPS_SCRIPT = path.join(WORLD_DIR, "ensure_client_deps.py");
const APWORLD_UPDATER_SCRIPT = path.join(WORLD_DIR, "apworld_updater.py");
const APWORLD_RELEASES_URL =
  "https://github.com/Dummydud3/metroid-dread-apworld/releases";

function findPythonLauncher() {
  if (cachedPythonLauncher) {
    return cachedPythonLauncher;
  }

  const versionOkShared =
    "import sys; raise SystemExit(0 if (3,11,9) <= sys.version_info < (3,14) else 1)";

  if (process.platform !== "win32") {
    const versionOk = versionOkShared;
    const probeUnix = (candidate, code) =>
      spawnSync(candidate.cmd, [...candidate.prefixArgs, "-c", code], {
        timeout: 30000,
      }).status === 0;

    // Linux Hub client deps live in a local venv (never systemwide pip).
    // Prefer venv over DREAD_HUB_PYTHON (which may point at managed install_only).
    const venvPython = path.join(WORLD_DIR, "_metroid_bread_venv", "bin", "python");
    if (process.platform === "linux" && fs.existsSync(venvPython)) {
      const venvLauncher = { cmd: venvPython, prefixArgs: [] };
      if (probeUnix(venvLauncher, versionOk)) {
        cachedPythonLauncher = venvLauncher;
        return cachedPythonLauncher;
      }
    }

    // Managed portable CPython from Hub Setup Wizard / hub_launcher.
    const dreadHubPython = (process.env.DREAD_HUB_PYTHON || "").trim();
    if (dreadHubPython && fs.existsSync(dreadHubPython)) {
      const managed = { cmd: dreadHubPython, prefixArgs: [] };
      if (probeUnix(managed, versionOk) || probeUnix(managed, "import open_dread_rando")) {
        cachedPythonLauncher = managed;
        return cachedPythonLauncher;
      }
    }

    const unixCandidates = [
      { cmd: "python3.12", prefixArgs: [] },
      { cmd: "python3.11", prefixArgs: [] },
      { cmd: "python3.13", prefixArgs: [] },
      { cmd: "python3", prefixArgs: [] },
      { cmd: "python", prefixArgs: [] },
    ];
    const foundUnix =
      unixCandidates.find((c) => probeUnix(c, "import open_dread_rando")) ||
      unixCandidates.find((c) => probeUnix(c, versionOk));
    cachedPythonLauncher = foundUnix || null;
    return cachedPythonLauncher;
  }

  // Windows: managed portable CPython from Hub Setup Wizard / hub_launcher.
  const dreadHubPython = (process.env.DREAD_HUB_PYTHON || "").trim();
  if (dreadHubPython && fs.existsSync(dreadHubPython)) {
    const managed = { cmd: dreadHubPython, prefixArgs: [] };
    const probeManaged = (code) =>
      spawnSync(managed.cmd, [...managed.prefixArgs, "-c", code], {
        timeout: 30000,
        windowsHide: true,
      }).status === 0;
    if (probeManaged(versionOkShared) || probeManaged("import open_dread_rando")) {
      cachedPythonLauncher = managed;
      return cachedPythonLauncher;
    }
  }

  // Windows Hub client deps install into %LOCALAPPDATA%\MetroidBread\venv
  // (see ensure_client_deps.py). Prefer that interpreter so Connect does not
  // spawn bare `py -3.12` without websockets/yaml after deps succeed.
  const winVenvPython = path.join(
    process.env.LOCALAPPDATA || "",
    "MetroidBread",
    "venv",
    "Scripts",
    "python.exe"
  );
  if (winVenvPython && fs.existsSync(winVenvPython)) {
    const venvLauncher = { cmd: winVenvPython, prefixArgs: [] };
    const probeVenv = (code) =>
      spawnSync(venvLauncher.cmd, [...venvLauncher.prefixArgs, "-c", code], {
        timeout: 30000,
        windowsHide: true,
      }).status === 0;
    if (
      probeVenv("import websockets") ||
      probeVenv(versionOkShared) ||
      probeVenv("import open_dread_rando")
    ) {
      cachedPythonLauncher = venvLauncher;
      return cachedPythonLauncher;
    }
  }

  // The patcher imports mercury-engine-data-structures in-process, so prefer an
  // interpreter that already has open-dread-rando over the newest one installed.
  const candidates = [
    { cmd: "py", prefixArgs: ["-3.11"] },
    { cmd: "py", prefixArgs: ["-3.12"] },
    { cmd: "py", prefixArgs: ["-3.13"] },
    { cmd: "python", prefixArgs: [] },
  ];
  const probe = (candidate, code) =>
    spawnSync(candidate.cmd, [...candidate.prefixArgs, "-c", code], {
      timeout: 30000,
      windowsHide: true,
    }).status === 0;

  const found =
    candidates.find((c) => probe(c, "import open_dread_rando")) ||
    candidates.find((c) =>
      probe(
        c,
        "import sys; raise SystemExit(0 if (3,11,9) <= sys.version_info < (3,14) else 1)"
      )
    );
  // Do NOT fall back to py -3.11 when nothing probes clean — that yields a bare
  // launcher exit (classic 103 / pymanager 0xA0000006) with no useful UI hint.
  if (!found) {
    return null;
  }
  cachedPythonLauncher = found;
  return cachedPythonLauncher;
}

/**
 * Install websockets/etc. for the Hub client.
 * Shares worlds/metroid_bread/ensure_client_deps.py with hub_launcher / bat / sh.
 * On Linux, ensure_client_deps creates/uses ``_metroid_bread_venv`` (not system pip).
 */
function ensureClientDeps(launcher) {
  if (!launcher) {
    return { ok: false, error: pythonMissingError() };
  }
  if (!fs.existsSync(ENSURE_CLIENT_DEPS_SCRIPT)) {
    return {
      ok: false,
      error:
        `ensure_client_deps.py not found:\n${ENSURE_CLIENT_DEPS_SCRIPT}\n` +
        "Reinstall/update metroid_bread.apworld (or refresh _metroid_bread_runtime).",
    };
  }
  const result = spawnSync(
    launcher.cmd,
    [...launcher.prefixArgs, ENSURE_CLIENT_DEPS_SCRIPT, "--world", WORLD_DIR],
    {
      cwd: WORLD_DIR,
      encoding: "utf8",
      timeout: 600000,
      windowsHide: true,
      env: {
        ...process.env,
        SKIP_REQUIREMENTS_UPDATE: "1",
        PYTHONUNBUFFERED: "1",
      },
    }
  );
  const stdout = String(result.stdout || "").trim();
  const stderr = String(result.stderr || "").trim();
  const combined = [stdout, stderr].filter(Boolean).join("\n");
  if (result.error) {
    const errMsg = String(result.error.message || result.error);
    const unsigned =
      result.status == null && /ENOENT/i.test(errMsg)
        ? null
        : result.status;
    if (/ENOENT/i.test(errMsg) || unsigned === 0xa0000006 || unsigned === 103) {
      return { ok: false, error: pythonMissingError() };
    }
    return {
      ok: false,
      error: `Failed to run ensure_client_deps.py:\n${errMsg}\n${combined}`.trim(),
    };
  }
  if (result.status === 2) {
    return { ok: false, error: pythonMissingError() };
  }
  if (result.status !== 0) {
    return {
      ok: false,
      error:
        combined ||
        `Failed to install Python client packages (exit ${result.status}).`,
    };
  }
  // Linux/Windows: ensure may have just created/refreshed the Hub venv —
  // clear cache so startClient re-resolves to that interpreter.
  if (process.platform === "linux" || process.platform === "win32") {
    cachedPythonLauncher = null;
  }
  return { ok: true, message: combined };
}

function findRyujinxPath() {
  const home = process.env.USERPROFILE || "";
  const candidates = [
    // Prefer the newer portable build when present.
    path.join(home, "Downloads", "ryujinx-1.2.78-win_x64", "publish", "Ryujinx.exe"),
    path.join(home, "Desktop", "publish", "Ryujinx.exe"),
    path.join(process.env.LOCALAPPDATA || "", "Ryujinx", "Ryujinx.exe"),
    path.join(process.env.ProgramFiles || "", "Ryujinx", "Ryujinx.exe"),
    "C:\\Ryujinx\\Ryujinx.exe",
  ];
  // Also accept any Downloads\ryujinx-*\publish\Ryujinx.exe (newest first).
  try {
    const downloads = path.join(home, "Downloads");
    if (fs.existsSync(downloads)) {
      const found = fs
        .readdirSync(downloads, { withFileTypes: true })
        .filter((d) => d.isDirectory() && /^ryujinx/i.test(d.name))
        .map((d) => path.join(downloads, d.name, "publish", "Ryujinx.exe"))
        .filter((p) => fs.existsSync(p))
        .sort((a, b) => {
          try {
            return fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs;
          } catch {
            return 0;
          }
        });
      candidates.unshift(...found);
    }
  } catch (_) {
    /* ignore */
  }
  const seen = new Set();
  for (const p of candidates) {
    if (!p || seen.has(p) || !fs.existsSync(p)) continue;
    seen.add(p);
    return p;
  }
  return "";
}

function readRyujinxGameDirs() {
  const cfgPath = path.join(process.env.APPDATA || "", "Ryujinx", "Config.json");
  try {
    if (!fs.existsSync(cfgPath)) return [];
    const cfg = readJsonFile(cfgPath);
    return Array.isArray(cfg.game_dirs) ? cfg.game_dirs.filter(Boolean) : [];
  } catch {
    return [];
  }
}

function looksLikeDreadRom(name) {
  const n = String(name || "").toLowerCase();
  return (
    n.includes("dread") ||
    n.includes("metroid") ||
    n.includes(DREAD_TITLE_ID) ||
    n.includes("01009380")
  );
}

function findDreadRomPath(cfg) {
  const dirs = [
    ...(cfg && cfg.dread_rom_path ? [path.dirname(cfg.dread_rom_path)] : []),
    ...readRyujinxGameDirs(),
    path.join(process.env.USERPROFILE || "", "Downloads"),
    path.join(process.env.USERPROFILE || "", "Games"),
  ];
  const seen = new Set();
  for (const dir of dirs) {
    if (!dir || !fs.existsSync(dir) || seen.has(dir)) continue;
    seen.add(dir);
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const ent of entries) {
        if (!ent.isFile()) continue;
        if (!/\.(nsp|xci)$/i.test(ent.name)) continue;
        if (!looksLikeDreadRom(ent.name)) continue;
        return path.join(dir, ent.name);
      }
    } catch {
      /* skip */
    }
  }
  return "";
}

function detectDefaultRyujinxOutput() {
  const p = path.join(
    process.env.APPDATA || "",
    "Ryujinx",
    "mods",
    "contents",
    DREAD_TITLE_ID
  );
  return p;
}

function trackerPayloadFromStatus(st) {
  const base = {
    ap_connected: false,
    received_items: [],
    checked_location_ids: [],
    in_logic_location_ids: [],
    in_logic_count: 0,
    logic_error: "",
    logic_item_count: 0,
    logic_start: "",
    items_received: 0,
    checked_locations: 0,
    missing_locations: 0,
    slot: "",
    scenario: "",
    tracker_item_pool: null,
  };
  if (!st || typeof st !== "object") return base;
  const pool =
    st.tracker_item_pool && typeof st.tracker_item_pool === "object"
      ? st.tracker_item_pool
      : null;
  return {
    ...base,
    ...st,
    received_items: Array.isArray(st.received_items) ? st.received_items : [],
    checked_location_ids: Array.isArray(st.checked_location_ids)
      ? st.checked_location_ids
      : [],
    in_logic_location_ids: Array.isArray(st.in_logic_location_ids)
      ? st.in_logic_location_ids
      : [],
    bosses: Array.isArray(st.bosses) ? st.bosses : [],
    in_logic_count: Array.isArray(st.in_logic_location_ids)
      ? st.in_logic_location_ids.length
      : Number(st.in_logic_count) || 0,
    tracker_item_pool: pool,
  };
}

function sendTrackerUpdate() {
  if (trackerWindow && !trackerWindow.isDestroyed()) {
    trackerWindow.webContents.send("tracker-update", trackerPayloadFromStatus(latestStatus));
  }
}

function openTrackerWindow() {
  if (trackerWindow && !trackerWindow.isDestroyed()) {
    trackerWindow.focus();
    sendTrackerUpdate();
    return { ok: true };
  }

  trackerWindow = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 820,
    minHeight: 560,
    backgroundColor: "#071016",
    title: "Metroid Bread Map Tracker",
    parent: mainWindow || undefined,
    webPreferences: {
      preload: path.join(__dirname, "tracker", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  trackerWindow.loadFile(path.join(__dirname, "tracker", "index.html"));
  trackerWindow.on("closed", () => {
    trackerWindow = null;
  });
  trackerWindow.webContents.on("did-finish-load", () => {
    sendTrackerUpdate();
  });
  return { ok: true };
}

function sendToRenderer(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}

const HUB_LOG_FILENAME = "metroid_bread_hub.log";
const HUB_LOG_MAX_BYTES = 8 * 1024 * 1024;

function getLogsDir() {
  // Matches Utils.user_path("logs") when Hub sets DREAD_HUB_INSTALL_ROOT /
  // Utils.local_path to INSTALL_ROOT (writable Archipelago install / ProgramData).
  const dir = path.join(INSTALL_ROOT, "logs");
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch (_) {
    /* ignore — openPath still attempts the path */
  }
  return dir;
}

function getHubLogPath() {
  return path.join(getLogsDir(), HUB_LOG_FILENAME);
}

function appendHubLogFile(text) {
  const cleaned = String(text || "");
  if (!cleaned) return;
  try {
    const filePath = getHubLogPath();
    try {
      const st = fs.statSync(filePath);
      if (st.isFile() && st.size >= HUB_LOG_MAX_BYTES) {
        const bak = `${filePath}.1`;
        try {
          fs.unlinkSync(bak);
        } catch (_) {
          /* ignore */
        }
        try {
          fs.renameSync(filePath, bak);
        } catch (_) {
          /* ignore */
        }
      }
    } catch (_) {
      /* missing file — fine */
    }
    fs.appendFileSync(filePath, cleaned, "utf8");
  } catch (_) {
    /* never block the UI on log IO */
  }
}

function appendLog(stream, text, level = "normal") {
  const payloadText = String(text || "");
  sendToRenderer("client-log", {
    stream,
    text: payloadText,
    level: level === "debug" ? "debug" : "normal",
  });
  // Always tee Hub/main-process lines to disk (including debug) so connect
  // failures are diagnosable even when the Log panel was unread.
  const stamp = new Date().toISOString().replace(/\..+$/, "");
  const tag = level === "debug" ? "DEBUG" : stream === "stderr" ? "STDERR" : "INFO";
  appendHubLogFile(`[${stamp}] ${tag} ${payloadText.replace(/\r?\n$/, "")}\n`);
}

async function openLogsFolder() {
  const dir = getLogsDir();
  const err = await shell.openPath(dir);
  if (err) {
    return { ok: false, error: err, path: dir };
  }
  return { ok: true, path: dir };
}

function handleStdoutLine(line) {
  if (line.startsWith(UI_PREFIX)) {
    try {
      const event = JSON.parse(line.slice(UI_PREFIX.length));
      if (event.type === "print_json") {
        sendToRenderer("client-status", event);
        return;
      }
      latestStatus = event.type === "status" ? event : { ...latestStatus, ...event };
      sendToRenderer("client-status", event);
      sendTrackerUpdate();
    } catch (err) {
      appendLog("stdout", line + "\n");
    }
    return;
  }
  if (line.startsWith("[tracker-logic]")) {
    return;
  }
  let level = "normal";
  let text = line;
  if (line.startsWith(UI_LOG_PREFIX)) {
    const m = line.match(UI_LOG_RE);
    if (m) {
      level = m[1].toLowerCase() === "debug" ? "debug" : "normal";
      text = m[2];
    }
  }
  appendLog("stdout", text + "\n", level);
}

function stopClient() {
  if (!clientProcess) return;
  try {
    if (clientProcess.stdin && !clientProcess.stdin.destroyed) {
      clientProcess.stdin.write("/exit\n");
    }
  } catch (_) {
    /* ignore */
  }
  try {
    clientProcess.kill();
  } catch (_) {
    /* ignore */
  }
  clientProcess = null;
  latestStatus = null;
  preparedSeed = null;
  sendToRenderer("client-status", {
    type: "status",
    ap_connected: false,
    game_connected: false,
    stopped: true,
    received_items: [],
    checked_location_ids: [],
  });
  sendTrackerUpdate();
}

function normalizeConnectOpts(opts) {
  let server = String(opts.server || "").trim();
  let slot = String(opts.slot || "").trim();
  let password = normalizeUriPassword(opts.password);
  let dreadIp = String(opts.dreadIp || "127.0.0.1").trim() || "127.0.0.1";
  let roomId = "";

  // Room page URL: https://archipelago.gg/room/<id>
  const roomMatch = server.match(/\/room\/([A-Za-z0-9_-]+)/i);
  if (roomMatch) {
    roomId = roomMatch[1];
  }

  // Text Client / launcher strings: optional scheme + slot:password@host:port.
  // Always pass bare host:port to Python --connect (ws-first in CommonClient).
  const parsed = parseConnectServerString(server);
  if (parsed.server) {
    server = parsed.server;
  }
  if (parsed.hasUserinfo) {
    // Prefer userinfo from the server string over separate fields.
    if (parsed.slot) slot = parsed.slot;
    password = parsed.password || "";
  }
  if (parsed.room) {
    roomId = parsed.room;
  }

  // Strip any leftover scheme/path so --connect matches Text Client / CommonClient.
  server = String(server || "")
    .replace(/^wss?:\/\//i, "")
    .replace(/^archipelago:\/\//i, "")
    .replace(/^https?:\/\//i, "")
    .split("/")[0];

  return {
    server,
    slot,
    password,
    dreadIp,
    roomId,
    autoConnectDread: opts.autoConnectDread === true,
  };
}

function startClient(opts) {
  if (clientProcess) {
    return { ok: false, error: "Client is already running. Disconnect first." };
  }
  if (!fs.existsSync(CLIENT_SCRIPT)) {
    return { ok: false, error: `Client script not found:\n${CLIENT_SCRIPT}` };
  }
  if (!hasCommonClient(AP_ROOT)) {
    const frozenHint = isFrozenApInstall(INSTALL_ROOT)
      ? `\nDetected frozen Archipelago install:\n${INSTALL_ROOT}\n` +
        `Expected bundled import root at:\n${path.join(WORLD_DIR, AP_CORE_DIRNAME)}\n\n` +
        `Reinstall/update metroid_bread.apworld (includes ap_core), or set ` +
        `DREAD_HUB_AP_ROOT to an Archipelago source/portable folder with CommonClient.py.`
      : `\nSet DREAD_HUB_AP_ROOT to your Archipelago source/portable folder, or launch ` +
        `from a checkout that contains CommonClient.py.`;
    return {
      ok: false,
      error:
        `Archipelago core not found (CommonClient.py) under:\n${AP_ROOT}\n` +
        frozenHint,
    };
  }

  const normalized = normalizeConnectOpts(opts || {});
  if (!normalized.server || !normalized.slot) {
    return {
      ok: false,
      error:
        "Server and slot are required. Enter host:port (or archipelago:// link) and your slot name.",
    };
  }

  saveConfig({
    server: normalized.server.replace(/^wss?:\/\//i, ""),
    slot: normalized.slot,
    password: normalized.password || "",
    dread_ip: normalized.dreadIp,
    auto_connect_dread: normalized.autoConnectDread,
    room_id: normalized.roomId || loadConfig().room_id || "",
  });

  const launcher = findPythonLauncher();
  if (!launcher) {
    return { ok: false, error: pythonMissingError() };
  }
  appendLog(
    "stdout",
    `[app] Logs folder: ${getLogsDir()}\n` +
      `[app] Hub log file: ${getHubLogPath()}\n` +
      `[app] Install root: ${INSTALL_ROOT}\n` +
      `[app] Checking Python client packages (${formatPythonCmd(launcher)})…\n`
  );
  if (process.platform === "linux") {
    appendLog(
      "stdout",
      `[app] Linux: client packages install into local venv ` +
        `${path.join(WORLD_DIR, "_metroid_bread_venv")} (not systemwide).\n`
    );
  }
  const deps = ensureClientDeps(launcher);
  if (!deps.ok) {
    appendLog("stderr", `\n[app] ${String(deps.error || "").replace(/\n/g, "\n[app] ")}\n`);
    return { ok: false, error: deps.error };
  }
  if (deps.message) {
    appendLog("stdout", `[app] ${deps.message.replace(/\n/g, "\n[app] ")}\n`);
  }

  // Re-resolve after ensure so Linux/Windows launch with the Hub venv python.
  const launchPy = findPythonLauncher() || launcher;
  const { cmd, prefixArgs } = launchPy;
  const args = [
    ...prefixArgs,
    CLIENT_SCRIPT,
    "--nogui",
    "--electron",
    "--connect",
    normalized.server,
    "--name",
    normalized.slot,
    "--dread-ip",
    normalized.dreadIp,
  ];
  if (normalized.password) {
    args.push("--password", normalized.password);
  }
  // Hub connects AP first; game attach happens after patch / launch.
  if (normalized.autoConnectDread) {
    args.push("--auto-dread");
  } else {
    args.push("--no-auto-dread");
  }

  let stderrBuf = "";
  try {
    clientProcess = spawn(cmd, args, {
      cwd: INSTALL_ROOT,
      env: pythonSpawnEnv(),
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
  } catch (err) {
    return { ok: false, error: String(err.message || err) };
  }

  let stdoutBuf = "";
  clientProcess.stdout.on("data", (chunk) => {
    stdoutBuf += chunk.toString("utf8");
    const parts = stdoutBuf.split(/\r?\n/);
    stdoutBuf = parts.pop() || "";
    for (const line of parts) {
      handleStdoutLine(line);
    }
  });
  clientProcess.stderr.on("data", (chunk) => {
    const text = chunk.toString("utf8");
    stderrBuf = (stderrBuf + text).slice(-8000);
    appendLog("stderr", text);
  });
  clientProcess.on("error", (err) => {
    clientProcess = null;
    const msg = `Failed to start Python (${formatPythonCmd(launchPy)}): ${err.message}`;
    appendLog("stderr", `\n[app] ${msg}\n`);
    latestStatus = {
      type: "status",
      ap_connected: false,
      game_connected: false,
      stopped: true,
      exit_code: null,
      exit_error: msg,
      received_items: [],
      checked_location_ids: [],
    };
    sendToRenderer("client-status", latestStatus);
    sendTrackerUpdate();
  });
  clientProcess.on("exit", (code, signal) => {
    if (stdoutBuf.trim()) handleStdoutLine(stdoutBuf.trim());
    stdoutBuf = "";
    clientProcess = null;
    appendLog("stdout", `\n[app] Client exited (code=${code}, signal=${signal || "none"})\n`);
    const crashHint = explainClientExit(code, stderrBuf);
    if (crashHint && stderrBuf.trim()) {
      // Ensure the UI status line is not the only place stderr is visible.
      appendLog("stdout", `[app] ${crashHint.replace(/\n/g, "\n[app] ")}\n`);
    }
    latestStatus = {
      type: "status",
      ap_connected: false,
      game_connected: false,
      stopped: true,
      exit_code: code,
      exit_error: crashHint,
      received_items: [],
      checked_location_ids: [],
    };
    sendToRenderer("client-status", latestStatus);
    sendTrackerUpdate();
  });

  appendLog(
    "stdout",
    `[app] Connecting to Archipelago…\n` +
      `      Server: ${normalized.server}\n` +
      `      Slot:   ${normalized.slot}\n` +
      `      Password: ${normalized.password ? "set" : "none"}\n` +
      `      Script: ${CLIENT_SCRIPT}\n` +
      `      Python: ${formatPythonCmd(launchPy)}\n` +
      `      AP import: ${AP_ROOT}\n` +
      `      AP install: ${INSTALL_ROOT}\n`
  );
  return { ok: true, roomId: normalized.roomId || "" };
}

function sendCommand(text) {
  if (!clientProcess || !clientProcess.stdin || clientProcess.stdin.destroyed) {
    return { ok: false, error: "Client is not running." };
  }
  const line = String(text || "").trim();
  if (!line) return { ok: false, error: "Empty command." };
  clientProcess.stdin.write(line + "\n");
  sendToRenderer("client-log", { stream: "cmd", text: line });
  return { ok: true };
}

/* ---------- Spoiler / seed discovery (from direct patcher) ---------- */

function creationMs(stat) {
  const birth = stat.birthtimeMs;
  if (Number.isFinite(birth) && birth > 0) return birth;
  if (Number.isFinite(stat.ctimeMs) && stat.ctimeMs > 0) return stat.ctimeMs;
  return stat.mtimeMs || 0;
}

function listSpoilerEntriesInZip(zipPath) {
  const zip = new AdmZip(zipPath);
  return zip
    .getEntries()
    .filter((e) => !e.isDirectory && /_Spoiler\.txt$/i.test(path.basename(e.entryName)))
    .sort((a, b) => {
      const da = a.entryName.split(/[/\\]/).length;
      const db = b.entryName.split(/[/\\]/).length;
      return da - db || a.entryName.localeCompare(b.entryName);
    });
}

function extractSpoilerFromZip(zipPath) {
  if (!zipPath || !fs.existsSync(zipPath)) {
    return { ok: false, error: `Zip not found:\n${zipPath}` };
  }
  let entries;
  try {
    entries = listSpoilerEntriesInZip(zipPath);
  } catch (err) {
    return { ok: false, error: `Could not read zip:\n${err.message || err}` };
  }
  if (!entries.length) {
    return { ok: false, error: `No *_Spoiler.txt inside zip:\n${zipPath}` };
  }

  const entry = entries[0];
  const stem = path.basename(zipPath, path.extname(zipPath));
  const outDir = path.join(EXTRACT_ROOT, stem);
  fs.mkdirSync(outDir, { recursive: true });

  const spoilerName = path.basename(entry.entryName);
  const spoilerPath = path.join(outDir, spoilerName);
  fs.writeFileSync(spoilerPath, entry.getData());

  let zipStat = null;
  try {
    zipStat = fs.statSync(zipPath);
  } catch {
    zipStat = null;
  }

  return {
    ok: true,
    spoilerPath,
    zipPath,
    gameFolder: zipPath,
    gameName: stem,
    source: "zip",
    createdAt: zipStat ? creationMs(zipStat) : Date.now(),
    createdAtLocal: zipStat
      ? new Date(creationMs(zipStat)).toLocaleString()
      : new Date().toLocaleString(),
  };
}

function isSoloDreadSpoiler(spoilerPath) {
  if (!spoilerPath || !fs.existsSync(spoilerPath)) return false;
  const text = fs.readFileSync(spoilerPath, "utf8");
  let sawPlayerHeader = false;
  let sawSoloGame = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (line === "Locations:") break;
    if (/^Player \d+:\s*/.test(line)) {
      sawPlayerHeader = true;
      break;
    }
    if (line.startsWith("Game:") && line.slice(line.indexOf(":") + 1).trim() === "Metroid Bread") {
      sawSoloGame = true;
    }
  }
  return sawSoloGame && !sawPlayerHeader;
}

function detectDreadPlayers(spoilerPath) {
  if (!spoilerPath || !fs.existsSync(spoilerPath)) return [];
  if (isSoloDreadSpoiler(spoilerPath)) {
    return ["(solo Metroid Bread)"];
  }
  const text = fs.readFileSync(spoilerPath, "utf8");
  const players = [];
  let current = null;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (line === "Locations:") break;
    const pm = line.match(/^Player \d+:\s*(.+)$/);
    if (pm) {
      current = pm[1].trim();
      continue;
    }
    if (current != null && line.startsWith("Game:")) {
      const game = line.slice(line.indexOf(":") + 1).trim();
      if (game === "Metroid Bread") players.push(current);
      current = null;
    }
  }
  return players;
}

function spoilerMentionsSeed(spoilerPath, seedName) {
  if (!seedName || !spoilerPath || !fs.existsSync(spoilerPath)) return false;
  try {
    const head = fs.readFileSync(spoilerPath, "utf8").slice(0, 4000);
    return head.includes(seedName);
  } catch {
    return false;
  }
}

function walkSpoilers(rootDir, maxDepth = 8) {
  const results = [];
  if (!rootDir || !fs.existsSync(rootDir)) return results;
  const rootResolved = path.resolve(rootDir);

  function topLevelBatch(filePath) {
    const rel = path.relative(rootResolved, filePath);
    const parts = rel.split(path.sep).filter(Boolean);
    if (!parts.length) return rootResolved;
    return path.join(rootResolved, parts[0]);
  }

  function walk(dir, depth) {
    if (depth > maxDepth) return;
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const ent of entries) {
      const full = path.join(dir, ent.name);
      if (ent.isDirectory()) {
        if (
          ent.name === "node_modules" ||
          ent.name === "_patcher_extract" ||
          ent.name.startsWith(".")
        ) {
          continue;
        }
        walk(full, depth + 1);
      } else if (ent.isFile() && /_Spoiler\.txt$/i.test(ent.name)) {
        try {
          const spoilerStat = fs.statSync(full);
          const batchFolder = topLevelBatch(full);
          const batchStat = fs.statSync(batchFolder);
          results.push({
            spoilerPath: full,
            gameFolder: batchFolder,
            gameName: path.basename(batchFolder),
            createdAt: creationMs(batchStat),
            spoilerCreatedAt: creationMs(spoilerStat),
            source: "folder",
            key: batchFolder,
          });
        } catch {
          /* skip */
        }
      } else if (ent.isFile() && /\.zip$/i.test(ent.name)) {
        try {
          const zipStat = fs.statSync(full);
          const spoilers = listSpoilerEntriesInZip(full);
          if (!spoilers.length) continue;
          results.push({
            spoilerPath: null,
            zipPath: full,
            gameFolder: full,
            gameName: path.basename(full, path.extname(full)),
            createdAt: creationMs(zipStat),
            spoilerCreatedAt: creationMs(zipStat),
            source: "zip",
            key: full,
          });
        } catch {
          /* skip */
        }
      }
    }
  }

  walk(rootResolved, 0);
  return results;
}

function attachPlayerInfo(payload, preferredPlayer) {
  if (!payload?.ok || !payload.spoilerPath) return payload;
  const dreadPlayers = detectDreadPlayers(payload.spoilerPath);
  const solo = isSoloDreadSpoiler(payload.spoilerPath);
  const cfgName = preferredPlayer || loadConfig().slot || "DreadPlayer";
  let suggested = cfgName;
  if (!solo && dreadPlayers.length) {
    const exact = dreadPlayers.find(
      (p) => p.toLowerCase() === String(cfgName).toLowerCase()
    );
    suggested = exact || dreadPlayers[0];
  }
  return {
    ...payload,
    dreadPlayers,
    soloDread: solo,
    suggestedPlayer: suggested,
  };
}

/* ---------- Singleplayer zip drop (Hub-optional patch flow) ---------- */

function loadSingleplayerZip(zipPath) {
  const clean = String(zipPath || "").trim();
  if (!clean) return { ok: false, error: "No file provided." };
  if (!/\.zip$/i.test(clean)) {
    return { ok: false, error: "Please select or drop a .zip file (Archipelago generated output)." };
  }
  if (!fs.existsSync(clean)) {
    return { ok: false, error: `File not found:\n${clean}` };
  }

  // Reuse the same zip -> spoiler extraction the direct patcher / seed scan use,
  // so a dropped output.zip feeds the exact same runPatch() path as multiworld.
  const extracted = extractSpoilerFromZip(clean);
  if (!extracted.ok) return extracted;

  preparedSeed = attachPlayerInfo(
    {
      ok: true,
      spoilerPath: extracted.spoilerPath,
      zipPath: extracted.zipPath,
      gameName: extracted.gameName,
      gameFolder: extracted.zipPath,
      createdAtLocal: extracted.createdAtLocal,
      source: "zip",
    },
    loadConfig().slot
  );
  return preparedSeed;
}

function httpGetBuffer(url, redirects = 0) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith("https") ? https : http;
    const req = lib.get(url, { timeout: 20000 }, (res) => {
      if (
        res.statusCode >= 300 &&
        res.statusCode < 400 &&
        res.headers.location &&
        redirects < 5
      ) {
        const next = new URL(res.headers.location, url).toString();
        res.resume();
        httpGetBuffer(next, redirects + 1).then(resolve, reject);
        return;
      }
      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode} for ${url}`));
        res.resume();
        return;
      }
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve(Buffer.concat(chunks)));
    });
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Request timed out"));
    });
  });
}

async function tryDownloadSpoilerFromRoom(roomId, slotName) {
  if (!roomId) return { ok: false, error: "No room id" };
  const apiUrl = `https://archipelago.gg/api/room_status/${roomId}`;
  let room;
  try {
    const buf = await httpGetBuffer(apiUrl);
    room = JSON.parse(buf.toString("utf8"));
  } catch (err) {
    return { ok: false, error: `Room lookup failed: ${err.message || err}` };
  }

  const players = Array.isArray(room.players) ? room.players : [];
  const match = players.find(
    (p) =>
      Array.isArray(p) &&
      String(p[0] || "").toLowerCase() === String(slotName || "").toLowerCase()
  );
  if (match && match[1] && match[1] !== "Metroid Bread") {
    return {
      ok: false,
      error: `Slot "${slotName}" is ${match[1]}, not Metroid Bread.`,
      game: match[1],
    };
  }

  // Spoiler lives on the seed page; scrape download link from room HTML.
  const roomPage = `https://archipelago.gg/room/${roomId}`;
  try {
    const html = (await httpGetBuffer(roomPage)).toString("utf8");
    const rel = html.match(/\/dl_spoiler\/([A-Za-z0-9_-]+)/i);
    if (rel) {
      const finalUrl = `https://archipelago.gg/dl_spoiler/${rel[1]}`;
      const textBuf = await httpGetBuffer(finalUrl);
      const text = textBuf.toString("utf8");
      if (!text.includes("Locations:") && !text.includes("Game:")) {
        return { ok: false, error: "Downloaded file does not look like a spoiler." };
      }
      const outDir = path.join(EXTRACT_ROOT, `room_${roomId}`);
      fs.mkdirSync(outDir, { recursive: true });
      const spoilerPath = path.join(outDir, `AP_${roomId}_Spoiler.txt`);
      fs.writeFileSync(spoilerPath, text, "utf8");
      return attachPlayerInfo(
        {
          ok: true,
          spoilerPath,
          zipPath: null,
          gameName: `room_${roomId}`,
          gameFolder: outDir,
          source: "download",
          createdAtLocal: new Date().toLocaleString(),
          roomPort: room.last_port || null,
        },
        slotName
      );
    }
  } catch (err) {
    return { ok: false, error: `Spoiler download failed: ${err.message || err}` };
  }

  return {
    ok: false,
    error:
      "Room found, but no spoiler download was available (host may have spoilers disabled).",
    roomPort: room.last_port || null,
  };
}

function findSeedForSlot({ gamesFolder, slotName, seedName }) {
  const folder = gamesFolder || loadConfig().games_folder || DEFAULT_OUTPUT_SCAN;
  const all = walkSpoilers(folder);
  if (!all.length) {
    return {
      ok: false,
      error: `No *_Spoiler.txt or seed .zip found under:\n${folder}`,
    };
  }

  const scored = [];
  for (const g of all) {
    let spoilerPath = g.spoilerPath;
    let zipPath = g.zipPath || null;
    if (g.source === "zip" && !spoilerPath) {
      const extracted = extractSpoilerFromZip(g.zipPath);
      if (!extracted.ok) continue;
      spoilerPath = extracted.spoilerPath;
      zipPath = extracted.zipPath;
    }
    if (!spoilerPath) continue;

    const dreadPlayers = detectDreadPlayers(spoilerPath);
    const solo = isSoloDreadSpoiler(spoilerPath);
    if (!solo && !dreadPlayers.length) continue;

    let score = g.createdAt;
    const slotLower = String(slotName || "").toLowerCase();
    if (solo) score += 1e12;
    if (dreadPlayers.some((p) => p.toLowerCase() === slotLower)) score += 5e12;
    if (seedName && (spoilerMentionsSeed(spoilerPath, seedName) || g.gameName.includes(seedName))) {
      score += 8e12;
    }
    scored.push({
      ok: true,
      spoilerPath,
      zipPath,
      gameFolder: g.gameFolder,
      gameName: g.gameName,
      source: g.source,
      createdAt: g.createdAt,
      createdAtLocal: new Date(g.createdAt).toLocaleString(),
      dreadPlayers,
      soloDread: solo,
      suggestedPlayer: solo
        ? slotName || "DreadPlayer"
        : dreadPlayers.find((p) => p.toLowerCase() === slotLower) || dreadPlayers[0],
      _score: score,
    });
  }

  if (!scored.length) {
    return {
      ok: false,
      error: `No Metroid Bread spoiler found for slot "${slotName}" under:\n${folder}`,
    };
  }

  scored.sort((a, b) => b._score - a._score);
  const best = scored[0];
  delete best._score;
  return { ok: true, game: best, scanned: scored.length };
}

async function preparePatchFiles(opts = {}) {
  const cfg = loadConfig();
  const slotName = opts.slot || cfg.slot || latestStatus?.slot || "";
  const seedName = opts.seedName || latestStatus?.seed_name || "";
  const roomId = opts.roomId || cfg.room_id || "";
  const gamesFolder = opts.gamesFolder || cfg.games_folder || DEFAULT_OUTPUT_SCAN;

  let downloadError = null;

  // Prefer room spoiler download when available.
  if (roomId) {
    const dl = await tryDownloadSpoilerFromRoom(roomId, slotName);
    if (dl.ok) {
      preparedSeed = dl;
      return { ok: true, game: dl, source: "download" };
    }
    downloadError = dl.error;
  }

  const local = findSeedForSlot({ gamesFolder, slotName, seedName });
  if (local.ok) {
    preparedSeed = local.game;
    return {
      ok: true,
      game: local.game,
      source: "local",
      scanned: local.scanned,
      downloadError,
    };
  }

  return {
    ok: false,
    error: local.error,
    downloadError,
  };
}

function estimatePatchProgress(text, current) {
  const stages = [
    { re: /Archipelago Dread Direct Patcher/i, pct: 5 },
    { re: /Wrote .*_patcher\.json/i, pct: 18 },
    { re: /SCHEMA_OK|passes open-dread-rando schema/i, pct: 28 },
    { re: /open-dread-rando|Running ODR|patching/i, pct: 40 },
    { re: /Extracting|Expacking|RomFS|exefs/i, pct: 55 },
    { re: /Writing|Building|pkg|TOC/i, pct: 72 },
    { re: /finalize|Installing|subsdk|reachable/i, pct: 88 },
    { re: /DONE/i, pct: 100 },
  ];
  let pct = current || 0;
  for (const s of stages) {
    if (s.re.test(text)) pct = Math.max(pct, s.pct);
  }
  return Math.min(100, pct);
}

function runPatch(opts) {
  if (patchProcess) {
    return Promise.resolve({ ok: false, error: "A patch is already running." });
  }
  if (!fs.existsSync(PATCHER_SCRIPT)) {
    return Promise.resolve({
      ok: false,
      error: `Patcher script not found:\n${PATCHER_SCRIPT}`,
    });
  }

  let spoilerPath = opts?.spoilerPath || preparedSeed?.spoilerPath;
  if (spoilerPath && /\.zip$/i.test(spoilerPath)) {
    const extracted = extractSpoilerFromZip(spoilerPath);
    if (!extracted.ok) return Promise.resolve(extracted);
    spoilerPath = extracted.spoilerPath;
  }
  if (!spoilerPath || !fs.existsSync(spoilerPath)) {
    return Promise.resolve({
      ok: false,
      error: "Seed data missing. Connect again so the hub can download it from the server.",
    });
  }

  const modCompatibility = normalizeModCompatibility(
    opts.modCompatibility || loadConfig().mod_compatibility
  );
  const cfg = saveConfig({
    base_rom_path: opts.baseRomPath || loadConfig().base_rom_path,
    output_path: opts.outputPath || loadConfig().output_path,
    slot: opts.playerName || loadConfig().slot,
    clean_output: Boolean(opts.cleanOutput),
    freesink: opts.freesink != null ? Boolean(opts.freesink) : loadConfig().freesink,
    mod_compatibility: modCompatibility,
  });

  const launcher = findPythonLauncher();
  if (!launcher) {
    return Promise.resolve({ ok: false, error: pythonMissingError() });
  }
  const { cmd, prefixArgs } = launcher;
  const args = [
    ...prefixArgs,
    PATCHER_SCRIPT,
    "--spoiler",
    spoilerPath,
    "--player",
    opts.playerName || cfg.slot || "DreadPlayer",
    "--base-rom",
    cfg.base_rom_path,
    "--output",
    cfg.output_path,
    "--mod-compatibility",
    cfg.mod_compatibility,
  ];
  if (cfg.clean_output) args.push("--clean");
  args.push(cfg.freesink ? "--freesink" : "--no-freesink");
  // Always point frozen/source Hub at the world-bundled deploy when present so
  // cwd/config quirks cannot fall through to a missing absolute-dev path.
  const bundledDeploy = path.join(WORLD_DIR, "exlaunch", "deploy");
  if (fs.existsSync(path.join(bundledDeploy, "subsdk9"))) {
    args.push("--custom-exlaunch-deploy", bundledDeploy);
  }

  return new Promise((resolve) => {
    let settled = false;
    let progress = 0;
    let patchStderr = "";
    const startedAt = Date.now();
    const finish = (payload) => {
      if (settled) return;
      settled = true;
      patchProcess = null;
      resolve(payload);
    };

    try {
      patchProcess = spawn(cmd, args, {
        cwd: WORLD_DIR,
        windowsHide: true,
        env: pythonSpawnEnv(),
      });
    } catch (err) {
      finish({ ok: false, error: String(err.message || err) });
      return;
    }

    const sendPatchLog = (chunk, stream) => {
      const text = chunk.toString();
      if (stream === "stderr") {
        patchStderr = (patchStderr + text).slice(-8000);
      }
      progress = estimatePatchProgress(text, progress);
      const elapsed = (Date.now() - startedAt) / 1000;
      let etaSec = null;
      if (progress > 5 && progress < 100) {
        etaSec = Math.max(0, Math.round((elapsed / progress) * (100 - progress)));
      }
      sendToRenderer("patch-log", { stream, text });
      sendToRenderer("patch-progress", {
        percent: progress,
        etaSec,
        elapsedSec: Math.round(elapsed),
      });
    };

    patchProcess.stdout.on("data", (d) => sendPatchLog(d, "stdout"));
    patchProcess.stderr.on("data", (d) => sendPatchLog(d, "stderr"));
    patchProcess.on("error", (err) => {
      finish({
        ok: false,
        error: `Failed to start Python (${formatPythonCmd(launcher)}): ${err.message}`,
      });
    });
    patchProcess.on("close", (code) => {
      if (code === 0) {
        sendToRenderer("patch-progress", {
          percent: 100,
          etaSec: 0,
          elapsedSec: Math.round((Date.now() - startedAt) / 1000),
        });
        saveConfig({ hub_stage: "client", last_patched_at: Date.now() });
      }
      const hint =
        code === 0 ? null : explainClientExit(code, patchStderr) || `Patcher exited with code ${code}`;
      finish({
        ok: code === 0,
        code,
        error: hint,
      });
    });
  });
}

function cancelPatch() {
  if (!patchProcess) return { ok: false };
  try {
    patchProcess.kill();
  } catch {
    /* ignore */
  }
  patchProcess = null;
  return { ok: true };
}

function launchRyujinx(opts = {}) {
  const prev = loadConfig();
  const cfg = saveConfig({
    ryujinx_path: opts.ryujinxPath || prev.ryujinx_path,
    dread_rom_path: opts.dreadRomPath || prev.dread_rom_path,
  });
  let ryujinx = cfg.ryujinx_path || findRyujinxPath();
  let rom = cfg.dread_rom_path || findDreadRomPath(cfg);

  if (!ryujinx || !fs.existsSync(ryujinx)) {
    return {
      ok: false,
      error: "Ryujinx.exe not found. Set the path on the client screen.",
    };
  }
  if (!rom || !fs.existsSync(rom)) {
    return {
      ok: false,
      error:
        "Metroid Dread ROM (.nsp/.xci) not found. Set the ROM path, then try again.",
      needsRom: true,
    };
  }

  saveConfig({ ryujinx_path: ryujinx, dread_rom_path: rom });
  const cwd = path.dirname(ryujinx);

  try {
    // Direct Electron/Node spawn of Ryujinx.exe exits immediately on Windows
    // (native exit 0xE0434352) — observed with .NET Ryujinx + detached stdio.
    // Launch via `cmd /c start` so the emulator process is fully independent.
    let child;
    if (process.platform === "win32") {
      child = spawn(
        process.env.ComSpec || "cmd.exe",
        ["/c", "start", "", "/D", cwd, ryujinx, rom],
        { detached: true, stdio: "ignore", windowsHide: true }
      );
    } else {
      child = spawn(ryujinx, [rom], {
        detached: true,
        stdio: "ignore",
        cwd,
      });
    }
    child.on("error", (err) => {
      appendLog("stdout", `[app] Ryujinx launch error: ${err.message}\n`);
    });
    child.unref();
  } catch (err) {
    return { ok: false, error: String(err.message || err) };
  }

  // Passive wait in MetroidBreadClient (poll until :6969 accepts). Only a short
  // grace so Ryujinx can spawn — do not use a blind 30s one-shot connect.
  const CONNECT_DELAY_MS = 3000;
  if (clientProcess) {
    const ip = cfg.dread_ip || "127.0.0.1";
    appendLog(
      "stdout",
      `[app] Waiting ${CONNECT_DELAY_MS / 1000}s, then passive RemoteLua connect ` +
        `(retries until ${ip}:6969 accepts)…\n`
    );
    setTimeout(() => {
      appendLog("stdout", `[app] Waiting for Remote Lua at ${ip}:6969…\n`);
      sendCommand(`/connect_dread ${ip}`);
    }, CONNECT_DELAY_MS);
  }

  return { ok: true, ryujinx, rom, connectDelayMs: CONNECT_DELAY_MS };
}

/* ---------- YAML helpers ---------- */

function defaultYamlConfig() {
  return {
    name: "DreadPlayer",
    game: "Metroid Bread",
    description: "Metroid Bread player options",
    "Metroid Bread": {
      death_link: false,
      progression_balancing: 50,
      accessibility: "items",
      game_goal: "defeat_raven_beak",
      required_dna: 0,
      dna_placement: "prefer_emmi",
      hint_all_dna: true,
      door_lock_rando: "vanilla",
      doors_to_change: [
        "Access Open",
        "Charge Beam Door",
        "Grapple Beam Door",
        "Missile Door",
        "Plasma Beam Door",
        "Power Beam Door",
        "Sensor Lock Door",
        "Super Missile Door",
        "Wave Beam Door",
        "Wide Beam Door",
      ],
      change_doors_to: [
        "Bomb Door",
        "Charge Beam Door",
        "Cross Bomb Door",
        "Diffusion Beam Door",
        "Grapple Beam Door",
        "Ice Missile Door",
        "Missile Door",
        "Plasma Beam Door",
        "Power Beam Door",
        "Power Bomb Door",
        "Storm Missile Door",
        "Super Missile Door",
        "Wave Beam Door",
        "Wide Beam Door",
      ],
      transport_rando: "off",
      include_boss_pickups: true,
      start_with_pulse_radar: true,
      starting_location: "default",
      starting_kit_items: 0,
      early_morph_ball: false,
      progressive_beams: true,
      progressive_charge: true,
      progressive_missiles: false,
      progressive_bombs: true,
      progressive_suit: true,
      progressive_spin: true,
      energy_tanks: 8,
      energy_parts: 16,
      missile_tanks: 35,
      missile_plus_tanks: 10,
      power_bomb_tanks: 12,
      speed_booster_upgrade_count: 0,
      energy_per_tank: 100,
      starting_missiles: 15,
      starting_power_bombs: 0,
      missile_tank_ammo: 2,
      missile_plus_tank_ammo: 10,
      power_bomb_tank_ammo: 1,
      vanilla_flash_shift_behaviour: true,
      flash_shift_upgrade_count: 3,
      flash_shift_upgrade_requires_main_item: true,
      flash_shift_upgrade_amount: 1,
      flash_shift_included_ammo: 2,
      show_boss_lifebar: true,
      show_enemy_life: false,
      show_enemy_damage: false,
      show_player_damage: true,
      immediate_energy_parts: true,
      constant_heat_damage: 20,
      constant_cold_damage: 20,
      constant_lava_damage: 20,
      enable_death_counter: true,
      show_dna_in_hud: true,
      room_name_display: "never",
      raven_beak_damage_table: "consistent_low",
      nerf_power_bombs: false,
      disabled_lights: [],
      x_starts_released: false,
      combat_tricks: "beginner",
      knowledge_tricks: "disabled",
      movement_tricks: "disabled",
      slide_jump: "disabled",
      wall_jump_tricks: "disabled",
      infinite_bomb_jump: "disabled",
      water_bomb_jump: "disabled",
      water_space_jump: "disabled",
      single_wall_wall_jump: "disabled",
      heat_cold_runs: "disabled",
      damage_boost: "disabled",
      pseudo_wave: "disabled",
      speedbooster_conservation: "disabled",
      stand_on_frozen_enemy: "disabled",
      grapple_movement: "disabled",
      cross_bomb_skip: "disabled",
      climb_sloped_tunnels: "disabled",
      short_boost: "disabled",
      diffusion_abuse: "disabled",
      flash_shift_skip: "disabled",
      diagonal_bomb_jump: "disabled",
      ledge_warp: "disabled",
      cross_bomb_launch: "disabled",
      floor_clip: "disabled",
      climb_sloped_surfaces: "disabled",
      reverse_grapple_block: false,
    },
  };
}

function yamlEscape(value) {
  if (typeof value === "boolean" || typeof value === "number") return String(value);
  const s = String(value);
  if (/^[\w.-]+$/.test(s)) return s;
  return JSON.stringify(s);
}

function configToYaml(config) {
  const dread = config["Metroid Bread"] || {};
  const lines = [
    `description: ${yamlEscape(config.description || "Metroid Bread player options")}`,
    `name: ${yamlEscape(config.name || "DreadPlayer")}`,
    `game: Metroid Bread`,
    ``,
    `Metroid Bread:`,
  ];
  for (const [key, value] of Object.entries(dread)) {
    if (value == null) continue;
    if (Array.isArray(value)) {
      if (value.length === 0) {
        lines.push(`  ${key}: []`);
      } else {
        lines.push(`  ${key}:`);
        for (const item of value) {
          lines.push(`    - ${yamlEscape(item)}`);
        }
      }
      continue;
    }
    if (typeof value === "object") {
      lines.push(`  ${key}: {}`);
      continue;
    }
    lines.push(`  ${key}: ${yamlEscape(value)}`);
  }
  return lines.join("\n") + "\n";
}

function parseSimpleYaml(text) {
  // Minimal parser for the flat Dread player YAML we write/read (incl. option sets).
  const result = defaultYamlConfig();
  const dread = { ...result["Metroid Bread"] };
  let inDread = false;
  let listKey = null;
  for (const raw of String(text || "").split(/\r?\n/)) {
    const line = raw.replace(/\t/g, "  ");
    if (!line.trim() || line.trim().startsWith("#")) continue;
    if (/^Metroid Bread:\s*$/.test(line.trim()) || /^"Metroid Bread":\s*$/.test(line.trim())) {
      inDread = true;
      listKey = null;
      continue;
    }
    if (!/^\s/.test(line) && line.includes(":")) {
      inDread = false;
      listKey = null;
      const idx = line.indexOf(":");
      const key = line.slice(0, idx).trim();
      let val = line.slice(idx + 1).trim();
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1);
      }
      if (key === "name" || key === "game" || key === "description") {
        result[key] = val;
      }
      continue;
    }
    if (!inDread) continue;

    const listItem = line.match(/^\s+-\s+(.*)$/);
    if (listItem && listKey) {
      let val = listItem[1].trim();
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1);
      }
      if (!Array.isArray(dread[listKey])) dread[listKey] = [];
      dread[listKey].push(val);
      continue;
    }

    const m = line.match(/^\s+([A-Za-z0-9_]+):\s*(.*)$/);
    if (!m) continue;
    const key = m[1];
    let val = m[2].trim();
    if (val === "") {
      listKey = key;
      dread[key] = [];
      continue;
    }
    listKey = null;
    if (val === "[]") {
      dread[key] = [];
      continue;
    }
    if (val === "{}") continue;
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    } else if (val === "true") val = true;
    else if (val === "false") val = false;
    else if (/^-?\d+$/.test(val)) val = parseInt(val, 10);
    dread[key] = val;
  }

  // Legacy Hub DNA → required_dna
  if (dread.required_dna == null && dread.game_goal === "dna_hunt") {
    const count = Number(dread.dna_count);
    if (Number.isFinite(count) && count > 0) dread.required_dna = count;
    else dread.required_dna = 8;
    dread.game_goal = "defeat_raven_beak";
  }
  if (dread.game_goal === "dna_hunt") dread.game_goal = "defeat_raven_beak";
  delete dread.dna_count;
  delete dread.dna_required;

  result["Metroid Bread"] = dread;
  return result;
}

function loadYamlFile(filePath) {
  const p = filePath || loadConfig().yaml_path;
  if (!p || !fs.existsSync(p)) {
    return { ok: true, path: p || "", config: defaultYamlConfig() };
  }
  try {
    const text = fs.readFileSync(p, "utf8");
    return { ok: true, path: p, config: parseSimpleYaml(text) };
  } catch (err) {
    return { ok: false, error: String(err.message || err), config: defaultYamlConfig() };
  }
}

function saveYamlFile(opts = {}) {
  const config = opts.config || defaultYamlConfig();
  let filePath = opts.path || loadConfig().yaml_path;
  if (!filePath) {
    fs.mkdirSync(PLAYERS_DIR, { recursive: true });
    filePath = path.join(PLAYERS_DIR, `${config.name || "dread_player"}_dread.yaml`);
  }
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, configToYaml(config), "utf8");
    saveConfig({ yaml_path: filePath, slot: config.name || loadConfig().slot });
    return { ok: true, path: filePath };
  } catch (err) {
    return { ok: false, error: String(err.message || err) };
  }
}

/* ---------- Apworld updater (GitHub Releases) ---------- */

function runApworldUpdater(actionArgs, { timeoutMs = 180000 } = {}) {
  const launcher = findPythonLauncher();
  if (!launcher) {
    return {
      ok: false,
      update_available: false,
      message: pythonMissingError(),
      error: "python_missing",
    };
  }
  if (!fs.existsSync(APWORLD_UPDATER_SCRIPT)) {
    return {
      ok: false,
      update_available: false,
      message: `apworld_updater.py not found:\n${APWORLD_UPDATER_SCRIPT}`,
      error: "script_missing",
    };
  }
  const result = spawnSync(
    launcher.cmd,
    [
      ...launcher.prefixArgs,
      APWORLD_UPDATER_SCRIPT,
      "--json",
      "--world-dir",
      WORLD_DIR,
      ...actionArgs,
    ],
    {
      cwd: WORLD_DIR,
      encoding: "utf8",
      timeout: timeoutMs,
      windowsHide: true,
      env: pythonSpawnEnv(),
    }
  );
  const stdout = String(result.stdout || "").trim();
  const stderr = String(result.stderr || "").trim();
  if (result.error) {
    return {
      ok: false,
      update_available: false,
      message: String(result.error.message || result.error),
      error: "spawn_failed",
      detail: stderr,
    };
  }
  // Last JSON object on stdout (ignore log lines if any).
  let payload = null;
  const lines = stdout.split(/\r?\n/).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      payload = JSON.parse(lines[i]);
      break;
    } catch (_err) {
      /* keep scanning */
    }
  }
  if (!payload || typeof payload !== "object") {
    return {
      ok: false,
      update_available: false,
      message: stdout || stderr || `Updater exited ${result.status}`,
      error: "bad_json",
    };
  }
  return payload;
}

function checkApworldUpdate() {
  try {
    return runApworldUpdater(["check"], { timeoutMs: 30000 });
  } catch (err) {
    return {
      ok: false,
      update_available: false,
      message: String(err.message || err),
      error: "check_exception",
    };
  }
}

function installApworldUpdate(opts = {}) {
  try {
    const args = ["install"];
    if (opts.url) {
      args.push("--url", String(opts.url));
    }
    if (opts.expectedVersion) {
      args.push("--expected-version", String(opts.expectedVersion));
    }
    return runApworldUpdater(args, { timeoutMs: 300000 });
  } catch (err) {
    return {
      ok: false,
      message: String(err.message || err),
      error: "install_exception",
    };
  }
}

async function promptApworldUpdateIfAvailable({ interactiveIfCurrent = false } = {}) {
  const check = checkApworldUpdate();
  if (!check || check.error === "network_or_prerelease" || check.error === "python_missing") {
    // Soft-fail: never block Hub startup on network / missing Python.
    if (interactiveIfCurrent && check && check.message) {
      await dialog.showMessageBox(mainWindow || undefined, {
        type: "info",
        title: "Apworld update check",
        message: check.message,
        buttons: ["OK"],
      });
    }
    return check;
  }
  if (!check.update_available) {
    if (interactiveIfCurrent) {
      await dialog.showMessageBox(mainWindow || undefined, {
        type: "info",
        title: "Apworld update",
        message: check.message || "Up to date.",
        buttons: ["OK"],
      });
    }
    return check;
  }

  const { response } = await dialog.showMessageBox(mainWindow || undefined, {
    type: "question",
    title: "Apworld update available",
    message: check.message || "A newer metroid_bread.apworld is available.",
    detail: "Download and install from GitHub Releases?",
    buttons: ["Yes", "Not now", "Open releases page"],
    defaultId: 0,
    cancelId: 1,
  });

  if (response === 2) {
    await shell.openExternal(check.releases_url || APWORLD_RELEASES_URL);
    return check;
  }
  if (response !== 0) {
    return check;
  }

  const installed = installApworldUpdate({
    url: check.download_url,
    expectedVersion: check.remote_version,
  });
  await dialog.showMessageBox(mainWindow || undefined, {
    type: installed && installed.ok ? "info" : "error",
    title: installed && installed.ok ? "Update installed" : "Update failed",
    message: (installed && installed.message) || "Unknown result",
    buttons: ["OK"],
  });
  return { check, installed };
}

/* ---------- App lifecycle / IPC ---------- */

app.whenReady().then(() => {
  try {
    getLogsDir();
    appendHubLogFile(
      `\n${"=".repeat(72)}\n` +
        `[${new Date().toISOString()}] Hub start\n` +
        `install_root: ${INSTALL_ROOT}\n` +
        `world_dir: ${WORLD_DIR}\n` +
        `ap_root: ${AP_ROOT}\n` +
        `hub_log: ${getHubLogPath()}\n`
    );
  } catch (_) {
    /* ignore */
  }
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
  // Async startup update check — non-blocking after window exists.
  setTimeout(() => {
    promptApworldUpdateIfAvailable({ interactiveIfCurrent: false }).catch((err) => {
      console.warn("Apworld startup update check failed:", err);
    });
  }, 2500);
});

app.on("window-all-closed", () => {
  stopClient();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  stopClient();
  cancelPatch();
});

ipcMain.handle("get-config", () => {
  const cfg = loadConfig();
  cfg.mod_compatibility = normalizeModCompatibility(cfg.mod_compatibility);
  if (cfg.mod_compatibility === "ryujinx") {
    if (!cfg.output_path || !fs.existsSync(path.dirname(cfg.output_path))) {
      cfg.output_path = detectDefaultRyujinxOutput();
      cfg.ryujinx_output_path = cfg.output_path;
    }
  }
  return cfg;
});
ipcMain.handle("save-config", (_e, partial) => saveConfig(partial || {}));
ipcMain.handle("open-logs-folder", () => openLogsFolder());
ipcMain.handle("append-hub-log", (_e, text) => {
  const stamp = new Date().toISOString().replace(/\..+$/, "");
  const body = String(text || "").replace(/\r?\n$/, "");
  if (!body) return { ok: true, path: getHubLogPath() };
  appendHubLogFile(`[${stamp}] UI ${body}\n`);
  return { ok: true, path: getHubLogPath() };
});
ipcMain.handle("get-logs-dir", () => ({ ok: true, path: getLogsDir(), hubLog: getHubLogPath() }));
ipcMain.handle("check-apworld-update", () => checkApworldUpdate());
ipcMain.handle("install-apworld-update", (_e, opts) =>
  installApworldUpdate(opts || {})
);
ipcMain.handle("prompt-apworld-update", (_e, opts) =>
  promptApworldUpdateIfAvailable({
    interactiveIfCurrent: Boolean(opts && opts.interactiveIfCurrent),
  })
);
ipcMain.handle("start-client", (_e, opts) => startClient(opts || {}));
ipcMain.handle("probe-room-info", (_e, server) => probeRoomInfo(server || ""));
ipcMain.handle("stop-client", () => {
  stopClient();
  return { ok: true };
});
ipcMain.handle("send-command", (_e, text) => sendCommand(text));
ipcMain.handle("get-status", () => latestStatus);
ipcMain.handle("is-running", () => Boolean(clientProcess));
ipcMain.handle("open-tracker", () => openTrackerWindow());
ipcMain.handle("get-tracker-catalog", () => {
  try {
    return readJsonFile(CATALOG_PATH);
  } catch (err) {
    return {
      error: String(err.message || err),
      regions: [],
      item_rows: [],
      items: [],
      locations: [],
      id_to_codes: {},
    };
  }
});
ipcMain.handle("get-tracker-status", () => trackerPayloadFromStatus(latestStatus));

ipcMain.handle("load-singleplayer-zip", (_e, zipPath) => loadSingleplayerZip(zipPath));
ipcMain.handle("prepare-patch-files", async (_e, opts) => preparePatchFiles(opts || {}));
ipcMain.handle("get-prepared-seed", () => preparedSeed);
ipcMain.handle("run-patch", async (_e, opts) => runPatch(opts || {}));
ipcMain.handle("cancel-patch", () => cancelPatch());
ipcMain.handle("launch-ryujinx", (_e, opts) => launchRyujinx(opts || {}));

ipcMain.handle("pick-folder", async (_e, title) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: title || "Select Folder",
    properties: ["openDirectory"],
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

ipcMain.handle("pick-file", async (_e, opts) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: opts?.title || "Select File",
    properties: ["openFile"],
    filters: opts?.filters || [{ name: "All Files", extensions: ["*"] }],
    defaultPath: opts?.defaultPath || undefined,
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

ipcMain.handle("pick-spoiler", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Select Spoiler (.txt) or Archipelago seed (.zip)",
    properties: ["openFile"],
    filters: [
      { name: "Archipelago seed / spoiler", extensions: ["zip", "txt"] },
      { name: "ZIP", extensions: ["zip"] },
      { name: "Spoiler text", extensions: ["txt"] },
      { name: "All Files", extensions: ["*"] },
    ],
    defaultPath: loadConfig().games_folder || DEFAULT_OUTPUT_SCAN,
  });
  if (result.canceled || !result.filePaths.length) return null;
  const chosen = result.filePaths[0];
  if (/\.zip$/i.test(chosen)) {
    const extracted = extractSpoilerFromZip(chosen);
    if (!extracted.ok) return extracted;
    preparedSeed = attachPlayerInfo(
      {
        ok: true,
        spoilerPath: extracted.spoilerPath,
        zipPath: extracted.zipPath,
        gameName: extracted.gameName,
        gameFolder: extracted.zipPath,
        createdAtLocal: extracted.createdAtLocal,
        source: "zip",
      },
      loadConfig().slot
    );
    return preparedSeed;
  }
  preparedSeed = attachPlayerInfo(
    {
      ok: true,
      spoilerPath: chosen,
      zipPath: null,
      gameName: path.basename(path.dirname(chosen)),
      gameFolder: path.dirname(chosen),
      source: "file",
    },
    loadConfig().slot
  );
  return preparedSeed;
});

ipcMain.handle("load-yaml", (_e, filePath) => loadYamlFile(filePath));
ipcMain.handle("save-yaml", (_e, opts) => saveYamlFile(opts || {}));
ipcMain.handle("pick-yaml-save", async (_e, suggestedName) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    title: "Save YAML",
    defaultPath: path.join(
      PLAYERS_DIR,
      suggestedName || "dread_player.yaml"
    ),
    filters: [{ name: "YAML", extensions: ["yaml", "yml"] }],
  });
  if (result.canceled || !result.filePath) return null;
  return result.filePath;
});
ipcMain.handle("pick-yaml-open", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Open YAML",
    properties: ["openFile"],
    filters: [{ name: "YAML", extensions: ["yaml", "yml"] }],
    defaultPath: PLAYERS_DIR,
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

const YAML_SPHERE0_CATALOGUE = path.join(
  WORLD_DIR,
  "logic_database",
  "start_sphere0_catalogue.json"
);
const YAML_PROBE_SCRIPT = path.join(WORLD_DIR, "start_sphere0_probe.py");
const TRICK_OPTION_KEYS = [
  "knowledge_tricks",
  "movement_tricks",
  "combat_tricks",
  "slide_jump",
  "wall_jump_tricks",
  "infinite_bomb_jump",
  "water_bomb_jump",
  "water_space_jump",
  "single_wall_wall_jump",
  "diagonal_bomb_jump",
  "cross_bomb_launch",
  "grapple_movement",
  "speedbooster_conservation",
  "short_boost",
  "flash_shift_skip",
  "heat_cold_runs",
  "climb_sloped_tunnels",
  "climb_sloped_surfaces",
  "floor_clip",
  "damage_boost",
  "pseudo_wave",
  "diffusion_abuse",
  "stand_on_frozen_enemy",
  "cross_bomb_skip",
  "ledge_warp",
];

function yamlProbeAllTricksDisabled(tricks) {
  if (!tricks || typeof tricks !== "object") return true;
  return TRICK_OPTION_KEYS.every((k) => Number(tricks[k] || 0) === 0);
}

function yamlProbeDoorsOff(opts) {
  const doors = String(opts.door_lock_rando || "vanilla").toLowerCase();
  const transport = String(opts.transport_rando || "off").toLowerCase();
  const doorsOff = ["vanilla", "off", "0"].includes(doors);
  const transportOff = ["off", "0", "vanilla"].includes(transport);
  return doorsOff && transportOff;
}

function formatTrickAlt(entries) {
  if (!Array.isArray(entries) || !entries.length) return "";
  return entries
    .map((e) => {
      const name = (e && (e.display || e.key)) || "?";
      const lvl = (e && (e.level_name || e.level)) || "?";
      return `${name} at ${lvl}+`;
    })
    .join(", ");
}

/** Keep in sync with worlds/metroid_bread/yaml_option_conflicts.py */
function yamlEffectiveEnergyTanks(opts) {
  const tanks = Math.max(0, Number(opts.energy_tanks) || 0);
  const parts = Math.max(0, Number(opts.energy_parts) || 0);
  const immediate = opts.immediate_energy_parts !== false && Number(opts.immediate_energy_parts) !== 0;
  return immediate ? tanks + parts : tanks + Math.floor(parts / 4);
}

/** Same peak-HP formula as MetroidBreadWorld._max_obtainable_energy */
function yamlMaxObtainableEnergy(opts) {
  const ept = Math.max(1, Number(opts.energy_per_tank != null ? opts.energy_per_tank : 100) || 100);
  const tanks = Math.max(0, Number(opts.energy_tanks != null ? opts.energy_tanks : 8) || 0);
  const parts = Math.max(0, Number(opts.energy_parts != null ? opts.energy_parts : 16) || 0);
  return Math.floor(ept - 1 + tanks * ept + parts * (ept / 4));
}

/** Raven Beak / Gold Chozo-style Damage gate still required at this Combat level */
function yamlCombatBossEnergyNeed(combat) {
  if (combat <= 0) return 799;
  if (combat === 1) return 549;
  if (combat === 2) return 299;
  return 0;
}

function yamlOptionConflicts(opts) {
  const tricks = opts.tricks || {};
  const combat =
    tricks.combat_tricks != null
      ? Number(tricks.combat_tricks) || 0
      : opts.combat_tricks != null
        ? Number(opts.combat_tricks) || 0
        : 1;
  const heatCold =
    tricks.heat_cold_runs != null
      ? Number(tricks.heat_cold_runs) || 0
      : Number(opts.heat_cold_runs) || 0;
  const tanks = Math.max(0, Number(opts.energy_tanks != null ? opts.energy_tanks : 8) || 0);
  const parts = Math.max(0, Number(opts.energy_parts != null ? opts.energy_parts : 16) || 0);
  const ept = Math.max(0, Number(opts.energy_per_tank != null ? opts.energy_per_tank : 100) || 0);
  const missiles = Math.max(
    0,
    Number(opts.starting_missiles != null ? opts.starting_missiles : 15) || 0
  );
  const values = {
    energy_tanks: tanks,
    energy_parts: parts,
    energy_per_tank: ept,
    immediate_energy_parts:
      opts.immediate_energy_parts === false || Number(opts.immediate_energy_parts) === 0
        ? 0
        : 1,
  };
  const effective = yamlEffectiveEnergyTanks(values);
  const maxEnergy = yamlMaxObtainableEnergy(values);
  const energyNeed = yamlCombatBossEnergyNeed(combat);
  const out = [];

  if (energyNeed > 0 && maxEnergy < energyNeed) {
    const combatLabel =
      combat <= 0 ? "Disabled" : combat === 1 ? "Beginner" : "Intermediate";
    const genNote =
      combat <= 0
        ? " Generation may raise Energy Per Tank or force Combat Beginner."
        : "";
    out.push({
      id: "energy_pool_below_combat_gate",
      severity: "warning",
      title: "Energy pool too low for Combat setting",
      message:
        `Max energy from the pool is ~${maxEnergy}, but Combat ${combatLabel} still expects ` +
        `>=${energyNeed} for hard boss Damage gates (e.g. Raven Beak / Gold Chozo).${genNote}`,
      fix: "Raise Energy Tanks/Parts or Energy Per Tank, or raise Combat.",
      fields: ["combat_tricks", "energy_tanks", "energy_parts", "energy_per_tank"],
    });
  }

  if (combat === 0 && effective < 4) {
    out.push({
      id: "combat_energy_starved",
      severity: "warning",
      title: "Combat Disabled with low energy pool",
      message:
        `Combat is Disabled while the energy pool is thin (~${effective} tank-equivalent(s)). ` +
        "Early bosses may need Energy in logic without Combat Beginner skips.",
      fix: "Set Combat to Beginner (default), or raise Energy Tanks/Parts.",
      fields: ["combat_tricks", "energy_tanks", "energy_parts"],
    });
  }
  if (combat <= 1 && tanks === 0 && parts === 0) {
    out.push({
      id: "combat_energy_empty",
      severity: "warning",
      title: "No energy in the item pool",
      message:
        "Energy Tanks and Energy Parts are both 0 while Combat is Disabled or Beginner - " +
        "bosses/heat have no energy upgrades.",
      fix: "Add Energy Tanks/Parts, or raise Combat above Beginner.",
      fields: ["combat_tricks", "energy_tanks", "energy_parts"],
    });
  }
  if (combat <= 1 && ept < 50) {
    out.push({
      id: "energy_per_tank_low",
      severity: "warning",
      title: "Low Energy Per Tank with low Combat",
      message:
        `Energy Per Tank is ${ept} while Combat is Disabled/Beginner - ` +
        "boss and heat/cold checks stay painful.",
      fix: "Raise Energy Per Tank (default 100) or raise Combat.",
      fields: ["combat_tricks", "energy_per_tank"],
    });
  }
  if (missiles === 0) {
    out.push({
      id: "starting_missiles_zero",
      severity: "warning",
      title: "Starting Missiles is 0",
      message:
        "Starting Missiles is 0 - early missile doors and combat have no ammo until tanks are found.",
      fix: "Set Starting Missiles to at least 15 (default) unless intentional.",
      fields: ["starting_missiles"],
    });
  }
  if (heatCold >= 2 && effective < 4) {
    out.push({
      id: "heat_cold_energy",
      severity: "warning",
      title: "Heat/Cold Runs with low energy pool",
      message:
        `Heat/Cold Runs is Intermediate+ while the energy pool is thin (~${effective} tank-equivalent(s)).`,
      fix: "Raise Energy Tanks/Parts, or lower Heat/Cold Runs.",
      fields: ["heat_cold_runs", "energy_tanks", "energy_parts"],
    });
  }
  const heatDps = Math.max(
    0,
    Number(opts.constant_heat_damage != null ? opts.constant_heat_damage : 20) || 0
  );
  const coldDps = Math.max(
    0,
    Number(opts.constant_cold_damage != null ? opts.constant_cold_damage : 20) || 0
  );
  if (heatCold >= 1 && effective < 4 && (heatDps > 20 || coldDps > 20)) {
    const hot = [];
    if (heatDps > 20) hot.push(`heat ${heatDps}`);
    if (coldDps > 20) hot.push(`cold ${coldDps}`);
    out.push({
      id: "heat_cold_dps_energy",
      severity: "warning",
      title: "High env DPS with Heat/Cold Runs and thin energy",
      message:
        `Heat/Cold Runs is on with constant ${hot.join(" / ")} DPS (>20) and a thin energy pool ` +
        `(~${effective} tank-equivalent(s)).`,
      fix:
        "Lower Constant Heat/Cold DPS to <=20, raise Energy Tanks/Parts, or disable Heat/Cold Runs.",
      fields: [
        "heat_cold_runs",
        "constant_heat_damage",
        "constant_cold_damage",
        "energy_tanks",
        "energy_parts",
      ],
    });
  }
  const damageBoost =
    tricks.damage_boost != null
      ? Number(tricks.damage_boost) || 0
      : Number(opts.damage_boost) || 0;
  if (damageBoost >= 2 && effective < 4) {
    out.push({
      id: "damage_boost_energy",
      severity: "warning",
      title: "Damage Boost with low energy pool",
      message:
        `Damage Boost is Intermediate+ while the energy pool is thin (~${effective} tank-equivalent(s)) ` +
        "- knockback routes spend health.",
      fix: "Raise Energy Tanks/Parts, or lower Damage Boost.",
      fields: ["damage_boost", "energy_tanks", "energy_parts"],
    });
  }
  const immediateOn =
    opts.immediate_energy_parts !== false && Number(opts.immediate_energy_parts) !== 0;
  if (!immediateOn && parts < 4) {
    out.push({
      id: "immediate_parts_off_low",
      severity: "warning",
      title: "Immediate Energy Parts off with few parts",
      message:
        `Immediate Energy Parts is off and Energy Parts is ${parts} ` +
        "(need 4 fragments for one tank-equivalent).",
      fix: "Enable Immediate Energy Parts, or set Energy Parts to at least 4.",
      fields: ["immediate_energy_parts", "energy_parts"],
    });
  }

  const access = String(opts.accessibility || "items").trim().toLowerCase();
  if (access === "minimal") {
    out.push({
      id: "accessibility_minimal_upgrade",
      severity: "warning",
      title: "Accessibility Minimal upgrades to Items",
      message:
        "Accessibility Minimal is upgraded to Items during generation " +
        "(Metroid Bread victory clearance).",
      fix: "Set Accessibility to Items (same effective result) or Full.",
      fields: ["accessibility"],
    });
  }

  return out;
}

function mergeYamlConflicts(result, conflicts) {
  if (!result || typeof result !== "object") return result;
  const out = { ...result, conflicts: Array.isArray(conflicts) ? conflicts : [] };
  if (!out.conflicts.length) return out;
  const sev = String(out.severity || "ok");
  const hasError = out.conflicts.some((c) => String(c.severity || "") === "error");
  const bullets = out.conflicts.map((c) => `* ${c.message}`).join(" ");
  const base = String(out.message || "");
  const err = out.conflicts.find((c) => String(c.severity || "") === "error");
  if (hasError) {
    out.severity = "error";
    out.title = (err && err.title) || out.conflicts[0].title || "Option conflicts";
    out.message =
      sev === "ok"
        ? `${base} ${bullets}`.trim()
        : `${base} Also: ${out.conflicts.map((c) => c.title).join("; ")}.`.trim();
    if (!out.fix) out.fix = (err && err.fix) || out.conflicts[0].fix || "";
  } else if (sev === "ok") {
    out.severity = "warning";
    out.title = "Option conflicts";
    out.message = `${base} ${bullets}`.trim();
    if (!out.fix) out.fix = out.conflicts[0].fix || "";
  } else {
    const summary = out.conflicts.map((c) => c.title).join("; ");
    out.message = `${base} Also: ${summary}.`.trim();
  }
  return out;
}

function evaluateFromCatalogue(opts) {
  if (!fs.existsSync(YAML_SPHERE0_CATALOGUE)) return null;
  let catalog;
  try {
    catalog = readJsonFile(YAML_SPHERE0_CATALOGUE);
  } catch (_) {
    return null;
  }
  const starts = Array.isArray(catalog.starts) ? catalog.starts : [];
  const budget = Math.max(0, Math.min(5, Number(opts.starting_kit_items) || 0));
  const key = String(opts.starting_location || "default");

  const byKey = (k) => {
    if (k === "default" || k === "artaria_intro_room_start_point") {
      return starts.find((s) => s.is_default) || starts[0];
    }
    return starts.find((s) => s.option_key === k);
  };

  const severityFor = (row) => {
    if (!row) {
      return {
        ok: false,
        severity: "error",
        title: "Unknown starting location",
        message: `No catalogue entry for ${key}.`,
        fix: "Pick Default or a listed save station.",
        fix_alt: "",
        starting_kit_items: budget,
        starting_location: key,
      };
    }
    const trickAlt = row.trick_alt || null;
    // Catalogue trick_alt opens with Starting Items=0. Still a valid alternative
    // when budget is under min_kit_size (raise items OR enable those tricks).
    const fixAlt =
      budget === 0 || budget < (row.min_kit_size || 0)
        ? formatTrickAlt(trickAlt)
        : "";
    if (!row.meets_min_checks) {
      return {
        ok: true,
        severity: "error",
        title: "Starting location can't open sphere 0",
        message:
          `${row.path} still has only ${row.checks_with_kit} check(s) even with a max Start Kit ` +
          `(need ${catalog.min_start_checks || 2}).`,
        fix: "Pick Default (Artaria Intro) or another open save.",
        fix_alt: fixAlt,
        trick_alt: trickAlt,
        selected: row,
        starting_kit_items: budget,
        starting_location: key,
      };
    }
    if (budget < row.min_kit_size) {
      const items = (row.kit || []).join(", ") || "(none)";
      return {
        ok: true,
        severity: "error",
        title: "Starting Items too low",
        message:
          `${row.path} needs ${row.min_kit_size} Starting Item(s) (${items}); ` +
          `Starting Items is ${budget}.`,
        fix: `Set Starting Items to at least ${row.min_kit_size}, or choose Default (Artaria Intro).`,
        fix_alt: fixAlt,
        trick_alt: trickAlt,
        selected: row,
        starting_kit_items: budget,
        starting_location: key,
      };
    }
    const note =
      row.min_kit_size === 0
        ? `${row.path} opens with ${row.empty_checks} sphere-0 check(s) on empty inventory.`
        : `${row.path} needs kit [${(row.kit || []).join(", ")}]; budget ${budget} is enough.`;
    return {
      ok: true,
      severity: "ok",
      title: "YAML looks good",
      message: `Likely to generate successfully. ${note}`,
      fix: "",
      fix_alt: "",
      selected: row,
      starting_kit_items: budget,
      starting_location: key,
    };
  };

  if (key === "random_save_station") {
    const under = starts.filter((s) => s.meets_min_checks && budget < s.min_kit_size);
    const hard = starts.filter((s) => !s.meets_min_checks);
    const okRows = starts.filter((s) => s.meets_min_checks && budget >= s.min_kit_size);
    if (!okRows.length) {
      const sample = under[0] || hard[0];
      return {
        ok: true,
        severity: "error",
        title: "Starting Items too low for every viable start",
        message: `${under.length + hard.length}/${starts.length} starts need more than Starting Items=${budget}.`,
        fix: "Raise Starting Items or choose Default.",
        fix_alt: sample ? formatTrickAlt(sample.trick_alt) : "",
        trick_alt: sample ? sample.trick_alt : null,
        starts,
        starting_kit_items: budget,
        starting_location: key,
      };
    }
    if (under.length) {
      const examples = under.slice(0, 3).map((s) => s.path).join(", ");
      const need = Math.max(...under.map((s) => s.min_kit_size));
      const sample = under[0];
      const sampleAlt = formatTrickAlt(sample && sample.trick_alt);
      return {
        ok: true,
        severity: "warning",
        title: "Some random starts need more Starting Items",
        message:
          `${under.length} of ${starts.length} starts need more than Starting Items=${budget} ` +
          `(e.g. ${examples}). Random may still pick a viable start.`,
        fix: `Raise Starting Items to ${need} to cover more of the pool, or keep Default.`,
        fix_alt: sampleAlt
          ? `e.g. for ${sample.path}: ${sampleAlt}`
          : "",
        trick_alt: sample ? sample.trick_alt : null,
        starts,
        starting_kit_items: budget,
        starting_location: key,
      };
    }
    return {
      ok: true,
      severity: "ok",
      title: "YAML looks good",
      message:
        `Likely to generate successfully. Random pool: ${okRows.length}/${starts.length} ` +
        `starts open with Starting Items=${budget}.`,
      fix: "",
      fix_alt: "",
      starts,
      starting_kit_items: budget,
      starting_location: key,
    };
  }

  return severityFor(byKey(key));
}

/** In-flight YAML sphere-0 Python probe (async so the Hub UI stays responsive). */
let yamlProbeChild = null;
let yamlProbeToken = 0;

function killYamlProbeProcess() {
  const child = yamlProbeChild;
  yamlProbeChild = null;
  if (!child || child.killed) return;
  try {
    if (process.platform === "win32" && child.pid) {
      spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
        windowsHide: true,
        stdio: "ignore",
      });
    } else {
      child.kill("SIGKILL");
    }
  } catch (_) {
    try {
      child.kill();
    } catch (__) {
      /* ignore */
    }
  }
}

function runYamlProbeProcess(payload) {
  const launcher = findPythonLauncher();
  if (!launcher) {
    return Promise.resolve({
      ok: false,
      severity: "error",
      title: "Python missing",
      message: pythonMissingError(),
      fix: "Install Python 3.11–3.13 for the Hub client.",
      fix_alt: "",
    });
  }
  if (!fs.existsSync(YAML_PROBE_SCRIPT)) {
    return Promise.resolve({
      ok: false,
      severity: "error",
      title: "Probe script missing",
      message: `Not found: ${YAML_PROBE_SCRIPT}`,
      fix: "Reinstall / update the Metroid Bread Hub package.",
      fix_alt: "",
    });
  }

  const token = ++yamlProbeToken;
  killYamlProbeProcess();

  const launchPy = findPythonLauncher() || launcher;
  // -P / PYTHONSAFEPATH: do not prepend the script directory to sys.path.
  // Otherwise world Options.py shadows ap_core Options (circular ImportError).
  const args = [...(launchPy.prefixArgs || []), "-P", YAML_PROBE_SCRIPT];

  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(launchPy.cmd, args, {
        cwd: INSTALL_ROOT,
        env: pythonSpawnEnv({ PYTHONSAFEPATH: "1" }),
        windowsHide: true,
        stdio: ["pipe", "pipe", "pipe"],
      });
    } catch (err) {
      resolve({
        ok: false,
        severity: "error",
        title: "Probe failed to start",
        message: String(err.message || err),
        fix: "Check Hub Python / venv, then retry.",
        fix_alt: "",
      });
      return;
    }

    yamlProbeChild = child;
    let stdout = "";
    let stderr = "";
    let settled = false;

    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (yamlProbeChild === child) yamlProbeChild = null;
      resolve(result);
    };

    const cancelledResult = () => ({
      cancelled: true,
      ok: false,
      severity: "probing",
      title: "",
      message: "",
      fix: "",
      fix_alt: "",
    });

    const timer = setTimeout(() => {
      if (token !== yamlProbeToken) {
        finish(cancelledResult());
        return;
      }
      killYamlProbeProcess();
      finish({
        ok: false,
        severity: "error",
        title: "Probe timed out",
        message: "Sphere-0 probe exceeded 120s.",
        fix: "Simplify YAML options or retry.",
        fix_alt: "",
      });
    }, 120000);

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", (err) => {
      if (token !== yamlProbeToken) {
        finish(cancelledResult());
        return;
      }
      finish({
        ok: false,
        severity: "error",
        title: "Probe failed to start",
        message: String(err.message || err),
        fix: "Check Hub Python / venv, then retry.",
        fix_alt: "",
      });
    });
    child.on("close", () => {
      if (token !== yamlProbeToken) {
        finish(cancelledResult());
        return;
      }
      const out = String(stdout || "").trim();
      const errText = String(stderr || "").trim();
      if (!out) {
        finish({
          ok: false,
          severity: "error",
          title: "Probe returned no data",
          message: errText || "empty stdout",
          fix:
            "Restart Hub after updating Metroid Bread. If this persists, check that ap_core is next to the world (Options circular import) and logic_database is present.",
          fix_alt: "",
        });
        return;
      }
      try {
        // Prefer last non-empty line that parses as a JSON object (ignore banners).
        const lines = out.split(/\r?\n/).filter(Boolean);
        let parsed = null;
        for (let i = lines.length - 1; i >= 0; i--) {
          const line = lines[i].trim();
          if (!line.startsWith("{")) continue;
          try {
            parsed = JSON.parse(line);
            break;
          } catch (_) {
            /* try earlier line */
          }
        }
        if (!parsed) {
          parsed = JSON.parse(lines[lines.length - 1]);
        }
        parsed.source = "probe";
        finish(parsed);
      } catch (err) {
        finish({
          ok: false,
          severity: "error",
          title: "Probe JSON parse failed",
          message: `${err.message}\n${out.slice(0, 400)}`,
          fix: "Update Hub / apworld and retry.",
          fix_alt: "",
        });
      }
    });

    try {
      child.stdin.write(JSON.stringify(payload));
      child.stdin.end();
    } catch (err) {
      killYamlProbeProcess();
      if (token !== yamlProbeToken) {
        finish(cancelledResult());
        return;
      }
      finish({
        ok: false,
        severity: "error",
        title: "Probe failed to start",
        message: String(err.message || err),
        fix: "Check Hub Python / venv, then retry.",
        fix_alt: "",
      });
    }
  });
}

ipcMain.handle("probe-yaml-start-sphere0", async (_e, opts) => {
  const payload = opts && typeof opts === "object" ? opts : {};
  const tricks = payload.tricks || {};
  const doorsOff = yamlProbeDoorsOff(payload);
  const tricksOff = yamlProbeAllTricksDisabled(tricks);
  const access = String(payload.accessibility || "items").trim().toLowerCase();
  // Full accessibility needs a live reachability check (uncleared pickups/events).
  const needsLive = access === "full";

  if (doorsOff && tricksOff && !needsLive) {
    const cached = evaluateFromCatalogue(payload);
    if (cached) {
      cached.source = "catalogue";
      cached.doors_unvalidated = false;
      // Cancel any leftover live probe from a prior tricks-on edit.
      yamlProbeToken += 1;
      killYamlProbeProcess();
      return mergeYamlConflicts(cached, yamlOptionConflicts(payload));
    }
  }

  return runYamlProbeProcess(payload);
});
