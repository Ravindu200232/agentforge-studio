'use strict'

/**
 * What the studio page may use of the app: its backend's live feed. Requests need nothing from here — the page's
 * own `/__agentforge/api/...` fetches are answered by the app (main.js) — so this is the WebSocket's replacement
 * only: send a message, hear every event, and know whether the engine is up (studio/lib/ws.js).
 */
const { contextBridge, ipcRenderer } = require('electron')

function listen(channel, callback) {
  const handler = (_event, value) => callback(value)
  ipcRenderer.on(channel, handler)
  return () => ipcRenderer.removeListener(channel, handler)
}

contextBridge.exposeInMainWorld('agentforgeDesktop', {
  send: message => ipcRenderer.send('feed:send', message),
  onEvent: callback => listen('feed:event', callback),
  onStatus: callback => listen('feed:status', callback),
  version: () => ipcRenderer.sendSync('app:version'),
})
