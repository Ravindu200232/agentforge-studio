'use client'

import { useCallback, useEffect, useEffectEvent, useRef, useState } from 'react'
import { api } from './api'
import { frameDoc } from './picker'
import { arrangePictures, clamp, newPicture, pictureMarkup, PICTURE_LAYER_STYLE, readPicture, resizePicture, selectPicture, setPicture, uid } from './picture-editor'

const CSS = `
  .__af_picture_item{position:absolute;box-sizing:border-box;pointer-events:auto;cursor:grab;touch-action:none}
  .__af_picture_item>svg{display:block;width:100%;height:100%;overflow:visible;pointer-events:none}
  .__af_picture_selected{outline:1px solid #586fe6}
  .__af_picture_crop{cursor:move;z-index:1}
  .__af_picture_handle{position:absolute;width:11px;height:11px;box-sizing:border-box;border:2px solid #586fe6;background:#fff;border-radius:2px;transform:translate(-50%,-50%);pointer-events:auto}
  .__af_picture_handle[data-picture-handle=nw]{top:0;left:0;cursor:nwse-resize}
  .__af_picture_handle[data-picture-handle=ne]{top:0;left:100%;cursor:nesw-resize}
  .__af_picture_handle[data-picture-handle=sw]{top:100%;left:0;cursor:nesw-resize}
  .__af_picture_handle[data-picture-handle=se]{top:100%;left:100%;cursor:nwse-resize}
  .__af_picture_handle[data-picture-handle=rotate]{top:-21px;left:50%;border-radius:50%;cursor:crosshair}
`
const point = (event, layer) => {
  const box = layer.getBoundingClientRect()
  return { x: event.clientX - box.left, y: event.clientY - box.top }
}
const move = (row, dx, dy) => ({ ...row, x: clamp(Math.round(row.x + dx), 0, 50000), y: clamp(Math.round(row.y + dy), 0, 50000) })
const isInput = event => Boolean(event.target.closest?.('input,textarea,select,[contenteditable=true]'))

export function usePictureEditor({ project, page, frame, loaded, onSaved, onClose, disabled }) {
  const [rows, setRows] = useState([])
  const [ids, setIds] = useState([])
  const [crop, setCrop] = useState(false)
  const [waiting, setWaiting] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const current = useRef([])
  const base = useRef([])
  const revision = useRef('')
  const undo = useRef([])
  const redo = useRef([])
  const lastField = useRef(null)
  const uploads = useRef(new Map())
  const layer = useRef(null)
  const painted = useRef(new Map())
  const panel = useRef(null)
  const drag = useRef(null)
  const sending = useRef(false)
  const alive = useRef(false)
  const locked = waiting || saving || disabled || !revision.current
  const picked = rows.filter(row => ids.includes(row.id))
  const selected = picked.length === 1 ? picked[0] : null

  const show = useCallback(next => { current.current = next; setRows(next) }, [])
  const commit = (next, before = current.current, field = null) => {
    if (JSON.stringify(next) === JSON.stringify(before)) return
    const time = Date.now()
    if (field !== lastField.current?.field || !field || time - lastField.current.time > 600) {
      undo.current = [...undo.current.slice(-79), before]
    }
    lastField.current = field && { field, time }
    redo.current = []
    show(next === current.current ? [...next] : next)
  }
  const history = direction => {
    const from = direction === 'undo' ? undo : redo
    const to = direction === 'undo' ? redo : undo
    if (!from.current.length || locked) return
    lastField.current = null
    const next = from.current.at(-1)
    from.current = from.current.slice(0, -1)
    to.current = [...to.current, current.current]
    show(next)
    setIds(ids => ids.filter(id => next.some(row => row.id === id)))
  }
  const update = (key, value) => {
    if (locked || !selected) return
    commit(current.current.map(row => row.id === selected.id ? setPicture(row, key, value) : row),
      current.current, selected.id + key)
  }
  const choose = (id, extend) => {
    const next = selectPicture(current.current, ids, id, extend)
    setIds(next)
    if (next.length !== 1 || !ids.includes(next[0])) setCrop(false)
    return next
  }
  const arrange = (command, axis, edge) => {
    if (!locked && ids.length) commit(arrangePictures(current.current, ids, command, axis, edge))
  }
  const duplicate = () => {
    if (locked || !ids.length) return
    const groups = new Map()
    const copies = current.current.filter(row => ids.includes(row.id)).map(row => {
      if (row.group && !groups.has(row.group)) groups.set(row.group, uid())
      return { ...move(row, 16, 16), id: uid(), group: groups.get(row.group) || '' }
    })
    commit([...current.current, ...copies])
    setIds(copies.map(row => row.id))
  }
  const remove = () => {
    if (locked || !ids.length) return
    commit(current.current.filter(row => !ids.includes(row.id)))
    setIds([])
    setCrop(false)
  }

  useEffect(() => {
    alive.current = true
    let active = true
    api.wireframePictures(project, page).then(result => {
      if (!active) return
      revision.current = result.revision
      base.current = result.pictures
      show(result.pictures)
    }).catch(failure => { if (active) setError(failure.message) })
      .finally(() => { if (active) setWaiting(false) })
    return () => { active = false; alive.current = false }
  }, [project, page, show])

  useEffect(() => {
    const retained = uploads.current
    return () => { for (const image of retained.values()) URL.revokeObjectURL(image.url) }
  }, [])

  const add = async (files, position, replace) => {
    if (locked || !files.length) return
    setError('')
    try {
      const incoming = replace ? [files[0]] : files
      if (current.current.length + (replace ? 0 : incoming.length) > 100) throw new Error('A wireframe page can have up to 100 pictures.')
      const results = await Promise.allSettled(incoming.map(readPicture))
      const pictures = results.flatMap(result => result.status === 'fulfilled' ? [result.value] : [])
      if (!alive.current || results.some(result => result.status === 'rejected')) {
        for (const picture of pictures) URL.revokeObjectURL(picture.url)
        if (alive.current) throw results.find(result => result.status === 'rejected').reason
        return
      }
      for (const picture of pictures) uploads.current.set(picture.asset, picture)
      if (replace) {
        const { asset, name, naturalW, naturalH } = pictures[0]
        commit(current.current.map(row => row.id === replace ? { ...row, asset, name, naturalW, naturalH, zoom: 1, panX: 0, panY: 0 } : row))
        return
      }
      const doc = frameDoc(frame.current)
      const box = layer.current?.getBoundingClientRect()
      const x = position?.x ?? Math.max(0, 24 - (box?.left || 0))
      const y = position?.y ?? Math.max(0, 80 - (box?.top || 0))
      const fresh = pictures.map((file, index) => newPicture(file, clamp(Math.round(x + index * 18), 0, 50000),
        clamp(Math.round(y + index * 18), 0, 50000), Math.min(280, (doc?.documentElement.clientWidth || 400) - 40)))
      commit([...current.current, ...fresh])
      setIds(fresh.map(row => row.id))
      setCrop(false)
    } catch (failure) { if (alive.current) setError(failure.message || 'The picture could not be opened.') }
  }

  const save = async () => {
    if (locked || sending.current || drag.current || !revision.current) return
    const used = new Set(current.current.map(row => row.asset))
    const added = [...uploads.current].filter(([asset]) => used.has(asset))
    if (added.reduce((size, [, item]) => size + item.bytes, 0) > 32 * 1024 * 1024) {
      setError('Save up to 32 MB of new pictures at a time.')
      return
    }
    sending.current = true
    setSaving(true)
    setError('')
    try {
      await api.wireframePictures(project, page, {
        revision: revision.current, pictures: current.current,
        uploads: Object.fromEntries(added.map(([asset, item]) => [asset, item.data])),
      })
      await onSaved()
      if (alive.current) onClose()
    } catch (failure) {
      if (alive.current) setError(failure.message || 'The pictures could not be saved.')
    } finally {
      sending.current = false
      if (alive.current) setSaving(false)
    }
  }

  const paint = useEffectEvent(() => {
    const surface = layer.current
    if (!surface) return
    const previous = painted.current
    const next = new Map()
    let anchor = surface.firstElementChild
    for (const row of rows) {
      const picked = ids.includes(row.id)
      const cropping = picked && crop
      const old = previous.get(row.id)
      let node = old?.node
      if (!old || old.picked !== picked || old.cropping !== cropping ||
          Object.keys(row).some(key => !['x', 'y', 'rotation'].includes(key) && row[key] !== old.row[key])) {
        const template = surface.ownerDocument.createElement('template')
        const url = uploads.current.get(row.asset)?.url
          || api.webUrl(project, 'wireframe-html/assets/pictures/' + encodeURIComponent(row.asset))
        template.innerHTML = pictureMarkup(row, url, picked, cropping)
        node = template.content.firstElementChild
        if (old?.node === anchor) anchor = anchor.nextElementSibling
        old?.node.remove()
      }
      Object.assign(node.style, { left: row.x + 'px', top: row.y + 'px', transform: `rotate(${row.rotation}deg)` })
      if (node !== anchor) surface.insertBefore(node, anchor)
      anchor = node.nextElementSibling
      next.set(row.id, { row, picked, cropping, node })
    }
    for (const [id, { node }] of previous) if (!next.has(id)) node.remove()
    painted.current = next
  })
  useEffect(() => { paint() }, [rows, ids, crop, loaded])

  const pointerDown = useEffectEvent(event => {
    if (locked || event.button !== 0 || !event.isPrimary) return
    const node = event.target.closest?.('[data-picture-id]')
    if (!node || !layer.current.contains(node)) { setIds([]); setCrop(false); return }
    const id = node.dataset.pictureId
    const next = ids.includes(id) && !event.shiftKey ? ids : choose(id, event.shiftKey)
    if (!next.includes(id)) return
    const before = current.current
    const item = before.find(row => row.id === id)
    const handle = event.target.dataset.pictureHandle
    const start = point(event, layer.current)
    const root = layer.current.ownerDocument.documentElement
    drag.current = { before, root, pointer: event.pointerId, start, ids: next, item,
      kind: handle || (crop && next.length === 1 && ids.includes(id) ? 'crop' : 'move') }
    event.preventDefault()
    root.setPointerCapture(event.pointerId)
  })
  const pointerMove = useEffectEvent(event => {
    const action = drag.current
    if (!action || event.pointerId !== action.pointer || locked) return
    const now = point(event, layer.current)
    const dx = now.x - action.start.x, dy = now.y - action.start.y
    if (dx === 0 && dy === 0 && current.current === action.before) return
    const { before, item, kind } = action
    if (kind === 'move') {
      const picked = before.filter(row => action.ids.includes(row.id))
      const x = clamp(dx, -Math.min(...picked.map(row => row.x)), 50000 - Math.max(...picked.map(row => row.x)))
      const y = clamp(dy, -Math.min(...picked.map(row => row.y)), 50000 - Math.max(...picked.map(row => row.y)))
      show(before.map(row => action.ids.includes(row.id) ? move(row, x, y) : row))
      return
    }
    const angle = item.rotation * Math.PI / 180
    let after
    if (kind === 'crop') {
      after = { ...item, panX: clamp(item.panX + dx * Math.cos(angle) + dy * Math.sin(angle), -10000, 10000),
        panY: clamp(item.panY - dx * Math.sin(angle) + dy * Math.cos(angle), -10000, 10000) }
    } else if (kind === 'rotate') {
      const cx = item.x + item.w / 2, cy = item.y + item.h / 2
      const delta = (Math.atan2(now.y - cy, now.x - cx) - Math.atan2(action.start.y - cy, action.start.x - cx)) * 180 / Math.PI
      const degree = (item.rotation + delta + 540) % 360 - 180
      after = { ...item, rotation: event.shiftKey ? Math.round(degree / 15) * 15 : Math.round(degree) }
    } else after = resizePicture(item, kind, dx, dy, event.shiftKey)
    show(before.map(row => row.id === item.id ? after : row))
  })
  const finish = useEffectEvent((event, cancel = false) => {
    const action = drag.current
    if (!action || event && event.pointerId !== action.pointer) return
    drag.current = null
    if (action.root.hasPointerCapture(action.pointer)) action.root.releasePointerCapture(action.pointer)
    if (cancel) show(action.before)
    else commit(current.current, action.before)
  })
  const keys = useEffectEvent(event => {
    if (locked || isInput(event) || (event.currentTarget === document && !panel.current?.contains(event.target))) return
    const modifier = event.ctrlKey || event.metaKey
    const key = event.key.toLowerCase()
    if (modifier && ['z', 'y', 'd'].includes(key)) {
      event.preventDefault()
      if (key === 'd') duplicate()
      else history(key === 'y' || event.shiftKey ? 'redo' : 'undo')
    }
    if (['delete', 'backspace'].includes(key) && ids.length) { event.preventDefault(); remove() }
    const arrows = { arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, -1], arrowdown: [0, 1] }
    if (arrows[key] && ids.length && !modifier) {
      event.preventDefault()
      const [x, y] = arrows[key].map(n => n * (event.shiftKey ? 10 : 1))
      commit(current.current.map(row => ids.includes(row.id) ? move(row, x, y) : row))
    }
  })
  const paste = useEffectEvent(event => {
    if (isInput(event)) return
    const files = [...(event.clipboardData?.files || [])]
    if (files.length) { event.preventDefault(); add(files) }
  })
  const drop = useEffectEvent(event => {
    const files = [...(event.dataTransfer?.files || [])]
    if (!files.length) return
    event.preventDefault()
    add(files, point(event, layer.current))
  })

  useEffect(() => {
    const doc = frameDoc(frame.current)
    if (!doc?.body || waiting) return undefined
    const saved = doc.querySelector('[data-af-picture-layer]')
    const display = saved?.style.display
    if (saved) saved.style.display = 'none'
    const preview = doc.createElement('div')
    preview.style.cssText = PICTURE_LAYER_STYLE
    const style = doc.createElement('style')
    style.textContent = CSS
    doc.head.append(style)
    doc.body.append(preview)
    layer.current = preview
    paint()
    const listeners = {
      pointerdown: pointerDown, pointermove: pointerMove, pointerup: event => { pointerMove(event); finish(event) },
      pointercancel: event => finish(event, true), lostpointercapture: event => finish(event, true),
      keydown: keys, paste, drop, dragover: event => { if (event.dataTransfer?.types.includes('Files')) event.preventDefault() },
      click: event => { event.preventDefault(); event.stopImmediatePropagation() },
    }
    for (const [name, listener] of Object.entries(listeners)) doc.addEventListener(name, listener, true)
    document.addEventListener('keydown', keys, true)
    document.addEventListener('paste', paste, true)
    return () => {
      finish(null, true)
      for (const [name, listener] of Object.entries(listeners)) doc.removeEventListener(name, listener, true)
      document.removeEventListener('keydown', keys, true)
      document.removeEventListener('paste', paste, true)
      preview.remove(); style.remove(); layer.current = null
      painted.current.clear()
      if (saved) saved.style.display = display
    }
  }, [frame, loaded, waiting])

  return { rows, ids, selected, picked, crop, setCrop, waiting, saving, locked, error, panel, add, save, choose, update, arrange,
    duplicate, remove, history, canUndo: undo.current.length > 0, canRedo: redo.current.length > 0,
    dirty: JSON.stringify(rows) !== JSON.stringify(base.current) }
}
