const { contextBridge, ipcRenderer, webFrame } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  minimize:      () => ipcRenderer.send('window-minimize'),
  maximize:      () => ipcRenderer.send('window-maximize'),
  close:         () => ipcRenderer.send('window-close'),
  isMaximized:   () => ipcRenderer.invoke('window-is-maximized'),
  openFileDialog: () => ipcRenderer.invoke('open-file-dialog'),
  onMaximizeChange: (cb) => ipcRenderer.on('maximize-change', (_e, val) => cb(val)),
  setZoom: (factor) => webFrame.setZoomFactor(factor),
  getZoom: () => webFrame.getZoomFactor(),
  // Update system
  downloadUpdate:    (url)  => ipcRenderer.invoke('update-download', url),
  installUpdate:     (path) => ipcRenderer.invoke('update-install', path),
  onUpdateProgress:  (cb)   => ipcRenderer.on('update-progress', (_e, pct) => cb(pct)),
  // Quick patches
  fetchPatches: () => ipcRenderer.invoke('patches-fetch'),
})
