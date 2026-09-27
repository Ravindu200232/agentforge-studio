'use client'

/** HTML Prototype viewer with element selection, pencil annotations, and interactive Figma positioning tools. */

import { useAgentPreview } from '@/lib/agent-preview'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Monitor, Tablet, Smartphone, MousePointerClick, Pencil, RotateCw,
  ExternalLink, Globe, Layers, Eraser, Undo2, ChevronLeft, ChevronRight,
  Sparkles, Rocket, FlaskConical, Loader2, SlidersHorizontal,
  Move, ArrowUpDown, AlignLeft, AlignCenter, AlignRight, Maximize2,
  Copy, Trash2, Type, ArrowUp, ArrowDown, ArrowLeft, ArrowRight,
  RotateCcw as UndoIcon, Save, Check,
} from 'lucide-react'
import { useStore } from '@/lib/store'
import { api, API } from '@/lib/api'
import { watchFrame } from '@/lib/console-log'
import { attachPicker, pickedFrom, pickLabel, frameDoc } from '@/lib/picker'
import VisualInspector from './VisualInspector'
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
  const [visualEditOn, setVisualEditOn] = useState(false)
  const [inspectedElement, setInspectedElement] = useState(null)
  const [inspectedDoc, setInspectedDoc] = useState(null)
  const visualDetachRef = useRef(null)
  const [currentFile, setCurrentFile] = useState('index.html')
  const [protoReady, setProtoReady] = useState(false)
  const [iframeLoading, setIframeLoading] = useState(true)

  // Figma-like Move & Position Tool states
  const [figmaMoveOn, setFigmaMoveOn] = useState(false)
  const [figmaPicked, setFigmaPicked] = useState('')
  const [figmaMetrics, setFigmaMetrics] = useState(null)
  const [figmaDragMode, setFigmaDragMode] = useState('free')
  const [figmaDirty, setFigmaDirty] = useState(false)
  const [savingProto, setSavingProto] = useState(false)
  const [saveProtoSuccess, setSaveProtoSuccess] = useState(false)
  const [figmaTyping, setFigmaTyping] = useState(false)
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
        setIframeLoading(false)
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
      setIframeLoading(true)
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
    setIframeLoading(true)
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

  const attachVisualInspector = useCallback(() => {
    visualDetachRef.current?.()
    visualDetachRef.current = null
    const f = frameRef.current
    if (!f) return
    const d = frameDoc(f)
    if (!d) return

    const STYLE_ID = '__vf_style'
    if (!d.getElementById(STYLE_ID)) {
      const st = d.createElement('style')
      st.id = STYLE_ID
      st.textContent = `
        .__vf_hi {
          outline: 2px dashed #10b981 !important;
          outline-offset: -2px !important;
          cursor: pointer !important;
        }
        .__vf_selected {
          outline: 2px solid #10b981 !important;
          outline-offset: -1px !important;
        }
      `
      d.head.appendChild(st)
    }

    const hover = (e) => {
      if (e.target && e.target.classList) {
        e.target.classList.add('__vf_hi')
      }
    }
    const leave = (e) => {
      if (e.target && e.target.classList) {
        e.target.classList.remove('__vf_hi')
      }
    }
    const click = (e) => {
      e.preventDefault()
      e.stopPropagation()
      e.stopImmediatePropagation()
      const prev = d.querySelector('.__vf_selected')
      if (prev) prev.classList.remove('__vf_selected')
      if (e.target && e.target.classList) {
        e.target.classList.add('__vf_selected')
      }
      setInspectedElement(e.target)
      setInspectedDoc(d)
    }

    d.addEventListener('mouseover', hover, true)
    d.addEventListener('mouseout', leave, true)
    d.addEventListener('click', click, true)

    visualDetachRef.current = () => {
      d.removeEventListener('mouseover', hover, true)
      d.removeEventListener('mouseout', leave, true)
      d.removeEventListener('click', click, true)
      const hi = d.querySelectorAll('.__vf_hi, .__vf_selected')
      hi.forEach(el => el.classList.remove('__vf_hi', '__vf_selected'))
      const st = d.getElementById(STYLE_ID)
      if (st) st.remove()
    }
  }, [])

  useEffect(() => {
    if (visualEditOn) attachVisualInspector()
    else {
      visualDetachRef.current?.()
      visualDetachRef.current = null
      setInspectedElement(null)
      setInspectedDoc(null)
    }
    return () => {
      visualDetachRef.current?.()
      visualDetachRef.current = null
    }
  }, [visualEditOn, attachVisualInspector])

  const attachFigmaEditor = useCallback(() => {
    protoEditorRef.current?.detach?.()
    protoEditorRef.current = null
    const f = frameRef.current
    if (!f) return
    import('@/lib/wireframe-html-editor').then(({ attachEditor }) => {
      protoEditorRef.current = attachEditor(f, {
        onSelect: setFigmaPicked,
        onDirty: setFigmaDirty,
        onMetrics: setFigmaMetrics,
      })
      if (protoEditorRef.current) {
        protoEditorRef.current.setDragMode(figmaDragMode)
      }
    })
  }, [figmaDragMode])

  useEffect(() => {
    const f = frameRef.current
    if (!f) return
    const onLoad = () => {
      watchFrame(f, project, 'designer')
      syncPath()
      setInspectedElement(null)
      setInspectedDoc(null)
      if (pickOn) attach()
      if (visualEditOn) attachVisualInspector()
      if (figmaMoveOn) attachFigmaEditor()
    }
    f.addEventListener('load', onLoad)
    return () => f.removeEventListener('load', onLoad)
  }, [pickOn, attach, visualEditOn, attachVisualInspector, figmaMoveOn, attachFigmaEditor, syncPath])

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

  function toggleFigmaMove() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!figmaMoveOn) {
      setPickOn(false)
      setPencilOn(false)
      setVisualEditOn(false)
      setInspectedElement(null)
      attachFigmaEditor()
    } else {
      protoEditorRef.current?.detach?.()
      protoEditorRef.current = null
      setFigmaPicked('')
      setFigmaMetrics(null)
      setFigmaDirty(false)
    }
    setFigmaMoveOn(v => !v)
  }

  const setProtoMode = mode => {
    setFigmaDragMode(mode)
    protoEditorRef.current?.setDragMode?.(mode)
  }

  async function savePrototypeFigma() {
    if (!protoEditorRef.current || !project) return
    setSavingProto(true)
    setSaveProtoSuccess(false)
    try {
      if (figmaTyping) {
        protoEditorRef.current.editText(false)
        setFigmaTyping(false)
      }
      const base = baseFileName(currentFile)
      const serializedHtml = protoEditorRef.current.serialize()
      await api.saveFile(
        project,
        `.agentforge/prototype/${base || 'index.html'}`,
        serializedHtml,
        `Figma layout edit in ${base || 'index.html'}`
      )
      protoEditorRef.current.saved()
      setFigmaDirty(false)
      setSaveProtoSuccess(true)
      addLog?.('SUCCESS', `Saved ${base || 'index.html'} directly to prototype HTML`)
      setTimeout(() => setSaveProtoSuccess(false), 3000)
    } catch (err) {
      addLog?.('WARN', `Could not save prototype: ${err.message}`)
    } finally {
      setSavingProto(false)
    }
  }

  const protoAct = (name, ...args) => () => {
    protoEditorRef.current?.[name]?.(...args)
    if (name === 'undo') {
      setFigmaDirty(false)
      setFigmaPicked('')
      setFigmaMetrics(null)
    }
  }

  function togglePick() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!pickOn) {
      setPencilOn(false)
      setVisualEditOn(false)
      setInspectedElement(null)
      if (figmaMoveOn) {
        protoEditorRef.current?.detach?.()
        protoEditorRef.current = null
        setFigmaMoveOn(false)
      }
    }
    setPickOn(v => !v)
  }

  function togglePencil() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!pencilOn) {
      setPickOn(false)
      setVisualEditOn(false)
      setInspectedElement(null)
      if (figmaMoveOn) {
        protoEditorRef.current?.detach?.()
        protoEditorRef.current = null
        setFigmaMoveOn(false)
      }
    }
    setPencilOn(v => { if (v) clearStrokes(); return !v })
  }

  function toggleVisualEdit() {
    if (!project) return addLog('WARN', 'Open a project first')
    if (!visualEditOn) {
      setPickOn(false)
      setPencilOn(false)
      if (figmaMoveOn) {
        protoEditorRef.current?.detach?.()
        protoEditorRef.current = null
        setFigmaMoveOn(false)
      }
    } else {
      setInspectedElement(null)
    }
    setVisualEditOn(v => !v)
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

        {/* Visual Quick Inspector (Zero-LLM Direct Editor) */}
        <div className="flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/[.08] p-1 shadow-sm">
          <Cell tip="Visual Inspector: click any element to live-edit text, colors, layout & move without LLM"
                side="left" on={visualEditOn} onClick={toggleVisualEdit} className={cn("rounded-full", visualEditOn && "!bg-emerald-600 !text-ink shadow-sm")}>
            <SlidersHorizontal className={cn("size-3.5", visualEditOn ? "text-ink" : "text-ink")} />
          </Cell>
        </div>

        {/* Figma Move & Position Tool (Zero-LLM Direct Canvas Positioning) */}
        <div className="flex items-center gap-1 rounded-full border border-[#BFB9FF]/40 bg-[#BFB9FF] p-1 shadow-sm">
          <Cell
            tip="Figma Move Tool: Drag elements with cursor, resize handles, nudge with arrows, position like Figma"
            side="left"
            on={figmaMoveOn}
            onClick={toggleFigmaMove}
            disabled={!protoReady || isBusy}
            className={cn("rounded-full", figmaMoveOn && "!bg-[#BFB9FF] !text-ink shadow-sm")}
          >
            <Move className={cn("size-3.5", figmaMoveOn ? "text-ink" : "text-[#BFB9FF]")} />
          </Cell>
        </div>
      </div>

      {/* Figma Design & Position Toolbar */}
      {figmaMoveOn && (
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-black/10 bg-[#F2F0EF]/95 px-3.5 py-2 select-none z-30 shadow-md backdrop-blur-md">
          {/* Mode Switcher: Move (Free Drag) vs Flow (Reorder) */}
          <div className="flex items-center rounded-lg bg-black/40 p-0.5 border border-black/10">
            <button
              type="button"
              onClick={() => setProtoMode('free')}
              title="Move Tool (V): Drag with cursor to freely position anywhere"
              className={cn('flex items-center gap-1 rounded-md px-2 py-1 text-[10.5px] font-medium transition cursor-pointer',
                figmaDragMode === 'free' ? 'bg-[#BFB9FF] text-ink font-semibold shadow-sm' : 'text-muted hover:text-ink')}
            >
              <Move className="size-3" />
              <span>Move</span>
            </button>
            <button
              type="button"
              onClick={() => setProtoMode('flow')}
              title="Reorder Tool: Drag with cursor to drop between elements"
              className={cn('flex items-center gap-1 rounded-md px-2 py-1 text-[10.5px] font-medium transition cursor-pointer',
                figmaDragMode === 'flow' ? 'bg-[#BFB9FF] text-ink font-semibold shadow-sm' : 'text-muted hover:text-ink')}
            >
              <ArrowUpDown className="size-3" />
              <span>Reorder</span>
            </button>
          </div>

          <span className="mx-1 h-4 w-px bg-black/10" />

          {figmaPicked ? (
            <>
              {/* Selected Tag & Dimensions */}
              <span className="flex items-center gap-1 rounded-md bg-black/[.07] px-2 py-1 font-mono text-[10.5px] text-ink border border-black/10">
                <span className="text-[#BFB9FF] font-semibold">&lt;{figmaPicked}&gt;</span>
                {figmaMetrics && (
                  <span className="text-muted2 text-[10px] ml-1">
                    {figmaMetrics.w}×{figmaMetrics.h}px
                  </span>
                )}
              </span>

              {/* Position Steppers (X, Y) */}
              <div className="flex items-center gap-1 rounded-md bg-black/30 px-1.5 py-0.5 border border-black/10 font-mono text-[10px]">
                <span className="text-muted2 uppercase font-semibold text-[9.5px]">X:</span>
                <button type="button" onClick={() => protoEditorRef.current?.nudge?.(-5, 0)} className="px-1 text-muted hover:text-ink hover:bg-black/10 rounded">-</button>
                <span className="text-ink font-medium min-w-[28px] text-center">{figmaMetrics?.x ?? 0}px</span>
                <button type="button" onClick={() => protoEditorRef.current?.nudge?.(5, 0)} className="px-1 text-muted hover:text-ink hover:bg-black/10 rounded">+</button>
              </div>

              <div className="flex items-center gap-1 rounded-md bg-black/30 px-1.5 py-0.5 border border-black/10 font-mono text-[10px]">
                <span className="text-muted2 uppercase font-semibold text-[9.5px]">Y:</span>
                <button type="button" onClick={() => protoEditorRef.current?.nudge?.(0, -5)} className="px-1 text-muted hover:text-ink hover:bg-black/10 rounded">-</button>
                <span className="text-ink font-medium min-w-[28px] text-center">{figmaMetrics?.y ?? 0}px</span>
                <button type="button" onClick={() => protoEditorRef.current?.nudge?.(0, 5)} className="px-1 text-muted hover:text-ink hover:bg-black/10 rounded">+</button>
              </div>

              {figmaMetrics?.hasOffset && (
                <button
                  type="button"
                  onClick={() => protoEditorRef.current?.resetPos?.()}
                  title="Reset Position to 0,0"
                  className="rounded-md bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 px-1.5 py-1 text-[10px] font-medium transition cursor-pointer"
                >
                  Reset Pos
                </button>
              )}

              {/* Nudge D-Pad */}
              <div className="flex items-center rounded-md bg-black/[.05] p-0.5 border border-black/10">
                <button type="button" onClick={() => protoEditorRef.current?.nudge?.(-1, 0)} title="Nudge Left (1px)" className="p-1 hover:bg-black/10 rounded text-muted hover:text-ink">
                  <ArrowLeft className="size-2.5" />
                </button>
                <button type="button" onClick={() => protoEditorRef.current?.nudge?.(0, -1)} title="Nudge Up (1px)" className="p-1 hover:bg-black/10 rounded text-muted hover:text-ink">
                  <ArrowUp className="size-2.5" />
                </button>
                <button type="button" onClick={() => protoEditorRef.current?.nudge?.(0, 1)} title="Nudge Down (1px)" className="p-1 hover:bg-black/10 rounded text-muted hover:text-ink">
                  <ArrowDown className="size-2.5" />
                </button>
                <button type="button" onClick={() => protoEditorRef.current?.nudge?.(1, 0)} title="Nudge Right (1px)" className="p-1 hover:bg-black/10 rounded text-muted hover:text-ink">
                  <ArrowRight className="size-2.5" />
                </button>
              </div>

              <span className="mx-1 h-4 w-px bg-black/10" />

              {/* Alignments */}
              <button type="button" onClick={protoAct('align', 'left')} title="Align Left" className="p-1 hover:bg-black/10 rounded text-ink hover:text-ink cursor-pointer"><AlignLeft className="size-3" /></button>
              <button type="button" onClick={protoAct('align', 'center')} title="Align Centre" className="p-1 hover:bg-black/10 rounded text-ink hover:text-ink cursor-pointer"><AlignCenter className="size-3" /></button>
              <button type="button" onClick={protoAct('align', 'right')} title="Align Right" className="p-1 hover:bg-black/10 rounded text-ink hover:text-ink cursor-pointer"><AlignRight className="size-3" /></button>
              <button type="button" onClick={protoAct('align', 'full')} title="Full Width" className="p-1 hover:bg-black/10 rounded text-ink hover:text-ink cursor-pointer"><Maximize2 className="size-3" /></button>

              <span className="mx-1 h-4 w-px bg-black/10" />

              {/* Hierarchy */}
              <button type="button" onClick={protoAct('parent')} title="Select Parent Container" className="px-1.5 py-1 text-[10px] hover:bg-black/10 rounded text-ink hover:text-ink font-medium cursor-pointer">Parent</button>
              <button type="button" onClick={protoAct('move', -1)} title="Move Up in DOM" className="p-1 hover:bg-black/10 rounded text-ink hover:text-ink text-[11px] font-medium cursor-pointer">↑</button>
              <button type="button" onClick={protoAct('move', 1)} title="Move Down in DOM" className="p-1 hover:bg-black/10 rounded text-ink hover:text-ink text-[11px] font-medium cursor-pointer">↓</button>

              {/* Size */}
              <button type="button" onClick={protoAct('wider', -10)} title="Narrower (-10%)" className="px-1.5 py-1 text-[10px] hover:bg-black/10 rounded text-ink hover:text-ink font-medium cursor-pointer">-10%</button>
              <button type="button" onClick={protoAct('wider', 10)} title="Wider (+10%)" className="px-1.5 py-1 text-[10px] hover:bg-black/10 rounded text-ink hover:text-ink font-medium cursor-pointer">+10%</button>

              <span className="mx-1 h-4 w-px bg-black/10" />

              {/* Actions */}
              <button type="button" onClick={protoAct('duplicate')} title="Duplicate Element" className="p-1 hover:bg-black/10 rounded text-ink hover:text-ink cursor-pointer"><Copy className="size-3" /></button>
              <button type="button" onClick={protoAct('remove')} title="Delete Element" className="p-1 hover:bg-black/10 rounded text-rose-300 hover:text-rose-200 cursor-pointer"><Trash2 className="size-3" /></button>
              <button type="button" onClick={() => { protoEditorRef.current?.editText(!figmaTyping); setFigmaTyping(!figmaTyping) }} title="Edit Text Directly" className={cn("inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10.5px] font-medium transition cursor-pointer", figmaTyping ? "bg-emerald-600 text-ink" : "bg-black/[.06] text-ink hover:bg-black/[.12]")}>
                <Type className="size-3" />
                <span>{figmaTyping ? 'Done typing' : 'Text'}</span>
              </button>
            </>
          ) : (
            <span className="flex items-center gap-1.5 font-mono text-[11px] text-muted2">
              <Move className="size-3 text-[#BFB9FF]" />
              <span>Click or drag any element to position freely with cursor · Drag corner handles to resize · Arrow keys to nudge</span>
            </span>
          )}

          <span className="flex-1" />

          {/* Save Button */}
          {figmaDirty && (
            <button
              type="button"
              onClick={savePrototypeFigma}
              disabled={savingProto}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-semibold text-ink shadow-sm hover:bg-emerald-500 disabled:opacity-50 transition cursor-pointer"
            >
              {savingProto ? <><Loader2 className="size-3 animate-spin" /> Saving…</> : <><Save className="size-3" /> Save to HTML</>}
            </button>
          )}

          {saveProtoSuccess && (
            <span className="flex items-center gap-1 font-mono text-[11px] text-ink">
              <Check className="size-3" /> Saved!
            </span>
          )}

          <button
            type="button"
            onClick={protoAct('undo')}
            title="Undo last change (Ctrl+Z)"
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition cursor-pointer bg-black/[.06] text-ink hover:bg-black/[.12] hover:text-ink"
          >
            <UndoIcon className="size-3" />
            <span>Undo</span>
          </button>
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

        {visualEditOn && !inspectedElement && (
          <p className="pointer-events-none absolute inset-x-0 bottom-7 z-[9] mx-auto w-fit rounded-full bg-emerald-700/90 px-3.5 py-1.5 text-[11px] font-medium text-ink shadow-lg backdrop-blur-md">
            Visual Inspector active: click any element to live-edit text, colors, layout and move without LLM
          </p>
        )}

        {visualEditOn && inspectedElement && inspectedDoc && (
          <VisualInspector
            element={inspectedElement}
            doc={inspectedDoc}
            project={project}
            currentFile={baseFileName(currentFile)}
            onClose={() => {
              const prev = inspectedDoc?.querySelector('.__vf_selected')
              if (prev) prev.classList.remove('__vf_selected')
              setInspectedElement(null)
            }}
            onLog={(lvl, msg) => addLog(lvl, msg)}
          />
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

                <div className="relative mb-5 grid size-16 place-items-center rounded-none border border-accent/25 bg-accent shadow-[0_0_35px_rgba(191, 185, 255,0.2)]">
                  <FlaskConical className="size-7 text-ink animate-pulse" />
                  <Loader2 className="absolute size-10 animate-spin text-ink/40" />
                </div>

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
