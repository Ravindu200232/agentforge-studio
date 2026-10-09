'use client'

/**
 * The select and pencil tools over a framed app, for a view that has no chat beside it (the wireframes' page view).
 *
 * `mode` is the tool in hand: 'pick' (click a thing on the page), 'pencil' (draw around it) or 'text' (retype words; see
 * AppTextEdit). What was pointed at or marked is kept in `items`, each as the record the agent is told about (`info`, or
 * `marked` for what a drawing is around), and is sent with the next request.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import { attachPicker, elementsUnderStrokes, pickedFrom, pickLabel } from '@/lib/picker'

let seq = 0
const MOST = 6

/** What a drawing was around, in a few words, for its chip. */
function markedLabel(marked) {
  const names = marked.slice(0, 2).map(info => `<${info.tag}>${info.text ? ' ' + info.text.slice(0, 28) : ''}`)
  return `Drawing around ${names.join(', ')}${marked.length > 2 ? ` +${marked.length - 2}` : ''}`
}

export function useFrameTools(frameRef, { loaded = 0 } = {}) {
  const [mode, setMode] = useState(null)
  const [items, setItems] = useState([])
  const [inked, setInked] = useState(false)
  const canvasRef = useRef(null)
  const strokes = useRef([])
  const drawing = useRef(false)

  const addItem = useCallback(item => setItems(list => [...list.filter(x => x.key !== item.key), item].slice(-MOST)), [])
  const removeItem = useCallback(key => setItems(list => list.filter(item => item.key !== key)), [])

  const clearInk = useCallback(() => {
    strokes.current = []
    setInked(false)
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    ctx.save()
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.restore()
  }, [])

  const clearItems = useCallback(() => { setItems([]); clearInk() }, [clearInk])

  const chooseTool = useCallback(next => setMode(current => (current === next ? null : next)), [])

  // Select: a click on anything in the page is a thing pointed at.
  useEffect(() => {
    const frame = frameRef.current
    if (mode !== 'pick' || !frame) return undefined
    const detach = attachPicker(frame, (element) => {
      const info = pickedFrom(frame, element, 'desktop')
      addItem({ key: `pick-${++seq}`, kind: 'element', info, label: pickLabel(info) })
    })
    return () => { detach?.() }
  }, [mode, loaded, frameRef, addItem])

  // The page is a new one (another screen, or the app was bundled again): what was drawn on the old one is gone.
  useEffect(() => { clearInk() }, [loaded, clearInk])

  // Pencil: draw on a layer over the page; when a stroke ends, what is under it is what was marked.
  useEffect(() => {
    const canvas = canvasRef.current
    const frame = frameRef.current
    if (mode !== 'pencil' || !canvas || !frame) return undefined

    const fit = () => {
      const dpr = window.devicePixelRatio || 1
      const wide = Math.round(canvas.clientWidth * dpr)
      if (canvas.width === wide) return
      canvas.width = wide
      canvas.height = Math.round(canvas.clientHeight * dpr)
      const ctx = canvas.getContext('2d')
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.strokeStyle = '#ff2d55'
      ctx.lineWidth = 3
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
    }
    fit()

    const at = (event) => {
      const box = canvas.getBoundingClientRect()
      let sx = 0
      let sy = 0
      try { sx = frame.contentWindow.scrollX; sy = frame.contentWindow.scrollY } catch { /* the frame is not ours yet */ }
      const cx = event.clientX - box.left
      const cy = event.clientY - box.top
      return { cx, cy, x: Math.round(cx + sx), y: Math.round(cy + sy) }
    }
    const down = (event) => {
      drawing.current = true
      const point = at(event)
      strokes.current.push([{ x: point.x, y: point.y }])
      const ctx = canvas.getContext('2d')
      ctx.beginPath()
      ctx.moveTo(point.cx, point.cy)
    }
    const move = (event) => {
      if (!drawing.current) return
      const point = at(event)
      strokes.current[strokes.current.length - 1].push({ x: point.x, y: point.y })
      const ctx = canvas.getContext('2d')
      ctx.lineTo(point.cx, point.cy)
      ctx.stroke()
    }
    const up = () => {
      if (!drawing.current) return
      drawing.current = false
      const stroke = strokes.current[strokes.current.length - 1]
      if (!stroke || stroke.length < 3) { strokes.current.pop(); return }
      setInked(true)
      const marked = elementsUnderStrokes(frame, [stroke], 'desktop')
      if (marked.length) addItem({ key: `draw-${++seq}`, kind: 'drawing', marked, label: markedLabel(marked) })
    }
    canvas.addEventListener('pointerdown', down)
    canvas.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('resize', fit)
    return () => {
      canvas.removeEventListener('pointerdown', down)
      canvas.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('resize', fit)
    }
  }, [mode, frameRef, addItem])

  /** The records the agent is told about: the things picked, and what the drawings were around. */
  const elements = items.flatMap(item => (item.kind === 'element' ? [item.info] : item.marked || []))

  return { mode, setMode, chooseTool, items, elements, removeItem, clearItems, clearInk, inked, canvasRef }
}
