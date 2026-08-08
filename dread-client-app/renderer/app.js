(() => {
  const $ = (id) => document.getElementById(id);
  const hub = window.dreadHub;

  const PROGRESSIVE = [
    ["progressive_beams", "Progressive Beams", true],
    ["progressive_charge", "Progressive Charge", true],
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
  ];

  const TRICKS = [
    ["combat_tricks", "Combat Tricks", "beginner"],
    ["knowledge_tricks", "Knowledge Tricks", "disabled"],
    ["movement_tricks", "Movement Tricks", "disabled"],
    ["slide_jump", "Slide Jump", "disabled"],
    ["wall_jump_tricks", "Wall Jump Tricks", "disabled"],
    ["infinite_bomb_jump", "Infinite Bomb Jump", "disabled"],
    ["water_bomb_jump", "Water Bomb Jump", "disabled"],
    ["water_space_jump", "Water Space Jump", "disabled"],
    ["single_wall_wall_jump", "Single-Wall Wall Jump", "disabled"],
    ["heat_cold_runs", "Heat/Cold Runs", "disabled"],
    ["damage_boost", "Damage Boost", "disabled"],
  ];

  const TRICK_LEVELS = ["disabled", "beginner", "easy", "medium", "hard", "expert"];

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
  };

  const ANSI_RE = /\u001b\[[0-9;]*m/g;

  /* ---------- Menu / views ---------- */

  function setView(view) {
    state.view = view;
    $("view-yaml").hidden = view !== "yaml";
    $("view-client").hidden = view !== "client";
    $("view-label").textContent = view === "yaml" ? "YAML Editor" : "Client";
    $("menu-panel").hidden = true;
    $("btn-menu").setAttribute("aria-expanded", "false");
  }

  function setStage(stage) {
    state.stage = stage;
    $("stage-connect").hidden = stage !== "connect";
    $("stage-patch").hidden = stage !== "patch";
    $("stage-client").hidden = stage !== "client";
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

  function scrollLog(el) {
    el.scrollTop = el.scrollHeight;
  }

  function appendPlainLine(text, target) {
    const el = target || $("log");
    const cleaned = String(text || "").replace(ANSI_RE, "");
    if (!cleaned) return;
    if (el.tagName === "PRE") {
      el.textContent += cleaned;
      scrollLog(el);
      return;
    }
    const parts = cleaned.split(/\r?\n/);
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      if (part === "" && i === parts.length - 1) continue;
      const line = document.createElement("div");
      line.className = "log-line";
      line.textContent = part;
      el.appendChild(line);
    }
    scrollLog(el);
  }

  function appendCommandEcho(text) {
    const line = document.createElement("div");
    line.className = "log-line log-cmd";
    line.textContent = `> ${text}`;
    $("log").appendChild(line);
    scrollLog($("log"));
  }

  function appendPrintJson(parts) {
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
    $("log").appendChild(line);
    scrollLog($("log"));
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

  function buildYamlForm() {
    const prog = $("yaml-progressive");
    prog.innerHTML = "";
    for (const [key, label] of PROGRESSIVE) {
      const lab = document.createElement("label");
      lab.className = "check";
      lab.innerHTML = `<input type="checkbox" data-yaml="${key}" /><span>${label}</span>`;
      prog.appendChild(lab);
    }

    const pool = $("yaml-pool");
    pool.innerHTML = "";
    for (const [key, label, min, max] of POOL) {
      const lab = document.createElement("label");
      lab.innerHTML = `${label}<input type="number" data-yaml="${key}" min="${min}" max="${max}" />`;
      pool.appendChild(lab);
    }

    const tricks = $("yaml-tricks");
    tricks.innerHTML = "";
    for (const [key, label] of TRICKS) {
      const lab = document.createElement("label");
      const opts = TRICK_LEVELS.map((v) => `<option value="${v}">${v}</option>`).join("");
      lab.innerHTML = `${label}<select data-yaml="${key}">${opts}</select>`;
      tricks.appendChild(lab);
    }

    // Reverse grapple toggle
    const rev = document.createElement("label");
    rev.className = "check";
    rev.style.gridColumn = "1 / -1";
    rev.innerHTML = `<input type="checkbox" data-yaml="reverse_grapple_block" /><span>Reverse Grapple Block</span>`;
    tricks.appendChild(rev);
  }

  function applyYamlToForm(config) {
    const dread = (config && config["Metroid Dread"]) || {};
    $("yaml-name").value = config.name || "DreadPlayer";
    $("yaml-goal").value = dread.game_goal || "defeat_raven_beak";
    $("yaml-start").value = dread.starting_location || "default";
    $("yaml-deathlink").checked = Boolean(dread.death_link);
    $("yaml-early-morph").checked = Boolean(dread.early_morph_ball);
    $("yaml-dna-count").value = dread.dna_count ?? 8;
    $("yaml-dna-req").value = dread.dna_required ?? 80;
    $("yaml-dna-row").hidden = $("yaml-goal").value !== "dna_hunt";

    document.querySelectorAll("[data-yaml]").forEach((el) => {
      const key = el.dataset.yaml;
      const val = dread[key];
      if (el.type === "checkbox") {
        const def = PROGRESSIVE.find((p) => p[0] === key);
        el.checked = val != null ? Boolean(val) : def ? def[2] : false;
      } else if (el.tagName === "SELECT") {
        const def = TRICKS.find((t) => t[0] === key);
        el.value = val != null ? String(val) : def ? def[2] : "disabled";
      } else {
        const def = POOL.find((p) => p[0] === key);
        el.value = val != null ? val : def ? def[4] : "";
      }
    });
  }

  function readYamlFromForm() {
    const dread = {
      death_link: $("yaml-deathlink").checked,
      accessibility: "items",
      progression_balancing: 50,
      game_goal: $("yaml-goal").value,
      starting_location: $("yaml-start").value,
      early_morph_ball: $("yaml-early-morph").checked,
    };
    if (dread.game_goal === "dna_hunt") {
      dread.dna_count = Number($("yaml-dna-count").value) || 8;
      dread.dna_required = Number($("yaml-dna-req").value) || 80;
    }
    document.querySelectorAll("[data-yaml]").forEach((el) => {
      const key = el.dataset.yaml;
      if (el.type === "checkbox") dread[key] = el.checked;
      else if (el.tagName === "SELECT") dread[key] = el.value;
      else if (el.type === "number") dread[key] = Number(el.value);
      else dread[key] = el.value;
    });
    return {
      name: $("yaml-name").value.trim() || "DreadPlayer",
      game: "Metroid Dread",
      description: "Metroid Dread player options",
      "Metroid Dread": dread,
    };
  }

  $("yaml-goal").addEventListener("change", () => {
    $("yaml-dna-row").hidden = $("yaml-goal").value !== "dna_hunt";
  });

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
      appendPlainLine(`[app] ${st.error || "Archipelago error"}`);
      if (st.detail) appendPlainLine(String(st.detail));
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
        setConnectStatus(
          st.exit_error ||
            (st.exit_code
              ? `Client exited (code ${st.exit_code}). Check the log.`
              : "Disconnected before Archipelago connected."),
          true
        );
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
    if (game && game !== "Metroid Dread") {
      setConnectStatus(`Slot is "${game}", not Metroid Dread.`, true);
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
  }

  async function gateOnRoomInfo(server, password) {
    // RoomInfo.password is the only reliable pre-Connect signal (WebHost API has none).
    setConnectStatus("Checking room…");
    let room;
    try {
      room = await hub.probeRoomInfo(server);
    } catch (err) {
      // Probe failed — fall through to normal Connect (Python client still handles auth).
      appendPlainLine(`[app] RoomInfo probe failed (${err}); continuing to Connect.`);
      return { action: "connect", password: normalizeUriPassword(password) };
    }
    if (!room || !room.ok) {
      appendPlainLine(
        `[app] RoomInfo probe unavailable (${(room && room.error) || "unknown"}); continuing to Connect.`
      );
      return { action: "connect", password: normalizeUriPassword(password) };
    }
    if (room.seed_name) state.seedName = room.seed_name;
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
    }
    return decision;
  }

  async function connect() {
    if (state.connecting) return;
    // Prior attempt may still own the Python process (password error, timeout, etc.).
    if (state.running) {
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
      return;
    }

    // Normalize URI "None"/empty before any Connect decision.
    $("password").value = normalizeUriPassword($("password").value);

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

    if (state.unsubLog) state.unsubLog();
    if (state.unsubStatus) state.unsubStatus();
    state.unsubLog = hub.onLog((payload) => {
      if (!payload) return;
      if (payload.stream === "cmd") {
        appendCommandEcho(payload.text || "");
        return;
      }
      appendPlainLine(payload.text || "");
    });
    state.unsubStatus = hub.onStatus((st) => applyStatus(st));

    const result = await hub.startClient({
      server,
      slot,
      password: gate.password,
      dreadIp: $("dread-ip").value.trim() || "127.0.0.1",
      autoConnectDread: false,
    });
    // Stash for onApConnected — it will await the same promise.
    state._earlyServerSpoilerPromise = earlyWait;

    if (!result.ok) {
      setConnectStatus(result.error || "Failed to start client", true);
      state.connecting = false;
      state.running = false;
      state._earlyServerSpoilerPromise = null;
      if (state.serverSpoilerWaiter) {
        state.serverSpoilerWaiter.resolve({ error: result.error || "Failed to start client" });
        state.serverSpoilerWaiter = null;
      }
      $("btn-connect").disabled = false;
      return;
    }
    if (result.roomId) state.roomId = result.roomId;
    state.running = true;

    // Safety timeout if AP never confirms — clear stuck Connecting and free Connect.
    const connectGeneration = (state._connectGeneration =
      (state._connectGeneration || 0) + 1);
    setTimeout(() => {
      if (state._connectGeneration !== connectGeneration) return;
      if (state.connecting && !state.apConnected) {
        setConnectStatus(
          "Timed out waiting for Archipelago. Check address / slot / password, then Connect again.",
          true
        );
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

  async function runPatch() {
    if (!$("base-rom").value.trim()) {
      appendPlainLine("Source path is required.", $("patch-log"));
      $("patch-log-wrap").open = true;
      return;
    }
    if (!$("output-path").value.trim()) {
      appendPlainLine("Ryujinx output folder is required.", $("patch-log"));
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

    const result = await hub.runPatch({
      spoilerPath: state.spoilerPath,
      baseRomPath: $("base-rom").value.trim(),
      outputPath: $("output-path").value.trim(),
      playerName: state.playerName || $("slot").value.trim(),
      freesink: $("freesink").checked,
      cleanOutput: false,
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
    const p = await hub.pickFolder("Select Ryujinx mod output folder");
    if (p) $("output-path").value = p;
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
    const waitSec = Math.round((result.connectDelayMs || 30000) / 1000);
    appendPlainLine(
      `[app] Launched Ryujinx with ${result.rom}\n` +
        `      Waiting ${waitSec}s for the game to boot, then connecting Remote Lua…\n` +
        `      Tip: stay on the title screen or fully in-game — avoid connecting mid-load.`
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
    const cfg = await hub.getConfig();
    $("server").value = cfg.server || "";
    $("slot").value = cfg.slot || "";
    $("password").value = normalizeUriPassword(cfg.password || "");
    $("dread-ip").value = cfg.dread_ip || "127.0.0.1";
    $("base-rom").value = cfg.base_rom_path || "";
    $("output-path").value = cfg.output_path || "";
    $("freesink").checked = cfg.freesink !== false;
    $("ryujinx-path").value = cfg.ryujinx_path || "";
    $("dread-rom").value = cfg.dread_rom_path || "";
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
      state.unsubLog = hub.onLog((payload) => {
        if (!payload) return;
        if (payload.stream === "cmd") {
          appendCommandEcho(payload.text || "");
          return;
        }
        appendPlainLine(payload.text || "");
      });
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
