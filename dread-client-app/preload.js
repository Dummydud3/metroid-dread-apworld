const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("dreadHub", {
  getConfig: () => ipcRenderer.invoke("get-config"),
  saveConfig: (partial) => ipcRenderer.invoke("save-config", partial),
  startClient: (opts) => ipcRenderer.invoke("start-client", opts),
  probeRoomInfo: (server) => ipcRenderer.invoke("probe-room-info", server),
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
