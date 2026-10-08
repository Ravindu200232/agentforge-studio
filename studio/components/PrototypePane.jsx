'use client'

/**
 * The prototype viewer: the high-fidelity React app, one page at a time with every page listed on the side, plus element
 * selection, pencil annotations and the text tool (click words, retype them). The app is framed by the same guarded
 * preview the wireframe uses, so a button in it goes to another page of the app and nowhere else.
 */

import { useAgentPreview } from '@/lib/agent-preview'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Monitor, Tablet, Smartphone, MousePointerClick, Pencil, RotateCw,
  ExternalLink, Layers, Eraser, Undo2, ChevronLeft, ChevronRight,
  Rocket, Loader2, Type, Route,
} from 'lucide-react'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { watchFrame } from '@/lib/console-log'
import { attachPicker, pickedFrom, pickLabel } from '@/lib/picker'
import { goTo } from '@/lib/preview-guard'
import { Tip } from './ui'
import AgentBrowser from './AgentBrowser'
import AppPreview from './AppPreview'
import AppTextEdit from './AppTextEdit'
import LiveE2EOverlay from './LiveE2EOverlay'
import { cn } from '@/lib/utils'

const VIEWPORTS = [
  { id: 'desktop', label: 'Desktop', Icon: Monitor },
  { id: 'tablet', label: 'Tablet', Icon: Tablet },
  { id: 'mobile', label: 'Mobile', Icon: Smartphone },
]

const MIN_INK = 3
let seq = 0

export default function PrototypePane({ project, hidden, onBuild, generating = false, generationStatus = '', canResumePrototype = false }) {
  const frameRef = useRef(null)
  const canvasRef = useRef(null)
  const detachRef = useRef(null)
  const strokesRef = useRef([])
  const drawingRef = useRef(false)

  const [vp, setVp] = useState('desktop')
  const [pickOn, setPickOn] = useState(false)
  const [pencilOn, setPencilOn] = useState(false)
  const [textOn, setTextOn] = useState(false)
  const [route, setRoute] = useState('/')
  const [pages, setPages] = useState([])
  const [protoReady, setProtoReady] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [loaded, setLoaded] = useState(0)

  const trail = useRef(['/'])
  const at = useRef(0)
  const jumping = useRef(false)
  const [nav, setNav] = useState({ back: false, forward: false })

  const { addLog, busy, workflowStatus, prototypeStamp, progress, drawing, setDrawing,
    selection, addSelection, patchSelection, clearSelection, undo, setUndo } = useAgentPreview(project, 'designer')
  const prototypeArtifactStamp = useStore(s => s.prototypeArtifactStamp[project] || 0)
  const buildAllowed = useStore(s => Boolean(s.buildAvailability[project]))
  const statusText = useStore(s => s.statusText)
  // The prototype's journeys being clicked through in a real browser: shown live over the prototype, like a build's tests.
  const liveFrame = useStore(s => s.browserFrame)
  const liveStep = useStore(s => s.e2eLive)
  const walking = Boolean(liveFrame?.frame || liveStep)
  const isBusy = busy || generating
  // Partial checkpoints may already expose several real pages. They are still
  // resumable until the backend marks the complete prototype buildable.
  const resumePrototype = canResumePrototype && !isBusy
  const actionEnabled = buildAllowed || resumePrototype

  const prototypeUrl = api.appUrl(project || '', 'prototype', route)

  // Whether the app is built is asked of the backend; the 1 MB bundle itself is only fetched by the frame.
  const checkPrototypeReady = useCallback(async () => {
    if (!project) return false
    try {
      const status = await api.appStatus(project)
      const ok = Boolean(status?.prototype?.built)
      setProtoReady(ok)
      return ok
    } catch {
      setProtoReady(false)
      return false
    }
  }, [project])

  // Check on open and on completed builds; never poll an absent idle drawing.
  useEffect(() => {
    const timer = setTimeout(() => { checkPrototypeReady() }, 200)
    return () => clearTimeout(timer)
  }, [project, isBusy, prototypeStamp, prototypeArtifactStamp, checkPrototypeReady])

  useEffect(() => {
    if (!generating) return
    const timer = setInterval(checkPrototypeReady, 2000)
    return () => clearInterval(timer)
  }, [generating, checkPrototypeReady])

  // The pages listed on the side are the screens the specification names.
  useEffect(() => {
    if (!project) return
    let live = true
    api.wireframes(project)
      .then(found => { if (live) setPages(found?.pages || []) })
      .catch(() => { if (live) setPages([]) })
    return () => { live = false }
  }, [project, prototypeArtifactStamp])

  // The page the app is on, followed by the list and the back/forward trail.
  const onRoute = useCallback((here) => {
    setRoute(here)
    if (jumping.current) {
      jumping.current = false
    } else if (trail.current[at.current] !== here) {
      trail.current = trail.current.slice(0, at.current + 1).concat(here)
      at.current = trail.current.length - 1
    }
    setNav({ back: at.current > 0, forward: at.current < trail.current.length - 1 })
  }, [])

  function step(by) {
    const next = at.current + by
    if (next < 0 || next >= trail.current.length) return
    at.current = next
    jumping.current = true
    goTo(frameRef.current, trail.current[next])
    setNav({ back: next > 0, forward: next < trail.current.length - 1 })
  }

  function reload() {
    checkPrototypeReady()
    setReloadKey(k => k + 1)
  }

  const prevBusyRef = useRef(busy)
  useEffect(() => {
    if (prevBusyRef.current && !busy) {
      checkPrototypeReady()
      reload()
    }
    prevBusyRef.current = busy
  }, [busy])

  const viewportOf = useCallback(() => {
    const f = frameRef.current
    return { w: f?.clientWidth || 1280, h: f?.clientHeight || 800, mode: vp }
  }, [vp])

  const attachShot = useCallback(async (item, body) => {
    addSelection(item)
    try {
      const r = await api.shot({ ...body, project })
      patchSelection(item.key, r?.image
        ? { shot: r.image, state: 'ready' }
        : { state: 'blank' })
    } catch (e) {
      patchSelection(item.key, { state: 'blank' })
      addLog('WARN', `could not photograph prototype — ${e.message}`)
    }
  }, [addSelection, patchSelection, addLog, project])

  const attach = useCallback(() => {
    detachRef.current?.()
    if (!frameRef.current) return
    detachRef.current = attachPicker(frameRef.current, (el) => {
      const info = pickedFrom(frameRef.current, el, vp)
      const shotRoute = api.appUrl(project, 'prototype', info.route.split('#').pop())
      attachShot(
        {
          key: `sel-${++seq}`,
          kind: 'element',
          info,
          state: 'shooting',
          label: pickLabel(info),
          route: shotRoute,
        },
        {
          route: shotRoute,
          viewport: info.viewport || viewportOf(),
          scroll: info.scroll,
          rect: info.rect,
        }
      )
    })
    if (!detachRef.current) addLog('WARN', 'The prototype is not loaded yet')
  }, [vp, addLog, attachShot, viewportOf, project])

  useEffect(() => {
    if (pickOn) attach()
    else { detachRef.current?.(); detachRef.current = null }
    return () => { detachRef.current?.(); detachRef.current = null }
  }, [pickOn, attach, loaded])

  const syncCanvas = useCallback(() => {
    const f = frameRef.current, c = canvasRef.current
    if (!f || !c || !c.offsetParent) return
    const frame = f.getBoundingClientRect()
    const parent = c.offsetParent.getBoundingClientRect()
    c.style.left = (frame.left - parent.left) + 'px'
    c.style.top = (frame.top - parent.top) + 'px'
    c.style.width = frame.width + 'px'
    c.style.height = frame.height + 'px'
    const dpr = window.devicePixelRatio || 1
    const want = Math.round(frame.width * dpr)
    if (c.width !== want) {
      c.width = want
      c.height = Math.round(frame.height * dpr)
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
    const up = () => {
      if (!drawingRef.current) return
      drawingRef.current = false
      const strokes = strokesRef.current
      if (strokes.reduce((a, s) => a + s.length, 0) < MIN_INK) return clearStrokes()
      const shotRoute = api.appUrl(project, 'prototype', route)
      attachShot(
        {
          key: `sel-${++seq}`,
          kind: 'drawing',
          strokes,
          route: shotRoute,
          state: 'shooting',
          label: `Drawing on ${route}`,
        },
        { route: shotRoute, viewport: viewportOf(), strokes }
      )
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
  }, [pencilOn, point, syncCanvas, clearStrokes, attachShot, viewportOf, project, route])

  function toggleTextEdit() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!textOn) { setPickOn(false); setPencilOn(false) }
    setTextOn(v => !v)
  }

  function togglePick() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!pickOn) {
      setPencilOn(false)
      setTextOn(false)
    }
    setPickOn(v => !v)
  }

  function togglePencil() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!pencilOn) {
      setPickOn(false)
      setTextOn(false)
    }
    setPencilOn(v => { if (v) clearStrokes(); return !v })
  }

  async function undoLast() {
    if (!project || !undo) return
    try {
      const r = await api.undo(project, undo.id || '')
      addLog('SUCCESS', 'Restored ' + (r.restored || []).join(', '))
      setUndo(null)
      reload()
    } catch (e) {
      addLog('WARN', 'Undo failed: ' + e.message)
    }
  }

  // Click through the journeys in a real browser, watch it, and fix what cannot be done by clicking or looks wrong.
  async function testJourneys() {
    try {
      await api.reviewScreens(project, 'journeys', true)
      addLog('INFO', 'Clicking through the prototype’s journeys in a real browser…')
    } catch (error) {
      addLog('WARN', `The journeys could not be tested: ${error.message}`)
    }
  }

  async function handleBuildAppNow() {
    if (isBusy || !actionEnabled) return
    if (resumePrototype) {
      onBuild?.()
      return
    }
    const id = drawing?.id
    if (id) {
      setDrawing(null)
      try {
        await api.decide({ id, decision: 'approve' })
        addLog('INFO', `Starting full application build for ${project} from approved prototype…`)
      } catch (e) {
        addLog('WARN', `Could not accept prototype — ${e.message}`)
        if (onBuild) onBuild()
      }
    } else if (onBuild) {
      onBuild()
    }
  }

  // A new project starts at its first page, with a fresh trail.
  useEffect(() => {
    trail.current = ['/']
    at.current = 0
    setRoute('/')
    setNav({ back: false, forward: false })
  }, [project])

  return (
    <div className={cn('flex min-h-0 flex-1 flex-col bg-transparent', hidden && 'hidden')}>
      {/* Top Navbar */}
      <div className="flex h-[54px] shrink-0 items-center gap-3 border-b border-line/70 bg-black/72 px-4 backdrop-blur-2xl dark:bg-black/[.03]">
        {/* Navigation buttons */}
        <div className="flex items-center gap-1 rounded-full border border-line/80 bg-panel/90 p-1 shadow-sm">
          <Cell tip={nav.back ? 'Back' : 'Nothing to go back to'}
                disabled={!nav.back} onClick={() => step(-1)} className="rounded-full px-3">
            <ChevronLeft className="size-3.5" />
          </Cell>
          <Cell tip={nav.forward ? 'Forward' : 'Nothing to go forward to'}
                disabled={!nav.forward} onClick={() => step(1)} className="rounded-full px-3">
            <ChevronRight className="size-3.5" />
          </Cell>
          <Cell tip="Reload prototype" onClick={reload} className="rounded-full px-3">
            <RotateCw className="size-3.5" />
          </Cell>
        </div>

        {/* Prototype tag & current page */}
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-[14px] bg-black/[.035] px-4 py-2 text-[12px] text-muted ring-1 ring-black/[.045] dark:bg-black/[.045] dark:ring-white/[.06]">
          <Layers className="size-3.5 shrink-0 text-purple-500" />
          <span className="truncate font-mono text-[11.5px] text-ink font-medium">
            {project} / {route}
          </span>
        </div>

        {/* Action: Build app from prototype */}
        {(onBuild || drawing?.id) && (
          <button
            onClick={handleBuildAppNow}
            disabled={isBusy || !actionEnabled}
            title={resumePrototype ? 'Resume the interrupted prototype generation' : 'Build full application from this prototype'}
            className="inline-flex items-center gap-1.5 rounded-full bg-[#BFB9FF] px-3.5 py-1.5 text-[11.5px] font-semibold text-ink shadow-[0_8px_16px_0_rgba(191, 185, 255,0.24)] transition-all hover:bg-[#9B94E8] active:scale-95 disabled:pointer-events-none disabled:opacity-50"
          >
            <Rocket className="size-3" /> {isBusy ? 'Generating…' : resumePrototype ? 'Resume Prototype' : 'Build App Now'}
          </button>
        )}

        {project && protoReady && (
          <button
            type="button"
            onClick={testJourneys}
            disabled={isBusy || walking}
            title="Click through the prototype's journeys in a real browser, a screenshot at every step, and fix what cannot be done"
            className="inline-flex items-center gap-1.5 rounded-full border border-line/80 bg-panel px-3.5 py-1.5 text-[11.5px] font-semibold text-ink shadow-sm transition-all hover:bg-ink/[.06] active:scale-95 disabled:pointer-events-none disabled:opacity-50"
          >
            {walking ? <Loader2 className="size-3 animate-spin" /> : <Route className="size-3" />}
            {walking ? 'Testing…' : 'Test journeys'}
          </button>
        )}

        <a
          href={prototypeUrl}
          target="_blank"
          rel="noreferrer"
          title="Open prototype in full browser window"
          className="grid size-8 place-items-center rounded-lg border border-line/80 bg-panel text-ink hover:bg-ink/[.06]"
        >
          <ExternalLink className="size-3.5" />
        </a>

        {/* Viewports */}
        <div className="hidden items-center gap-1 rounded-full border border-line/80 bg-panel/80 p-1 shadow-sm md:flex">
          {VIEWPORTS.map(({ id, label, Icon }) => (
            <Cell key={id} tip={label} side="left" on={vp === id}
                  onClick={() => setVp(id)} className="rounded-full px-3">
              <Icon className="size-3.5" />
            </Cell>
          ))}
        </div>

        {/* Select & Pencil Tools */}
        <div className="flex items-center gap-1 rounded-full border border-line/80 bg-panel/80 p-1 shadow-sm">
          <Cell tip="Click prototype elements to attach them to chat"
                side="left" on={pickOn} onClick={togglePick} className="rounded-full">
            <MousePointerClick className="size-3.5" />
          </Cell>
          <Cell tip="Draw on prototype to attach a marked-up screenshot"
                side="left" on={pencilOn} onClick={togglePencil} className="rounded-full">
            <Pencil className="size-3.5" />
          </Cell>
          <Cell tip={selection.length
                       ? `Clear ${selection.length} attachment${selection.length === 1 ? '' : 's'}`
                       : 'Nothing attached yet'}
                side="left" disabled={!selection.length}
                onClick={() => { clearSelection(); clearStrokes() }} className="rounded-full">
            <Eraser className="size-3.5" />
          </Cell>
          <Cell tip={undo ? `Undo the last edit (${undo.files.join(', ')})`
                          : 'Nothing to undo yet'}
                side="left" disabled={!undo} onClick={undoLast} className="rounded-full">
            <Undo2 className="size-3.5" />
          </Cell>
        </div>

        {/* The text tool: click any words on the page, retype them */}
        <div className="flex items-center gap-1 rounded-full border border-line/80 bg-panel/80 p-1 shadow-sm">
          <Cell
            tip="Edit text: click any words on the page and retype them"
            side="left"
            on={textOn}
            onClick={toggleTextEdit}
            disabled={!protoReady || isBusy}
            className="rounded-full"
          >
            <Type className="size-3.5" />
          </Cell>
        </div>
      </div>

      {/* The preview: every page on the side, the app in the frame. */}
      <div className="relative flex min-h-0 flex-1 overflow-hidden bg-canvas">
        {protoReady && (
          <AppPreview
            key={`${project}:${reloadKey}`}
            project={project} kind="prototype" pages={pages} stamp={prototypeArtifactStamp} viewport={vp}
            frameRef={frameRef} onRoute={onRoute}
            onLoaded={(frame) => { watchFrame(frame, project, 'designer'); setLoaded(n => n + 1) }}
          >
            <canvas ref={canvasRef}
                    className={cn('absolute z-[8]', pencilOn ? 'block' : 'hidden')}
                    style={{ pointerEvents: pencilOn ? 'auto' : 'none',
                             cursor: pencilOn ? 'crosshair' : 'default' }} />

            {(pickOn || pencilOn || textOn) && (
              <p className="pointer-events-none absolute inset-x-0 bottom-7 z-[9] mx-auto w-fit rounded-full bg-ink/85 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-lg">
                {pencilOn ? 'Draw around what you mean — it attaches to the chat'
                  : textOn ? 'Click any words on the page and retype them · Enter saves'
                    : 'Click anything on the prototype — it attaches to the chat'}
              </p>
            )}

            <AppTextEdit
              frameRef={frameRef} active={textOn} loaded={loaded} project={project} kind="prototype"
              onSaved={(done) => addLog?.('SUCCESS', `Changed the text in ${done?.file || 'the prototype'}`)}
              onAskAi={({ old, value }) => {
                setTextOn(false)
                addLog('INFO', `Ask in the chat to change “${old}” to “${value}” — it is built in code`)
              }}
            />

            {/* The journeys being clicked through, live: the browser's picture and pointer, and the step it is on. */}
            <AgentBrowser />
            {liveStep && <LiveE2EOverlay event={liveStep} />}
          </AppPreview>
        )}

        {!protoReady && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-[#F2F0EF] p-6 text-center select-none">
            {/* Glowing top line */}
            <div className="absolute inset-x-0 top-0 h-[2px] overflow-hidden bg-black/5">
              <div className="h-full w-full bg-accent animate-pulse" />
            </div>

            <Loader2 className="mb-5 size-10 animate-spin text-accent" />

            <h3 className="font-display text-[16px] font-bold tracking-tight text-ink">
              {isBusy ? 'Generating the prototype…' : 'No prototype is ready yet'}
            </h3>
            <p className="mt-1.5 max-w-sm text-center text-[12px] text-muted leading-relaxed">
              {isBusy
                ? 'The AI agent is taking the wireframe app and editing it into a high-fidelity, animated prototype.'
                : 'Approve the wireframes and choose a design to generate the prototype.'}
            </p>

            {resumePrototype && (
              <button
                type="button"
                onClick={handleBuildAppNow}
                className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#BFB9FF] px-4 py-2 text-[12px] font-semibold text-ink shadow-sm transition hover:bg-[#9B94E8]"
              >
                <RotateCw className="size-3.5" /> Resume Prototype
              </button>
            )}

            <div className="mt-4 flex items-center gap-2 rounded-none border border-accent/20 bg-accent px-4 py-1.5 font-mono text-[11px] text-ink shadow-sm">
              <span className="size-2 rounded-full bg-accent animate-ping" />
              <span className="truncate max-w-[280px]">
                {generating
                  ? (generationStatus || 'Editing the wireframe into the prototype…')
                  : (resumePrototype && ['paused', 'failed'].includes(workflowStatus)
                    ? 'Generation was interrupted. Continue from the saved checkpoint.'
                    : (statusText || (typeof progress === 'string' ? progress : '') || (isBusy ? 'Designing pages…' : `${project || 'project'} / ${route}`)))}
              </span>
            </div>
          </div>
        )}
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
