
export const API = '/__agentforge/api'

let authToken = ''

export function setAuthToken(token) {
  authToken = token || ''
  if (typeof window !== 'undefined') {
    if (token) localStorage.setItem('agentforge_token', token)
    else localStorage.removeItem('agentforge_token')
  }
}

export function getAuthToken() {
  if (authToken) return authToken
  if (typeof window !== 'undefined') {
    return localStorage.getItem('agentforge_token') || ''
  }
  return ''
}

let onSignedOut = null

const NETWORK_MESSAGE = 'Unable to reach AgentForge right now. Your project is saved; check the connection and try again.'

function networkError(cause) {
  const error = new Error(NETWORK_MESSAGE)
  error.code = 'network'
  error.cause = cause
  return error
}

/** Called when the server says this session is over, from wherever it happens. */
export function whenSignedOut(fn) {
  onSignedOut = fn
}

async function req(path, opts = {}) {
  const token = getAuthToken()
  const headers = { ...(opts.headers || {}) }
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`
  }
  let r
  try {
    r = await fetch(API + path, { ...opts, headers })
  } catch (cause) {
    // Browser fetch rejects without a response for offline, proxy and server
    // restart failures.  Give every screen the same actionable message rather
    // than exposing an unhelpful browser-specific "Failed to fetch".
    throw networkError(cause)
  }
  const text = await r.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = { raw: text } }
  // The session expired, or was ended elsewhere: back to the sign-in page
  // rather than a studio full of errors about someone who is not signed in.
  if (r.status === 401 && data?.auth === 'required' && token === getAuthToken()) onSignedOut?.()
  if (!r.ok) {
    const error = new Error((data && (data.error || data.detail)) || `HTTP ${r.status}`)
    error.status = r.status
    throw error
  }
  return data
}

/**
 * Download an authenticated API artifact without exposing the session token in
 * a URL. A normal <a href> cannot attach the Bearer header, so protected PDFs
 * otherwise open as the API's "sign in to continue" JSON response.
 */
async function download(path, filename) {
  const token = getAuthToken()
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  let r
  try { r = await fetch(API + path, { headers }) } catch (cause) { throw networkError(cause) }
  if (!r.ok) {
    const text = await r.text()
    let data = null
    try { data = text ? JSON.parse(text) : null } catch { }
    if (r.status === 401 && data?.auth === 'required' && token === getAuthToken()) onSignedOut?.()
    throw new Error((data && (data.error || data.detail)) || `HTTP ${r.status}`)
  }
  const url = URL.createObjectURL(await r.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // The browser has consumed the object URL by now; defer revocation one turn
  // so downloads remain reliable in Chromium and Firefox alike.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

const post = (path, body) => req(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
})

export const api = {
  // Lightweight Studio API readiness check. It stays available even when
  // Ollama, previews, or cloud integrations are still starting up.
  health: () => req('/health'),
  auth: {
    signup: (data) => post('/auth/signup', data),
    login: (data) => post('/auth/login', data),
    me: () => req('/auth/me'),
    logout: () => post('/auth/logout', {}),
  },
  // A project belongs to whoever built it, from the moment it is created;
  // there is nothing for the studio to assign.
  projects: () => req('/projects'),
  chooseWorkspace: () => post('/workspace/pick', {}),
  models: () => req('/models'),
  settings: () => req('/settings'),
  saveSettings: (s) => post('/settings', s),
  mcpProbe: (server) => post('/mcp/probe', server),
  setPlanMode: (project, enabled) => post(`/projects/${encodeURIComponent(project)}/plan-mode`, { enabled }),
  files: (project, agent = 'developer') => req(`/files/${encodeURIComponent(project)}?agent=${agent}`),
  saveFile: (project, path, content, changeSummary = '') => post('/save-file', { project, path, content, change_summary: changeSummary }),
  open: (project) => post(`/open/${encodeURIComponent(project)}`, {}),
  runtime: (project) => req(`/runtime/${encodeURIComponent(project)}`),
  stopPreview: (project) => post(`/runtime/${encodeURIComponent(project)}/stop`, {}),

  // An address for this project's app that works away from this machine.
  previewLink: (project) => post('/preview-link', { project }),
  previewActivity: (project, runtimeId) => post(`/runtime/${encodeURIComponent(project)}/activity`, { runtimeId }),
  deleteProject: (project) => post('/delete-project', { project }),

  // Stop the running build.
  cancelBuild: (project, agent) => post('/build/cancel', { project, agent }),

  // Answer a question the run is waiting on: the plan, or the design.
  decide: (body) => post('/decision', body),

  // The project's versions: every update approved in the chat, newest first.
  versions: (project) => req(`/versions/${encodeURIComponent(project)}`),

  // The buttons on a plan shown in the chat: approve, revise (with their words), cancel.
  changeDecide: (project, id, body) =>
    post(`/change/${encodeURIComponent(project)}/${encodeURIComponent(id)}/decide`, body),

  // What a run is waiting on right now, for a studio that missed the message.
  decisions: () => req('/decisions'),

  // Everything that has happened to a project, so a reload does not lose it.
  stream: (project) => req(`/stream/${encodeURIComponent(project)}`),
  retrySync: project => post('/sync/retry', { project }),

  // Every user-approved update is retained before a run starts. The execution
  // still uses the existing SRS transaction; this adds the company audit trail.
  createChangeRequest: body => post('/change-requests/draft', body),
  approveChangeRequest: (project, id, targets) =>
    post(`/change-requests/${encodeURIComponent(id)}/approve`, { project, targets }),
  workflow: (project) => req(`/workflow/${encodeURIComponent(project)}`),
  lifecycle: (project) => req(`/lifecycle/${encodeURIComponent(project)}`),

  // Throw away a specification that has not been approved.
  discardSrs: (srs_id) => post('/discard-srs', { srs_id }),

  // Keep an approved specification as a project, without building it.
  keepSrs: (srs_id) => post('/keep-srs', { srs_id }),
  undo: (project, id) => post('/undo', { project, id }),

  logoPrompt: (prompt, model, opts) => localJob('/logo-prompt', { prompt, model }, opts),
  image: (body, opts) => localJob('/image', body, opts),

  // The same answer as `image`, from a file instead of a prompt.
  imageUpload: (file, body) => Promise.resolve(tooBig(file)).then(big => {
    if (big) throw big
    return fileToBase64(file).then(data_base64 =>
      post('/image-upload', { ...body, filename: file.name, data_base64 }))
  }),

  // Manage customer pictures and wireframes across specification review and active projects.
  wireframes: (owner) => (/^prj_/.test(String(owner || ''))
    ? api.srs(`/projects/${encodeURIComponent(owner)}/wireframes`)
    : req(`/project-wireframes/${encodeURIComponent(owner)}`)),
  // Queue asynchronous prototype drawing jobs for specific routes or entire specifications.
  drawWireframeHtml: (srsId, route = '', quiet = true) =>
    api.srs(`/projects/${encodeURIComponent(srsId)}/wireframes/html`, { route, quiet }),
  // What the tools editor rearranged, as the page itself.
  saveWireframeHtml: (srsId, route, html) =>
    api.srs(`/projects/${encodeURIComponent(srsId)}/wireframes/html/edit`, { route, html }),
  // A direct, page-scoped request: it skips planning and replaces only this
  // wireframe's saved HTML with the AI's revised low-fidelity page.
  aiEditWireframeHtml: (srsId, route, prompt) =>
    api.srs(`/projects/${encodeURIComponent(srsId)}/wireframes/html/ai-edit`, { route, prompt }),
  // Read straight from the agent rather than through a job: it is one page of
  // HTML and it is what the <iframe> loads.
  wireframeHtmlUrl: (srsId, route) =>
    `${API}/srs/projects/${encodeURIComponent(srsId)}/wireframes/html`
      + `?route=${encodeURIComponent(route)}`,

  siteImages: (project) => req(`/site-images/${encodeURIComponent(project)}`),
  siteImageSave: (project, file, purpose = '') => Promise.resolve(tooBig(file)).then(big => {
    if (big) throw big
    return fileToBase64(file).then(data_base64 =>
      post('/site-image-save', { project, filename: file.name, purpose, data_base64 }))
  }),
  siteImageDrop: (project, file) => post('/site-image-drop', { project, file }),

  // Photograph what the user pointed at, so it can travel with the message.
  shot: (body) => post('/shot', body),

  // Save one chat attachment in the output project's media folder.
  attach: (file, body) => Promise.resolve(tooBig(file)).then(big => {
    if (big) throw big
    return fileToBase64(file).then(data_base64 =>
      post('/attach', { ...body, filename: file.name, mode: uploadMode(file),
                        content_type: file.type || '', data_base64 }))
  }),

  // Hold one file for a build that has no project yet. Over HTTP on purpose:
  // the build message itself goes over the socket, which refuses this size.
  buildAttach: (token, file, opts = {}) => Promise.resolve(tooBig(file)).then(big => {
    if (big) throw big
    return fileToBase64(file).then(data_base64 =>
      post('/build-attach', { token, filename: file.name || 'upload',
                              purpose: opts.purpose || '', data_base64 }))
  }),

  uploadProject: (body) => post('/upload-project', body),
  mongoPrefetch: () => post('/mongo/prefetch', {}),

  qa: (project) => req(`/qa/${encodeURIComponent(project)}`),
  qaScreenshotUrl: (project, path, at = '') => `${API}/qa-screenshot/${encodeURIComponent(project)}?path=${encodeURIComponent(path)}&v=${encodeURIComponent(at)}`,
  qaPdfUrl: (project) => `${API}/qa-pdf/${encodeURIComponent(project)}`,
  downloadQaPdf: (project) => download(`/qa-pdf/${encodeURIComponent(project)}`,
    `${project}-test-report.pdf`),

  srsResults: (project) => req(`/srs-results/${encodeURIComponent(project)}`),

  designSpec: srsId => api.srs(`/projects/${encodeURIComponent(srsId)}/design-spec`),
  draftDesignSpec: (srsId, spec, direction = '') => api.srs(`/projects/${encodeURIComponent(srsId)}/design-spec/draft`, {
    spec, direction, source: 'design-customizer',
  }),
  approveDesignSpec: (srsId, version) =>
    api.srs(`/projects/${encodeURIComponent(srsId)}/design-spec/${encodeURIComponent(version)}/approve`, {}),

  srsPdfUrl: (project) => `${API}/srs-pdf/${encodeURIComponent(project)}`,
  downloadProjectSrsPdf: (project) => download(`/srs-pdf/${encodeURIComponent(project)}`,
    'SRS.pdf'),
  downloadSrsPdf: (srsId, name = 'SRS.pdf') =>
    download(`/srs/projects/${encodeURIComponent(srsId)}/download/pdf`, name),
  integrations: (project) => req(`/srs/projects/${encodeURIComponent(project)}/integrations`),

  resumeSrs: path => resumeSrsJob(path),
  srs: (path, body) => body === undefined
    ? req(`/srs${path}`)
    : srsJob(path, body),

  // `purpose` describes how the file will be used.
  srsUpload: (project, file, opts = {}) => Promise.resolve(tooBig(file)).then(big => {
    if (big) throw big
    return fileToBase64(file).then(data_base64 =>
      srsJob(`/projects/${encodeURIComponent(project)}/inputs-json`, {
        mode: uploadMode(file),
        filename: file.name || 'upload',
        content_type: file.type || '',
        purpose: opts.purpose || '',
        data_base64,
      }, opts))
  }),

  deployResults: (project) => req(`/deploy-results/${encodeURIComponent(project)}`),
  deployStart: (body) => post('/deploy-start', body),

  deploy: (path, body) => body === undefined
    ? req(`/deploy${path}`)
    : deployJob('POST', path, body),

  deployRead: (path, opts) => deployJob('GET', path, null, opts),

  // Signing in to GitHub in the browser. The token is written into this
  // person's settings by the server; it never comes back through here.
  githubDeviceStart: (clientId = '') => post('/github/device/start', { client_id: clientId }),
  githubDevicePoll: (flowId) => post('/github/device/poll', { flow_id: flowId }),

  // Every deployment provider's own command line tool signs in (`gh`, `aws`, `vercel`, `netlify`, `az`):
  // the server runs its login, shows what it prints, and reads what it leaves behind. `available` also says
  // whether the tool is installed and who it is signed in as; `useExisting` keeps that account with no browser.
  // What a deployment's own command line tools can show, run when opened and read back as it is written.
  // `scope: 'database'` is the same thing for the project's databases: the Supabase CLI and the MongoDB driver.
  cliMonitorList: (project, scope = 'deploy') => post('/cli-monitor/list', { project, scope }),
  cliMonitorStart: (project, command, scope = 'deploy') => post('/cli-monitor/start', { project, command, scope }),
  cliMonitorPoll: (job, since) => post('/cli-monitor/poll', { job, since }),
  cliMonitorStop: (job) => post('/cli-monitor/stop', { job }),

  // A few rows of one table (`{source: 'supabase', schema, table}`) or collection (`{source: 'mongodb', collection}`),
  // credential-like fields masked; and the Atlas cluster behind the MongoDB connection.
  databaseRows: (project, body, opts) => localJob('/database/rows', { project, ...body }, opts),
  databaseAtlas: () => post('/database/atlas', {}),

  // The terminal: what the running app printed (from byte `since`; -1 = its current run), and a command typed in the
  // project folder, read back with cliMonitorPoll / stopped with cliMonitorStop.
  previewLog: (project, since = -1) => post('/preview/log', { project, since }),
  // Every part of the running app and whether it listens; a part that does not is started with
  // send({ type: 'preview_start', project, part }).
  previewPorts: (project) => post('/preview/ports', { project }),
  terminalRun: (project, command) => post('/terminal/run', { project, command }),

  cliSigninAvailable: (provider = '', fresh = false) => post('/cli-signin/available', { provider, fresh }),
  cliSigninStart: (provider, region = '') => post('/cli-signin/start', { provider, region }),
  cliSigninPoll: (flowId) => post('/cli-signin/poll', { flow_id: flowId }),
  cliSigninUseExisting: (provider, region = '') => post('/cli-signin/use-existing', { provider, region }),
  cliSigninCancel: (flowId) => post('/cli-signin/cancel', { flow_id: flowId }),

  supabaseOauthStatus: () => post('/supabase/oauth/status', {}),
  supabaseOauthStart: () => post('/supabase/oauth/start', {}),
  supabaseOauthPoll: (flowId) => post('/supabase/oauth/poll', { flow_id: flowId }),
  supabaseOauthCancel: (flowId) => post('/supabase/oauth/cancel', { flow_id: flowId }),

  // The providers this person has an account with. `plugins()` answers with the
  // catalogue and, for each one, which settings are saved and the last four
  // characters of each — never a value, because a browser that can read a key
  // back is a browser that can leak one.
  plugins: () => req('/plugins'),
  savePlugin: (plugin, mode, values, project = '') => post('/plugins/save', { plugin, mode, values, project }),
  forgetPlugin: (plugin) => post('/plugins/forget', { plugin }),

  // Which plugins one app uses. Saving this is the whole opt-in: the next run
  // merges their settings into that project's .env.local and hands the model
  // their skill pages to read.
  projectPlugins: (project) => req(`/plugins/project/${encodeURIComponent(project)}`),
  setProjectPlugins: (project, enabled) => post('/plugins/project', { project, enabled }),
}


async function deployJob(method, path, body, { onWait, signal } = {}) {
  const started = await post('/deploy/jobs', { path, method, body })
  const id = started.job_id
  for (let i = 0; ; i++) {
    if (signal?.aborted) throw new Error('cancelled')
    await new Promise(r => setTimeout(r, i < 10 ? 300 : 900))
    const job = await req(`/deploy/jobs/${id}`)
    if (job.status === 'running') { onWait?.(job.elapsed); continue }
    if (job.status === 'error') throw new Error(job.error || 'the deployment agent failed')
    if (job.http_status >= 400) {
      const detail = job.result?.error ?? job.result?.detail
      throw new Error(typeof detail === 'string'
        ? detail : `HTTP ${job.http_status}`)
    }
    return job.result
  }
}

const srsInflight = new Map()
async function digest(text) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('')
}
async function srsPrefix() { return `agentforge-srs-job:${await digest(getAuthToken())}:` }
/** Whatever the server said went wrong, as a sentence. */
function readDetail(job) {
  const detail = job?.result?.detail ?? job?.result?.error
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map(d => [Array.isArray(d?.loc) ? d.loc.join('.') : d?.loc, d?.msg]
        .filter(Boolean).join(': '))
      .filter(Boolean).join('; ')
  }
  try { return JSON.stringify(detail) } catch { return String(detail) }
}

async function pollSrs(id, key, { onWait, signal } = {}) {
  const started = Date.now()
  let failures = 0
  while (Date.now() - started < 60 * 60 * 1000) {
    if (signal?.aborted) throw new Error('cancelled')
    await new Promise(resolve => setTimeout(resolve, 1500))
    let job
    try { job = await req(`/srs/jobs/${id}`); failures = 0 }
    catch (error) {
      if (error.status === 404) { try { localStorage.removeItem(key) } catch { }; throw error }
      if (++failures >= 3) throw error
      continue
    }
    if (job.status === 'running') { onWait?.(job.elapsed); continue }
    try { localStorage.removeItem(key) } catch { }
    if (job.status === 'error') throw new Error(job.error || 'The SRS update failed')
    // Format validation error detail lists into human-readable error messages.
    if (job.http_status >= 400) throw new Error(readDetail(job) || `HTTP ${job.http_status}`)
    return job.result
  }
  throw new Error('The SRS job is still pending. Reopen this project to continue following it.')
}
async function srsJob(path, body, options = {}) {
  const key = (await srsPrefix()) + await digest(path + JSON.stringify(body))
  if (srsInflight.has(key)) return srsInflight.get(key)
  const work = (async () => {
    let saved
    try { saved = JSON.parse(localStorage.getItem(key) || 'null') } catch { }
    if (!saved) {
      const started = await post('/srs/jobs', { path, method: 'POST', body })
      saved = { id: started.job_id, path, started: Date.now() }
      try { localStorage.setItem(key, JSON.stringify(saved)) } catch { }
    }
    return pollSrs(saved.id, key, options)
  })()
  srsInflight.set(key, work)
  try { return await work } finally { srsInflight.delete(key) }
}
async function resumeSrsJob(path) {
  const prefix = await srsPrefix()
  for (const key of Object.keys(localStorage)) {
    if (!key.startsWith(prefix)) continue
    let saved
    try { saved = JSON.parse(localStorage.getItem(key)) } catch { continue }
    if (saved?.path !== path) continue
    try { return { resumed: true, result: await (srsInflight.get(key) || pollSrs(saved.id, key)) } }
    catch (error) { if (error.status !== 404) throw error }
  }
  return { resumed: false }
}

const MAX_UPLOAD_BYTES = 7_500_000

function tooBig(file) {
  if ((file?.size || 0) <= MAX_UPLOAD_BYTES) return null
  const mb = n => `${(n / 1_000_000).toFixed(1)} MB`
  return new Error(
    `${file.name || 'that file'} is ${mb(file.size)} — the limit is ${mb(MAX_UPLOAD_BYTES)}.`)
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error(`${file.name} could not be read`))
    // readAsDataURL gives "data:<type>;base64,<payload>".
    reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '')
    reader.readAsDataURL(file)
  })
}

// Supported document and media upload file extensions.
export const ACCEPT_UPLOAD =
  '.pdf,.png,.jpg,.jpeg,.webp,.gif,.bmp,.wav,.mp3,.m4a,.ogg,.webm,.flac,'
  + '.doc,.docx,.pptx,.xlsx,.rtf,.zip,.txt,.md,.csv,.tsv,.json,.yaml,.yml,.html,.xml,'
  + 'image/*,audio/*,application/pdf,application/zip'

export function uploadMode(file) {
  const type = (file.type || '').toLowerCase()
  const name = (file.name || '').toLowerCase()
  if (type.includes('pdf') || name.endsWith('.pdf')) return 'pdf'
  if (type.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp)$/.test(name)) return 'image'
  if (type.startsWith('audio/') || /\.(wav|mp3|m4a|ogg|webm|flac)$/.test(name)) return 'voice'
  if (/\.(docx?|pptx|xlsx|rtf)$/.test(name)) return 'document'
  if (/\.zip$/.test(name) || type.includes('zip')) return 'archive'
  return 'text'
}

async function localJob(path, body, { onWait, signal } = {}) {
  const started = await post('/jobs', { path, method: 'POST', body })
  const id = started.job_id
  for (let i = 0; ; i++) {
    if (signal?.aborted) throw new Error('cancelled')
    await new Promise(r => setTimeout(r, i < 10 ? 300 : 900))
    const job = await req(`/jobs/${id}`)
    if (job.status === 'running') { onWait?.(job.elapsed); continue }
    if (job.status === 'unknown') throw new Error(job.error || 'the job expired')
    if (job.status === 'error') throw new Error(job.error || 'the request failed')
    if (job.http_status >= 400) {
      const detail = job.result?.error ?? job.result?.detail
      throw new Error(typeof detail === 'string' ? detail : `HTTP ${job.http_status}`)
    }
    return job.result
  }
}

export const HTTP_FALLBACK = {
  agent_build: '/agent-build',
  agent_update: '/agent-update',
  agent_resume: '/resume',
  feature: '/feature',
  element_edit: '/element-edit',
  preview_start: '/preview-start',
}
