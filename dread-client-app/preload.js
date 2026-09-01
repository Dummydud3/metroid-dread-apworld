const { contextBridge, ipcRenderer, webUtils } = require("electron");
const { parseConnectServerString } = require("./room_info_gate");

contextBridge.exposeInMainWorld("dreadHub", {
  getConfig: () => ipcRenderer.invoke("get-config"),
  saveConfig: (partial) => ipcRenderer.invoke("save-config", partial),
  openLogsFolder: () => ipcRenderer.invoke("open-logs-folder"),
  /** Tee a renderer Log line into INSTALL_ROOT/logs/metroid_bread_hub.log */
  appendHubLog: (text) => ipcRenderer.invoke("append-hub-log", text),
  checkApworldUpdate: () => ipcRenderer.invoke("check-apworld-update"),
  installApworldUpdate: (opts) =>
    ipcRenderer.invoke("install-apworld-update", opts),
  promptApworldUpdate: (opts) =>
    ipcRenderer.invoke("prompt-apworld-update", opts),
  startClient: (opts) => ipcRenderer.invoke("start-client", opts),
  probeRoomInfo: (server) => ipcRenderer.invoke("probe-room-info", server),
  parseConnectServer: (server) => parseConnectServerString(server || ""),
  stopClient: () => ipcRenderer.invoke("stop-client"),
  sendCommand: (text) => ipcRenderer.invoke("send-command", text),
  getStatus: () => ipcRenderer.invoke("get-status"),
  isRunning: () => ipcRenderer.invoke("is-running"),
  openTracker: () => ipcRenderer.invoke("open-tracker"),
  getPreparedSeed: () => ipcRenderer.invoke("get-prepared-seed"),
  runPatch: (opts) => ipcRenderer.invoke("run-patch", opts),
  cancelPatch: () => ipcRenderer.invoke("cancel-patch"),
  launchRyujinx: (opts) => ipcRenderer.invoke("launch-ryujinx", opts),
  pickFolder: (title) => ipcRenderer.invoke("pick-folder", title),
  pickFile: (opts) => ipcRenderer.invoke("pick-file", opts),
  // Singleplayer dropzone: drag/drop or Browse a generated AP output .zip
  // straight into the same patch flow used by the direct patcher.
  loadSingleplayerZip: (zipPath) => ipcRenderer.invoke("load-singleplayer-zip", zipPath),
  getPathForFile: (file) => webUtils.getPathForFile(file),
  loadYaml: (path) => ipcRenderer.invoke("load-yaml", path),
  saveYaml: (opts) => ipcRenderer.invoke("save-yaml", opts),
  pickYamlSave: (name) => ipcRenderer.invoke("pick-yaml-save", name),
  pickYamlOpen: () => ipcRenderer.invoke("pick-yaml-open"),
  onLog: (handler) => {
    const listener = (_e, payload) => handler(payload);
    ipcRenderer.on("client-log", listener);
    return () => ipcRenderer.removeListener("client-log", listener);
  },
  onStatus: (handler) => {
    const listener = (_e, payload) => handler(payload);
    ipcRenderer.on("client-status", listener);
    return () => ipcRenderer.removeListener("client-status", listener);
  },
  onPatchLog: (handler) => {
    const listener = (_e, payload) => handler(payload);
    ipcRenderer.on("patch-log", listener);
    return () => ipcRenderer.removeListener("patch-log", listener);
  },
  onPatchProgress: (handler) => {
    const listener = (_e, payload) => handler(payload);
    ipcRenderer.on("patch-progress", listener);
    return () => ipcRenderer.removeListener("patch-progress", listener);
  },
});

// Back-compat alias used by older tracker code paths if needed.
contextBridge.exposeInMainWorld("dreadClient", {
  getConfig: () => ipcRenderer.invoke("get-config"),
  openTracker: () => ipcRenderer.invoke("open-tracker"),
  getStatus: () => ipcRenderer.invoke("get-status"),
  onStatus: (handler) => {
    const listener = (_e, payload) => handler(payload);
    ipcRenderer.on("client-status", listener);
    return () => ipcRenderer.removeListener("client-status", listener);
  },
});
