const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("dreadTracker", {
  getCatalog: () => ipcRenderer.invoke("get-tracker-catalog"),
  getStatus: () => ipcRenderer.invoke("get-tracker-status"),
  onUpdate: (handler) => {
    const listener = (_e, payload) => handler(payload);
    ipcRenderer.on("tracker-update", listener);
    return () => ipcRenderer.removeListener("tracker-update", listener);
  },
});
