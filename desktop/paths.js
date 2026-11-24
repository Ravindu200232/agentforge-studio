'use strict'

/**
 * Where everything the app runs lives, installed or run from a checkout.
 *
 * Installed on Windows (AgentForgeSetup.exe), under %LOCALAPPDATA%\Programs\AgentForge:
 *   AgentForge.exe, resources\app\backend   the backend (server.py, its modules, agents, prompts)
 *                   resources\app\studio    the studio UI (a static build)
 *                   resources\app\python    the Python it runs on, with its packages
 *   tools\node, tools\git, tools\gh, ...    the command line tools a blank computer gets (see release/manifest)
 *
 * From a checkout (`npm start` in desktop/): the repository is the backend, studio/out the UI, and Python is the
 * one AGENTFORGE_PYTHON names (or the first `py -3.12` / `python` on PATH).
 *
 * Installed on macOS, inside AgentForge.app:
 *   Contents/Resources/app/backend   the backend
 *                         /studio    the static UI
 *                         /python    the bundled Python runtime
 *                         /tools     bundled command-line runtimes such as Node.js
 *
 * The user's own things live outside both: settings and records in Electron's userData folder, projects in
 * Documents/AgentForge, so an update or a reinstall never touches them.
 */
const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { app } = require('electron')

function installed() {
  return app.isPackaged
}

function appRoot() {
  return installed() ? path.join(process.resourcesPath, 'app') : path.resolve(__dirname, '..')
}

function backendRoot() {
  return installed() ? path.join(appRoot(), 'backend') : appRoot()
}

function studioRoot() {
  return installed() ? path.join(appRoot(), 'studio') : path.join(appRoot(), 'studio', 'out')
}

/** The install folder: AgentForge.exe's own, whose `tools` holds the command line tools. */
function installRoot() {
  return installed() ? path.dirname(process.execPath) : appRoot()
}

/** Packaged macOS tools live in the read-only app resources; Windows' online installer keeps them beside the exe. */
function toolsRoot() {
  if (installed() && process.platform === 'darwin') return path.join(appRoot(), 'tools')
  return path.join(installRoot(), 'tools')
}

function findPython() {
  if (process.env.AGENTFORGE_PYTHON) return process.env.AGENTFORGE_PYTHON
  const bundled = process.platform === 'win32'
    ? path.join(appRoot(), 'python', 'python.exe')
    : path.join(appRoot(), 'python', 'bin', 'python3')
  if (fs.existsSync(bundled)) return bundled
  const commands = process.platform === 'win32'
    ? [['py', ['-3.12', '-c', 'import sys;print(sys.executable)']],
       ['python', ['-c', 'import sys;print(sys.executable)']]]
    : [['python3', ['-c', 'import sys;print(sys.executable)']],
       ['python', ['-c', 'import sys;print(sys.executable)']]]
  for (const [command, args] of commands) {
    try {
      const found = execFileSync(command, args, { encoding: 'utf8', windowsHide: true }).trim()
      if (found) return found
    } catch { /* not this one */ }
  }
  return 'python'
}

/** The command line tool folders, first on PATH so the app's own copies win over anything else installed. */
function toolPaths() {
  const tools = toolsRoot()
  const candidates = [
    path.join(tools, 'node', 'bin'),              // macOS/Linux Node distribution
    path.join(tools, 'node'),                     // Windows Node distribution
    path.join(tools, 'npm'),                     // vercel, netlify, supabase (npm --prefix)
    path.join(tools, 'git', 'cmd'),
    path.join(tools, 'gh', 'bin'),
    path.join(tools, 'aws', 'Amazon', 'AWSCLIV2'),
    path.join(tools, 'az', 'bin'),
    path.join(tools, 'az', 'wbin'),
    path.join(tools, 'atlas', 'bin'),            // MongoDB Atlas CLI: the browser sign-in for MongoDB
  ]
  if (process.platform === 'darwin') {
    // Finder-launched apps receive a deliberately small PATH. Include the normal package-manager locations so tools
    // the customer already installed remain available without starting AgentForge from Terminal.
    candidates.push('/opt/homebrew/bin', '/usr/local/bin', '/opt/local/bin')
  }
  return candidates.filter(folder => fs.existsSync(folder))
}

function dataRoot() {
  return app.getPath('userData')                // %APPDATA%\AgentForge
}

function workspacesRoot() {
  return path.join(app.getPath('documents'), 'AgentForge')
}

module.exports = { appRoot, backendRoot, studioRoot, installRoot, toolsRoot, findPython, toolPaths, dataRoot, workspacesRoot, installed }
