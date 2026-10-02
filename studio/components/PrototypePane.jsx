'use client'

/** HTML Prototype viewer with element selection, pencil annotations and the wireframe's text tool: click text, type, save. */

import { useAgentPreview } from '@/lib/agent-preview'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Monitor, Tablet, Smartphone, MousePointerClick, Pencil, RotateCw,
  ExternalLink, Layers, Eraser, Undo2, ChevronLeft, ChevronRight,
  Rocket, Loader2, Type,
  RotateCcw as UndoIcon, Save, Check,
} from 'lucide-react'
import { useStore } from '@/lib/store'
import { api, API } from '@/lib/api'
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

function currentPath(frame) {
  try {
    const loc = frame?.contentWindow?.location
    if (!loc) return 'index.html'
    const name = (loc.pathname || '').split('/').filter(Boolean).pop() || 'index.html'
    const cleanName = name.endsWith('.html') ? name : 'index.html'
    const search = loc.search || ''
    const hash = loc.hash || ''
    return cleanName + search + hash
  } catch {
    return 'index.html'
  }
}

function baseFileName(path) {
  return (path || '').split('?')[0].split('#')[0] || 'index.html'
}

export default function PrototypePane({ project, hidden, onBuild, generating = false, generationStatus = '', canResumePrototype = false }) {
  const frameRef = useRef(null)
  const canvasRef = useRef(null)
  const detachRef = useRef(null)
  const strokesRef = useRef([])
  const drawingRef = useRef(false)
  const lastFileRef = useRef('index.html')

  const [vp, setVp] = useState('desktop')
  const [pickOn, setPickOn] = useState(false)
  const [pencilOn, setPencilOn] = useState(false)
  const [currentFile, setCurrentFile] = useState('index.html')
  const [protoReady, setProtoReady] = useState(false)

  // The wireframe's text tool, on the prototype page: click text, type, save. Nothing else is edited here.
  const [textOn, setTextOn] = useState(false)
  const [textDirty, setTextDirty] = useState(false)
  const [savingProto, setSavingProto] = useState(false)
  const [saveProtoSuccess, setSaveProtoSuccess] = useState(false)
  const protoEditorRef = useRef(null)

  const trail = useRef(['index.html'])
  const at = useRef(0)
  const jumping = useRef(false)
  const [nav, setNav] = useState({ back: false, forward: false })

  const { addLog, busy, workflowStatus, prototypeStamp, progress, drawing, setDrawing,
    selection, addSelection, patchSelection, clearSelection, undo, setUndo } = useAgentPreview(project, 'designer')
  const prototypeArtifactStamp = useStore(s => s.prototypeArtifactStamp[project] || 0)
  const buildAllowed = useStore(s => Boolean(s.buildAvailability[project]))
  const statusText = useStore(s => s.statusText)
  const isBusy = busy || generating
  const resumePrototype = canResumePrototype && !protoReady && !isBusy
  const actionEnabled = buildAllowed || resumePrototype

  const prototypeUrl = `${API}/prototype/${encodeURIComponent(project || '')}/${currentFile}`
  const width = VIEWPORTS.find(x => x.id === vp)?.w

  const checkPrototypeReady = useCallback(async () => {
    if (!project) return false
    try {
      const base = baseFileName(currentFile)
      const map = await fetch(`${API}/prototype/${encodeURIComponent(project)}/routes.json?check=${Date.now()}`)
      if (!map.ok) { setProtoReady(false); return false }
      const url = `${API}/prototype/${encodeURIComponent(project)}/${base || 'index.html'}?check=${Date.now()}`
      const res = await fetch(url)
      if (res.ok) {
        const text = await res.text()
        if (text.includes('Generating HTML Prototype') || text.includes('no index.html in this drawing')) {
          setProtoReady(false)
          return false
        }
        setProtoReady(true)
        return true
      }
      setProtoReady(false)
      return false
    } catch {
      setProtoReady(false)
      return false
    }
  }, [project, currentFile])

  // Check on open and on completed file events; never poll an absent idle drawing.
  useEffect(() => {
    const timer = setTimeout(() => { checkPrototypeReady() }, 200)
    return () => clearTimeout(timer)
  }, [project, isBusy, prototypeStamp, prototypeArtifactStamp, checkPrototypeReady])

  useEffect(() => {
    if (!generating) return
    const timer = setInterval(checkPrototypeReady, 2000)
    return () => clearInterval(timer)
  }, [generating, checkPrototypeReady])

  const syncPath = useCallback(() => {
    const here = currentPath(frameRef.current)
    if (!here) return
    if (lastFileRef.current === here) return
    lastFileRef.current = here
    setCurrentFile(here)

    if (jumping.current) {
      jumping.current = false
    } else if (trail.current[at.current] !== here) {
      trail.current = trail.current.slice(0, at.current + 1).concat(here)
      at.current = trail.current.length - 1
    }
    setNav({ back: at.current > 0, forward: at.current < trail.current.length - 1 })
  }, [])

  function step(by) {
    const f = frameRef.current
    const next = at.current + by
    if (!f || next < 0 || next >= trail.current.length) return
    at.current = next
    jumping.current = true
    const targetFile = trail.current[next]
    lastFileRef.current = targetFile
    setCurrentFile(targetFile)
    f.src = `${API}/prototype/${encodeURIComponent(project || '')}/${targetFile}`
    setNav({ back: next > 0, forward: next < trail.current.length - 1 })
  }

  function reload() {
    const f = frameRef.current
    if (f) {
      const page = currentPath(f)
      checkPrototypeReady()
      const sep = page.includes('?') ? '&' : '?'
      f.src = `${API}/prototype/${encodeURIComponent(project || '')}/${page}${sep}t=${Date.now()}`
    }
  }

  const lastArtifactRefresh = useRef(0)
  useEffect(() => {
    if (!prototypeArtifactStamp || prototypeArtifactStamp === lastArtifactRefresh.current) return
    lastArtifactRefresh.current = prototypeArtifactStamp
    const f = frameRef.current
    if (!f) return
    const page = currentPath(f) || currentFile || 'index.html'
    checkPrototypeReady()
    const sep = page.includes('?') ? '&' : '?'
    f.src = `${API}/prototype/${encodeURIComponent(project || '')}/${page}${sep}t=${prototypeArtifactStamp}`
  }, [prototypeArtifactStamp, project, currentFile, checkPrototypeReady])

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
      const pageFile = currentPath(frameRef.current)
      const shotRoute = `${API}/prototype/${encodeURIComponent(project)}/${pageFile}`
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

  // The same editor the wireframe pages use, in its text-only form.
  const attachTextEditor = useCallback(() => {
    protoEditorRef.current?.detach?.()
    protoEditorRef.current = null
    const f = frameRef.current
    if (!f) return
    import('@/lib/wireframe-html-editor').then(({ attachEditor }) => {
      protoEditorRef.current = attachEditor(f, { onDirty: setTextDirty, textOnly: true })
    })
  }, [])

  useEffect(() => {
    const f = frameRef.current
    if (!f) return
    const onLoad = () => {
      watchFrame(f, project, 'designer')
      syncPath()
      if (pickOn) attach()
      if (textOn) attachTextEditor()
    }
    f.addEventListener('load', onLoad)
    return () => f.removeEventListener('load', onLoad)
  }, [pickOn, attach, textOn, attachTextEditor, syncPath])

  useEffect(() => {
    const id = setInterval(syncPath, 500)
    return () => clearInterval(id)
  }, [syncPath])

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
      const pageFile = currentPath(frameRef.current)
      const shotRoute = `${API}/prototype/${encodeURIComponent(project)}/${pageFile}`
      attachShot(
        {
          key: `sel-${++seq}`,
          kind: 'drawing',
          strokes,
          route: shotRoute,
          state: 'shooting',
          label: `Drawing on ${pageFile}`,
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

  useEffect(() => () => { protoEditorRef.current?.detach?.() }, [])

  function stopTextEdit() {
    protoEditorRef.current?.detach?.()
    protoEditorRef.current = null
    setTextDirty(false)
    setTextOn(false)
  }

  function toggleTextEdit() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (textOn) return stopTextEdit()
    setPickOn(false)
    setPencilOn(false)
    attachTextEditor()
    setTextOn(true)
  }

  async function saveTextEdits() {
    if (!protoEditorRef.current || !project) return
    setSavingProto(true)
    setSaveProtoSuccess(false)
    try {
      protoEditorRef.current.editText(false)
      const base = baseFileName(currentFile)
      const serializedHtml = protoEditorRef.current.serialize()
      await api.saveFile(
        project,
        `.agentforge/prototype/${base || 'index.html'}`,
        serializedHtml,
        `Text edit in ${base || 'index.html'}`
      )
      protoEditorRef.current.saved()
      setTextDirty(false)
      setSaveProtoSuccess(true)
      addLog?.('SUCCESS', `Saved ${base || 'index.html'} directly to prototype HTML`)
      setTimeout(() => setSaveProtoSuccess(false), 3000)
    } catch (err) {
      addLog?.('WARN', `Could not save prototype: ${err.message}`)
    } finally {
      setSavingProto(false)
    }
  }

  function undoText() {
    if (protoEditorRef.current?.undo?.()) setTextDirty(protoEditorRef.current?.hasHistory?.() ?? false)
  }

  function togglePick() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!pickOn) {
      setPencilOn(false)
      if (textOn) stopTextEdit()
    }
    setPickOn(v => !v)
  }

  function togglePencil() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!pencilOn) {
      setPickOn(false)
      if (textOn) stopTextEdit()
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

  // Reload when project changes or when drawing becomes active
  useEffect(() => {
    if (frameRef.current && project) {
      const firstPage = drawing?.pages?.[0]?.file || 'index.html'
      setCurrentFile(firstPage)
      lastFileRef.current = firstPage
      frameRef.current.src = `${API}/prototype/${encodeURIComponent(project)}/${firstPage}`
    }
  }, [project, drawing?.id])

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

        {/* Prototype tag & current file */}
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-[14px] bg-black/[.035] px-4 py-2 text-[12px] text-muted ring-1 ring-black/[.045] dark:bg-black/[.045] dark:ring-white/[.06]">
          <Layers className="size-3.5 shrink-0 text-purple-500" />
          <span className="truncate font-mono text-[11.5px] text-ink font-medium">
            {project} / {currentFile}
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

        {/* The wireframe's text tool: click any text on the page and type, then save */}
        <div className="flex items-center gap-1 rounded-full border border-line/80 bg-panel/80 p-1 shadow-sm">
          <Cell
            tip="Edit text: click any text on the page and type, then save"
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

      {/* While the text tool is on: what to do, and Save / Undo once something was typed. */}
      {textOn && (
        <div className="z-30 flex shrink-0 items-center gap-2 border-b border-black/10 bg-[#F2F0EF]/95 px-3.5 py-2 select-none backdrop-blur-md">
          <span className="flex min-w-0 items-center gap-1.5 text-[11.5px] text-muted">
            <Type className="size-3 shrink-0" />
            <span className="truncate">Click any text on the page and type · Esc stops typing</span>
          </span>
          <span className="flex-1" />
          {saveProtoSuccess && (
            <span className="flex items-center gap-1 text-[11px] text-ink"><Check className="size-3" /> Saved</span>
          )}
          <button type="button" onClick={undoText} disabled={!textDirty} title="Undo the last change (Ctrl+Z)"
                  className="inline-flex h-7 items-center gap-1 rounded-lg px-2.5 text-[11px] font-medium text-ink ring-1 ring-inset ring-black/10 hover:bg-black/[.06] disabled:opacity-40">
            <UndoIcon className="size-3" /> Undo
          </button>
          {textDirty && (
            <button type="button" onClick={saveTextEdits} disabled={savingProto}
                    className="inline-flex h-7 items-center gap-1.5 rounded-lg bg-accent px-3 text-[11px] font-semibold text-ink shadow-sm hover:bg-press disabled:opacity-50">
              {savingProto ? <><Loader2 className="size-3 animate-spin" /> Saving…</> : <><Save className="size-3" /> Save page</>}
            </button>
          )}
        </div>
      )}

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
            <iframe
              ref={frameRef}
              title="prototype-preview"
              src={prototypeUrl}
              onLoad={() => {
                checkPrototypeReady()
              }}
              className={cn(
                "absolute inset-0 block h-full w-full border-0 bg-white transition-opacity duration-300",
                !protoReady ? "opacity-0 pointer-events-none" : "opacity-100"
              )}
            />

            {!protoReady && (
              <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-[#F2F0EF] p-6 text-center select-none">
                {/* Glowing top line */}
                <div className="absolute inset-x-0 top-0 h-[2px] overflow-hidden bg-black/5">
                  <div className="h-full w-full bg-accent animate-pulse" />
                </div>

                <Loader2 className="mb-5 size-10 animate-spin text-accent" />

                <h3 className="font-display text-[16px] font-bold tracking-tight text-ink">
                  {isBusy ? 'Generating HTML Prototype…' : 'No prototype is ready yet'}
                </h3>
                <p className="mt-1.5 max-w-sm text-center text-[12px] text-muted leading-relaxed">
                  {isBusy
                    ? 'The AI agent is crafting interactive wireframes, layouts, and responsive components.'
                    : 'Connecting to prototype canvas and mounting UI assets.'}
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
                      ? (generationStatus || 'Planning and drawing prototype pages…')
                      : (resumePrototype && ['paused', 'failed'].includes(workflowStatus)
                        ? 'Generation was interrupted. Continue from the saved checkpoint.'
                        : (statusText || (typeof progress === 'string' ? progress : '') || (isBusy ? 'Designing pages…' : `${project || 'project'} / ${currentFile}`)))}
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
