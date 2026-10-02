'use client'

import { useEffect, useRef, useState } from 'react'
import { Eye, Code2, Database, EthernetPort, FileText, FlaskConical, History, Plus, Rocket, Layers, Menu, LayoutGrid, SquareTerminal } from 'lucide-react'
import { useStore } from '@/lib/store'
import { answerQuestion, connect, send } from '@/lib/ws'
import { forgetConsole } from '@/lib/console-log'
import { api } from '@/lib/api'
import { previewHref } from '@/lib/preview'
import { catalogue, TIERS } from '@/lib/models'
import { readFolder } from '@/lib/importer'
import Sidebar from '@/components/Sidebar'
import Home from '@/components/Home'
import ProjectsView from '@/components/ProjectsView'
import PreviewPane from '@/components/PreviewPane'
import DesignCustomize from '@/components/DesignCustomize'
import PrototypePane from '@/components/PrototypePane'
import CodePane from '@/components/CodePane'
import SettingsModal from '@/components/SettingsModal'
import TestingResult from '@/components/testing/TestingResult'
import SrsResult from '@/components/srs/SrsResult'
import { Wireframes } from '@/components/srs/Wireframes'
import DeployPanel from '@/components/deploy/DeployPanel'
import VersionsPanel from '@/components/VersionsPanel'
import DatabasePanel from '@/components/database/DatabasePanel'
import TerminalPane from '@/components/TerminalPane'
import PortsPane from '@/components/PortsPane'
import AgentChat from '@/components/AgentChat'
import AgentDecision from '@/components/AgentDecision'
import { useAuthStore } from '@/lib/auth'
import AuthModal from '@/components/AuthModal'
import { Badge } from '@/components/ui'
import { cn } from '@/lib/utils'
import { projectUnitTestStatus } from '@/lib/test-counts'

const TABS = [
  { id: 'srs', label: 'SRS', Icon: FileText },
  { id: 'wireframe', label: 'Wireframe', Icon: LayoutGrid },
  { id: 'prototype', label: 'Prototype', Icon: Layers },
  { id: 'preview', label: 'Preview', Icon: Eye },
  { id: 'code', label: 'Code', Icon: Code2 },
  { id: 'testing', label: 'Testing', Icon: FlaskConical },
  { id: 'deploy', label: 'Deploy', Icon: Rocket },
  { id: 'versions', label: 'Version', Icon: History },
  // The project's tools rather than its stages: what its databases hold, and its terminal.
  { id: 'database', label: 'Database', Icon: Database, group: 'tools' },
  { id: 'terminal', label: 'Terminal', Icon: SquareTerminal, group: 'tools' },
  { id: 'ports', label: 'Ports', Icon: EthernetPort, group: 'tools' },
]

// Lifecycle names and workspace tab ids differ for a few stages.  This lets
// the navigation show the stage the project is currently in.
const STAGE_TAB = {
  interview: 'srs', plan: 'srs', srs: 'srs',
  design: 'wireframe', wireframe: 'wireframe',
  prototype: 'prototype', build: 'preview', builder: 'preview',
  test: 'testing', qa: 'testing',
  deploy: 'deploy', deployment: 'deploy', done: 'versions',
}

const WIREFRAME_APPROVAL_PROMPT =
  'Use the approved /plan as the scope. Read the site map and the application spec at ' +
  '.agentforge/srs/handoff/ (sitemap.md, app.md). Before drawing anything, search the web ' +
  '(the web_search tool) for how good products of this kind lay out their screens, and take ideas ' +
  'from what you find. Then draw one creative, strictly black-and-white low-fidelity HTML wireframe ' +
  'for every planned screen, with no page limit. A screen is one page with one job: tables, forms and ' +
  'detail views each get a page of their own and are linked from the pages that lead to them, never ' +
  'piled into another page; use a popup only for a short contextual action. Draw the shared layout ' +
  'once and keep it identical on every page: the same navigation, header, sidebar and footer in the ' +
  'same position, and the same buttons, forms, cards, tables and status marks. Use realistic sample ' +
  'data and make the way from page to page obvious. Show the pages as a grid, one by one as they ' +
  'finish, and enable editing.'

const PROTOTYPE_APPROVAL_PROMPT =
  'Generate a full prototype by reading the approved wireframes and SRS handoff files. ' +
  'Make a coherent, world-class, realistic prototype using HTML, CSS and purposeful animation, with ' +
  'consistent shared components and a clear end-to-end user flow. If sign-in exists, place clearly ' +
  'labelled fictitious demo credentials for every approved role on the sign-in page, add convenient ' +
  'role demo access, and make each role enter the correct home, navigation and permitted workflow. ' +
  'Use relevant real sample images discovered through Google Images wherever the wireframes call for ' +
  'photography or image content, with descriptive alt text and graceful fallbacks. Check for CSS, link, ' +
  'interaction and runtime errors before finishing.'

async function retry(fn, times, waitMs) {
  let last
  for (let i = 0; i < times; i++) {
    try { return await fn() } catch (e) {
      last = e
      await new Promise(r => setTimeout(r, waitMs))
    }
  }
  throw last
}

/** Show a paused picker question and its answers. */
function ScopeQuestion() {
  const question = useStore(s => s.question)
  if (!question) return null

  const routes = question.routes || []
  return (
    <div className="mb-2 border-l-[3px] border-accent bg-tint p-2.5">
      <p className="text-[12px] leading-relaxed text-ink">
        <b className="font-semibold">{question.file}</b> is on {routes.length} route
        {routes.length === 1 ? '' : 's'}, not just{' '}
        {question.route || 'this page'} — which did you mean?
      </p>
      {routes.length > 0 && (
        <p className="mt-1 truncate font-mono text-[10px] text-muted"
           title={routes.join(', ')}>
          {routes.join(' · ')}
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {(question.options || []).map((option, i) => (
          <button key={option} title={option}
                  onClick={() => answerQuestion(option)}
                  className="border border-line2 bg-panel px-2.5 py-1
                             text-left text-[11px] font-semibold text-ink
                             transition-colors hover:border-accent hover:text-accent">
            {i === 0 ? `${question.route || 'This page'} only`
                     : `All ${routes.length} routes`}
          </button>
        ))}
        <button onClick={() => useStore.setState({ question: null })}
                className="px-1.5 text-[11px] text-muted hover:text-ink">
          Leave it
        </button>
      </div>
    </div>
  )
}

export default function Studio() {
  const view = useStore(s => s.view)
  const setView = useStore(s => s.setView)
  const project = useStore(s => s.project)
  const agentRole = useStore(s => s.agentRole)
  const buildAllowed = useStore(s => Boolean(s.buildAvailability[s.project]))
  const syncState = useStore(s => s.projectSync[s.project])
  const busy = useStore(s => s.busy)
  const busyProject = useStore(s => s.busyProject)
  const testsRunning = useStore(s => s.tests.running)
  const qa = useStore(s => s.qaReport)
  const setQa = useStore(s => s.setQaReport)
  const liveFile = useStore(s => s.liveFile)

  const [projects, setProjects] = useState([])
  const [cat, setCat] = useState(() => catalogue(null))
  const [screen, setScreen] = useState('home')
  const [settingsOpen, setSettingsOpen] = useState(false)
  // The tab Settings opens on ('' = its own first tab), and a count of closings: Home re-reads
  // the account connections whenever Settings closes, since that is where they are made.
  const [settingsTab, setSettingsTab] = useState('')
  const [settingsClosed, setSettingsClosed] = useState(0)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [mobileView, setMobileView] = useState('view') // 'chat' | 'view'
  const opening = useRef(0)
  const wireframeApproval = useRef(null)
  const prototypeApproval = useRef(null)

  useEffect(() => {
    if (busy) setMobileView('chat')
  }, [busy])

  const { user, init: initAuth, logout } = useAuthStore()
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [authInitialScreen, setAuthInitialScreen] = useState('methods')
  // A fresh modal every time it opens: its screen is only read when it mounts,
  // and the last person's email and password must not be waiting in it.
  const [authKey, setAuthKey] = useState(0)

  function openAuth(which) {
    setAuthInitialScreen(which)
    setAuthKey(k => k + 1)
    setAuthModalOpen(true)
  }

  // Signing out goes straight to signing in, with nothing of the last
  // person's work left on screen for whoever signs in next.
  async function signOut() {
    await logout()
    setProjects([])
    setScreen('home')
  }

  const refreshProjects = () => {
    const requestedAt = Date.now()
    const epoch = useStore.getState().accountEpoch
    return api.projects().then(r => {
      if (useStore.getState().accountEpoch !== epoch) return []
      const list = Array.isArray(r) ? r : (r.projects || [])
      setProjects(list)
      useStore.getState().setProjectMetadata(list, requestedAt)
      return list
    })
    .catch(() => [])
  }

  const projectsStamp = useStore(s => s.projectsStamp)
  useEffect(() => {
    if (projectsStamp) refreshProjects()
  }, [projectsStamp])

  useEffect(() => {
    initAuth()
  }, [])

  // A session that ends - signed out here, expired, or ended from somewhere
  // else - lands on the sign-in page rather than an empty studio.
  const wasSignedIn = useRef(false)
  useEffect(() => {
    if (user) {
      wasSignedIn.current = true
      return
    }
    if (!wasSignedIn.current) return
    wasSignedIn.current = false
    openAuth('email')
  }, [user])

  useEffect(() => {
    refreshProjects()
  }, [user])

  useEffect(() => {
    useStore.getState().hydrate()
    const disconnect = connect()
    refreshProjects()
    api.models().then(r => {
      const c = catalogue(r)
      setCat(c)

      const cur = useStore.getState().models
      const known = new Set([...c.cloud, ...(c.local || [])].map(m => m.id))
      api.settings().then(s => {
        const legacy = String(s?.agent_model || '').trim()
        // A first run has nothing saved: a model this engine really has, preferring the usual default.
        const fallback = [TIERS.medium.model, TIERS.high.model, TIERS.ultra.model].find(id => known.has(id))
          || c.cloud[0]?.id || (c.local || []).find(m => !m.willPull)?.id || TIERS.medium.model
        const pick = value => {
          const saved = String(value || legacy).trim()
          return (saved && known.has(saved)) ? saved : fallback
        }
        const now = useStore.getState().models
        // A choice this engine does not have (an earlier default, a model since removed) is chosen again.
        const keep = value => value && (!known.size || known.has(value))
        if (!(keep(now.planner) && keep(now.design) && keep(now.builder))) {
          useStore.setState({ models: {
            ...now,
            planner: keep(now.planner) ? now.planner : pick(s?.planner_model),
            design: keep(now.design) ? now.design : pick(s?.design_model),
            builder: keep(now.builder) ? now.builder : pick(s?.builder_model),
          } })
        }
        // The interview and the specification run on the saved model: never leave it empty or unknown.
        const chosen = useStore.getState().models.builder
        if (chosen && (!legacy || !known.has(legacy)) && known.has(chosen)) {
          api.saveSettings({ agent_model: chosen }).catch(() => { })
        }
      }).catch(() => {
        if (cur.planner && cur.design && cur.builder) return
        const now = useStore.getState().models
        useStore.setState({ models: {
          ...now,
          planner: now.planner || TIERS.medium.model,
          design: now.design || TIERS.medium.model,
          builder: now.builder || TIERS.medium.model,
        } })
      })
    }).catch(() => { })
    return disconnect
  }, [])

  useEffect(() => {
    if (!project || agentRole !== 'developer' || testsRunning || qa?.project === project) return
    let active = true
    retry(() => api.qa(project), 4, 700).then(report => {
      const current = useStore.getState()
      if (active && current.project === project && current.agentRole === 'developer' && !current.tests.running) {
        setQa(report)
      }
    }).catch(() => { })
    return () => { active = false }
  }, [project, agentRole, testsRunning, qa?.project, setQa])

  useEffect(() => {
    if (!project) return
    let live = true
    api.files(project, agentRole).then(raw => {
      if (!live) return
      const files = Object.fromEntries(Object.entries(raw || {}).map(([name, value]) => [name, typeof value === 'string' ? value : value.content || '']))
      useStore.getState().setFiles(files)
    }).catch(() => {})
    return () => { live = false }
  }, [project, agentRole])

  const unitStatus = projectUnitTestStatus(qa, project)

  const currentProjectObj = projects.find(p => p.name === project)
  const currentStageTab = STAGE_TAB[String(currentProjectObj?.stage || '').toLowerCase()] || null
  const specOnly = Boolean(currentProjectObj?.spec_only) && busyProject !== project
  const prototypeOnly = Boolean(currentProjectObj?.prototype_only) && busyProject !== project

  let tabs = TABS

  useEffect(() => {
    if (liveFile) setScreen('workspace')
  }, [liveFile])

  const drawing = useStore(s => s.drawing)

  useEffect(() => {
    if (drawing && view !== 'prototype') setView('prototype')
  }, [drawing, view, setView])


  async function openProject(name, row = null) {
    const st = useStore.getState()
    if (!name || (st.opening && st.project === name)) return
    st.noteOpened(name)
    const request = ++opening.current
    const rowObj = row || projects.find(p => p.name === name)
    const savedView = st.projectViews[name]
    // Return to the exact tab the customer left open. A built project defaults
    // to Preview only when it has no saved tab yet.
    const built = Boolean(rowObj?.build_available || st.buildAvailability[name])
    const requestedView = savedView === 'design' ? 'wireframe'
      : savedView || (built ? 'preview'
        : rowObj?.spec_only && !rowObj?.prototype_only ? 'srs'
          : rowObj?.prototype_only ? 'prototype' : 'preview')
    const projectView = ['preview', 'testing', 'deploy'].includes(requestedView) && !built ? 'prototype' : requestedView

    if (st.project === name && st.runtimes[name]?.status === 'running') {
      try {
        st.setRuntime(await api.open(name))
        if (opening.current === request) {
          setScreen('workspace')
          setView(projectView)
        }
      } catch (error) {
        if (opening.current === request) st.addLog('WARN', `Could not open app: ${error.message}`)
      }
      return
    }

    st.reset(name)
    setScreen('workspace')

    setView(projectView)

    st.setOpening(true)
    st.setProgress(`Opening ${name}…`, 0)
    forgetConsole()

    api.workflow(name)
      .then(snapshot => {
        if (opening.current !== request) return
        useStore.getState().restoreProject(snapshot)
      })
      .catch(() => { })


    let opened = false
    try {
      const runtime = await api.open(name)
      if (opening.current === request && useStore.getState().project === name) {
        useStore.getState().setRuntime(runtime)
        opened = true
      }
    } catch (e) {
      if (opening.current !== request) return
      useStore.getState().addLog('WARN', `could not open ${name}: ${e.message}`)
      if (!opened) useStore.getState().setRuntime({ ...useStore.getState().runtimes[name],
        project: name, status: 'failed', error: e.message })
    } finally {
      if (opening.current === request && useStore.getState().project === name) {
        useStore.getState().setOpening(false)
      }
    }
  }

  function resumeBuild() {
    const st = useStore.getState()
    const name = st.project
    const row = projects.find(item => item.name === name)
    const resumesPrototype = !st.buildAvailability[name]
      && ['design', 'prototype'].includes(row?.stage)
    if (!name || st.busy || (!st.buildAvailability[name] && !resumesPrototype)) return
    st.switchAgent(resumesPrototype ? 'designer' : 'developer')
    st.setView(resumesPrototype ? 'prototype' : 'preview')
    st.setBusy(true)
    st.setProgress(resumesPrototype ? 'Resuming prototype…' : 'Resuming…', 0)
    st.addLog('INFO', `Resuming ${name} — picking up where it stopped`)
    setScreen('workspace')
    send({ type: 'agent_resume', project: name,
           agent: resumesPrototype ? 'designer' : 'developer',
           model: st.models.builder || st.models.agent,
           builder_model: st.models.builder || st.models.agent,
           planner_model: st.models.planner || st.models.agent,
           design_model: st.models.design || st.models.agent,
           think: st.think,
           thinking_level: st.thinkingLevel,
           qa_model: st.models.qa })
  }

  function approveSrsAndDraw() {
    const name = useStore.getState().project
    if (!name || wireframeApproval.current) return
    useStore.getState().applyProjectEvent({
      type: 'sync_state', project: name, status: 'running', source: 'wireframe',
    })
    setView('wireframe')
    setMobileView('view')
    const job = api.srs(`/projects/${encodeURIComponent(name)}/approve`, {
      prompt: WIREFRAME_APPROVAL_PROMPT,
    })
    wireframeApproval.current = job
    job.then(() => {
      useStore.getState().applyProjectEvent({
        type: 'sync_state', project: name, status: 'clean', source: 'wireframe',
      })
      useStore.getState().bumpProjects()
    }).catch(error => {
      useStore.getState().applyProjectEvent({
        type: 'sync_state', project: name, status: 'failed', source: 'wireframe',
        error: error.message,
      })
      useStore.getState().addLog('WARN', `Wireframe generation failed: ${error.message}`)
    }).finally(() => { wireframeApproval.current = null })
  }

  function approveWireframesAndBuildPrototype() {
    const name = useStore.getState().project
    if (!name) return
    setView('design')
    setMobileView('view')
  }

  function startPrototypeFromDesign(customizerPrompt = '') {
    const name = useStore.getState().project
    if (!name || prototypeApproval.current) return
    useStore.getState().switchAgent('designer')
    useStore.getState().applyProjectEvent({
      type: 'sync_state', project: name, status: 'running', source: 'prototype',
      detail: 'Planning the prototype from the selected design…',
    })
    setView('prototype')
    setMobileView('view')
    const job = api.srs(`/projects/${encodeURIComponent(name)}/wireframes/approve`, {
      prompt: [PROTOTYPE_APPROVAL_PROMPT, customizerPrompt].filter(Boolean).join('\n\n'),
    })
    prototypeApproval.current = job
    job.then(() => {
      useStore.getState().applyProjectEvent({
        type: 'sync_state', project: name, status: 'clean', source: 'prototype',
      })
      useStore.getState().bumpProjects()
    }).catch(error => {
      useStore.getState().applyProjectEvent({
        type: 'sync_state', project: name, status: 'failed', source: 'prototype',
        error: error.message,
      })
      useStore.getState().addLog('WARN', `Prototype generation failed: ${error.message}`)
    }).finally(() => { prototypeApproval.current = null })
  }

  async function importFolder(list) {
    const s = useStore.getState()
    setScreen('workspace')
    s.reset(null)
    s.setBusy(true)
    s.setStatus('busy', 'importing…')
    try {
      const { name, title, files, skipped } = await readFolder(list, (done, total) => {
        if (done % 25 === 0 || done === total) {
          s.setProgress(`Reading ${done}/${total}…`, Math.round(done / total * 60))
        }
      })
      s.addLog('INFO', `${Object.keys(files).length} file(s) to import`
                     + (skipped ? `, ${skipped} skipped` : ''))
      const r = await api.uploadProject({ name, title, files })
      const imported = r.project || r.name || name
      s.addLog('SUCCESS', `Imported ${imported}`)
      s.setBusy(false)
      s.setStatus('live', 'ready')
      await refreshProjects()
      await openProject(imported)
    } catch (e) {
      s.addLog('ERROR', 'Import failed: ' + e.message)
      s.setBusy(false)
      s.setStatus('disconnected', 'import failed')
    }
  }

  async function downloadZip() {
    const st = useStore.getState()
    if (!st.project) return
    try {
      const { default: JSZip } = await import('jszip')
      const zip = new JSZip()
      for (const [path, body] of Object.entries(st.files)) zip.file(path, body)
      const blob = await zip.generateAsync({ type: 'blob' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = st.project + '.zip'
      a.click()
      URL.revokeObjectURL(url)
      st.addLog('SUCCESS', `Downloaded ${st.project}.zip`)
    } catch (e) {
      st.addLog('WARN', 'Could not build the zip: ' + e.message)
    }
  }

  async function openPreviewInNewTab() {
    const name = useStore.getState().project
    if (!name) return
    const tab = window.open('about:blank', '_blank')
    try {
      const runtime = await api.open(name)
      useStore.getState().setRuntime(runtime)
      if (tab) {
        tab.opener = null
        tab.location.href = previewHref(runtime) || runtime.previewUrl
      }
    } catch (error) {
      tab?.close()
      useStore.getState().addLog('WARN', `Could not open preview: ${error.message}`)
    }
  }

  return (
    <div className="flex h-full w-full overflow-hidden bg-bg text-ink">
      {user && (
        <Sidebar
          projects={projects}
          onImport={importFolder}
          onSettings={() => {
            setMobileNavOpen(false)
            setSettingsOpen(true)
          }}
          workspaceTabs={TABS}
          currentView={view}
          currentStageTab={currentStageTab}
          buildAllowed={buildAllowed}
          onViewChange={setView}
          onZip={downloadZip}
          screen={screen}
          onScreenChange={(s) => {
            setMobileNavOpen(false)
            setScreen(s)
          }}
          user={user}
          onLogout={signOut}
          mobileOpen={mobileNavOpen}
          onMobileClose={() => setMobileNavOpen(false)}
        />
      )}

      <AgentDecision />

      {settingsOpen && (
        <SettingsModal initialTab={settingsTab}
                       onClose={() => { setSettingsOpen(false); setSettingsTab(''); setSettingsClosed(n => n + 1) }}
                       onSaved={() => api.models().then(r => setCat(catalogue(r)))
                                         .catch(() => { })}
                       onImport={importFolder}
                       onZip={downloadZip}
                       onOpenInNewTab={openPreviewInNewTab}
                       onLogout={signOut} />
      )}

      <AuthModal
        key={authKey}
        isOpen={authModalOpen}
        initialScreen={authInitialScreen}
        onClose={() => setAuthModalOpen(false)}
        onSuccess={() => {
          setAuthModalOpen(false)
          refreshProjects()
        }}
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-panel">
        {/* Mobile Header for Home / Projects when signed in */}
        {user && screen !== 'workspace' && (
          <div className="md:hidden flex h-12 shrink-0 items-center justify-between border-b border-line bg-panel/95 px-4 backdrop-blur-md">
            <button
              onClick={() => setMobileNavOpen(true)}
              className="flex items-center justify-center size-8 rounded-lg border border-line bg-panel2/80 text-muted hover:text-ink"
              title="Open Navigation"
            >
              <Menu className="size-4" />
            </button>
            <div className="flex items-center gap-2">
              <div className="flex size-6 items-center justify-center rounded-lg bg-accent ring-1 ring-accent/30">
                <img src="/__agentforge/agentforge-mark.png" alt="AgentForge" className="size-4 object-contain" />
              </div>
              <span className="font-display text-[14px] font-bold text-ink">agentforge</span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => {
                  useStore.getState().resetSrs()
                  useStore.getState().reset(null)
                  setScreen('home')
                }}
                className="flex items-center justify-center size-8 rounded-lg border border-line bg-panel2/80 text-muted hover:text-ink cursor-pointer"
                title="New project"
              >
                <Plus className="size-4" />
              </button>
            </div>
          </div>
        )}

        {/* Workspace Top Navbar */}
        {screen === 'workspace' && (
          <div className="md:hidden flex h-[48px] shrink-0 items-center gap-2 border-b border-line bg-panel/95 px-2 sm:px-4 backdrop-blur-md">
            {/* Mobile Sidebar Hamburger Button */}
            <button
              onClick={() => setMobileNavOpen(true)}
              className="md:hidden flex items-center justify-center size-8 rounded-lg border border-line bg-panel2/80 text-muted hover:text-ink shrink-0"
              title="Open Menu"
            >
              <Menu className="size-4" />
            </button>

            <div className="flex items-center gap-1 rounded-full bg-panel2/80 p-0.5 border border-line overflow-x-auto no-scrollbar max-w-[calc(100vw-190px)] sm:max-w-none">
              {tabs.map(({ id, label, Icon }) => {
                const isCurrentStage = id === currentStageTab
                const isSelected = view === id
                return (
                <button key={id} onClick={() => setView(id)}
                        disabled={!buildAllowed && ['preview', 'testing', 'deploy'].includes(id)}
                        title={!buildAllowed && ['preview', 'testing', 'deploy'].includes(id) ? 'Complete the prototype first' : label}
                        className={cn('inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full px-3',
                          'font-display text-[11px] font-semibold transition-all disabled:opacity-35 disabled:cursor-not-allowed',
                          isSelected ? 'text-deep'
                                      : 'text-muted hover:bg-black/[.03] hover:text-ink dark:hover:bg-black/5')}>
                  <Icon className={cn('size-3.5 shrink-0', isCurrentStage ? 'text-ok' : isSelected ? 'text-deep' : 'text-muted2')} />
                  {label}
                  {id === 'testing' && unitStatus?.failed > 0
                    && !(busy && (!busyProject || busyProject === project)) && (
                    <Badge tone="bad">{unitStatus.failed}</Badge>
                  )}
                </button>
                )
              })}
            </div>

            <span className="flex-1" />

            {/* Mobile View Switcher Pill: Chat vs Workspace View */}
            <div className="lg:hidden flex items-center rounded-full bg-panel2/80 p-0.5 border border-line shrink-0 mr-1">
              <button
                type="button"
                onClick={() => setMobileView('chat')}
                className={cn(
                  'h-7 px-2.5 rounded-full text-[11px] font-semibold transition-all flex items-center gap-1.5',
                  mobileView === 'chat'
                    ? 'text-deep'
                    : 'text-muted hover:text-ink'
                )}
              >
                <span>Chat</span>
                {busy && <span className="size-1.5 rounded-full bg-white animate-pulse" />}
              </button>
              <button
                type="button"
                onClick={() => setMobileView('view')}
                className={cn(
                  'h-7 px-2.5 rounded-full text-[11px] font-semibold transition-all',
                  mobileView === 'view'
                    ? 'text-deep'
                    : 'text-muted hover:text-ink'
                )}
              >
                <span>Workspace</span>
              </button>
            </div>

            {/* Action to Build full app from SRS-only project */}
            {specOnly && !prototypeOnly && !busy && buildAllowed && (
              <button
                onClick={resumeBuild}
                title="Build this application from the approved SRS"
                className="inline-flex h-9 items-center gap-2 rounded-full bg-accent hover:bg-press px-4 text-[11.5px] font-semibold text-ink shadow-[0_8px_16px_0_rgba(191, 185, 255,0.24)] transition-all mr-2"
              >
                <Rocket className="size-[13px]" /> Build Now
              </button>
            )}

            {/* Action to Build full app from Prototype-only project */}
            {prototypeOnly && !busy && buildAllowed && (
              <button
                onClick={resumeBuild}
                title="Build full application from this prototype"
                className="inline-flex h-9 items-center gap-2 rounded-full bg-accent hover:bg-press px-4 text-[11.5px] font-semibold text-ink shadow-[0_8px_16px_0_rgba(191, 185, 255,0.24)] transition-all mr-2"
              >
                <Rocket className="size-[13px]" /> Build App Now
              </button>
            )}

            {busy && (
              <span className="flex items-center gap-2 rounded-full bg-accent px-3 py-1.5 text-[11px] font-medium text-ink">
                <span className="size-1.5 animate-pulse bg-accent" />
                working
              </span>
            )}

            <button onClick={() => {
                      useStore.getState().resetSrs()
                      setScreen('home')
                    }}
                    className="inline-flex h-9 items-center gap-2 rounded-full bg-panel px-3.5 text-[11px] font-semibold text-ink shadow-sm ring-1 ring-line/70 transition-all hover:bg-raised">
              <Plus className="size-[13px]" /> New
            </button>
          </div>
        )}

        {screen === 'home' ? (
          <Home
            modelOptions={cat.all}
            user={user}
            onSettings={tab => { setSettingsTab(tab || ''); setSettingsOpen(true) }}
            connectionsVersion={settingsClosed}
            onRequireAuth={() => openAuth('methods')}
            onSignIn={() => openAuth('email')}
            onSignUp={() => openAuth('email')}
            onStarted={() => setScreen('workspace')}
            onKept={async (name) => {
              const list = await refreshProjects()
              openProject(name, list.find(p => p.name === name))
            }}
          />
        ) : screen === 'projects' ? (
          <ProjectsView
            projects={projects}
            activeProject={project}
            busyProject={busyProject}
            onOpen={(name, p) => openProject(name, p)}
            onCreateNew={() => {
              useStore.getState().resetSrs()
              useStore.getState().reset(null)
              setScreen('home')
            }}
            onDelete={async (name) => {
              try {
                await api.deleteProject(name)
              } catch (e) {
                // Server might have already removed it; still refresh the list
                console.warn('deleteProject error:', e.message)
              }
              refreshProjects()
              if (project === name) {
                useStore.getState().reset(null)
                setScreen('home')
              }
            }}
            onBuildProject={async (name, p) => {
              await openProject(name, p)
              if (useStore.getState().project === name) resumeBuild()
            }}
          />
        ) : (
          <div className="flex min-h-0 flex-1 bg-bg/40 overflow-hidden">
            <div className={cn(
              "shrink-0 h-full",
              mobileView === 'chat' ? 'flex w-full lg:w-auto' : 'hidden lg:flex'
            )}>
              <AgentChat key={`${project}-${agentRole}`}
                         projectTitle={projects.find(row => row?.name === project)?.title || ''} />
            </div>

            <div className={cn(
              "relative min-w-0 flex-1 flex-col h-full",
              mobileView === 'view' ? 'flex' : 'hidden lg:flex'
            )}>
              <ScopeQuestion />
              {syncState?.status === 'failed' && <div role="alert" className="flex items-center gap-3 border-b border-line bg-panel p-3 text-xs text-muted">
                <span>{syncState.source === 'wireframe' ? 'Wireframe generation paused' : syncState.source === 'prototype' ? 'Prototype generation paused' : 'Document update paused'}: {syncState.error}</span>
                {['wireframe', 'prototype'].includes(syncState.source)
                  ? <button className="shrink-0 text-accent" onClick={() => setView(syncState.source === 'prototype' ? 'wireframe' : 'srs')}>
                      {syncState.source === 'prototype' ? 'Open Wireframe to retry' : 'Open SRS to retry'}
                    </button>
                  : <button className="shrink-0 text-accent" onClick={() => api.retrySync(project)}>Retry update</button>}
              </div>}

              <PreviewPane key={`preview-${project}`} hidden={view !== 'preview'} onBuild={resumeBuild} />
              <PrototypePane key={`proto-${project}`} project={project} hidden={view !== 'prototype'} onBuild={resumeBuild}
                             generating={syncState?.status === 'running' && syncState?.source === 'prototype'}
                             generationStatus={syncState?.source === 'prototype' ? syncState?.detail : ''}
                             canResumePrototype={!buildAllowed && ['design', 'prototype'].includes(currentProjectObj?.stage)} />
              {view === 'design' && <DesignCustomize key={`design-${project}`} projectId={project}
                onBack={() => setView('wireframe')}
                onContinue={async ({ direction, designSpec }) => {
                  if (project?.startsWith('prj_') && !buildAllowed) {
                    const design = await api.draftDesignSpec(project, designSpec, direction)
                    await api.approveDesignSpec(project, design.version)
                    startPrototypeFromDesign(direction)
                    return
                  }
                  const found = await api.srsResults(project)
                  const srsId = found?.link?.srs_id
                  if (!srsId) throw new Error('This project has no linked SRS for a versioned design update.')
                  const design = await api.draftDesignSpec(srsId, designSpec, direction)
                  await api.approveDesignSpec(srsId, design.version)
                  const created = await api.createChangeRequest({
                    project, kind: 'design', prompt: direction, targets: ['designer'],
                    design_spec_version: design.version, summary: design.summary || [],
                  })
                  await api.approveChangeRequest(project, created?.request?.id, ['designer'])
                  const current = useStore.getState()
                  current.addLog('INFO', `Approved Design Spec v${design.version}; updating the prototype.`)
                  setView('prototype')
                }} />}
              <CodePane hidden={view !== 'code'} />
              {view === 'testing' && <TestingResult key={`testing-${project}`} />}
              {view === 'srs' && (
                <SrsResult key={`srs-${project}`} onApprove={approveSrsAndDraw} />
              )}
              {view === 'wireframe' && (
                <div className="min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top_right,rgba(191, 185, 255,.07),transparent_30%)] p-5">
                  <div className="mx-auto max-w-[1400px]">
                    <div className="mb-5">
                      <h1 className="text-lg font-semibold text-ink">Wireframes</h1>
                      <p className="text-xs text-muted">All planned screens in a grid. Open a page to edit its layout.</p>
                    </div>
                    <Wireframes srs={{ project }} generating={syncState?.status === 'running' && ['srs', 'wireframe'].includes(syncState?.source)}
                                approving={syncState?.status === 'running' && syncState?.source === 'prototype'}
                                onApprove={approveWireframesAndBuildPrototype}
                                onRetryPrototype={() => startPrototypeFromDesign()} />
                  </div>
                </div>
              )}
              {view === 'deploy' && (
                <DeployPanel key={`deploy-${project}`}
                             onSettings={() => setSettingsOpen(true)} />
              )}
              {view === 'versions' && <VersionsPanel key={`versions-${project}`} />}
              {view === 'database' && (
                <DatabasePanel key={`database-${project}`} stack={currentProjectObj?.stack || ''}
                               onSettings={tab => { setSettingsTab(tab || ''); setSettingsOpen(true) }}
                               connectionsVersion={settingsClosed} />
              )}
              <TerminalPane key={`terminal-${project}`} hidden={view !== 'terminal'} />
              {view === 'ports' && <PortsPane key={`ports-${project}`} />}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
