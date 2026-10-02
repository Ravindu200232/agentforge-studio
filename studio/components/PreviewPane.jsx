'use client'

/** Live application preview pane with element picking and pencil annotation tools. */

import { useAgentPreview } from '@/lib/agent-preview'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Monitor, Tablet, Smartphone, MousePointerClick, Pencil, Undo2, RotateCw, ChevronLeft, ChevronRight, Globe,
  Eraser, Rocket, Layers, Loader2, Play, ExternalLink, Square, Bot,
} from 'lucide-react'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { send } from '@/lib/ws'
import { attachPicker, pickedFrom, pickLabel } from '@/lib/picker'
import { previewHref, needsAddress } from '@/lib/preview'
import { watchFrame, recordConsole } from '@/lib/console-log'
import { Tip } from './ui'
import AgentBrowser from './AgentBrowser'
import LiveE2EOverlay from './LiveE2EOverlay'
import { cn } from '@/lib/utils'

const VIEWPORTS = [
  { id: 'desktop', label: 'Desktop', w: null, Icon: Monitor },
  { id: 'tablet', label: 'Tablet', w: 834, Icon: Tablet },
  { id: 'mobile', label: 'Mobile', w: 390, Icon: Smartphone },
]

// Fewer points than this is a stray click, not a drawing.
const MIN_INK = 3

let seq = 0

function currentPath(frame) {
  if (frame?.dataset?.remote === 'true') return frame.dataset.route || '/'
  try {
    const loc = frame?.contentWindow?.location
    if (!loc || !loc.pathname?.startsWith('/') || !/^https?:$/.test(loc.protocol)) return '/'
    return `${loc.pathname || '/'}${loc.search || ''}${loc.hash || ''}`
  } catch {
    return '/'
  }
}

export default function PreviewPane({ hidden, onBuild }) {
  const frameRef = useRef(null)
  const canvasRef = useRef(null)
  const detachRef = useRef(null)
  const strokesRef = useRef([])
  const drawingRef = useRef(false)
  const lastPathRef = useRef('/')

  const project = useStore(s => s.project)
  const browserFrame = useStore(s => s.browserFrame)
  const { files, busy, workflowStatus, agentState, addLog, setPreviewRoute, undo, setUndo, tests, e2eLive,
    drawing, setDrawing, selection, addSelection, patchSelection, clearSelection } = useAgentPreview(project, 'developer')
  const isE2EActive = Boolean(tests?.running || e2eLive || browserFrame?.frame)
  const runtime = useStore(s => s.runtimes[project])
  const hasBuiltApp = Object.keys(files || {}).some(f =>
    f.startsWith('app/') || f.startsWith('src/') || f.startsWith('pages/') || f.startsWith('packages/') || f.startsWith('client/') || f === 'package.json'
  )
  const isAppBuilt = hasBuiltApp || runtime?.status === 'running' || runtime?.status === 'starting'
  const canResume = !busy && ['paused', 'failed'].includes(workflowStatus) && Boolean(onBuild)
  const planning = busy && agentState === 'planning'

  const [vp, setVp] = useState('desktop')
  const [pickOn, setPickOn] = useState(false)
  const [pencilOn, setPencilOn] = useState(false)
  const [path, setPath] = useState('/')
  const [iframeLoading, setIframeLoading] = useState(true)
  const [previewStopped, setPreviewStopped] = useState(false)
  // The agent was asked to start the app after the preview could not.
  const [agentStarting, setAgentStarting] = useState(false)
  const trail = useRef(['/'])
  const at = useRef(0)
  const jumping = useRef(false)
  const [nav, setNav] = useState({ back: false, forward: false })

  useEffect(() => { setPreviewStopped(false); setAgentStarting(false) }, [project])
  useEffect(() => { if (!busy) setAgentStarting(false) }, [busy])

  // The app's own address as seen from this browser: its local one here, the
  // published one from a phone or another computer (lib/preview.js).
  const previewUrl = previewHref(runtime)
  const [publishing, setPublishing] = useState('')
  const asked = useRef('')

  const bridgeSend = useCallback((kind, data = {}) => {
    if (!previewUrl || !runtime?.runtimeId) return
    frameRef.current?.contentWindow?.postMessage({ type: 'agentforge:command', kind,
      project, runtimeId: runtime.runtimeId, ...data }, new URL(previewUrl).origin)
  }, [project, runtime?.runtimeId, previewUrl])

  const markActivity = useCallback(() => {
    if (runtime?.runtimeId) api.previewActivity(project, runtime.runtimeId).catch(() => {})
  }, [project, runtime?.runtimeId])

  const navigate = useCallback((route = '/') => {
    const f = frameRef.current
    if (!f || !previewUrl) return
    f.dataset.remote = 'true'
    f.dataset.route = route
    f.dataset.scrollX = '0'; f.dataset.scrollY = '0'
    const targetUrl = new URL(route, previewUrl).href
    if (f.src !== targetUrl) {
      setIframeLoading(true)
      f.src = targetUrl
    }
  }, [previewUrl])

  // Resolve network-accessible preview URL for cross-device testing.
  useEffect(() => {
    if (!project || !needsAddress(runtime) || asked.current === project) return
    asked.current = project
    setPublishing('working')
    api.previewLink(project)
      .then(state => { useStore.getState().setRuntime(state); setPublishing('') })
      .catch(error => {
        setPublishing(error.message)
        addLog('WARN', `This app has no public address — ${error.message}`)
      })
  }, [project, runtime?.previewUrl, runtime?.publicUrl, addLog])

  // Reset loading state and auto-start project if stopped
  useEffect(() => {
    setIframeLoading(true)
    if (hidden || !project || busy || drawing || !hasBuiltApp || previewStopped) return
    if (!runtime || runtime?.status === 'stopped') {
      api.open(project).then(res => {
        useStore.getState().setRuntime(res)
      }).catch(() => {})
    }
  }, [project, hidden, hasBuiltApp, previewStopped])

  // Safety fallback for iframe loading state once status is running
  useEffect(() => {
    if (runtime?.status === 'running' && iframeLoading) {
      const timer = setTimeout(() => setIframeLoading(false), 3500)
      return () => clearTimeout(timer)
    }
  }, [runtime?.status, iframeLoading])

  // Observing status never keeps an idle app alive. This also recovers missed
  // socket events after a Studio reload or a backend reconnect.
  useEffect(() => {
    if (!project) return
    let active = true
    const read = () => api.runtime(project).then(result => {
      if (active) useStore.getState().setRuntime(result)
    }).catch(() => {})
    read()
    const timer = setInterval(read, 2000)
    return () => { active = false; clearInterval(timer) }
  }, [project])

  useEffect(() => {
    if (!drawing && runtime?.status === 'running') navigate(lastPathRef.current)
  }, [runtime?.runtimeId, runtime?.status, drawing, navigate])

  const syncPath = useCallback((reason = 'navigation') => {
    const here = currentPath(frameRef.current)
    if (!here) return
    if (lastPathRef.current === here && reason !== 'load') return
    lastPathRef.current = here
    setPath(here)
    setPreviewRoute(here)

    if (jumping.current) {
      jumping.current = false
    } else if (trail.current[at.current] !== here) {
      trail.current = trail.current.slice(0, at.current + 1).concat(here)
      at.current = trail.current.length - 1
    }
    setNav({ back: at.current > 0, forward: at.current < trail.current.length - 1 })
  }, [setPreviewRoute])

  /** The viewport a shot has to be taken at, or the box lands on the wrong thing. */
  const viewportOf = useCallback(() => {
    const f = frameRef.current
    return { w: f?.clientWidth || 1280, h: f?.clientHeight || 800, mode: vp }
  }, [vp])

  /** Attach a picked element or canvas drawing and capture its screenshot. */
  const attachShot = useCallback(async (item, body) => {
    addSelection(item)
    try {
      const r = await api.shot({ ...body, project, runtimeId: runtime?.runtimeId })
      patchSelection(item.key, r?.image
        ? { shot: r.image, state: 'ready' }
        : { state: 'blank' })
    } catch (e) {
      patchSelection(item.key, { state: 'blank' })
      addLog('WARN', `could not photograph that — ${e.message}`)
    }
  }, [addSelection, patchSelection, addLog, project, runtime?.runtimeId])

  const attach = useCallback(() => {
    detachRef.current?.()
    if (frameRef.current?.dataset.remote === 'true') {
      bridgeSend('pick', { enabled: true, mode: vp })
      detachRef.current = () => bridgeSend('pick', { enabled: false })
      return
    }
    detachRef.current = attachPicker(frameRef.current, (el) => {
      const info = pickedFrom(frameRef.current, el, vp)
      attachShot(
        { key: `sel-${++seq}`, kind: 'element', info, state: 'shooting',
          label: pickLabel(info), route: info.route || currentPath(frameRef.current) },
        { route: info.route, viewport: info.viewport || viewportOf(),
          scroll: info.scroll, rect: info.rect })
    })
    if (!detachRef.current) addLog('WARN', 'The preview is not loaded yet')
  }, [vp, addLog, attachShot, viewportOf, bridgeSend])

  useEffect(() => {
    const receive = event => {
      const message = event.data
      if (!previewUrl || event.source !== frameRef.current?.contentWindow ||
          event.origin !== new URL(previewUrl).origin ||
          message?.type !== 'agentforge:preview' || message.project !== project ||
          message.runtimeId !== runtime.runtimeId) return
      if (message.kind === 'route' && typeof message.route === 'string' && message.route.startsWith('/')) {
        const f = frameRef.current
        f.dataset.route = message.route
        f.dataset.scrollX = String(message.scroll?.x || 0)
        f.dataset.scrollY = String(message.scroll?.y || 0)
        syncPath()
      }
      if (message.kind === 'ready' && pickOn) bridgeSend('pick', { enabled: true, mode: vp })
      if (message.kind === 'console') recordConsole(message.level, message.text, project, 'developer')
      if (message.kind === 'picked' && pickOn && message.info) {
        const info = message.info
        attachShot({ key: `sel-${++seq}`, kind: 'element', info, state: 'shooting',
          label: pickLabel(info), route: info.route },
          { route: info.route, viewport: info.viewport || viewportOf(), scroll: info.scroll, rect: info.rect })
      }
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [project, runtime?.previewUrl, runtime?.runtimeId, syncPath, pickOn, bridgeSend, vp, attachShot, viewportOf])

  useEffect(() => {
    if (pickOn) attach()
    else { detachRef.current?.(); detachRef.current = null }
    return () => { detachRef.current?.(); detachRef.current = null }
  }, [pickOn, attach])

  useEffect(() => {
    const f = frameRef.current
    if (!f) return
    const onLoad = () => {
      setIframeLoading(false)
      bridgeSend('init')
      watchFrame(f, project, 'developer')
      syncPath('load')
      if (pickOn) attach()
    }
    f.addEventListener('load', onLoad)
    return () => f.removeEventListener('load', onLoad)
  }, [pickOn, attach, syncPath, bridgeSend])

  useEffect(() => {
    const id = setInterval(() => syncPath('poll'), 250)
    return () => clearInterval(id)
  }, [syncPath])

  // Mirror the route the agent's journey is on in the visible preview.
  useEffect(() => {
    const route = String(e2eLive?.route || '')
    if (!tests.running || !route.startsWith('/')) return
    const f = frameRef.current
    if (!f || currentPath(f) === route) return
    jumping.current = true
    if (runtime?.status === 'running') navigate(route)
  }, [e2eLive?.route, tests.running, runtime?.status, navigate])

  const syncCanvas = useCallback(() => {
    const f = frameRef.current, c = canvasRef.current
    if (!f || !c) return
    c.style.left = f.offsetLeft + 'px'
    c.style.top = f.offsetTop + 'px'
    c.style.width = f.clientWidth + 'px'
    c.style.height = f.clientHeight + 'px'
    const dpr = window.devicePixelRatio || 1
    const want = Math.round(f.clientWidth * dpr)
    if (c.width !== want) {
      c.width = want
      c.height = Math.round(f.clientHeight * dpr)
      const ctx = c.getContext('2d')
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.strokeStyle = '#ff2d55'
      ctx.lineWidth = 3
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
    }
  }, [])

  const clearStrokes = useCallback(() => {
    strokesRef.current = []
    const c = canvasRef.current
    if (!c) return
    const ctx = c.getContext('2d')
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, c.width, c.height); ctx.restore()
  }, [])

  const point = useCallback((e) => {
    const c = canvasRef.current
    const r = c.getBoundingClientRect()
    let sx = 0, sy = 0
    if (frameRef.current?.dataset.remote === 'true') {
      sx = Number(frameRef.current.dataset.scrollX || 0)
      sy = Number(frameRef.current.dataset.scrollY || 0)
    }
    try {
      const w = frameRef.current.contentWindow
      sx = w.scrollX; sy = w.scrollY
    } catch { }
    return {
      cx: e.clientX - r.left, cy: e.clientY - r.top,
      x: Math.round(e.clientX - r.left + sx),
      y: Math.round(e.clientY - r.top + sy),
    }
  }, [])

  useEffect(() => {
    const c = canvasRef.current
    if (!c || !pencilOn) return
    syncCanvas()

    const down = (e) => {
      markActivity()
      drawingRef.current = true
      const pt = point(e)
      strokesRef.current.push([{ x: pt.x, y: pt.y }])
      const ctx = c.getContext('2d')
      ctx.beginPath(); ctx.moveTo(pt.cx, pt.cy)
    }
    const move = (e) => {
      if (!drawingRef.current) return
      const pt = point(e)
      strokesRef.current[strokesRef.current.length - 1].push({ x: pt.x, y: pt.y })
      const ctx = c.getContext('2d')
      ctx.lineTo(pt.cx, pt.cy); ctx.stroke()
    }
    // Lifting the pen finishes one annotation: it is photographed as it stands
    // and attached, and the canvas is wiped so the next ring is its own note.
    const up = () => {
      if (!drawingRef.current) return
      drawingRef.current = false
      const strokes = strokesRef.current
      if (strokes.reduce((a, s) => a + s.length, 0) < MIN_INK) return clearStrokes()
      const route = currentPath(frameRef.current)
      attachShot(
        { key: `sel-${++seq}`, kind: 'drawing', strokes, route, state: 'shooting',
          label: `Drawing on ${route}` },
        { route, viewport: viewportOf(), strokes })
      clearStrokes()
    }

    c.addEventListener('pointerdown', down)
    c.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    const onResize = () => syncCanvas()
    window.addEventListener('resize', onResize)
    return () => {
      c.removeEventListener('pointerdown', down)
      c.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('resize', onResize)
    }
  }, [pencilOn, point, syncCanvas, clearStrokes, attachShot, viewportOf, markActivity])

  function togglePick() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!pickOn) setPencilOn(false)
    setPickOn(v => !v)
  }

  function togglePencil() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!pencilOn) setPickOn(false)
    setPencilOn(v => { if (v) clearStrokes(); return !v })
  }

  async function undoLast() {
    if (!project || !undo) return
    try {
      const r = await api.undo(project, undo.id || '')
      addLog('SUCCESS', 'Restored ' + (r.restored || []).join(', '))
      setUndo(null)
      const f = frameRef.current
      if (f) navigate(currentPath(f))
    } catch (e) {
      addLog('WARN', 'Undo failed: ' + e.message)
    }
  }

  function step(by) {
    const f = frameRef.current
    const next = at.current + by
    if (!f || next < 0 || next >= trail.current.length) return
    at.current = next
    jumping.current = true
    markActivity()
    navigate(trail.current[next])
    setNav({ back: next > 0, forward: next < trail.current.length - 1 })
  }

  async function reloadPreview(fromRoot = false) {
    const f = frameRef.current
    if (!f) return
    setPreviewStopped(false)
    setIframeLoading(true)
    // An iframe mounted before startup may still be about:blank or a browser
    // error document. Reloading that document never reaches the ready app.
    if (drawing) { f.src = currentPath(f); return }
    try {
      const result = await api.open(project)
      useStore.getState().setRuntime(result)
      if (result.status === 'running') navigate(fromRoot === true ? '/' : currentPath(f))
    } catch (error) { 
      addLog('WARN', `Could not reopen app: ${error.message}`)
      setIframeLoading(false)
    }
  }

  /** Hand a preview that will not start to the agent: no chat message and no plan. It starts the
   *  app the way the preview does, fixes what stops it, and the preview opens once it answers. */
  function startWithAgent() {
    const st = useStore.getState()
    if (!project || busy) return
    setPreviewStopped(false)
    setAgentStarting(true)
    st.setBusy(true)
    addLog('INFO', 'The agent is starting the app and fixing what stops it')
    send({ type: 'preview_start', project, agent: 'developer',
           model: st.models.builder || st.models.agent,
           builder_model: st.models.builder || st.models.agent,
           thinking_level: st.thinkingLevel })
  }

  async function stopPreview() {
    if (!project || drawing) return
    setPreviewStopped(true)
    setPickOn(false)
    setPencilOn(false)
    try {
      const result = await api.stopPreview(project)
      useStore.getState().setRuntime(result)
      if (frameRef.current) frameRef.current.src = 'about:blank'
      setIframeLoading(false)
      addLog('INFO', 'Preview stopped. Other project previews keep running.')
    } catch (error) {
      setPreviewStopped(false)
      addLog('WARN', `Could not stop preview: ${error.message}`)
    }
  }

  /** Navigates preview to home when runtime is active; prototypes are served under /prototype/. */
  useEffect(() => {
    const f = frameRef.current
    if (!f) return
    if (!drawing && runtime?.status === 'running') {
      navigate('/')
    }
  }, [drawing, project, runtime?.status, navigate])

  async function approveDrawing() {
    const id = drawing?.id
    if (!id) return
    setDrawing(null)
    try {
      await api.decide({ id, decision: 'approve' })
    } catch (e) {
      addLog('WARN', `Could not accept the drawing — ${e.message}`)
    }
  }

  const wasBusy = useRef(false)
  const hasReadyPreview = useRef(!busy)
  useEffect(() => {
    if (wasBusy.current && !busy) {
      // The shared public origin may still display the previous project's
      // route while this one starts. Its first ready navigation begins at /.
      reloadPreview(!hasReadyPreview.current)
      hasReadyPreview.current = true
    }
    wasBusy.current = busy
  }, [busy])

  // The desktop/tablet/mobile toggle sizes the interactive dev preview. A live test
  // streams its own browser at its own real viewport, so boxing it into whatever
  // width the toggle last picked only shrinks the picture into a partial-looking
  // strip instead of filling the pane it actually has.
  const width = isE2EActive ? null : VIEWPORTS.find(x => x.id === vp)?.w
  const shownPath = tests.running && e2eLive?.route ? e2eLive.route : path

  return (
    <div className={cn('flex min-h-0 flex-1 flex-col bg-panel', hidden && 'hidden')}>
      {/* App preview uses the same compact editing rail as the prototype. */}
      <div className="flex h-[48px] shrink-0 items-center gap-2 border-b border-line/70 bg-panel px-3 backdrop-blur-2xl">
        <div className="flex items-center gap-0.5 rounded-xl border border-line/80 bg-panel/90 p-0.5 shadow-sm">
          <Cell tip={nav.back ? 'Back' : 'Nothing to go back to'}
                disabled={!nav.back} onClick={() => step(-1)} className="rounded-lg px-2">
            <ChevronLeft className="size-3" />
          </Cell>
          <Cell tip={nav.forward ? 'Forward' : 'Nothing to go forward to'}
                disabled={!nav.forward} onClick={() => step(1)} className="rounded-lg px-2">
            <ChevronRight className="size-3" />
          </Cell>
          <Cell tip="Reload the preview" onClick={reloadPreview} className="rounded-lg px-2">
            <RotateCw className={cn("size-3", iframeLoading && "animate-spin text-accent")} />
          </Cell>
        </div>

        <div className="flex min-w-0 flex-1 items-center gap-1.5 rounded-[10px] border border-line bg-panel2/50 px-3 py-1.5 text-[11px] text-muted">
          <Globe className="size-3 shrink-0 text-accent" />
          <span className="truncate font-mono text-[10.5px] font-medium text-ink">
            {drawing ? `the drawing — ${shownPath.split('/').pop() || 'index.html'}`
                     : previewUrl ? `${new URL(previewUrl).host}${shownPath === '/' ? '' : shownPath}`
                     : publishing === 'working' ? 'publishing an address for this app…'
                     : publishing ? publishing
                     : 'App preview'}
          </span>
        </div>

        {!drawing && (canResume ? (
          <button onClick={onBuild}
                  title="Resume the paused build from its saved project state"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1 text-[10.5px] font-semibold text-ink transition-all disabled:pointer-events-none disabled:opacity-50">
            <Play className="size-2.5" /> <span>Resume</span>
          </button>
        ) : planning ? (
          <div className="flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1 text-[10.5px] font-semibold text-ink">
            <Loader2 className="size-2.5 animate-spin text-accent" />
            <span>Planning</span>
          </div>
        ) : runtime?.status === 'running' && !iframeLoading ? (
          <div className="flex items-center gap-1.5 rounded-lg border border-ok/30 bg-panel px-3 py-1 text-[10.5px] font-semibold text-ink">
            <span className="size-1.5 rounded-full bg-ok" />
            <span>Running</span>
          </div>
        ) : (runtime?.status === 'starting' || iframeLoading) ? (
          <div className="flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1 text-[10.5px] font-semibold text-ink">
            <Loader2 className="size-2.5 animate-spin text-accent" />
            <span>Starting</span>
          </div>
        ) : null)}

        {!drawing && ['running', 'starting'].includes(runtime?.status) && (
          <Cell tip="Stop this preview only; other project previews keep running"
                onClick={stopPreview} className="rounded-lg text-bad hover:bg-bad/10">
            <Square className="size-3" />
          </Cell>
        )}

        {/* The drawing is judged here, in the preview, so this is where it is
            accepted. Sending it back is typed in the chat like anything else. */}
        {drawing && (
          <button onClick={approveDrawing}
                  className="shrink-0 rounded-lg border border-line bg-panel px-3 py-1 text-[10.5px] font-semibold text-ink transition-all active:scale-95">
            Build this
          </button>
        )}

        {previewUrl && (
          <a href={previewUrl} target="_blank" rel="noreferrer"
             title="Open app preview in a full browser window"
             className="grid size-7 place-items-center rounded-lg border border-line/80 bg-panel text-ink hover:bg-ink/[.06]">
            <ExternalLink className="size-3" />
          </a>
        )}

        <div className="hidden items-center gap-0.5 rounded-xl border border-line/80 bg-panel/80 p-0.5 shadow-sm md:flex">
          {VIEWPORTS.map(({ id, label, Icon }) => (
            <Cell key={id} tip={label} side="left" on={vp === id}
                  onClick={() => setVp(id)} className="rounded-lg px-2">
              <Icon className="size-3" />
            </Cell>
          ))}
        </div>

        <div className="flex items-center gap-0.5 rounded-xl border border-line/80 bg-panel/80 p-0.5 shadow-sm">
          <Cell tip="Click elements in the preview to attach them to your message"
                side="left" on={pickOn} onClick={togglePick} className="rounded-lg">
            <MousePointerClick className="size-3" />
          </Cell>
          <Cell tip="Draw on the preview to attach a marked-up screenshot"
                side="left" on={pencilOn} onClick={togglePencil} className="rounded-lg">
            <Pencil className="size-3" />
          </Cell>
          <Cell tip={selection.length
                       ? `Clear ${selection.length} attachment${selection.length === 1 ? '' : 's'}`
                       : 'Nothing attached yet'}
                side="left" disabled={!selection.length}
                onClick={() => { clearSelection(); clearStrokes() }} className="rounded-lg">
            <Eraser className="size-3" />
          </Cell>
          <Cell tip={undo ? `Undo the last edit (${undo.files.join(', ')})`
                          : 'Nothing to undo yet'}
                side="left" disabled={!undo} onClick={undoLast} className="rounded-lg">
            <Undo2 className="size-3" />
          </Cell>
        </div>
      </div>

      <div className="relative flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-panel p-3">
        <canvas ref={canvasRef}
                className={cn('absolute z-[8]', pencilOn ? 'block' : 'hidden')}
                style={{ pointerEvents: pencilOn ? 'auto' : 'none',
                         cursor: pencilOn ? 'crosshair' : 'default' }} />

        {(pickOn || pencilOn) && (
          <p className="pointer-events-none absolute inset-x-0 bottom-7 z-[9] mx-auto w-fit rounded-full border border-black/15 bg-panel/95 px-4 py-2 text-[11px] font-medium text-ink shadow-2xl backdrop-blur-xl">
            {pencilOn ? 'Draw around what you mean — it attaches to the chat'
                      : 'Click anything — it attaches to the chat'}
          </p>
        )}

        {tests.running && e2eLive && <LiveE2EOverlay event={e2eLive} />}

        <div className="relative flex h-full min-h-0 flex-1 w-full items-center justify-center overflow-hidden rounded-2xl border border-black/10 bg-panel shadow-2xl">
          <div className={cn("relative h-full w-full max-w-full overflow-hidden bg-panel", width && "border-x border-black/10 shadow-2xl")}
               style={{ width: width ? width + 'px' : '100%' }}>
            <iframe ref={frameRef} id="frame" title="preview" src="about:blank"
                    onLoad={() => setIframeLoading(false)}
                    className={cn("absolute inset-0 block h-full w-full border-0 bg-panel transition-opacity duration-300",
                      ((iframeLoading || runtime?.status === 'starting') && !isE2EActive) ? "opacity-0 pointer-events-none" : "opacity-100")} />

            {/* Smooth Bolt.new loading animation */}
            {((iframeLoading || runtime?.status === 'starting') && !isE2EActive) && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-panel p-6 text-center">
                <div className="absolute inset-x-0 top-0 h-[2px] overflow-hidden bg-black/5">
                  <div className="h-full w-full bg-gradient-to-r from-accent via-accent to-cyan-400 animate-pulse" />
                </div>

                <div className="relative mb-4 grid size-16 place-items-center rounded-2xl border border-accent/20 bg-accent shadow-[0_0_35px_rgba(191, 185, 255,0.18)]">
                  <div className="absolute inset-0 rounded-2xl bg-gradient-to-tr from-ink/10 to-ink/10 animate-pulse" />
                  <Loader2 className="size-7 animate-spin text-ink" />
                </div>

                <h3 className="text-[15px] font-bold tracking-wide text-ink">
                  {runtime?.status === 'starting' ? 'Starting development server…' : 'Loading project preview…'}
                </h3>
                <p className="mt-1.5 max-w-xs text-center text-xs text-muted leading-relaxed">
                  {runtime?.status === 'starting'
                    ? 'Starting the project runtime and loading its pages.'
                    : 'Rendering live application components and compiling assets.'}
                </p>

                {project && (
                  <div className="mt-4 flex items-center gap-2 rounded-full border border-black/10 bg-black/[0.04] px-3.5 py-1 font-mono text-[11px] text-ink shadow-sm">
                    <span className="size-1.5 rounded-full bg-accent animate-ping" />
                    <span className="truncate max-w-[200px]">{project}</span>
                  </div>
                )}
              </div>
            )}

            {previewStopped ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-panel p-8 text-center" role="status">
                <Square className="size-7 text-muted2" />
                <p className="font-semibold text-ink">Preview stopped</p>
                <button onClick={() => reloadPreview(true)} className="rounded-lg border border-line bg-panel px-4 py-2 text-sm font-semibold text-ink hover:border-accent/50">
                  Start preview
                </button>
              </div>
            ) : !canResume && !isAppBuilt && !runtime?.working && runtime?.status !== 'starting' && runtime?.status !== 'running' ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-panel p-8 text-center" role="status">
                <div className="grid size-16 place-items-center rounded-2xl border border-accent/20 bg-accent text-ink shadow-xl">
                  <Rocket className="size-8 text-ink" />
                </div>
                <div className="max-w-md">
                  <h3 className="text-base font-bold text-ink">This app has not been built yet</h3>
                  <p className="mt-1 text-sm text-muted leading-relaxed">
                    Only the specification or HTML prototype exists so far. Build the full application to preview and interact with it live here.
                  </p>
                </div>
                <div className="flex items-center gap-3 mt-2">
                  <button
                    onClick={() => useStore.getState().setView('prototype')}
                    className="inline-flex items-center gap-2 rounded-xl border border-black/10 bg-black/[0.05] px-4 py-2 text-xs font-semibold text-ink shadow-sm transition hover:bg-black/[0.1]"
                  >
                    <Layers className="size-3.5 text-accent" /> View Prototype
                  </button>
                  {onBuild && (
                    <button
                      onClick={onBuild}
                      className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2 text-xs font-semibold text-ink shadow-lg shadow-accent/20 transition hover:bg-accent"
                    >
                      <Rocket className="size-3.5" /> Build App Now
                    </button>
                  )}
                </div>
              </div>
            ) : canResume ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-panel p-8 text-center" role="status">
                <div className="grid size-14 place-items-center rounded-2xl border border-accent/20 bg-accent text-ink">
                  <Play className="size-7" />
                </div>
                <p className="font-semibold text-ink">Build paused</p>
                <p className="max-w-lg text-sm text-muted">The generated files and conversation are saved. Continue from the planning or build stage where it stopped.</p>
                <button onClick={onBuild} className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2 text-sm font-semibold text-ink hover:bg-accent">
                  <Play className="size-3.5" /> Resume Build
                </button>
              </div>
            ) : agentStarting && busy ? (
              <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-panel p-8 text-center" role="status">
                <div className="grid size-14 place-items-center rounded-2xl border border-accent/20 bg-accent text-ink">
                  <Bot className="size-7" />
                </div>
                <p className="flex items-center gap-2 font-semibold text-ink">
                  <Loader2 className="size-3.5 animate-spin text-accent" /> The agent is starting the app
                </p>
                <p className="max-w-lg text-sm text-muted">
                  It runs the app the way the preview does, fixes what stops it, and the preview opens here as soon as the app answers. Its commands show in the chat.
                </p>
              </div>
            ) : runtime?.status === 'failed' ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-panel p-8 text-center" role="status">
                <p className="font-semibold text-rose-400">App could not start</p>
                <p className="max-w-lg whitespace-pre-wrap break-words text-sm text-muted">{runtime?.detail || runtime?.error || 'Failed to start runtime.'}</p>
                <div className="flex items-center gap-2">
                  <button onClick={() => reloadPreview()} disabled={busy}
                          className="rounded-xl border border-line bg-panel px-5 py-2 text-sm font-semibold text-ink hover:border-accent/50 disabled:pointer-events-none disabled:opacity-50">
                    Retry
                  </button>
                  <button onClick={startWithAgent} disabled={busy}
                          title={busy ? 'This project is already working — wait for it to finish' : 'The agent starts the app with its own commands, fixes what stops it, and opens the preview'}
                          className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2 text-sm font-semibold text-ink hover:bg-accent disabled:pointer-events-none disabled:opacity-50">
                    <Bot className="size-3.5" /> Start with agent
                  </button>
                </div>
              </div>
            ) : null}
            {/* While the agent is driving its own browser, that is the more
                interesting of the two — it is the one being tested. */}
            <AgentBrowser />
          </div>
        </div>

      </div>
    </div>
  )
}

function Cell({ tip, on, className, children, ...rest }) {
  return (
    <Tip text={tip}>
      <button {...rest}
              aria-label={tip} aria-pressed={typeof on === 'boolean' ? on : undefined}
              className={cn('grid h-9 place-items-center px-2 text-ink transition-colors',
                on ? 'bg-accent text-ink shadow-sm'
                   : 'hover:bg-ink/[.06] dark:hover:bg-black/[.06]',
                'disabled:pointer-events-none disabled:text-faint', className)}>
        {children}
      </button>
    </Tip>
  )
}
