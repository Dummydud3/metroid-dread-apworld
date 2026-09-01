(() => {
  const $ = (id) => document.getElementById(id);
  const hub = window.dreadHub;

  const PROGRESSIVE = [
    ["progressive_beams", "Progressive Beams", true],
    ["progressive_charge", "Progressive Charge Beam", true],
    ["progressive_missiles", "Progressive Missiles", false],
    ["progressive_bombs", "Progressive Bombs", true],
    ["progressive_suit", "Progressive Suit", true],
    ["progressive_spin", "Progressive Spin", true],
  ];

  const POOL = [
    ["energy_tanks", "Energy Tanks", 0, 12, 8],
    ["energy_parts", "Energy Parts", 0, 20, 16],
    ["missile_tanks", "Missile Tanks", 10, 50, 35],
    ["missile_plus_tanks", "Missile+ Tanks", 0, 15, 10],
    ["power_bomb_tanks", "Power Bomb Tanks", 0, 15, 12],
    ["speed_booster_upgrade_count", "Speed Booster Upgrade Count", 0, 10, 0],
  ];

  const AMMO = [
    ["energy_per_tank", "Energy Per Tank", 1, 1000, 100],
    ["starting_missiles", "Starting Missiles", 0, 255, 15],
    ["starting_power_bombs", "Starting Power Bombs", 0, 10, 0],
    ["missile_tank_ammo", "Missile Tank Ammo", 1, 50, 2],
    ["missile_plus_tank_ammo", "Missile+ Tank Ammo", 1, 100, 10],
    ["power_bomb_tank_ammo", "Power Bomb Tank Ammo", 1, 10, 1],
  ];

  const FLASH_SHIFT = {
    vanillaKey: "vanilla_flash_shift_behaviour",
    vanillaDefault: true,
    requireMainKey: "flash_shift_upgrade_requires_main_item",
    requireMainDefault: true,
    countKey: "flash_shift_upgrade_count",
    countMin: 1,
    countMax: 5,
    countDefault: 3,
    amountKey: "flash_shift_upgrade_amount",
    amountMin: 1,
    amountMax: 10,
    amountDefault: 1,
    includedKey: "flash_shift_included_ammo",
    includedMin: 0,
    includedMax: 10,
    includedDefault: 2,
  };

  // Defaults match Options.py (DefaultOnToggle vs Toggle).
  const COSMETICS = [
    ["show_boss_lifebar", "Show Boss Lifebar", true],
    ["show_enemy_life", "Show Enemy Life", false],
    ["show_enemy_damage", "Show Enemy Damage", false],
    ["show_player_damage", "Show Player Damage", true],
    ["immediate_energy_parts", "Immediate Energy Parts", true],
    ["enable_death_counter", "Death Counter", true],
    ["show_dna_in_hud", "Show DNA In HUD", true],
    ["nerf_power_bombs", "Nerf Power Bombs", false],
    ["x_starts_released", "X Starts Released", false],
  ];

  const COSMETIC_ENV = [
    ["constant_heat_damage", "Constant Heat DPS", 0, 1000, 20],
    ["constant_cold_damage", "Constant Cold DPS", 0, 1000, 20],
    ["constant_lava_damage", "Constant Lava DPS", 0, 1000, 20],
  ];

  const COSMETIC_CHOICE = [
    [
      "room_name_display",
      "Room Name Display",
      "never",
      [
        ["never", "Never"],
        ["always", "Always"],
        ["with_fade", "With Fade"],
      ],
    ],
    [
      "raven_beak_damage_table",
      "Raven Beak Damage Table",
      "consistent_low",
      [
        ["unmodified", "Unmodified"],
        ["consistent_low", "Consistent Low"],
        ["consistent_high", "Consistent High"],
      ],
    ],
  ];

  const START_FLAGS = [
    ["early_morph_ball", "Early Morph Ball", false],
    ["start_with_pulse_radar", "Start With Pulse Radar", true],
    ["include_boss_pickups", "Include Boss & EMMI Pickups", true],
  ];

  const DNA_FLAGS = [
    ["hint_all_dna", "Hint All Metroid DNA", true],
  ];

  const GAME_GOAL = [
    ["defeat_raven_beak", "Defeat Raven Beak"],
    ["one_hundred_percent", "100%"],
    ["all_bosses", "All Bosses"],
  ];

  const DNA_PLACEMENT = [
    ["prefer_emmi", "Prefer EMMI / Central Unit"],
    ["prefer_bosses", "Prefer Bosses"],
    ["anywhere", "Anywhere"],
  ];

  const DOOR_LOCK = [
    ["vanilla", "Vanilla"],
    ["individual_doors", "Individual Doors"],
  ];

  const TRANSPORT = [
    ["off", "Off"],
    ["randomized", "Randomized"],
  ];

  const LIGHT_REGIONS = [
    "artaria",
    "burenia",
    "cataris",
    "dairon",
    "elun",
    "ferenia",
    "ghavoran",
    "hanubia",
    "itorash",
  ];

  // Align with Options.py valid_keys (RDV change_from / basic change_to).
  // Never offer Sensor / Phase Shift / blast as Change Doors To targets.
  const DOORS_TO_CHANGE_KEYS = [
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
  ];

  const CHANGE_DOORS_TO_KEYS = [
    "Charge Beam Door",
    "Grapple Beam Door",
    "Missile Door",
    "Plasma Beam Door",
    "Power Beam Door",
    "Super Missile Door",
    "Wave Beam Door",
    "Wide Beam Door",
  ];

  const DEFAULT_DOORS_TO_CHANGE = new Set(DOORS_TO_CHANGE_KEYS);

  const DEFAULT_CHANGE_DOORS_TO = new Set(CHANGE_DOORS_TO_KEYS);

  // RDV LayoutTrickLevel names + per-trick used levels from Dread header.json.
  const TRICK_LEVEL_LABEL = {
    disabled: "Disabled",
    beginner: "Beginner",
    intermediate: "Intermediate",
    advanced: "Advanced",
    expert: "Expert",
    ludicrous: "Ludicrous",
  };

  const LEGACY_TRICK_LEVEL = {
    easy: "intermediate",
    medium: "advanced",
    hard: "expert",
  };

  // [key, label, default, allowedLevels]
  const TRICKS = [
    ["combat_tricks", "Combat", "beginner", ["disabled", "beginner", "intermediate", "advanced", "expert", "ludicrous"]],
    ["knowledge_tricks", "Knowledge", "disabled", ["disabled", "beginner", "intermediate", "advanced"]],
    ["movement_tricks", "Movement", "disabled", ["disabled", "beginner", "intermediate", "advanced", "ludicrous"]],
    ["slide_jump", "Slide Jump", "disabled", ["disabled", "beginner", "intermediate", "advanced"]],
    ["wall_jump_tricks", "Wall Jump", "disabled", ["disabled", "beginner", "intermediate", "advanced"]],
    ["infinite_bomb_jump", "Infinite Bomb Jump", "disabled", ["disabled", "beginner", "intermediate", "advanced", "expert", "ludicrous"]],
    ["water_bomb_jump", "Water Bomb Jump", "disabled", ["disabled", "beginner", "intermediate"]],
    ["water_space_jump", "Water Space Jump", "disabled", ["disabled", "beginner", "intermediate", "advanced"]],
    ["single_wall_wall_jump", "Single-wall Wall Jump", "disabled", ["disabled", "intermediate", "advanced", "expert"]],
    ["diagonal_bomb_jump", "Diagonal Bomb Jump", "disabled", ["disabled", "beginner", "intermediate", "advanced", "expert", "ludicrous"]],
    ["cross_bomb_launch", "Cross Bomb Launch", "disabled", ["disabled", "beginner", "intermediate", "advanced"]],
    ["grapple_movement", "Grapple Movement", "disabled", ["disabled", "beginner", "intermediate", "advanced"]],
    ["speedbooster_conservation", "Speed Booster Conservation", "disabled", ["disabled", "beginner", "intermediate", "advanced", "expert"]],
    ["short_boost", "Short Boost", "disabled", ["disabled", "intermediate", "expert"]],
    ["flash_shift_skip", "Flash Shift Skip", "disabled", ["disabled", "beginner", "intermediate"]],
    ["heat_cold_runs", "Heat/Cold Runs", "disabled", ["disabled", "beginner", "intermediate", "advanced"]],
    ["climb_sloped_tunnels", "Climb Sloped Tunnels", "disabled", ["disabled", "beginner", "intermediate", "advanced", "expert"]],
    ["climb_sloped_surfaces", "Climb Sloped Surfaces", "disabled", ["disabled", "beginner", "intermediate", "advanced", "expert"]],
    ["floor_clip", "Floor Clip", "disabled", ["disabled", "intermediate", "advanced", "expert"]],
    ["damage_boost", "Damage Boost", "disabled", ["disabled", "beginner", "intermediate", "advanced"]],
    ["pseudo_wave", "Pseudo-Wave Beam", "disabled", ["disabled", "beginner", "intermediate", "advanced"]],
    ["diffusion_abuse", "Diffusion Abuse", "disabled", ["disabled", "beginner", "intermediate", "advanced", "ludicrous"]],
    ["stand_on_frozen_enemy", "Stand on Frozen Enemy", "disabled", ["disabled", "beginner", "intermediate", "advanced", "expert"]],
    ["cross_bomb_skip", "Cross Bomb Skip", "disabled", ["disabled", "intermediate", "advanced", "expert"]],
    ["ledge_warp", "Ledge Warp", "disabled", ["disabled", "intermediate"]],
  ];

  const state = {
    view: "client",
    stage: "connect",
    running: false,
    apConnected: false,
    gameConnected: false,
    deathlinkOn: false,
    connecting: false,
    roomId: "",
    seedName: "",
    spoilerPath: "",
    zipPath: "",
    playerName: "",
    singleplayer: false,
    patched: false,
    waitingServerSpoiler: false,
    serverSpoilerWaiter: null,
    unsubLog: null,
    unsubStatus: null,
    unsubPatchLog: null,
    unsubPatchProgress: null,
    // Last loaded / saved Metroid Bread YAML block (preserves unknown keys).
    yamlLoadedDread: null,
    // Hub Log: false = hide @@APLOG@@debug@@ / .log-debug lines (default).
    debugLogs: false,
    // Patch output layout: ryujinx | atmosphere
    modCompatibility: "ryujinx",
    ryujinxOutputPath: "",
    atmosphereOutputPath: "",
  };

  const ANSI_RE = /\u001b\[[0-9;]*m/g;

  function normalizeTrickLevel(raw, allowed, fallback) {
    let v = String(raw == null ? "" : raw).toLowerCase();
    if (LEGACY_TRICK_LEVEL[v]) v = LEGACY_TRICK_LEVEL[v];
    // Old Hub "expert" meant max (5 / Ludicrous) when that option existed as top.
    if (v === "expert" && allowed && !allowed.includes("expert") && allowed.includes("ludicrous")) {
      v = "ludicrous";
    }
    if (allowed && allowed.includes(v)) return v;
    return fallback || "disabled";
  }

  function appendCheck(root, key, label, opts = {}) {
    const lab = document.createElement("label");
    lab.className = "check";
    if (opts.span) lab.style.gridColumn = "1 / -1";
    lab.innerHTML = `<input type="checkbox" data-yaml="${key}" ${opts.id ? `id="${opts.id}"` : ""} /><span>${label}</span>`;
    root.appendChild(lab);
    return lab;
  }

  function appendNumber(root, key, label, min, max) {
    const lab = document.createElement("label");
    lab.innerHTML = `${label}<input type="number" data-yaml="${key}" min="${min}" max="${max}" />`;
    root.appendChild(lab);
    return lab;
  }

  function appendSelect(root, key, label, options, opts = {}) {
    const lab = document.createElement("label");
    if (opts.id) lab.id = opts.id;
    const optsHtml = options
      .map(([val, text]) => `<option value="${val}">${text}</option>`)
      .join("");
    lab.innerHTML = `${label}<select data-yaml="${key}" ${opts.selectId ? `id="${opts.selectId}"` : ""}>${optsHtml}</select>`;
    root.appendChild(lab);
    return lab;
  }

  function appendOptionSet(root, key, values, defaults) {
    root.innerHTML = "";
    for (const val of values) {
      const lab = document.createElement("label");
      lab.className = "check";
      const checked = defaults.has(val) ? "checked" : "";
      lab.innerHTML =
        `<input type="checkbox" data-yaml-set="${key}" value="${val.replace(/"/g, "&quot;")}" ${checked} />` +
        `<span>${val}</span>`;
      root.appendChild(lab);
    }
  }

  function readOptionSet(key) {
    return Array.from(document.querySelectorAll(`[data-yaml-set="${key}"]`))
      .filter((el) => el.checked)
      .map((el) => el.value);
  }

  function writeOptionSet(key, values) {
    if (values == null) return; // keep form defaults from buildYamlForm
    const set = new Set(Array.isArray(values) ? values : []);
    document.querySelectorAll(`[data-yaml-set="${key}"]`).forEach((el) => {
      el.checked = set.has(el.value);
    });
  }

  /* ---------- Menu / views ---------- */

  function setView(view) {
    state.view = view;
    $("view-yaml").hidden = view !== "yaml";
    $("view-client").hidden = view !== "client";
    $("view-label").textContent = view === "yaml" ? "YAML Editor" : "Client";
    $("menu-panel").hidden = true;
    $("btn-menu").setAttribute("aria-expanded", "false");
  }

  function setMainLogExpanded(expanded) {
    const wrap = $("main-log-wrap");
    const hint = $("main-log-hint");
    if (!wrap) return;
    wrap.open = !!expanded;
    if (hint) {
      hint.textContent = expanded ? "(click to collapse)" : "(click to expand)";
    }
  }

  function setStage(stage) {
    state.stage = stage;
    $("stage-connect").hidden = stage !== "connect";
    $("stage-patch").hidden = stage !== "patch";
    $("stage-client").hidden = stage !== "client";
    // Patch stage already has its own collapsed log — hide the shared Connect log.
    const mainLog = $("main-log-wrap");
    if (mainLog) {
      mainLog.hidden = stage === "patch";
    }
    // Connect/patch: keep Log minimized so the form stays primary.
    // Post-connect Play stage: open the log by default.
    if (stage !== "patch") {
      setMainLogExpanded(stage === "client");
    }
    hub.saveConfig({ hub_stage: stage }).catch(() => {});
  }

  $("btn-menu").addEventListener("click", () => {
    const panel = $("menu-panel");
    const open = panel.hidden;
    panel.hidden = !open;
    $("btn-menu").setAttribute("aria-expanded", open ? "true" : "false");
  });

  document.addEventListener("click", (e) => {
    if (!$("menu-panel").contains(e.target) && e.target !== $("btn-menu")) {
      $("menu-panel").hidden = true;
      $("btn-menu").setAttribute("aria-expanded", "false");
    }
  });

  document.querySelectorAll(".menu-item").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });

  /* ---------- Logging ---------- */

  function isLogPinnedToBottom(el, slackPx = 64) {
    return el.scrollHeight - el.scrollTop - el.clientHeight <= slackPx;
  }

  function scrollLogIfPinned(el, wasPinned) {
    if (wasPinned) {
      el.scrollTop = el.scrollHeight;
    }
  }

  function applyDebugLogsPreference(enabled) {
    state.debugLogs = Boolean(enabled);
    const logEl = $("log");
    if (logEl) {
      logEl.classList.toggle("show-debug", state.debugLogs);
    }
    const toggle = $("debug-logs");
    if (toggle) {
      toggle.checked = state.debugLogs;
    }
  }

  function appendPlainLine(text, target, level, opts) {
    const el = target || $("log");
    const cleaned = String(text || "").replace(ANSI_RE, "");
    if (!cleaned) return;
    const isDebug = level === "debug";
    const persist = !(opts && opts.persist === false);
    const pin = isLogPinnedToBottom(el);
    if (el.tagName === "PRE") {
      el.textContent += cleaned;
      scrollLogIfPinned(el, pin);
      return;
    }
    const parts = cleaned.split(/\r?\n/);
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      if (part === "" && i === parts.length - 1) continue;
      const line = document.createElement("div");
      line.className = isDebug ? "log-line log-debug" : "log-line";
      line.textContent = part;
      el.appendChild(line);
    }
    scrollLogIfPinned(el, pin);
    // Persist renderer-originated main Log lines (RoomInfo / connect UI).
    // Lines from main-process client-log are already teed to the hub file.
    if (persist && (!target || target === $("log")) && hub.appendHubLog) {
      hub.appendHubLog(cleaned.endsWith("\n") ? cleaned : `${cleaned}\n`).catch(() => {});
    }
  }

  function appendCommandEcho(text) {
    const el = $("log");
    const pin = isLogPinnedToBottom(el);
    const line = document.createElement("div");
    line.className = "log-line log-cmd";
    line.textContent = `> ${text}`;
    el.appendChild(line);
    scrollLogIfPinned(el, pin);
  }

  function handleClientLog(payload) {
    if (!payload) return;
    if (payload.stream === "cmd") {
      appendCommandEcho(payload.text || "");
      return;
    }
    const text = payload.text || "";
    const level = payload.level === "debug" ? "debug" : "normal";
    // Main process already tees these into metroid_bread_hub.log.
    appendPlainLine(text, null, level, { persist: false });
    // Volume modal still ingests AP_VOL even when Debug logs is off.
    ingestVolumeLog(text);
  }

  function appendPrintJson(parts) {
    const el = $("log");
    const pin = isLogPinnedToBottom(el);
    const line = document.createElement("div");
    line.className = "log-line log-chat";
    const list = Array.isArray(parts) ? parts : [];
    for (const part of list) {
      const span = document.createElement("span");
      span.textContent = part && part.text != null ? String(part.text) : "";
      if (part && part.color) {
        span.style.color = `#${part.color}`;
        span.className = "ap-part";
      }
      line.appendChild(span);
    }
    el.appendChild(line);
    scrollLogIfPinned(el, pin);
  }

  function setConnectStatus(msg, isError) {
    const el = $("connect-status");
    el.textContent = msg || "";
    el.style.color = isError ? "var(--danger)" : "var(--muted)";
  }

  function promptForRoomPassword(message, { clear = false } = {}) {
    setStage("connect");
    state.connecting = false;
    state.running = false;
    state.apConnected = false;
    setPill($("pill-ap"), false);
    $("btn-connect").disabled = false;
    if (clear) $("password").value = "";
    setConnectStatus(message || "This room requires a password.", true);
    try {
      $("password").focus({ preventScroll: false });
      $("password").select();
    } catch (_) {
      $("password").focus();
    }
  }

  function isPasswordGateError(st) {
    if (!st) return false;
    if (st.type === "password_required") return true;
    if (st.type !== "ap_error") return false;
    const blob = `${st.error || ""} ${st.detail || ""}`.toLowerCase();
    return blob.includes("password");
  }

  /* ---------- Singleplayer zip dropzone ---------- */
  // Set true to show the Singleplayer ZIP dropzone on the connect screen again.
  const SHOW_SINGLEPLAYER_DROPZONE = false;

  function pathBasename(p) {
    if (!p) return "";
    const parts = String(p).split(/[/\\]/);
    return parts[parts.length - 1] || p;
  }

  function setSingleplayerStatus(msg, isError) {
    const el = $("singleplayer-status");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isError ? "var(--danger)" : "var(--muted)";
  }

  async function handleSingleplayerZip(zipPath) {
    if (!zipPath) return;
    if (!/\.zip$/i.test(zipPath)) {
      setSingleplayerStatus("Please choose a .zip file (Archipelago generated output).", true);
      return;
    }
    if (state.running || state.connecting) {
      setSingleplayerStatus("Disconnect from the server first to use a singleplayer zip.", true);
      return;
    }

    setSingleplayerStatus(`Reading ${pathBasename(zipPath)}…`);
    const result = await hub.loadSingleplayerZip(zipPath);
    if (!result || !result.ok) {
      setSingleplayerStatus((result && result.error) || "Could not read that zip.", true);
      return;
    }

    // Same downstream state the AP-server path fills in via onApConnected(),
    // so runPatch() and the Patch stage behave identically either way.
    state.singleplayer = true;
    state.spoilerPath = result.spoilerPath || "";
    state.zipPath = result.zipPath || "";
    state.seedName = result.gameName || state.seedName;
    state.playerName = result.suggestedPlayer || $("slot").value.trim() || "DreadPlayer";
    if (result.suggestedPlayer) $("slot").value = result.suggestedPlayer;

    const playerNote = result.soloDread
      ? " (solo)"
      : result.suggestedPlayer
        ? ` · player ${result.suggestedPlayer}`
        : "";
    setSingleplayerStatus(`Loaded ${pathBasename(zipPath)}${playerNote}`);
    appendPlainLine(`[app] Singleplayer seed loaded from ${zipPath}${playerNote}\n`);

    $("patch-seed-pill").textContent = `Seed: ${state.seedName || "from zip"}`;
    $("patch-hint").textContent =
      "Loaded from your singleplayer output .zip — no Archipelago server needed. Confirm paths and patch.";
    $("btn-patch").disabled = false;
    // No server to re-download from in singleplayer mode.
    $("btn-redownload").hidden = true;
    setStage("patch");
  }

  const singleplayerDrop = $("singleplayer-drop");
  const singleplayerPanel = singleplayerDrop && singleplayerDrop.closest("section.panel");
  if (!SHOW_SINGLEPLAYER_DROPZONE) {
    if (singleplayerPanel) singleplayerPanel.hidden = true;
  } else if (singleplayerDrop) {
    singleplayerDrop.addEventListener("click", async () => {
      const p = await hub.pickFile({
        title: "Select your generated Archipelago output (.zip)",
        filters: [
          { name: "Archipelago Output", extensions: ["zip"] },
          { name: "All Files", extensions: ["*"] },
        ],
      });
      if (p) handleSingleplayerZip(p);
    });
    singleplayerDrop.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        singleplayerDrop.click();
      }
    });
    ["dragenter", "dragover"].forEach((evt) =>
      singleplayerDrop.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        singleplayerDrop.classList.add("is-dragover");
      })
    );
    ["dragleave", "dragend"].forEach((evt) =>
      singleplayerDrop.addEventListener(evt, (e) => {
        e.preventDefault();
        singleplayerDrop.classList.remove("is-dragover");
      })
    );
    singleplayerDrop.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      singleplayerDrop.classList.remove("is-dragover");
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (!file) return;
      const filePath = hub.getPathForFile(file);
      if (!filePath) {
        setSingleplayerStatus("Could not resolve dropped file path.", true);
        return;
      }
      handleSingleplayerZip(filePath);
    });
  }

  // Prevent Electron's default "navigate to dropped file" behavior anywhere
  // outside the dropzone itself.
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  /* ---------- YAML editor ---------- */

  async function loadStartingLocationOptions() {
    const sel = $("yaml-start");
    if (!sel || sel.dataset.startsLoaded === "1") return;
    try {
      const res = await fetch("starting_locations.json");
      if (!res.ok) return;
      const starts = await res.json();
      for (const s of starts) {
        if (s.default) continue; // covered by "default"
        const opt = document.createElement("option");
        opt.value = s.key;
        opt.textContent = s.label;
        sel.appendChild(opt);
      }
      sel.dataset.startsLoaded = "1";
    } catch (_) {
      /* optional catalog */
    }
  }

  function buildYamlForm() {
    const goal = $("yaml-goal");
    if (goal) {
      goal.innerHTML = "";
      appendSelect(goal, "game_goal", "Game Goal", GAME_GOAL);
    }
    const dna = $("yaml-dna");
    if (dna) {
      dna.innerHTML = "";
      appendNumber(dna, "required_dna", "Required Metroid DNA", 0, 12);
      appendSelect(dna, "dna_placement", "Metroid DNA Placement", DNA_PLACEMENT);
    }
    const dnaFlags = $("yaml-dna-flags");
    if (dnaFlags) {
      dnaFlags.innerHTML = "";
      for (const [key, label] of DNA_FLAGS) appendCheck(dnaFlags, key, label);
    }

    const doors = $("yaml-doors");
    if (doors) {
      doors.innerHTML = "";
      appendSelect(doors, "door_lock_rando", "Door Lock Randomizer", DOOR_LOCK, {
        selectId: "yaml-door-lock",
      });
      appendSelect(doors, "transport_rando", "Transport Randomizer", TRANSPORT);
    }
    appendOptionSet($("yaml-doors-to-change"), "doors_to_change", DOORS_TO_CHANGE_KEYS, DEFAULT_DOORS_TO_CHANGE);
    appendOptionSet($("yaml-change-doors-to"), "change_doors_to", CHANGE_DOORS_TO_KEYS, DEFAULT_CHANGE_DOORS_TO);

    const syncDoorSets = () => {
      const on = $("yaml-door-lock")?.value === "individual_doors";
      const wrap = $("yaml-door-sets");
      if (wrap) wrap.hidden = !on;
    };
    $("yaml-door-lock")?.addEventListener("change", syncDoorSets);
    doors && (doors._syncDoorSets = syncDoorSets);

    const startFlags = $("yaml-start-flags");
    if (startFlags) {
      startFlags.innerHTML = "";
      for (const [key, label] of START_FLAGS) appendCheck(startFlags, key, label);
    }

    const prog = $("yaml-progressive");
    prog.innerHTML = "";
    for (const [key, label] of PROGRESSIVE) appendCheck(prog, key, label);

    const pool = $("yaml-pool");
    pool.innerHTML = "";
    for (const [key, label, min, max] of POOL) appendNumber(pool, key, label, min, max);

    const ammo = $("yaml-ammo");
    if (ammo) {
      ammo.innerHTML = "";
      for (const [key, label, min, max] of AMMO) appendNumber(ammo, key, label, min, max);
    }

    const flash = $("yaml-flash-shift");
    const flashNums = $("yaml-flash-shift-nums");
    if (flash) {
      flash.innerHTML = "";
      appendCheck(flash, FLASH_SHIFT.vanillaKey, "Vanilla Flash Shift Behaviour", {
        id: "yaml-flash-vanilla",
        span: true,
      });
      appendCheck(flash, FLASH_SHIFT.requireMainKey, "Require Main Item", {
        id: "yaml-flash-require",
      });
    }
    if (flashNums) {
      flashNums.innerHTML = "";
      const count = appendNumber(
        flashNums,
        FLASH_SHIFT.countKey,
        "Flash Shift Upgrade Count",
        FLASH_SHIFT.countMin,
        FLASH_SHIFT.countMax
      );
      count.id = "yaml-flash-count-wrap";
      count.querySelector("input").id = "yaml-flash-count";
      const amount = appendNumber(
        flashNums,
        FLASH_SHIFT.amountKey,
        "Flash Shift Upgrade Amount",
        FLASH_SHIFT.amountMin,
        FLASH_SHIFT.amountMax
      );
      amount.id = "yaml-flash-amount-wrap";
      const included = appendNumber(
        flashNums,
        FLASH_SHIFT.includedKey,
        "Flash Shift Included Ammo",
        FLASH_SHIFT.includedMin,
        FLASH_SHIFT.includedMax
      );
      included.id = "yaml-flash-included-wrap";

      const syncFlashDeps = () => {
        const vanilla = Boolean($("yaml-flash-vanilla")?.checked);
        const requireMain = Boolean($("yaml-flash-require")?.checked);
        const requireEl = $("yaml-flash-require");
        if (requireEl) requireEl.disabled = vanilla;
        ["yaml-flash-count", "yaml-flash-amount-wrap", "yaml-flash-count-wrap"].forEach((id) => {
          const el = $(id);
          if (!el) return;
          if (el.tagName === "INPUT") el.disabled = vanilla;
          else {
            const inp = el.querySelector("input");
            if (inp) inp.disabled = vanilla;
            el.style.opacity = vanilla ? "0.45" : "";
          }
        });
        const reqWrap = requireEl?.closest("label");
        if (reqWrap) reqWrap.style.opacity = vanilla ? "0.45" : "";
        // Included ammo used when vanilla OR (non-vanilla + require main).
        const includedWrap = $("yaml-flash-included-wrap");
        const includedInp = includedWrap?.querySelector("input");
        const includedUseful = vanilla || (!vanilla && requireMain);
        if (includedInp) includedInp.disabled = !includedUseful;
        if (includedWrap) includedWrap.style.opacity = includedUseful ? "" : "0.45";
      };
      $("yaml-flash-vanilla")?.addEventListener("change", syncFlashDeps);
      $("yaml-flash-require")?.addEventListener("change", syncFlashDeps);
      flash._syncFlashDeps = syncFlashDeps;
    }

    const cosmetics = $("yaml-cosmetics");
    if (cosmetics) {
      cosmetics.innerHTML = "";
      for (const [key, label] of COSMETICS) appendCheck(cosmetics, key, label);
    }

    const envDmg = $("yaml-cosmetics-env");
    if (envDmg) {
      envDmg.innerHTML = "";
      for (const [key, label, min, max] of COSMETIC_ENV) appendNumber(envDmg, key, label, min, max);
    }

    const cosChoice = $("yaml-cosmetics-choice");
    if (cosChoice) {
      cosChoice.innerHTML = "";
      for (const [key, label, , options] of COSMETIC_CHOICE) {
        appendSelect(cosChoice, key, label, options);
      }
    }

    appendOptionSet($("yaml-disabled-lights"), "disabled_lights", LIGHT_REGIONS, new Set());

    const tricks = $("yaml-tricks");
    tricks.innerHTML = "";
    for (const [key, label, , levels] of TRICKS) {
      const lab = document.createElement("label");
      const opts = levels
        .map((v) => `<option value="${v}">${TRICK_LEVEL_LABEL[v] || v}</option>`)
        .join("");
      lab.innerHTML = `${label}<select data-yaml="${key}">${opts}</select>`;
      tricks.appendChild(lab);
    }

    // Reverse Grapple: Options.py Toggle (RDV only uses Beginner).
    const rev = document.createElement("label");
    rev.className = "check";
    rev.style.gridColumn = "1 / -1";
    rev.innerHTML =
      `<input type="checkbox" data-yaml="reverse_grapple_block" />` +
      `<span>Reverse Grapple Block</span>`;
    tricks.appendChild(rev);

    const syncDnaDeps = () => {
      const n = Number(document.querySelector('[data-yaml="required_dna"]')?.value || 0);
      const on = n > 0;
      ["hint_all_dna", "show_dna_in_hud"].forEach((key) => {
        const el = document.querySelector(`[data-yaml="${key}"]`);
        if (!el) return;
        el.disabled = !on;
        const wrap = el.closest("label");
        if (wrap) wrap.style.opacity = on ? "" : "0.45";
      });
      const place = document.querySelector('[data-yaml="dna_placement"]');
      if (place) {
        place.disabled = !on;
        const wrap = place.closest("label");
        if (wrap) wrap.style.opacity = on ? "" : "0.45";
      }
    };
    document.querySelector('[data-yaml="required_dna"]')?.addEventListener("input", syncDnaDeps);
    dna && (dna._syncDnaDeps = syncDnaDeps);

    if (doors && doors._syncDoorSets) doors._syncDoorSets();
  }

  function defaultForKey(key) {
    const prog = PROGRESSIVE.find((p) => p[0] === key);
    if (prog) return prog[2];
    const cos = COSMETICS.find((p) => p[0] === key);
    if (cos) return cos[2];
    const start = START_FLAGS.find((p) => p[0] === key);
    if (start) return start[2];
    const dna = DNA_FLAGS.find((p) => p[0] === key);
    if (dna) return dna[2];
    if (key === FLASH_SHIFT.vanillaKey) return FLASH_SHIFT.vanillaDefault;
    if (key === FLASH_SHIFT.requireMainKey) return FLASH_SHIFT.requireMainDefault;
    if (key === "death_link") return false;
    if (key === "reverse_grapple_block") return false;
    return null;
  }

  function applyYamlToForm(config) {
    const dread = (config && config["Metroid Bread"]) || {};
    $("yaml-name").value = config.name || "DreadPlayer";

    // Migrate legacy Hub DNA keys → required_dna.
    if (dread.required_dna == null && dread.game_goal === "dna_hunt") {
      const pct = Number(dread.dna_required);
      const count = Number(dread.dna_count);
      if (Number.isFinite(count) && count > 0) dread.required_dna = count;
      else if (Number.isFinite(pct)) dread.required_dna = Math.max(0, Math.round((pct / 100) * 12));
      else dread.required_dna = 8;
      dread.game_goal = "defeat_raven_beak";
    }
    // Drop retired DNA-hunt goal; keep defeat / 100%.
    if (dread.game_goal === "dna_hunt") dread.game_goal = "defeat_raven_beak";

    document.querySelectorAll("[data-yaml]").forEach((el) => {
      const key = el.dataset.yaml;
      let val = dread[key];
      if (el.type === "checkbox") {
        const def = defaultForKey(key);
        el.checked = val != null ? Boolean(val) : Boolean(def);
      } else if (el.tagName === "SELECT") {
        const trick = TRICKS.find((t) => t[0] === key);
        if (trick) {
          el.value = normalizeTrickLevel(val, trick[3], trick[2]);
        } else {
          const choice = COSMETIC_CHOICE.find((c) => c[0] === key);
          if (choice) el.value = val != null ? String(val) : choice[2];
          else if (key === "accessibility") el.value = val != null ? String(val) : "items";
          else if (key === "starting_location") el.value = val != null ? String(val) : "default";
          else if (key === "door_lock_rando") el.value = val != null ? String(val) : "vanilla";
          else if (key === "transport_rando") el.value = val != null ? String(val) : "off";
          else if (key === "dna_placement") el.value = val != null ? String(val) : "prefer_emmi";
          else if (key === "game_goal") el.value = val != null ? String(val) : "defeat_raven_beak";
          else el.value = val != null ? String(val) : el.options[0]?.value;
        }
      } else if (el.type === "number") {
        const defPool = POOL.find((p) => p[0] === key);
        const defAmmo = AMMO.find((p) => p[0] === key);
        const defEnv = COSMETIC_ENV.find((p) => p[0] === key);
        let defVal = null;
        if (key === FLASH_SHIFT.countKey) defVal = FLASH_SHIFT.countDefault;
        else if (key === FLASH_SHIFT.amountKey) defVal = FLASH_SHIFT.amountDefault;
        else if (key === FLASH_SHIFT.includedKey) defVal = FLASH_SHIFT.includedDefault;
        else if (key === "required_dna") defVal = 0;
        else if (defPool) defVal = defPool[4];
        else if (defAmmo) defVal = defAmmo[4];
        else if (defEnv) defVal = defEnv[4];
        el.value = val != null ? val : defVal != null ? defVal : "";
      } else {
        el.value = val != null ? val : "";
      }
    });

    writeOptionSet("doors_to_change", dread.doors_to_change);
    writeOptionSet("change_doors_to", dread.change_doors_to);
    writeOptionSet("disabled_lights", dread.disabled_lights);

    const flashRoot = $("yaml-flash-shift");
    if (flashRoot && flashRoot._syncFlashDeps) flashRoot._syncFlashDeps();
    const doorsRoot = $("yaml-doors");
    if (doorsRoot && doorsRoot._syncDoorSets) doorsRoot._syncDoorSets();
    const dnaRoot = $("yaml-dna");
    if (dnaRoot && dnaRoot._syncDnaDeps) dnaRoot._syncDnaDeps();

    state.yamlLoadedDread = { ...dread };
  }

  function readYamlFromForm() {
    const dread = {
      ...(state.yamlLoadedDread || {}),
      progression_balancing: 50,
    };
    // Drop retired Hub-only DNA-hunt keys; keep game_goal (defeat / 100%).
    if (dread.game_goal === "dna_hunt") dread.game_goal = "defeat_raven_beak";
    delete dread.dna_count;
    delete dread.dna_required;

    document.querySelectorAll("[data-yaml]").forEach((el) => {
      const key = el.dataset.yaml;
      if (el.type === "checkbox") dread[key] = el.checked;
      else if (el.tagName === "SELECT") dread[key] = el.value;
      else if (el.type === "number") dread[key] = Number(el.value);
      else dread[key] = el.value;
    });

    dread.doors_to_change = readOptionSet("doors_to_change");
    dread.change_doors_to = readOptionSet("change_doors_to");
    dread.disabled_lights = readOptionSet("disabled_lights");

    // When door rando is off, keep sets for round-trip but generator ignores them.
    state.yamlLoadedDread = { ...dread };
    return {
      name: $("yaml-name").value.trim() || "DreadPlayer",
      game: "Metroid Bread",
      description: "Metroid Bread player options",
      "Metroid Bread": dread,
    };
  }

  $("yaml-open").addEventListener("click", async () => {
    const path = await hub.pickYamlOpen();
    if (!path) return;
    const result = await hub.loadYaml(path);
    if (!result.ok) {
      $("yaml-status").textContent = result.error || "Failed to load YAML";
      return;
    }
    applyYamlToForm(result.config);
    $("yaml-status").textContent = `Loaded ${path}`;
  });

  $("yaml-save").addEventListener("click", async () => {
    const config = readYamlFromForm();
    let path = await hub.pickYamlSave(`${config.name}_dread.yaml`);
    if (!path) return;
    const result = await hub.saveYaml({ path, config });
    if (!result.ok) {
      $("yaml-status").textContent = result.error || "Failed to save";
      return;
    }
    $("yaml-status").textContent = `Saved ${result.path}`;
    // Convenience: prefill client slot name
    $("slot").value = config.name;
  });

  /* ---------- Client status ---------- */

  function setPill(el, on) {
    el.dataset.state = on ? "on" : "off";
  }

  function formatEta(sec) {
    if (sec == null) return "";
    if (sec < 5) return "ETA <5s";
    if (sec < 60) return `ETA ~${sec}s`;
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `ETA ~${m}m ${s}s`;
  }

  function setProgress(pct, etaSec, label) {
    const p = Math.max(0, Math.min(100, Number(pct) || 0));
    $("progress-fill").style.width = `${p}%`;
    $("progress-pct").textContent = `${Math.round(p)}%`;
    $("progress-eta").textContent = formatEta(etaSec);
    if (label) $("progress-label").textContent = label;
  }

  function applyStatus(st) {
    if (!st) return;

    if (st.type === "print_json") {
      appendPrintJson(st.parts);
      return;
    }
    if (st.type === "ap_error" || st.type === "password_required") {
      // Show the log when connect fails — panel is minimized on the connect screen.
      setMainLogExpanded(true);
      appendPlainLine(`[app] ${st.error || "Archipelago error"}`);
      if (st.detail) appendPlainLine(String(st.detail));
      if (st.exception) appendPlainLine(`[app] Exception: ${st.exception}`);
      if (st.errors) {
        const list = Array.isArray(st.errors) ? st.errors.join(", ") : String(st.errors);
        appendPlainLine(`[app] Server errors: ${list}`);
      }
      if (state.connecting || state.running || st.type === "password_required") {
        // Kill the Python process so the next Connect is not a silent no-op.
        hub.stopClient().catch(() => {});
        if (isPasswordGateError(st)) {
          promptForRoomPassword(
            st.detail ||
              st.error ||
              "This room needs a password. Enter it, then Connect again.",
            { clear: true }
          );
        } else {
          setConnectStatus(st.error || "Connection failed", true);
          state.connecting = false;
          state.running = false;
          state.apConnected = false;
          setPill($("pill-ap"), false);
          $("btn-connect").disabled = false;
        }
      }
      return;
    }
    if (st.type === "ap_disconnect") {
      // Mid-session drop — log loudly but leave autoreconnect / process alone.
      appendPlainLine(`[app] Archipelago disconnected: ${st.error || "connection lost"}`);
      if (st.detail) appendPlainLine(String(st.detail));
      if (st.exception) appendPlainLine(`[app] Exception: ${st.exception}`);
      return;
    }
    if (st.type === "patch_files_progress") {
      setConnectStatus(st.detail || "Downloading seed data from server…");
      appendPlainLine(`[app] ${st.detail || "Downloading seed data…"}`);
      return;
    }
    if (st.type === "patch_files_ready") {
      if (state.serverSpoilerWaiter) {
        state.serverSpoilerWaiter.resolve(st);
        state.serverSpoilerWaiter = null;
      }
      return;
    }
    if (st.type === "patch_files_error") {
      appendPlainLine(`[app] Server patch download: ${st.error || "failed"}`);
      if (state.serverSpoilerWaiter) {
        state.serverSpoilerWaiter.resolve({ error: st.error || "failed" });
        state.serverSpoilerWaiter = null;
      }
      return;
    }
    if (st.type === "seed_mismatch") {
      const detail =
        st.error ||
        "Seed mismatch! Please make sure to patch the game to the right folder.";
      appendPlainLine(`[app] ${detail}`);
      setConnectStatus(detail, true);
      return;
    }
    if (st.type === "room_info" && st.seed_name) {
      state.seedName = st.seed_name;
    }
    if (st.seed_name) state.seedName = st.seed_name;

    if (st.deaths_total != null) $("deaths-total").textContent = String(st.deaths_total);
    if (st.deaths_self != null) $("deaths-self").textContent = String(st.deaths_self);
    if (st.deaths_deathlink != null) $("deaths-dl").textContent = String(st.deaths_deathlink);
    if (st.items_received != null) $("items-recv").textContent = String(st.items_received);
    if (st.checked_locations != null) $("checks-done").textContent = String(st.checked_locations);

    if (st.ap_connected != null) {
      state.apConnected = Boolean(st.ap_connected);
      setPill($("pill-ap"), state.apConnected);
      $("btn-deathlink").disabled = !state.running || !state.apConnected;
      if (state.apConnected && state.connecting) {
        onApConnected(st);
      }
    }
    if (st.game_connected != null) {
      state.gameConnected = Boolean(st.game_connected);
      setPill($("pill-game"), state.gameConnected);
      if (volumeModalOpen) updateVolumeStatusFromConnection();
    }
    if (st.scenario != null) {
      $("pill-scenario").textContent = `Scenario: ${st.scenario || "—"}`;
    }
    if (st.deathlink_enabled != null) {
      state.deathlinkOn = Boolean(st.deathlink_enabled);
      $("btn-deathlink").textContent = state.deathlinkOn ? "DeathLink: ON" : "DeathLink: OFF";
    }
    if (st.stopped) {
      const wasConnecting = state.connecting;
      state.apConnected = false;
      state.gameConnected = false;
      state.running = false;
      state.connecting = false;
      setPill($("pill-ap"), false);
      setPill($("pill-game"), false);
      $("btn-connect").disabled = false;
      // Client crash/exit used to leave the label stuck on "Connecting…".
      if (wasConnecting) {
        setMainLogExpanded(true);
        const msg =
          st.exit_error ||
          (st.exit_code
            ? `Client exited (code ${st.exit_code}). Check the log.`
            : "Disconnected before Archipelago connected.");
        setConnectStatus(msg, true);
        appendPlainLine(`[app] ${msg}`);
        if (st.exit_code != null) {
          appendPlainLine(`[app] Client exit code=${st.exit_code}`);
        }
      }
    }
  }

  function waitForServerSpoiler(timeoutMs = 50000) {
    return new Promise((resolve) => {
      let settled = false;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        if (state.serverSpoilerWaiter && state.serverSpoilerWaiter.resolve === finish) {
          state.serverSpoilerWaiter = null;
        }
        resolve(value);
      };
      state.serverSpoilerWaiter = { resolve: finish };
      setTimeout(() => finish({ error: "Timed out waiting for server placements." }), timeoutMs);
    });
  }

  async function onApConnected(st) {
    if (state.waitingServerSpoiler) return;
    const game = st.game || "";
    if (game && game !== "Metroid Bread") {
      setConnectStatus(`Slot is "${game}", not Metroid Bread.`, true);
      appendPlainLine(`[app] Rejected slot — game is ${game}`);
      await hub.stopClient();
      state.connecting = false;
      state.running = false;
      $("btn-connect").disabled = false;
      return;
    }

    state.waitingServerSpoiler = true;
    state.running = true;
    setConnectStatus("Connected. Asking Archipelago for seed placements…");
    appendPlainLine(
      "[app] Archipelago connected — downloading patch data from the server (no local spoiler needed)."
    );

    const serverResult = await (state._earlyServerSpoilerPromise || waitForServerSpoiler());
    state._earlyServerSpoilerPromise = null;
    state.waitingServerSpoiler = false;
    state.connecting = false;

    if (serverResult && serverResult.spoiler_path) {
      state.spoilerPath = serverResult.spoiler_path;
      state.playerName = $("slot").value.trim();
      $("patch-seed-pill").textContent = `Seed: ${state.seedName || "from server"}`;
      $("patch-hint").textContent =
        "Seed data downloaded from the Archipelago server. Confirm paths and patch.";
      $("btn-patch").disabled = false;
      appendPlainLine(
        `[app] Server seed ready (${serverResult.placement_count || "?"} placements)` +
          (serverResult.has_patch_extras ? " with door/elevator extras." : ".")
      );
      setStage("patch");
      setConnectStatus("");
      return;
    }

    const err = (serverResult && serverResult.error) || "Server did not return seed data.";
    appendPlainLine(`[app] ${err}`);
    state.spoilerPath = "";
    state.playerName = $("slot").value.trim();
    $("patch-seed-pill").textContent = `Seed: ${state.seedName || "download failed"}`;
    $("patch-hint").textContent =
      "Could not download seed data from the server. Use Re-download seed, or disconnect and try again.";
    $("btn-patch").disabled = true;
    setStage("patch");
    setConnectStatus("");
  }

  function normalizeUriPassword(password) {
    if (password == null) return "";
    let text;
    try {
      text = decodeURIComponent(String(password)).trim();
    } catch (_) {
      text = String(password).trim();
    }
    if (!text || text.toLowerCase() === "none" || text.toLowerCase() === "null") {
      return "";
    }
    return text;
  }

  function fillFromServerField() {
    const raw = $("server").value.trim();
    if (!raw) return;

    // Text Client paste: optional ws(s):// + slot:password@host:port, or plain host:port.
    const parsed =
      typeof hub.parseConnectServer === "function"
        ? hub.parseConnectServer(raw)
        : null;
    if (!parsed) {
      // Preload unavailable — keep prior archipelago:// / ws(s):// only behavior.
      const roomMatch = raw.match(/\/room\/([A-Za-z0-9_-]+)/i);
      if (roomMatch) state.roomId = roomMatch[1];
      if (!/^archipelago:\/\//i.test(raw) && !/^wss?:\/\//i.test(raw)) return;
      try {
        const u = new URL(raw.replace(/^archipelago:\/\//i, "http://"));
        if (u.hostname) {
          $("server").value = u.port ? `${u.hostname}:${u.port}` : u.hostname;
        }
        if (u.username) $("slot").value = decodeURIComponent(u.username);
        if (u.password != null) $("password").value = normalizeUriPassword(u.password);
        const room = u.searchParams.get("room");
        if (room) state.roomId = room;
      } catch (_) {
        /* ignore */
      }
      return;
    }

    if (parsed.room) state.roomId = parsed.room;
    if (parsed.server) $("server").value = parsed.server;
    if (parsed.hasUserinfo) {
      // Always prefer userinfo from the server string when present.
      if (parsed.slot) $("slot").value = parsed.slot;
      $("password").value = normalizeUriPassword(parsed.password);
    }
  }

  async function gateOnRoomInfo(server, password) {
    // RoomInfo.password is the only reliable pre-Connect signal (WebHost API has none).
    setConnectStatus("Checking room…");
    appendPlainLine(`[app] RoomInfo probe starting for ${server}`);
    let room;
    try {
      room = await hub.probeRoomInfo(server);
    } catch (err) {
      // Probe failed — fall through to normal Connect (Python client still handles auth).
      appendPlainLine(`[app] RoomInfo probe threw: ${err && err.stack ? err.stack : err}`);
      appendPlainLine("[app] Continuing to Connect — Python client will report the real failure.");
      return { action: "connect", password: normalizeUriPassword(password) };
    }
    if (!room || !room.ok) {
      const err = (room && room.error) || "unknown";
      appendPlainLine(`[app] RoomInfo probe failed: ${err}`);
      if (room && Array.isArray(room.attempts) && room.attempts.length) {
        for (const attempt of room.attempts) {
          appendPlainLine(
            `[app]   tried ${attempt.url || "?"}: ${attempt.error || "failed"}`
          );
        }
      }
      appendPlainLine("[app] Continuing to Connect — Python client will report the real failure.");
      return { action: "connect", password: normalizeUriPassword(password) };
    }
    if (room.seed_name) {
      state.seedName = room.seed_name;
      appendPlainLine(`[app] RoomInfo seed: ${room.seed_name}`);
    }
    if (room.password) {
      appendPlainLine(`[app] RoomInfo: password required (${room.url || "ok"}).`);
    } else {
      appendPlainLine(`[app] RoomInfo: no password required (${room.url || "ok"}).`);
    }
    const decision = room.password && !normalizeUriPassword(password)
      ? { action: "need_password", password: "" }
      : { action: "connect", password: normalizeUriPassword(password) };
    if (decision.action === "need_password") {
      setConnectStatus("This room requires a password.", true);
      setMainLogExpanded(true);
    }
    return decision;
  }

  async function connect() {
    if (state.connecting) return;
    // Prior attempt may still own the Python process (password error, timeout, etc.).
    if (state.running) {
      appendPlainLine("[app] Stopping previous client before Connect…");
      await hub.stopClient();
      state.running = false;
      state.apConnected = false;
      setPill($("pill-ap"), false);
    }
    fillFromServerField();
    const server = $("server").value.trim();
    const slot = $("slot").value.trim();
    if (!server || !slot) {
      setConnectStatus("Server and slot name are required.", true);
      appendPlainLine("[app] Connect aborted: server and slot name are required.");
      setMainLogExpanded(true);
      return;
    }

    // Normalize URI "None"/empty before any Connect decision.
    $("password").value = normalizeUriPassword($("password").value);
    const hasPassword = Boolean(normalizeUriPassword($("password").value));
    appendPlainLine(
      `[app] Connect requested — server=${server} slot=${slot} password=${
        hasPassword ? "set" : "none"
      }`
    );

    state.connecting = true;
    state.patched = false;
    state.singleplayer = false;
    state.waitingServerSpoiler = false;
    $("btn-redownload").hidden = false;
    $("btn-connect").disabled = true;

    const gate = await gateOnRoomInfo(server, $("password").value);
    if (gate.action === "need_password") {
      promptForRoomPassword(
        "This room requires a password. Enter it below, then Connect.",
        { clear: false }
      );
      appendPlainLine("[app] Waiting for room password before Connect.");
      return;
    }

    // Arm waiter before the Python client starts so we never miss patch_files_ready.
    const earlyWait = waitForServerSpoiler(50000);
    setConnectStatus("Connecting…");
    appendPlainLine("[app] Spawning Metroid Bread Python client…");

    if (state.unsubLog) state.unsubLog();
    if (state.unsubStatus) state.unsubStatus();
    state.unsubLog = hub.onLog(handleClientLog);
    state.unsubStatus = hub.onStatus((st) => applyStatus(st));

    const result = await hub.startClient({
      // Bare host:port (or URI) — Hub/CommonClient use ws:// first like Text Client.
      // dread-ip is only for Remote Lua after patch; never used as the AP server.
      server,
      slot,
      password: gate.password,
      dreadIp: $("dread-ip").value.trim() || "127.0.0.1",
      autoConnectDread: false,
    });
    // Stash for onApConnected — it will await the same promise.
    state._earlyServerSpoilerPromise = earlyWait;

    if (!result.ok) {
      setMainLogExpanded(true);
      const err = result.error || "Failed to start client";
      setConnectStatus(err, true);
      appendPlainLine(`[app] Failed to start client: ${err}`);
      state.connecting = false;
      state.running = false;
      state._earlyServerSpoilerPromise = null;
      if (state.serverSpoilerWaiter) {
        state.serverSpoilerWaiter.resolve({ error: err });
        state.serverSpoilerWaiter = null;
      }
      $("btn-connect").disabled = false;
      return;
    }
    if (result.roomId) state.roomId = result.roomId;
    state.running = true;
    appendPlainLine("[app] Python client running — waiting for Archipelago handshake…");

    // Safety timeout if AP never confirms — clear stuck Connecting and free Connect.
    const connectGeneration = (state._connectGeneration =
      (state._connectGeneration || 0) + 1);
    setTimeout(() => {
      if (state._connectGeneration !== connectGeneration) return;
      if (state.connecting && !state.apConnected) {
        setMainLogExpanded(true);
        const timeoutMsg =
          "Timed out waiting for Archipelago. Confirm Server is host:port (not Game IP), " +
          "slot/password match Text Client, then Connect again. Check the log above for spawn/import errors.";
        setConnectStatus(timeoutMsg, true);
        appendPlainLine(`[app] ${timeoutMsg}`);
        state.connecting = false;
        state.running = false;
        $("btn-connect").disabled = false;
        hub.stopClient().catch(() => {});
        if (state.serverSpoilerWaiter) {
          state.serverSpoilerWaiter.resolve({ error: "Timed out connecting to Archipelago." });
          state.serverSpoilerWaiter = null;
        }
        state._earlyServerSpoilerPromise = null;
      }
    }, 20000);
  }

  async function disconnect() {
    await hub.stopClient();
    state.running = false;
    state.connecting = false;
    state.apConnected = false;
    state.gameConnected = false;
    state.spoilerPath = "";
    state.singleplayer = false;
    setPill($("pill-ap"), false);
    setPill($("pill-game"), false);
    $("btn-connect").disabled = false;
    setStage("connect");
    appendPlainLine("[app] Disconnected.");
  }

  /* ---------- Patch stage ---------- */

  function bindPatchLog() {
    if (state.unsubPatchLog) state.unsubPatchLog();
    if (state.unsubPatchProgress) state.unsubPatchProgress();
    state.unsubPatchLog = hub.onPatchLog((payload) => {
      appendPlainLine(payload.text || "", $("patch-log"));
    });
    state.unsubPatchProgress = hub.onPatchProgress((p) => {
      const label =
        p.percent >= 100 ? "Done" : p.percent > 0 ? "Patching…" : "Starting…";
      setProgress(p.percent, p.etaSec, label);
    });
  }

  function normalizeModCompatibility(value) {
    const raw = String(value || "ryujinx").trim().toLowerCase();
    if (["atmosphere", "atmos", "cfw", "switch", "hardware"].includes(raw)) {
      return "atmosphere";
    }
    return "ryujinx";
  }

  function applyModCompatibilityUi(compat, { persist = false } = {}) {
    const next = normalizeModCompatibility(compat);
    state.modCompatibility = next;
    const ryuBtn = $("btn-compat-ryujinx");
    const atmBtn = $("btn-compat-atmosphere");
    if (ryuBtn) ryuBtn.classList.toggle("active", next === "ryujinx");
    if (atmBtn) atmBtn.classList.toggle("active", next === "atmosphere");
    const label = $("output-path-label");
    const hint = $("compat-hint");
    if (next === "atmosphere") {
      if (label) label.textContent = "Atmosphere CFW root (e.g. SD:/atmosphere)";
      if (hint) {
        hint.textContent =
          "Writes contents/010093801237c000/{romfs,exefs} + exefs_patches/DreadRandovania/*.ips under this folder. Custom OdrMap/OdrTip subsdk9 is required for map reachability.";
      }
    } else {
      if (label) label.textContent = "Ryujinx output folder";
      if (hint) {
        hint.textContent =
          "Writes under DreadRandovania/ for the Ryujinx mod folder (usually …/mods/contents/010093801237c000).";
      }
    }
    if (persist) {
      const outputPath = ($("output-path") && $("output-path").value.trim()) || "";
      const partial = {
        mod_compatibility: next,
        output_path: outputPath,
        ryujinx_output_path: state.ryujinxOutputPath || "",
        atmosphere_output_path: state.atmosphereOutputPath || "",
      };
      if (next === "atmosphere") {
        partial.atmosphere_output_path = outputPath || state.atmosphereOutputPath || "";
        state.atmosphereOutputPath = partial.atmosphere_output_path;
      } else {
        partial.ryujinx_output_path = outputPath || state.ryujinxOutputPath || "";
        state.ryujinxOutputPath = partial.ryujinx_output_path;
      }
      hub.saveConfig(partial).catch(() => {});
    }
  }

  async function switchModCompatibility(compat) {
    const next = normalizeModCompatibility(compat);
    const prev = normalizeModCompatibility(state.modCompatibility);
    const currentOut = ($("output-path") && $("output-path").value.trim()) || "";
    if (prev === "atmosphere") {
      state.atmosphereOutputPath = currentOut || state.atmosphereOutputPath || "";
    } else {
      state.ryujinxOutputPath = currentOut || state.ryujinxOutputPath || "";
    }
    const restored =
      next === "atmosphere"
        ? state.atmosphereOutputPath || ""
        : state.ryujinxOutputPath || "";
    if ($("output-path")) $("output-path").value = restored;
    applyModCompatibilityUi(next, { persist: true });
  }

  async function runPatch() {
    if (!$("base-rom").value.trim()) {
      appendPlainLine("Source path is required.", $("patch-log"));
      $("patch-log-wrap").open = true;
      return;
    }
    const outputLabel =
      state.modCompatibility === "atmosphere"
        ? "Atmosphere CFW root"
        : "Ryujinx output folder";
    if (!$("output-path").value.trim()) {
      appendPlainLine(`${outputLabel} is required.`, $("patch-log"));
      $("patch-log-wrap").open = true;
      return;
    }
    if (!state.spoilerPath) {
      appendPlainLine("No seed data from the server yet. Use Re-download seed.", $("patch-log"));
      $("patch-log-wrap").open = true;
      return;
    }

    bindPatchLog();
    $("btn-patch").disabled = true;
    $("btn-cancel-patch").disabled = false;
    setProgress(2, null, "Starting…");
    $("patch-log").textContent = "";

    const modCompatibility = normalizeModCompatibility(state.modCompatibility);
    const outputPath = $("output-path").value.trim();
    if (modCompatibility === "atmosphere") {
      state.atmosphereOutputPath = outputPath;
    } else {
      state.ryujinxOutputPath = outputPath;
    }

    const result = await hub.runPatch({
      spoilerPath: state.spoilerPath,
      baseRomPath: $("base-rom").value.trim(),
      outputPath,
      playerName: state.playerName || $("slot").value.trim(),
      freesink: $("freesink").checked,
      cleanOutput: false,
      modCompatibility,
    });

    $("btn-patch").disabled = false;
    $("btn-cancel-patch").disabled = true;

    if (!result.ok) {
      setProgress(0, null, "Failed");
      $("patch-log-wrap").open = true;
      appendPlainLine(`[app] ${result.error || "Patch failed"}`, $("patch-log"));
      return;
    }

    state.patched = true;
    setProgress(100, 0, "Done");
    appendPlainLine("[app] Patch complete — opening client.", $("patch-log"));
    setStage("client");
  }

  /* ---------- Set Volume modal ---------- */

  const VOLUME_CHANNELS = [
    { id: "vol-master", channel: "master", prop: "fMainVolume" },
    { id: "vol-music", channel: "music", prop: "fMusicVolume" },
    { id: "vol-sfx", channel: "sfx", prop: "fSfxVolume" },
    { id: "vol-env", channel: "env", prop: "fEnvironmentStreamsVolume" },
  ];
  const volumeTimers = Object.create(null);
  let volumeModalOpen = false;
  let volumeSuppressSend = false;

  function setVolumeStatus(text, isError) {
    const el = $("volume-status");
    if (!el) return;
    el.textContent = text;
    el.style.color = isError ? "var(--warn)" : "";
  }

  function clampVolumePercent(raw) {
    const n = Number(raw);
    if (!Number.isFinite(n)) return null;
    return Math.min(100, Math.max(0, Math.round(n * 10) / 10));
  }

  function updateVolumeStatusFromConnection() {
    if (!state.running) {
      setVolumeStatus("Client not running — edits stay local until you connect.", true);
      return;
    }
    if (!state.gameConnected) {
      setVolumeStatus("Not connected to the game — Connect Game first. Edits will not send.", true);
      return;
    }
    setVolumeStatus("Connected — changes send over Remote Lua (tunable + Game.Set*).");
  }

  function ingestVolumeLog(text) {
    if (!volumeModalOpen) return;
    const cleaned = String(text || "").replace(ANSI_RE, "");
    for (const line of cleaned.split(/\r?\n/)) {
      let m = line.match(/AP_VOL:\s*get\s+(music|sfx|env|master)\s+ok\s+val=([0-9.]+)/i);
      if (m) {
        applyVolumeReadback(m[1].toLowerCase(), Number(m[2]));
        continue;
      }
      m = line.match(
        /AP_VOL:\s*tunable-get\s+ok\s+cat=\S+\s+prop=(fMusicVolume|fSfxVolume|fEnvironmentStreamsVolume|fMainVolume)\s+val=([0-9.]+)/i
      );
      if (m) {
        const prop = m[1];
        const ch =
          prop === "fMusicVolume"
            ? "music"
            : prop === "fSfxVolume"
              ? "sfx"
              : prop === "fEnvironmentStreamsVolume"
                ? "env"
                : "master";
        applyVolumeReadback(ch, Number(m[2]));
      }
    }
  }

  function applyVolumeReadback(channel, frac) {
    if (!Number.isFinite(frac)) return;
    const entry = VOLUME_CHANNELS.find((c) => c.channel === channel);
    if (!entry) return;
    const input = $(entry.id);
    if (!input) return;
    const pct = clampVolumePercent(frac * 100);
    if (pct == null) return;
    volumeSuppressSend = true;
    input.value = String(pct);
    volumeSuppressSend = false;
  }

  async function sendVolumeChannel(channel, percent) {
    if (!state.running || !state.gameConnected) {
      updateVolumeStatusFromConnection();
      return;
    }
    const result = await hub.sendCommand(`/volume_set ${channel} ${percent}`);
    if (!result || !result.ok) {
      setVolumeStatus((result && result.error) || "Failed to send volume command.", true);
      return;
    }
    setVolumeStatus(`Sent ${channel} = ${percent}% (tunable + Game.Set*).`);
  }

  function scheduleVolumeSend(channel, percent) {
    if (volumeTimers[channel]) clearTimeout(volumeTimers[channel]);
    volumeTimers[channel] = setTimeout(() => {
      volumeTimers[channel] = null;
      sendVolumeChannel(channel, percent).catch((err) => {
        setVolumeStatus(String(err), true);
      });
    }, 75);
  }

  function openVolumeModal() {
    const modal = $("volume-modal");
    if (!modal) return;
    volumeModalOpen = true;
    modal.hidden = false;
    updateVolumeStatusFromConnection();
    if (state.running && state.gameConnected) {
      setVolumeStatus("Reading current volumes…");
      hub.sendCommand("/volume_get").then((result) => {
        if (!result || !result.ok) {
          setVolumeStatus((result && result.error) || "Could not read volumes.", true);
          return;
        }
        updateVolumeStatusFromConnection();
      });
    }
    const first = $("vol-music");
    if (first) first.focus();
  }

  function closeVolumeModal() {
    const modal = $("volume-modal");
    if (!modal) return;
    volumeModalOpen = false;
    modal.hidden = true;
    for (const key of Object.keys(volumeTimers)) {
      if (volumeTimers[key]) clearTimeout(volumeTimers[key]);
      volumeTimers[key] = null;
    }
  }

  for (const entry of VOLUME_CHANNELS) {
    const input = $(entry.id);
    if (!input) continue;
    const onChange = () => {
      if (volumeSuppressSend) return;
      const pct = clampVolumePercent(input.value);
      if (pct == null) {
        setVolumeStatus("Enter a number from 0 to 100.", true);
        return;
      }
      if (String(pct) !== String(input.value).trim()) {
        volumeSuppressSend = true;
        input.value = String(pct);
        volumeSuppressSend = false;
      }
      scheduleVolumeSend(entry.channel, pct);
    };
    input.addEventListener("input", onChange);
    input.addEventListener("change", onChange);
  }

  $("btn-set-volume").addEventListener("click", () => openVolumeModal());
  document.querySelectorAll("[data-volume-close]").forEach((el) => {
    el.addEventListener("click", () => closeVolumeModal());
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && volumeModalOpen) closeVolumeModal();
  });

  /* ---------- Main client actions ---------- */

  $("btn-connect").addEventListener("click", () => connect());
  $("btn-disconnect").addEventListener("click", () => disconnect());
  $("server").addEventListener("change", fillFromServerField);
  $("server").addEventListener("blur", fillFromServerField);
  // After RoomInfo password gate focuses the field, Enter should retry Connect.
  $("password").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      connect();
    }
  });

  $("btn-browse-rom").addEventListener("click", async () => {
    const p = await hub.pickFolder("Select decompiled Dread / md rando folder");
    if (p) $("base-rom").value = p;
  });
  $("btn-browse-output").addEventListener("click", async () => {
    const atm = state.modCompatibility === "atmosphere";
    const p = await hub.pickFolder(
      atm
        ? "Select Atmosphere CFW root (usually the atmosphere folder on your SD)"
        : "Select Ryujinx mod output folder"
    );
    if (p) {
      $("output-path").value = p;
      if (atm) state.atmosphereOutputPath = p;
      else state.ryujinxOutputPath = p;
      applyModCompatibilityUi(state.modCompatibility, { persist: true });
    }
  });
  $("btn-compat-ryujinx").addEventListener("click", () => {
    switchModCompatibility("ryujinx");
  });
  $("btn-compat-atmosphere").addEventListener("click", () => {
    switchModCompatibility("atmosphere");
  });
  $("btn-patch").addEventListener("click", () => runPatch());
  $("btn-cancel-patch").addEventListener("click", async () => {
    await hub.cancelPatch();
    $("btn-patch").disabled = false;
    $("btn-cancel-patch").disabled = true;
    setProgress(0, null, "Cancelled");
  });
  $("btn-redownload").addEventListener("click", async () => {
    if (!state.running || !state.apConnected) {
      appendPlainLine("Connect to Archipelago first.", $("patch-log"));
      $("patch-log-wrap").open = true;
      return;
    }
    $("btn-redownload").disabled = true;
    $("btn-patch").disabled = true;
    $("patch-hint").textContent = "Re-downloading seed data from the Archipelago server…";
    appendPlainLine("[app] Requesting seed data from server…", $("patch-log"));

    const wait = waitForServerSpoiler(50000);
    await hub.sendCommand("/download_patch");
    const serverResult = await wait;
    $("btn-redownload").disabled = false;

    if (serverResult && serverResult.spoiler_path) {
      state.spoilerPath = serverResult.spoiler_path;
      $("patch-seed-pill").textContent = `Seed: ${state.seedName || "from server"}`;
      $("patch-hint").textContent =
        "Seed data downloaded from the Archipelago server. Confirm paths and patch.";
      $("btn-patch").disabled = false;
      appendPlainLine(
        `[app] Server seed ready (${serverResult.placement_count || "?"} placements).`,
        $("patch-log")
      );
      return;
    }
    $("patch-hint").textContent =
      (serverResult && serverResult.error) ||
      "Re-download failed. Disconnect and connect again.";
    appendPlainLine(`[app] ${(serverResult && serverResult.error) || "Re-download failed"}`, $("patch-log"));
    $("patch-log-wrap").open = true;
  });
  $("btn-skip-patch").addEventListener("click", () => {
    state.patched = true;
    setStage("client");
  });
  $("btn-back-patch").addEventListener("click", () => setStage("patch"));

  $("btn-browse-ryujinx").addEventListener("click", async () => {
    const p = await hub.pickFile({
      title: "Select Ryujinx.exe",
      filters: [
        { name: "Ryujinx", extensions: ["exe"] },
        { name: "All Files", extensions: ["*"] },
      ],
    });
    if (p) $("ryujinx-path").value = p;
  });
  $("btn-browse-rom-file").addEventListener("click", async () => {
    const p = await hub.pickFile({
      title: "Select Metroid Dread ROM",
      filters: [
        { name: "Switch ROM", extensions: ["nsp", "xci"] },
        { name: "All Files", extensions: ["*"] },
      ],
    });
    if (p) $("dread-rom").value = p;
  });

  $("btn-launch").addEventListener("click", async () => {
    const ryujinxPath = $("ryujinx-path").value.trim();
    const dreadRomPath = $("dread-rom").value.trim();
    const partial = { dread_ip: $("dread-ip").value.trim() || "127.0.0.1" };
    if (ryujinxPath) partial.ryujinx_path = ryujinxPath;
    if (dreadRomPath) partial.dread_rom_path = dreadRomPath;
    await hub.saveConfig(partial);
    const result = await hub.launchRyujinx({
      ryujinxPath: ryujinxPath || undefined,
      dreadRomPath: dreadRomPath || undefined,
    });
    if (!result.ok) {
      appendPlainLine(`[app] ${result.error || "Failed to launch Ryujinx"}`);
      return;
    }
    if (result.ryujinx) $("ryujinx-path").value = result.ryujinx;
    if (result.rom) $("dread-rom").value = result.rom;
    const waitSec = Math.round((result.connectDelayMs || 3000) / 1000);
    appendPlainLine(
      `[app] Launched Ryujinx with ${result.rom}\n` +
        `      After ${waitSec}s the client waits passively until RemoteLua (:6969) accepts.\n` +
        `      Tip: stay on the title screen or fully in-game — avoid mid-load if grants stall.`
    );
  });

  $("btn-connect-game").addEventListener("click", async () => {
    const ip = $("dread-ip").value.trim() || "127.0.0.1";
    await hub.sendCommand(`/connect_dread ${ip}`);
  });
  $("btn-deathlink").addEventListener("click", async () => {
    if (!state.apConnected) return;
    await hub.sendCommand(state.deathlinkOn ? "/deathlink off" : "/deathlink on");
  });
  $("btn-tracker").addEventListener("click", async () => {
    const result = await hub.openTracker();
    if (!result.ok) appendPlainLine(`[app] ${result.error || "Failed to open tracker"}`);
  });
  $("btn-clear-log").addEventListener("click", () => {
    $("log").textContent = "";
  });
  // Keep summary actions from toggling the <details>; sync hint on manual open/close.
  const mainLogActions = $("main-log-actions");
  if (mainLogActions) {
    mainLogActions.addEventListener("click", (e) => e.stopPropagation());
  }
  const mainLogWrap = $("main-log-wrap");
  if (mainLogWrap) {
    mainLogWrap.addEventListener("toggle", () => {
      const hint = $("main-log-hint");
      if (hint) {
        hint.textContent = mainLogWrap.open
          ? "(click to collapse)"
          : "(click to expand)";
      }
    });
  }
  $("debug-logs").addEventListener("change", () => {
    applyDebugLogsPreference($("debug-logs").checked);
    hub.saveConfig({ debug_logs: state.debugLogs }).catch(() => {});
  });
  $("btn-open-logs").addEventListener("click", async () => {
    const result = await hub.openLogsFolder();
    if (!result || !result.ok) {
      appendPlainLine(
        `[app] Could not open logs folder: ${(result && result.error) || "unknown"}`
      );
      return;
    }
    if (result.path) {
      appendPlainLine(`[app] Opened logs folder: ${result.path}`);
    }
  });
  $("btn-check-updates").addEventListener("click", async () => {
    appendPlainLine("[app] Checking for apworld updates…");
    try {
      await hub.promptApworldUpdate({ interactiveIfCurrent: true });
    } catch (err) {
      appendPlainLine(`[app] Update check failed: ${err && err.message ? err.message : err}`);
    }
  });
  $("cmd-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("cmd").value.trim();
    if (!text) return;
    const result = await hub.sendCommand(text);
    if (!result.ok) appendPlainLine(`[app] ${result.error}`);
    $("cmd").value = "";
  });

  /* ---------- Boot ---------- */

  async function boot() {
    buildYamlForm();
    await loadStartingLocationOptions();
    const cfg = await hub.getConfig();
    $("server").value = cfg.server || "";
    $("slot").value = cfg.slot || "";
    $("password").value = normalizeUriPassword(cfg.password || "");
    $("dread-ip").value = cfg.dread_ip || "127.0.0.1";
    $("base-rom").value = cfg.base_rom_path || "";
    state.modCompatibility = normalizeModCompatibility(cfg.mod_compatibility);
    state.ryujinxOutputPath =
      cfg.ryujinx_output_path ||
      (state.modCompatibility === "ryujinx" ? cfg.output_path || "" : "") ||
      "";
    state.atmosphereOutputPath = cfg.atmosphere_output_path || "";
    $("output-path").value = cfg.output_path || "";
    applyModCompatibilityUi(state.modCompatibility);
    $("freesink").checked = cfg.freesink !== false;
    $("ryujinx-path").value = cfg.ryujinx_path || "";
    $("dread-rom").value = cfg.dread_rom_path || "";
    applyDebugLogsPreference(Boolean(cfg.debug_logs));
    if (cfg.room_id) state.roomId = cfg.room_id;

    // Launcher may leave a full archipelago:// URI in the server field.
    if (/^archipelago:\/\//i.test($("server").value.trim())) {
      fillFromServerField();
    }

    const yaml = await hub.loadYaml(cfg.yaml_path);
    applyYamlToForm(yaml.config || {});

    const running = await hub.isRunning();
    state.running = Boolean(running);
    if (state.running) {
      state.unsubLog = hub.onLog(handleClientLog);
      state.unsubStatus = hub.onStatus((st) => applyStatus(st));
      const st = await hub.getStatus();
      applyStatus(st);
      if (st && st.ap_connected) {
        setStage(cfg.hub_stage === "patch" ? "patch" : "client");
      } else {
        setStage("connect");
      }
    } else {
      setStage("connect");
    }

    setView("client");

    // archipelago:// launch: probe RoomInfo → Connect (or wait for password) → patcher.
    const shouldAutoConnect =
      !state.running &&
      Boolean(cfg.auto_connect_ap) &&
      Boolean(($("server").value || "").trim()) &&
      Boolean(($("slot").value || "").trim());
    if (shouldAutoConnect) {
      appendPlainLine("[app] Launcher URI detected — checking room, then connecting…");
      setConnectStatus("Connecting from Archipelago link…");
      // One-shot: clear so a manual reopen does not reconnect unexpectedly.
      hub
        .saveConfig({ auto_connect_ap: false, launcher_uri: cfg.launcher_uri || "" })
        .catch(() => {});
      setTimeout(() => {
        connect().catch((err) => setConnectStatus(String(err), true));
      }, 150);
    }
  }

  boot().catch((err) => {
    setConnectStatus(String(err), true);
  });
})();
