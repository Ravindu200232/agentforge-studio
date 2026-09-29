
import { create } from 'zustand'
import { advance, emptyProgress } from './progress-model'
import { captureSession, emptySession, reduceSession, ROLES } from './agent-session'

const LS = typeof window === 'undefined' ? null : window.localStorage
const read = (k, fallback) => {
  try { return LS?.getItem(k) ?? fallback } catch { return fallback }
}
const readJSON = (k, fallback) => {
  try { return JSON.parse(LS?.getItem(k) || '') ?? fallback } catch { return fallback }
}


const DEFAULTS = {
  theme: 'dark',

  models: { planner: '', design: '', builder: '', agent: '', qa: '',
            srs: '', deploy: '', image: 'fooocus' },
  // Kept alongside the boolean for older build controls. The chat picker uses
  // this richer level so it can offer Low, High and Extra high explicitly.
  thinkingLevel: 'high',
  think: true,
  // Whether the run in flight is actually reasoning, as reported by the
  // engine - not the same thing as the `think` switch, which is only a request.
  reasoning: false,
  images: false,
  hist: [],
}


export const KEYS = {
  theme: 'agentforge-theme', hist: 'agentforge-hist',
  agent: 'agentforge-am',
  planner: 'agentforge-pm', design: 'agentforge-design-m',
  builder: 'agentforge-builder-m', qa: 'agentforge-qm',
  srs: 'agentforge-sm', deploy: 'agentforge-dm', image: 'agentforge-im',

  srsId: 'agentforge-srs-id', srsPhase: 'agentforge-srs-phase',
  think: 'agentforge-think', thinkingLevel: 'agentforge-thinking-level', images: 'agentforge-img',
  starred: 'agentforge-starred', recent: 'agentforge-recent',
}

const RECENT_KEPT = 20

function readList(key) {
  try {
    const raw = JSON.parse(LS?.getItem(key) || '[]')
    return Array.isArray(raw) ? raw.filter(x => typeof x === 'string') : []
  } catch { return [] }
}


const RESUMABLE_SRS_PHASES = new Set(['planning', 'interview', 'plan', 'review', 'design'])




export const useStore = create((set, get) => ({
  accountEpoch: 0,
  projectSessions: {},
  projectViews: {},
  buildAvailability: {},
  projectSync: {},
  srsStamp: {},
  // Whether a typed change is planned first (propose -> approve) or applied
  // at once — per project, defaulting true (today's always-on behavior) for
  // any project that has never set it.
  planModeByProject: {},
  setPlanMode: (project, enabled) => set(state => ({
    planModeByProject: { ...state.planModeByProject, [project]: enabled } })),
  // Artifact-specific refresh signals. They update only the matching panel and
  // never reset project navigation or reload the whole Studio app.
  prototypeArtifactStamp: {},
  setProjectMetadata: (rows, requestedAt = Date.now()) => set(state => ({ buildAvailability: { ...state.buildAvailability,
    ...Object.fromEntries(rows.filter(row => {
      const designer = state.project === row.name && state.agentRole === 'designer'
        ? state : state.projectSessions[row.name]?.designer
      return !designer || designer.lastEventAt <= requestedAt
    }).map(row => [row.name, Boolean(row.build_available)])) } })),
  agentRole: 'developer',
  draft: '',
  setDraft: (draft) => set({ draft }),
  patchAgentSession: (project, role, patch) => set(state => {
    if (!project || !ROLES.includes(role)) return {}
    const own = state.projectSessions[project] || {}
    const visible = state.project === project && state.agentRole === role
    const previous = visible ? captureSession(state) : (own[role] || emptySession())
    const session = { ...previous, ...(typeof patch === 'function' ? patch(previous) : patch) }
    return { projectSessions: { ...state.projectSessions, [project]: { ...own, [role]: session } },
      ...(visible ? session : {}) }
  }),
  clearAccount: () => {
    get().reset(null)
    get().resetSrs()
    try { LS?.removeItem('agentforge-project-views') } catch { }
    set({ accountEpoch: get().accountEpoch + 1, streams: {}, projectSessions: {}, projectViews: {}, buildAvailability: {}, projectSync: {}, planModeByProject: {},
      srsStamp: {}, prototypeArtifactStamp: {}, runtimes: {}, queue: [] })
  },
  switchAgent: (agentRole) => set(state => {
    if (agentRole === 'developer' && state.project && !state.buildAvailability[state.project]) return {}
    if (!ROLES.includes(agentRole) || agentRole === state.agentRole) return {}
    const own = state.projectSessions[state.project] || {}
    return { projectSessions: { ...state.projectSessions, [state.project]: {
      ...own, [state.agentRole]: captureSession(state) } },
      ...emptySession(), ...own[agentRole], agentRole }
  }),
  applyProjectEvent: (event) => set(state => {
    const project = event.project
    if (!project) return {}
    if (event.type === 'sync_state') return { projectSync: { ...state.projectSync, [project]: event },
      srsStamp: { ...state.srsStamp, [project]: Date.now() } }
    const role = ROLES.includes(event.agent) ? event.agent : 'developer'
    const own = state.projectSessions[project] || {}
    const visible = project === state.project && role === state.agentRole
    const session = reduceSession(visible ? captureSession(state) : own[role], event)
    const availability = role === 'designer' && event.type === 'done'
      ? { buildAvailability: { ...state.buildAvailability, [project]: event.type === 'done' } } : {}
    const changedPath = String(event.name || '')
    const artifactRefresh = event.type === 'file' ? {
      ...(changedPath.startsWith('.agentforge/srs/')
        ? { srsStamp: { ...state.srsStamp, [project]: Date.now() } } : {}),
      ...(changedPath.startsWith('.agentforge/prototype/')
        ? { prototypeArtifactStamp: { ...state.prototypeArtifactStamp, [project]: Date.now() } } : {}),
    } : {}
    return { ...availability, ...artifactRefresh,
      projectSessions: { ...state.projectSessions, [project]: { ...own, [role]: session } },
      ...(visible ? session : {}) }
  }),
  restoreProject: (snapshot) => set(state => {
    if (!snapshot?.project) return {}
    const own = state.projectSessions[snapshot.project] || {}
    const restored = {}
    for (const role of ROLES) {
      const current = snapshot.project === state.project && role === state.agentRole
        ? captureSession(state) : own[role]
      const latestEventAt = Math.max(0, ...(snapshot.events?.[role] || []).map(event => event.at || 0))
      let session = (snapshot.events?.[role] || []).reduce(reduceSession, emptySession())
      // Preserve live events and composer state which arrived while the snapshot was fetched.
      if (current) {
        const saved = session
        if (current.lastEventAt > latestEventAt) session = { ...session, ...current,
          runStats: current.runStats || session.runStats }
        const ids = new Set(session.eventIds)
        session.logs = [...saved.logs, ...current.logs.filter(row => row.at > (saved.logs.at(-1)?.at || 0))].slice(-800)
        session.chat = [...saved.chat, ...current.chat.filter(row => row.at > (saved.chat.at(-1)?.at || 0))].slice(-300)
        session = { ...session, draft: current.draft, selection: current.selection, previewRoute: current.previewRoute,
          files: current.files, eventIds: [...new Set([...ids, ...current.eventIds])].slice(-1200) }
      }
      const run = snapshot.agents?.[role]
      if (run && (!current || current.lastEventAt <= latestEventAt)) { session.busy = ['running', 'queued'].includes(run.status); session.workflowStatus = run.status; session.runId = run.run_id || '' }
      restored[role] = session
    }
    const designerCurrent = snapshot.project === state.project && state.agentRole === 'designer' ? captureSession(state) : own.designer
    const allowed = designerCurrent?.lastEventAt > snapshot.updated_at * 1000 ? state.buildAvailability[snapshot.project] : Boolean(snapshot.build_available)
    return { buildAvailability: { ...state.buildAvailability, [snapshot.project]: allowed },
      projectSync: { ...state.projectSync, [snapshot.project]: snapshot.sync },
      projectSessions: { ...state.projectSessions, [snapshot.project]: restored },
      planModeByProject: { ...state.planModeByProject,
        [snapshot.project]: snapshot.plan_mode !== false },
      ...(state.project === snapshot.project ? restored[state.agentRole] : {}) }
  }),

  status: 'connecting',
  statusText: 'connecting…',
  setStatus: (status, statusText) => set({ status, statusText }),

  busy: false,
  // Preview startup is independent of an agent build in another project.
  opening: false,
  runtimes: {},
  setRuntime: (runtime) => set(state => {
    if (!runtime?.project) return {}
    const previous = state.runtimes[runtime.project]
    if (previous?.serverId === runtime.serverId && previous.revision > runtime.revision) return {}
    return { runtimes: { ...state.runtimes, [runtime.project]: runtime },
      ...(state.project === runtime.project ? { opening: runtime.status === 'starting' } : {}) }
  }),

  // Increment when projects on disk change.
  projectsStamp: 0,

  // Which kind of work is running.
  workKind: '',
  setWorkKind: (workKind) => set({ workKind }),
  setOpening: (opening) => set({ opening }),
  askOpen: false,
  setAskOpen: (askOpen) => set({ askOpen }),
  setBusy: (busy) => set(busy ? { busy } : { busy, opening: false }),
  bumpProjects: () => set(s => ({ projectsStamp: s.projectsStamp + 1 })),

  // Which page of the generated app the preview is showing.
  previewRoute: '/',
  setPreviewRoute: (previewRoute) => set({ previewRoute }),

  e2eLive: null,
  setE2eLive: (e2eLive) => set({ e2eLive }),
  project: null,
  view: 'preview',
  // The deployment run the Deploy panel is showing, so the chat beside it can
  // show that run's conversation without fetching the deploy state twice.
  deployRunId: '',
  setDeployRunId: (deployRunId) => set({ deployRunId: deployRunId || '' }),

  // Store starred and recently opened project IDs in browser local storage.
  starred: readList(KEYS.starred),
  recent: readList(KEYS.recent),
  // Which shelf the Projects screen is showing, set from the sidebar.
  projectFilter: '',
  setProjectFilter: (projectFilter) => set({ projectFilter: projectFilter || '' }),
  toggleStar: (name) => {
    if (!name) return
    const starred = get().starred.includes(name)
      ? get().starred.filter(x => x !== name)
      : [...get().starred, name]
    set({ starred })
    try { LS?.setItem(KEYS.starred, JSON.stringify(starred)) } catch { }
  },
  noteOpened: (name) => {
    if (!name) return
    const recent = [name, ...get().recent.filter(x => x !== name)].slice(0, RECENT_KEPT)
    set({ recent })
    try { LS?.setItem(KEYS.recent, JSON.stringify(recent)) } catch { }
  },
  setView: (view) => {
    const state = get()
    if (['preview', 'testing', 'deploy'].includes(view) && state.project && !state.buildAvailability[state.project]) return
    if (view === 'prototype' || view === 'design') get().switchAgent('designer')
    else if (['preview', 'testing', 'deploy'].includes(view)) get().switchAgent('developer')
    const views = state.project ? { ...state.projectViews, [state.project]: view } : state.projectViews
    set({ view, projectViews: views })
    try { LS?.setItem('agentforge-project-views', JSON.stringify(views)) } catch { }
  },

  srsId: null,

  srsPhase: 'idle',
  srsBusy: '',

  setSrs: (patch) => {
    set(patch)
    try {
      const s = get()
      if (s.srsId) LS?.setItem(KEYS.srsId, s.srsId)
      else LS?.removeItem(KEYS.srsId)
      LS?.setItem(KEYS.srsPhase, s.srsPhase || 'idle')
    } catch { }
  },
  resetSrs: () => {
    set({ srsId: null, srsPhase: 'idle', srsBusy: '' })
    try {
      LS?.removeItem(KEYS.srsId)
      LS?.removeItem(KEYS.srsPhase)
    } catch { }
  },

  logs: [],
  addLog: (level, text) => set(s => ({
    logs: [...s.logs.slice(-800), { level, text, at: Date.now() }],
  })),

  // What the console shows about the run itself: the model, how much of its
  // context window is in use, and how much work it has done.
  runStats: null,
  setRunStats: (runStats) => set({ runStats }),

  // Composing the next move, or carrying one out. The gap between the two is
  // where a feed looks stalled, so it is shown rather than left blank.
  agentState: '',
  setAgentState: (agentState) => set({ agentState }),

  // The one question a run is waiting on, if any. It carries its own deadline
  // and clears itself, so a closed dialog costs a choice and not a build.
  approval: null,
  setApproval: (approval) => set({ approval }),

  // A question the agent stopped to ask, shown in the chat stream rather than
  // over the top of it. The deployment agent has always asked this way and it
  // reads as the agent waiting on you; a dialog reads as the app interrupting.
  ask: null,
  setAsk: (ask) => set({ ask }),

  // Prototype drawing state displayed in preview for interactive user approval.
  drawing: null,
  setDrawing: (drawing) => set({ drawing }),

  // The engine's own browser, as it is right now. Headless, so this is the
  // only way to see what it is doing.
  browserFrame: null,
  setBrowserFrame: (browserFrame) => set({ browserFrame }),

  // Visual attachments for pending messages, including element selections and annotated screenshots.
  selection: [],
  addSelection: (item) => set(s => (
    s.selection.some(x => x.key === item.key)
      ? s
      : { selection: [...s.selection, item].slice(-8) })),
  patchSelection: (key, patch) => set(s => ({
    selection: s.selection.map(x => (x.key === key ? { ...x, ...patch } : x)),
  })),
  removeSelection: (key) => set(s => ({
    selection: s.selection.filter(x => x.key !== key),
  })),
  clearSelection: () => set({ selection: [] }),

  // What the agent and the user actually said to each other, as opposed to the
  // tool activity the chat panel derives from `logs`.
  chat: [],
  pushChat: (entry) => set(s => ({
    chat: [...s.chat.slice(-200), { at: Date.now(), ...entry }],
  })),

  // Queue messages entered while a run is in progress to be sent automatically once it finishes.
  queue: [],
  enqueue: (entry) => set(s => ({
    queue: [...s.queue, { id: `q-${Date.now()}-${s.queue.length}`, at: Date.now(), ...entry }],
  })),
  dropQueued: (id) => set(s => ({ queue: s.queue.filter(item => item.id !== id) })),
  takeQueued: (project, role = get().agentRole) => {
    const next = get().queue.find(item => item.project === project && (!item.payload?.agent || item.payload.agent === role))
    if (next) set(s => ({ queue: s.queue.filter(item => item.id !== next.id) }))
    return next || null
  },

  steps: {},
  setStep: (id, status) => set(s => ({ steps: { ...s.steps, [id]: status } })),
  progress: emptyProgress(),
  setProgress: (step, pct) =>
    set(s => ({ progress: advance(s.progress, step, pct) })),
  phases: [],
  upsertPhase: (p) => set(s => {
    const key = `${p.kind || 'run'}:${p.key || p.title || p.phase}`
    const i = s.phases.findIndex(x => `${x.kind || 'run'}:${x.key || x.title || x.phase}` === key)
    if (i < 0) return { phases: [...s.phases, p] }
    const next = s.phases.slice()
    next[i] = { ...next[i], ...p }
    return { phases: next }
  }),

  files: {},
  activeFile: null,
  liveFile: null,
  liveBuf: '',

  // While a file is being written the code pane follows the writer.
  follow: true,
  putFile: (name, content) => set(s => ({ files: { ...s.files, [name]: content } })),
  setFiles: (files) => set({ files }),
  setActiveFile: (activeFile) => set({ activeFile, follow: false }),

  ...DEFAULTS,

  hydrate: () => {
    if (!LS) return
    // Migrate the former single Agent choice into each explicit role. Once a
    // role is picked it has its own key and no longer follows the legacy one.
    const legacyAgent = read(KEYS.agent, DEFAULTS.models.agent)

    try {
      document.documentElement.setAttribute('data-theme', 'dark')
      document.documentElement.classList.add('dark')
      LS?.setItem(KEYS.theme, 'dark')
    } catch { }
    set({
      theme: 'dark',
      models: {
        planner: read(KEYS.planner, legacyAgent),
        design: read(KEYS.design, legacyAgent),
        builder: read(KEYS.builder, legacyAgent),
        agent: legacyAgent,
        qa: read(KEYS.qa, DEFAULTS.models.qa),
        srs: read(KEYS.srs, DEFAULTS.models.srs),
        deploy: read(KEYS.deploy, DEFAULTS.models.deploy),
        image: read(KEYS.image, DEFAULTS.models.image),
      },
      // Both tiers think. What an older browser saved came from the switch
      // the tiers replaced, and would have sent High without its thinking.
      think: DEFAULTS.think,
      thinkingLevel: ['low', 'high', 'xhigh'].includes(read(KEYS.thinkingLevel, ''))
        ? read(KEYS.thinkingLevel, 'high') : DEFAULTS.thinkingLevel,
      images: read(KEYS.images, '0') === '1',
      hist: readJSON(KEYS.hist, []),
      projectViews: readJSON('agentforge-project-views', {}),
    })

    const srsId = read(KEYS.srsId, '')
    const srsPhase = read(KEYS.srsPhase, 'idle')
    if ((srsId || srsPhase === 'planning') && RESUMABLE_SRS_PHASES.has(srsPhase)) {
      set({ srsId: srsId || null, srsPhase })
    }
  },

  setTheme: () => {
    set({ theme: 'dark' })
    try {
      document.documentElement.setAttribute('data-theme', 'dark')
      document.documentElement.classList.add('dark')
      LS?.setItem(KEYS.theme, 'dark')
    } catch { }
  },
  toggleTheme: () => {},
  persist: (key, value) => { try { LS?.setItem(key, value) } catch { } },

  /** Agent roles that adopt the globally selected language model. */
  ROLE_MODELS: ['agent', 'planner', 'design', 'builder', 'qa', 'srs', 'deploy'],

  applyModel: (model) => {
    const chosen = String(model || '').trim()
    if (!chosen) return []
    const roles = useStore.getState().ROLE_MODELS
    set(state => ({
      models: { ...state.models,
                ...Object.fromEntries(roles.map(role => [role, chosen])) },
    }))
    for (const role of roles) {
      try { LS?.setItem(KEYS[role], chosen) } catch { }
    }
    return roles
  },

  /** Change only the model this chat role will send on its next turn. */
  setRoleModel: (role, model) => {
    const chosen = String(model || '').trim()
    if (!chosen || !useStore.getState().ROLE_MODELS.includes(role)) return
    set(state => ({ models: { ...state.models, [role]: chosen } }))
    try { LS?.setItem(KEYS[role], chosen) } catch { }
  },

  /** The richer effort setting mirrors the legacy on/off request for old flows. */
  setThinkingLevel: (thinkingLevel) => {
    const level = ['low', 'high', 'xhigh'].includes(thinkingLevel) ? thinkingLevel : 'high'
    set({ thinkingLevel: level, think: level !== 'low' })
    try { LS?.setItem(KEYS.thinkingLevel, level) } catch { }
  },

  /** Persisted chat and log streams cached per project across workspace navigation. */
  streams: {},

  // The project a run belongs to, which is not always the one on screen: you
  // can start a build and go and look at something else while it works.
  busyProject: '',
  setBusyProject: (busyProject) => set({ busyProject }),

  /** Merges restored historical project stream events behind any live incoming socket messages. */
  adoptStream: (stream) => set(state => ({
    logs: [...(stream.logs || []), ...state.logs],
    chat: [...(stream.chat || []), ...state.chat],
  })),

      // Persist active project chat stream when switching project context.
  reset: (project) => set(state => {
    const sessions = { ...state.projectSessions }
    if (state.project) sessions[state.project] = { ...sessions[state.project], [state.agentRole]: captureSession(state) }
    const restoredSession = sessions[project]?.[state.agentRole]
    // Event histories and model contexts are durable on the server. Bound browser caches.
    const evictable = Object.keys(sessions).filter(name => name !== project && !ROLES.some(role => sessions[name]?.[role]?.busy))
    for (const name of evictable.slice(0, Math.max(0, Object.keys(sessions).length - 8))) delete sessions[name]
    return {
    project, agentState: '', approval: null, drawing: null,
    browserFrame: null, selection: [],
    steps: {}, phases: [], files: {},
    activeFile: null, liveFile: null, liveBuf: '', follow: true,
    progress: emptyProgress(),
    tests: emptyTests(),
    ask: null,
    question: null,
    qaReport: null,
    undo: null,
    previewRoute: '/',
    e2eLive: null,
    e2eParallel: emptyE2eParallel(),
    ...emptySession(), ...restoredSession,
    projectSessions: sessions,
    opening: false,
    }
  }),

  tests: emptyTests(),
  testStart: () => set({
    tests: { ...emptyTests(), running: true, startedAt: Date.now() },
    e2eParallel: emptyE2eParallel(),
  }),
  testRun: (attempt) => set(s => ({ tests: { ...s.tests, attempt, running: true } })),

  stage: '',
  setStage: (stage) => set({ stage }),
  testResult: (m) => set(s => {
    const rows = [...s.tests.rows, {
      status: m.status || 'run', msg: m.msg || '', detail: m.detail || '',
      stage: s.stage, at: Date.now(),
    }]

    const pass = rows.filter(r => r.status === 'pass').length
    const fail = rows.filter(r => r.status === 'fail').length
    const warn = rows.filter(r => r.status === 'warn').length
    return { tests: { ...s.tests, rows, pass, fail, warn } }
  }),
  testFixing: (m) => set(s => ({
    tests: {
      ...s.tests,
      fixing: [...s.tests.fixing,
               { attempt: m.attempt, errors: m.errors || [], at: Date.now() }],
    },
  })),
  testDone: () => set(s => ({
    tests: { ...s.tests, running: false },
    e2eParallel: { ...s.e2eParallel, active: false },
  })),

  e2eParallel: emptyE2eParallel(),
  e2eParallelEvent: (m) => set(s => {
    const current = s.e2eParallel || emptyE2eParallel()
    if (m.state === 'start') {
      return { e2eParallel: {
        ...emptyE2eParallel(), active: true,
        workers: Math.max(1, Math.min(4, Number(m.workers) || 1)),
        waves: Number(m.waves) || 0,
      } }
    }
    if (m.state === 'wave') {
      return { e2eParallel: {
        ...current, active: true, wave: Number(m.wave) || 0,
        waves: Number(m.waves) || current.waves,
        lanes: emptyE2eLanes(),
      } }
    }
    if (m.state === 'done') {
      return { e2eParallel: { ...current, active: false } }
    }
    return { e2eParallel: current }
  }),
  e2eEvent: (m) => set(s => {
    const current = s.e2eParallel || emptyE2eParallel()
    const laneNo = Math.max(1, Math.min(4, Number(m.lane) || 1))
    const lanes = [...(current.lanes || emptyE2eLanes())]
    const old = lanes[laneNo - 1] || emptyE2eLane(laneNo)
    const state = String(m.state || '')
    lanes[laneNo - 1] = {
      ...old,
      lane: laneNo,
      state,
      title: m.title ?? old.title,
      role: m.role ?? old.role,
      route: m.route ?? old.route,
      label: m.label ?? old.label,
      message: m.message ?? (state === 'journey_start' ? '' : old.message),
      index: Number.isFinite(Number(m.index)) ? Number(m.index) : old.index,
      total: Number.isFinite(Number(m.total)) ? Number(m.total) : old.total,
      ok: m.ok ?? old.ok,
      updatedAt: Date.now(),
    }
    return { e2eParallel: {
      ...current,
      active: current.active || state !== 'journey_done',
      workers: Math.max(current.workers || 0, laneNo),
      lanes,
    } }
  }),

  qaReport: null,
  setQaReport: (qaReport) => set({ qaReport }),

  undo: null,
  setUndo: (undo) => set({ undo }),

  // A question the run stopped on, waiting for an answer.
  question: null,
}))

/** A project's saved stream, or a clean one for a project with no history. */
function restored(stream) {
  return { logs: stream?.logs || [], chat: stream?.chat || [],
           runStats: stream?.runStats || null }
}


function emptyTests() {
  return { running: false, attempt: 0, rows: [], fixing: [],
           pass: 0, fail: 0, warn: 0, startedAt: 0 }
}

function emptyE2eLane(lane) {
  return {
    lane, state: 'idle', title: '', role: '', route: '', label: '',
    message: '', index: 0, total: 0, ok: null, updatedAt: 0,
  }
}

function emptyE2eLanes() {
  return [1, 2, 3, 4].map(emptyE2eLane)
}

function emptyE2eParallel() {
  return { active: false, workers: 0, waves: 0, wave: 0, lanes: emptyE2eLanes() }
}
