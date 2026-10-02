'use strict'

/**
 * The backend, as a child of this app: `server.py --stdio`, hidden, talked to over its stdin and stdout
 * (server_modules/stdio_bridge.py describes the lines). Nothing listens on a port.
 *
 * Requests wait for the backend to say it is ready; one that is cut short by a crash is answered 503 and the
 * backend is started again. Quitting closes its stdin, gives it a moment, then ends its whole process tree
 * (previews and commands included), so nothing of AgentForge outlives the window.
 */
const { spawn, execFile } = require('node:child_process')
const path = require('node:path')
const readline = require('node:readline')
const { EventEmitter } = require('node:events')

const RESTART_DELAY_MS = 1500
const MAX_QUICK_RESTARTS = 5

class Backend extends EventEmitter {
  constructor({ python, root, env, log }) {
    super()
    this.python = python
    this.root = root
    this.env = env
    this.log = log || (() => {})
    this.child = null
    this.pending = new Map()
    this.nextId = 1
    this.quitting = false
    this.restarts = []
    this.readyPromise = null
  }

  start() {
    this.status('starting')
    let resolveReady
    this.readyPromise = new Promise(resolve => { resolveReady = resolve })
    const child = spawn(this.python, ['-u', path.join(this.root, 'server.py'), '--stdio'], {
      cwd: this.root, env: this.env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.child = child
    child.stdout.setEncoding('utf8')
    readline.createInterface({ input: child.stdout }).on('line', line => {
      let message
      try { message = JSON.parse(line) } catch { this.log(`[backend stdout] ${line}`); return }
      if (message.type === 'ready') { resolveReady(); this.status('ready') }
      else if (message.type === 'response') this.settle(message)
      else if (message.type === 'event') this.emit('event', message.event)
    })
    child.stderr.setEncoding('utf8')
    child.stderr.on('data', chunk => this.log(chunk))
    child.on('error', error => this.log(`[backend] could not start ${this.python}: ${error.message}`))
    child.on('exit', code => {
      if (this.child !== child) return
      this.child = null
      for (const [, waiting] of this.pending) waiting.resolve({ status: 503, contentType: 'application/json',
        json: { error: 'The AgentForge engine stopped while answering. It is starting again.' } })
      this.pending.clear()
      if (this.quitting) return
      const now = Date.now()
      this.restarts = this.restarts.filter(at => now - at < 60_000).concat(now)
      if (this.restarts.length > MAX_QUICK_RESTARTS) {
        this.status('stopped: the engine keeps failing to start — see the log in %APPDATA%\\AgentForge\\logs')
        return
      }
      this.log(`[backend] exited with code ${code}; starting again`)
      this.status('restarting')
      setTimeout(() => { if (!this.quitting) this.start() }, RESTART_DELAY_MS)
    })
  }

  status(value) {
    this.lastStatus = value
    this.emit('status', value)
  }

  write(message) {
    if (!this.child?.stdin?.writable) return false
    this.child.stdin.write(JSON.stringify(message) + '\n')
    return true
  }

  settle(message) {
    const waiting = this.pending.get(String(message.id))
    if (!waiting) return
    this.pending.delete(String(message.id))
    waiting.resolve(message)
  }

  /** One API request: `{status, contentType, json | base64, filename}`. */
  async request({ method, path: apiPath, query, body }) {
    await this.readyPromise
    const id = String(this.nextId++)
    return new Promise(resolve => {
      this.pending.set(id, { resolve })
      if (!this.write({ type: 'request', id, method, path: apiPath, query, body })) {
        this.pending.delete(id)
        resolve({ status: 503, contentType: 'application/json', json: { error: 'The AgentForge engine is starting.' } })
      }
    })
  }

  /** What the studio used to send over its WebSocket (runs.handle on the other side). */
  async feed(message) {
    await this.readyPromise
    this.write({ type: 'feed', message })
  }

  /** Close the backend and everything it started. */
  stop() {
    this.quitting = true
    const child = this.child
    if (!child) return Promise.resolve()
    return new Promise(resolve => {
      const done = () => resolve()
      child.once('exit', done)
      try { child.stdin.end() } catch { /* already closed */ }
      setTimeout(() => {
        if (child.exitCode !== null) return
        if (process.platform === 'win32') {
          execFile('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true }, done)
        } else {
          try { process.kill(-child.pid) } catch { child.kill('SIGKILL') }
          done()
        }
      }, 3000)
    })
  }
}

module.exports = { Backend }
