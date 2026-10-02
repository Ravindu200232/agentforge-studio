'use strict'

/**
 * AgentForge as a desktop app. One window, the studio in it, its backend a hidden child process, and no port:
 *
 *   agentforge://app/__agentforge/...        the studio's own files (a static build)
 *   agentforge://app/__agentforge/api/...    the API, answered by the backend over its stdin/stdout (bridge.js)
 *   window.agentforgeDesktop                 the live feed, in place of the WebSocket (preload.js)
 *
 * Every process the app starts (the backend, the previews and commands it runs) is its child, so Windows shows
 * them together as one "AgentForge" in Task Manager, and quitting ends them all.
 */
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const { app, BrowserWindow, ipcMain, net, protocol, shell } = require('electron')

const paths = require('./paths')
const { Backend } = require('./bridge')

const SCHEME = 'agentforge'
const HOME = `${SCHEME}://app/__agentforge/`
const BASE = '/__agentforge'
const API = `${BASE}/api`

protocol.registerSchemesAsPrivileged([{
  scheme: SCHEME,
  privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true },
}])

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.setAppUserModelId('ai.agentforge.desktop')
  start()
}

let win = null
let backend = null

function logFile() {
  const folder = path.join(paths.dataRoot(), 'logs')
  fs.mkdirSync(folder, { recursive: true })
  const file = path.join(folder, 'backend.log')
  try { if (fs.statSync(file).size > 10 * 1024 * 1024) fs.renameSync(file, `${file}.1`) } catch { /* none yet */ }
  return fs.createWriteStream(file, { flags: 'a' })
}

function backendEnv() {
  const env = { ...process.env }
  delete env.ELECTRON_RUN_AS_NODE
  const tools = path.join(paths.installRoot(), 'tools')
  Object.assign(env, {
    AGENTFORGE_TRANSPORT: 'stdio',
    AGENTFORGE_DATA: paths.dataRoot(),
    AGENTFORGE_WORKSPACES: paths.workspacesRoot(),
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
    PATH: [...paths.toolPaths(), env.PATH || env.Path || ''].join(path.delimiter),
  })
  delete env.Path                                      // one PATH, not two spellings of it
  if (fs.existsSync(path.join(tools, 'ms-playwright'))) env.PLAYWRIGHT_BROWSERS_PATH = path.join(tools, 'ms-playwright')
  if (!paths.installed()) {
    // A checkout keeps its Python packages in .deps (studio.ps1 does the same).
    env.PYTHONPATH = [path.join(paths.backendRoot(), '.deps'), path.join(paths.backendRoot(), 'src')].join(path.delimiter)
  }
  return env
}

/** A file of the studio's static build, by its URL path. */
function staticFile(urlPath) {
  const root = paths.studioRoot()
  let relative = decodeURIComponent(urlPath.startsWith(BASE) ? urlPath.slice(BASE.length) : urlPath)
  relative = relative.replace(/^\/+/, '')
  const candidates = relative
    ? [relative, `${relative}.html`, path.join(relative, 'index.html')]
    : ['index.html']
  for (const candidate of candidates) {
    const file = path.resolve(root, candidate)
    if (!file.startsWith(path.resolve(root))) break             // never outside the build
    if (fs.existsSync(file) && fs.statSync(file).isFile()) return file
  }
  return path.join(root, 'index.html')                          // the studio is one page
}

async function answerApi(request, url) {
  let body = {}
  if (request.method === 'POST') {
    const text = await request.text()
    try { body = text ? JSON.parse(text) : {} } catch { body = {} }
    if (!body || typeof body !== 'object' || Array.isArray(body)) body = { body }
  }
  const reply = await backend.request({
    method: request.method,
    path: url.pathname.slice(API.length) || '/',
    query: Object.fromEntries(url.searchParams.entries()),
    body,
  })
  const headers = { 'content-type': reply.contentType || 'application/json', 'cache-control': 'no-store' }
  if (reply.filename) headers['content-disposition'] = `attachment; filename="${reply.filename}"`
  const payload = reply.base64 !== undefined ? Buffer.from(reply.base64, 'base64') : JSON.stringify(reply.json ?? null)
  return new Response(payload, { status: reply.status || 200, headers })
}

function serveProtocol() {
  protocol.handle(SCHEME, async request => {
    const url = new URL(request.url)
    if (url.pathname === API || url.pathname.startsWith(`${API}/`)) return answerApi(request, url)
    if (!url.pathname.startsWith(BASE)) return Response.redirect(HOME, 302)
    return net.fetch(pathToFileURL(staticFile(url.pathname)).toString())
  })
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440, height: 920, minWidth: 1000, minHeight: 640,
    title: 'AgentForge', backgroundColor: '#ffffff', show: false, autoHideMenuBar: true,
    icon: path.join(__dirname, 'build', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  win.once('ready-to-show', () => win.show())

  // Links leave the app for the system browser. "Open in a new tab" opens a blank window and then sends it
  // somewhere: that window is kept hidden, and where it is sent goes to the browser instead.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url === 'about:blank') return { action: 'allow', overrideBrowserWindowOptions: { show: false } }
    if (/^https?:/i.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('did-create-window', child => {
    const leave = (event, target) => {
      if (!/^https?:/i.test(target)) return
      event.preventDefault?.()
      shell.openExternal(target)
      setTimeout(() => { if (!child.isDestroyed()) child.close() }, 0)
    }
    child.webContents.on('will-navigate', leave)
    child.webContents.on('did-start-navigation', details => leave({}, details.url))
  })
  win.webContents.on('will-navigate', (event, target) => {
    if (!target.startsWith(`${SCHEME}://`)) { event.preventDefault(); if (/^https?:/i.test(target)) shell.openExternal(target) }
  })

  win.loadFile(path.join(__dirname, 'starting.html'))
  const open = () => { if (win && !win.isDestroyed() && !win.webContents.getURL().startsWith(SCHEME)) win.loadURL(HOME) }
  if (backend.lastStatus === 'ready') open()
  backend.on('status', status => {
    if (!win || win.isDestroyed()) return
    if (status === 'ready') open()
    win.webContents.send('feed:status', status)
  })
  win.on('closed', () => { win = null })
}

function start() {
  app.on('second-instance', () => {
    if (!win) return
    if (win.isMinimized()) win.restore()
    win.focus()
  })

  app.whenReady().then(() => {
    const log = logFile()
    backend = new Backend({
      python: paths.findPython(),
      root: paths.backendRoot(),
      env: backendEnv(),
      log: text => log.write(text.endsWith('\n') ? text : `${text}\n`),
    })
    backend.on('event', event => { if (win && !win.isDestroyed()) win.webContents.send('feed:event', event) })
    backend.start()

    ipcMain.on('feed:send', (_event, message) => { if (message && typeof message === 'object') backend.feed(message) })
    ipcMain.on('app:version', event => { event.returnValue = app.getVersion() })

    serveProtocol()
    createWindow()
  })

  app.on('window-all-closed', () => app.quit())

  let stopping = false
  app.on('before-quit', event => {
    if (stopping || !backend) return
    event.preventDefault()
    stopping = true
    backend.stop().finally(() => app.exit(0))
  })
}
