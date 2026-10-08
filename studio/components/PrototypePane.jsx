'use client'

/** The prototype: a bundled React app framed on its own address, with a page list, element selection and pencil annotations. */

import { useAgentPreview } from '@/lib/agent-preview'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Monitor, Tablet, Smartphone, MousePointerClick, Pencil, RotateCw,
  ExternalLink, Layers, Eraser, Undo2, ChevronLeft, ChevronRight, Rocket, Loader2,
} from 'lucide-react'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { watchFrame } from '@/lib/console-log'
import { attachPicker, pickedFrom, pickLabel } from '@/lib/picker'
import { Tip } from './ui'
import { cn } from '@/lib/utils'

const VIEWPORTS = [
  { id: 'desktop', label: 'Desktop', w: null, Icon: Monitor },
  { id: 'tablet', label: 'Tablet', w: 834, Icon: Tablet },
  { id: 'mobile', label: 'Mobile', w: 390, Icon: Smartphone },
]

const MIN_INK = 3
let seq = 0

/** The screen the app in the frame is on: its address hash (`#/orders` is `/orders`). */
function currentRoute(frame) {
  try {
    const hash = frame?.contentWindow?.location?.hash || ''
    return hash.replace(/^#/, '').split('?')[0] || '/'
  } catch {
    return '/'
  }
}

export default function PrototypePane({ project, hidden, onBuild, generating = false, generationStatus = '', canResumePrototype = false }) {
  const frameRef = useRef(null)
  const canvasRef = useRef(null)
  const detachRef = useRef(null)
  const strokesRef = useRef([])
  const drawingRef = useRef(false)
  const lastRouteRef = useRef('/')

  const [vp, setVp] = useState('desktop')
  const [pickOn, setPickOn] = useState(false)
  const [pencilOn, setPencilOn] = useState(false)
  const [route, setRoute] = useState('/')
  const [pages, setPages] = useState([])
  const [status, setStatus] = useState({ built: false, version: 0 })

  const trail = useRef(['/'])
  const at = useRef(0)
  const jumping = useRef(false)
  const [nav, setNav] = useState({ back: false, forward: false })

  const { addLog, busy, workflowStatus, prototypeStamp, progress, drawing, setDrawing,
    selection, addSelection, patchSelection, clearSelection, undo, setUndo } = useAgentPreview(project, 'designer')
  const buildAllowed = useStore(s => Boolean(s.buildAvailability[project]))
  const statusText = useStore(s => s.statusText)
  const isBusy = busy || generating
  // A prototype stopped part of the way is still resumable until the backend marks the complete one buildable.
  const resumePrototype = canResumePrototype && !isBusy
  const actionEnabled = buildAllowed || resumePrototype

  const protoReady = status.built
  const width = VIEWPORTS.find(x => x.id === vp)?.w
  // The frame loads the bundle once for each version of it; moving between screens only changes the hash.
  const src = useMemo(() => (project && protoReady ? api.webUrl(project, 'prototype', lastRouteRef.current, status.version) : ''),
    [project, protoReady, status.version])
  const openUrl = project ? api.webUrl(project, 'prototype', route, status.version) : ''

  const checkReady = useCallback(async () => {
    if (!project) return
    try {
      const answer = await api.webStatus(project, 'prototype')
      setStatus(old => (old.built === Boolean(answer?.built) && old.version === (answer?.version || 0)
        ? old : { built: Boolean(answer?.built), version: answer?.version || 0 }))
    } catch {
      setStatus(old => (old.built ? { built: false, version: 0 } : old))
    }
  }, [project])

  useEffect(() => {
    if (!project) return
    api.wireframes(project).then(answer => setPages(answer?.pages || [])).catch(() => {})
  }, [project, status.version])

  // Check on open and whenever the agent reports a change; poll while it is working.
  useEffect(() => {
    const timer = setTimeout(checkReady, 200)
    return () => clearTimeout(timer)
  }, [project, isBusy, prototypeStamp, checkReady])

  useEffect(() => {
    if (!generating) return
    const timer = setInterval(checkReady, 2500)
    return () => clearInterval(timer)
  }, [generating, checkReady])

  const syncRoute = useCallback(() => {
    const here = currentRoute(frameRef.current)
    if (lastRouteRef.current === here) return
    lastRouteRef.current = here
    setRoute(here)
    if (jumping.current) {
      jumping.current = false
    } else if (trail.current[at.current] !== here) {
      trail.current = trail.current.slice(0, at.current + 1).concat(here)
      at.current = trail.current.length - 1
    }
    setNav({ back: at.current > 0, forward: at.current < trail.current.length - 1 })
  }, [])

  useEffect(() => {
    const id = setInterval(syncRoute, 400)
    return () => clearInterval(id)
  }, [syncRoute])

  function go(next) {
    const f = frameRef.current
    if (!f || !next) return
    try { f.contentWindow.location.hash = '#' + next } catch { f.src = api.webUrl(project, 'prototype', next, status.version) }
    syncRoute()
  }

  function step(by) {
    const f = frameRef.current
    const next = at.current + by
    if (!f || next < 0 || next >= trail.current.length) return
    at.current = next
    jumping.current = true
    go(trail.current[next])
    setNav({ back: next > 0, forward: next < trail.current.length - 1 })
  }

  function reload() {
    checkReady()
    try { frameRef.current?.contentWindow?.location.reload() } catch { /* not loaded */ }
  }

  const prevBusyRef = useRef(busy)
  useEffect(() => {
    if (prevBusyRef.current && !busy) checkReady()
    prevBusyRef.current = busy
  }, [busy, checkReady])

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
      const here = currentRoute(frameRef.current)
      const shotRoute = api.webUrl(project, 'prototype', here)
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
  }, [pickOn, attach])

  useEffect(() => {
    const f = frameRef.current
    if (!f) return
    const onLoad = () => {
      watchFrame(f, project, 'designer')
      syncRoute()
      if (pickOn) attach()
    }
    f.addEventListener('load', onLoad)
    return () => f.removeEventListener('load', onLoad)
  }, [pickOn, attach, syncRoute, project, src])

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
      const here = currentRoute(frameRef.current)
      const shotRoute = api.webUrl(project, 'prototype', here)
      attachShot(
        {
          key: `sel-${++seq}`,
          kind: 'drawing',
          strokes,
          route: shotRoute,
          state: 'shooting',
          label: `Drawing on ${here}`,
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
  }, [pencilOn, point, syncCanvas, clearStrokes, attachShot, viewportOf, project])

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
      reload()
    } catch (e) {
      addLog('WARN', 'Undo failed: ' + e.message)
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

  // A different project starts on its home page.
  useEffect(() => {
    lastRouteRef.current = '/'
    trail.current = ['/']
    at.current = 0
    setRoute('/')
    setNav({ back: false, forward: false })
    setStatus({ built: false, version: 0 })
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

        {/* The prototype, and the screen it is on: pick another from the list. */}
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-[14px] bg-black/[.035] px-4 py-2 text-[12px] text-muted ring-1 ring-black/[.045] dark:bg-black/[.045] dark:ring-white/[.06]">
          <Layers className="size-3.5 shrink-0 text-purple-500" />
          <span className="truncate font-mono text-[11.5px] text-ink font-medium">{project} /</span>
          {pages.length > 0 && protoReady ? (
            <select value={pages.some(p => p.route === route) ? route : ''} onChange={event => go(event.target.value)}
                    aria-label="Screen"
                    className="min-w-0 flex-1 truncate bg-transparent font-mono text-[11.5px] font-medium text-ink outline-none">
              {!pages.some(p => p.route === route) && <option value="">{route}</option>}
              {pages.map(page => <option key={page.route} value={page.route}>{page.route} — {page.page_name}</option>)}
            </select>
          ) : (
            <span className="truncate font-mono text-[11.5px] text-ink font-medium">{route}</span>
          )}
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

        <a
          href={openUrl}
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
      </div>

      {/* Frame Container */}
      <div className="relative min-h-0 flex-1 overflow-hidden bg-canvas">
        <canvas ref={canvasRef}
                className={cn('absolute z-[8]', pencilOn ? 'block' : 'hidden')}
                style={{ pointerEvents: pencilOn ? 'auto' : 'none',
                         cursor: pencilOn ? 'crosshair' : 'default' }} />

        {(pickOn || pencilOn) && (
          <p className="pointer-events-none absolute inset-x-0 bottom-7 z-[9] mx-auto w-fit rounded-full bg-ink/85 px-3.5 py-1.5 text-[11px] font-medium text-ink shadow-lg">
            {pencilOn ? 'Draw around what you mean — it attaches to the chat'
                      : 'Click anything on the prototype — it attaches to the chat'}
          </p>
        )}

        <div className="relative flex min-h-0 h-full w-full items-start justify-center overflow-hidden bg-[#F2F0EF]">
          <div
            className={cn("relative h-full w-full max-w-full overflow-hidden bg-[#F2F0EF]", width && "border-x border-black/10 shadow-2xl")}
            style={{ width: width ? width + 'px' : '100%' }}
          >
            {src && (
              <iframe
                ref={frameRef}
                key={src}
                title="prototype-preview"
                src={src}
                className="absolute inset-0 block h-full w-full border-0 bg-white"
              />
            )}

            {!protoReady && (
              <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-[#F2F0EF] p-6 text-center select-none">
                {/* Glowing top line */}
                <div className="absolute inset-x-0 top-0 h-[2px] overflow-hidden bg-black/5">
                  <div className="h-full w-full bg-accent animate-pulse" />
                </div>

                <Loader2 className="mb-5 size-10 animate-spin text-accent" />

                <h3 className="font-display text-[16px] font-bold tracking-tight text-ink">
                  {isBusy ? 'Making the prototype…' : 'No prototype is ready yet'}
                </h3>
                <p className="mt-1.5 max-w-sm text-center text-[12px] text-muted leading-relaxed">
                  {isBusy
                    ? 'The AI agent is editing the wireframes into a high-fidelity, animated React app, then bundling it.'
                    : 'Approve the wireframes and the design, and the prototype is made from them.'}
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
                      ? (generationStatus || 'Editing the wireframes into the prototype…')
                      : (resumePrototype && ['paused', 'failed'].includes(workflowStatus)
                        ? 'Generation was interrupted. Continue from the saved checkpoint.'
                        : (statusText || (typeof progress === 'string' ? progress : '') || (isBusy ? 'Designing pages…' : `${project || 'project'} / ${route}`)))}
                  </span>
                </div>
              </div>
            )}
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
