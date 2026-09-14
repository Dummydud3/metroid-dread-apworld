const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("dreadVisualizer", {
  getCatalog: () => ipcRenderer.invoke("get-tracker-catalog"),
  getStatus: () => ipcRenderer.invoke("get-tracker-status"),
  explainLocation: (locationId, requestId) =>
    ipcRenderer.invoke("explain-visualizer-location", {
      id: locationId,
      requestId,
    }),
  onUpdate: (handler) => {
    const listener = (_e, payload) => handler(payload);
    ipcRenderer.on("tracker-update", listener);
    return () => ipcRenderer.removeListener("tracker-update", listener);
  },
});
