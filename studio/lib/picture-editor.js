export const PICTURE_TYPES = 'image/png,image/jpeg,image/webp,image/gif'
export const PICTURE_LAYER_STYLE = 'position:absolute;top:0;left:0;width:100%;height:0;pointer-events:none;z-index:100'
export const PICTURE_SHAPES = [
  ['rectangle', 'Rectangle'], ['square', 'Square'], ['rounded', 'Rounded rectangle'],
  ['circle', 'Circle'], ['ellipse', 'Ellipse'], ['triangle', 'Triangle'],
]
export const uid = () => crypto.randomUUID().replaceAll('-', '')
export const clamp = (n, min, max) => Math.max(min, Math.min(max, n))
const round = n => Math.round(n * 100) / 100

export async function readPicture(file) {
  if (!file) throw new Error('Choose a picture file.')
  if (file.size > 8 * 1024 * 1024) throw new Error('Each picture must be 8 MB or smaller.')
  const type = file.type || ({ png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif' })[file.name.split('.').at(-1).toLowerCase()]
  if (!PICTURE_TYPES.split(',').includes(type)) throw new Error('Choose a PNG, JPEG, WebP or GIF picture.')
  const object = URL.createObjectURL(file)
  try {
    const image = new Image()
    image.src = object
    await image.decode()
    const encoded = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result).split(',')[1])
      reader.onerror = () => reject(reader.error)
      reader.readAsDataURL(file)
    })
    return { asset: 'new-' + uid(), data: encoded, url: object, bytes: file.size,
      name: file.name || 'Clipboard picture', naturalW: image.naturalWidth, naturalH: image.naturalHeight }
  } catch (error) { URL.revokeObjectURL(object); throw error }
}

export function newPicture(file, x, y, available = 280) {
  const w = clamp(file.naturalW, 32, Math.max(32, available))
  return { id: uid(), asset: file.asset, name: file.name, alt: '', x, y,
    w, h: clamp(round(w * file.naturalH / file.naturalW), 8, 900),
    naturalW: file.naturalW, naturalH: file.naturalH, shape: 'rectangle', fit: 'fill', radius: 16,
    zoom: 1, panX: 0, panY: 0, rotation: 0, flipX: false, flipY: false, locked: false, group: '',
    border: 0, color: '#222222', opacity: 100, shadow: 0, brightness: 100, contrast: 100, saturation: 100 }
}

export function placeholderPicture(bounds, shape) {
  return { ...newPicture({ asset: 'placeholder', name: 'Picture placeholder', naturalW: 1, naturalH: 1 }, 0, 0),
    ...bounds, shape, border: 1, color: '#737373' }
}

export function setPicture(fields, key, value) {
  const row = { ...fields, [key]: value }
  const square = row.shape === 'square' || row.shape === 'circle'
  if (square && (key === 'shape' || key === 'w' || key === 'h')) row.w = row.h = key === 'h' ? row.h : row.w
  else if (row.locked && key === 'w') row.h = clamp(round(row.w * fields.h / fields.w), 8, 10000)
  else if (row.locked && key === 'h') row.w = clamp(round(row.h * fields.w / fields.h), 8, 10000)
  if (key === 'fit') Object.assign(row, { zoom: 1, panX: 0, panY: 0 })
  return row
}

export function selectPicture(rows, ids, id, extend) {
  const row = rows.find(item => item.id === id)
  if (!row) return []
  const next = row.group ? rows.filter(item => item.group === row.group).map(item => item.id) : [id]
  if (!extend) return next
  return next.every(item => ids.includes(item)) ? ids.filter(item => !next.includes(item)) : [...new Set([...ids, ...next])]
}

export function visualBounds(row) {
  const angle = row.rotation * Math.PI / 180
  const w = row.w * Math.abs(Math.cos(angle)) + row.h * Math.abs(Math.sin(angle))
  const h = row.w * Math.abs(Math.sin(angle)) + row.h * Math.abs(Math.cos(angle))
  return { x: row.x + (row.w - w) / 2, y: row.y + (row.h - h) / 2, w, h }
}

export function arrangePictures(rows, ids, command, axis, edge) {
  const picked = rows.filter(row => ids.includes(row.id))
  if (command === 'forward' || command === 'backward') {
    const out = [...rows]
    const forward = command === 'forward'
    for (let i = forward ? out.length - 2 : 1; i >= 0 && i < out.length; i += forward ? -1 : 1) {
      const next = i + (forward ? 1 : -1)
      if (next >= 0 && next < out.length && ids.includes(out[i].id) && !ids.includes(out[next].id)) {
        [out[i], out[next]] = [out[next], out[i]]
      }
    }
    return out
  }
  if (command === 'group' || command === 'ungroup') {
    const group = command === 'group' ? uid() : ''
    return rows.map(row => ids.includes(row.id) ? { ...row, group } : row)
  }
  const length = axis === 'x' ? 'w' : 'h'
  const bounds = picked.map(row => ({ row, ...visualBounds(row) })).sort((a, b) => a[axis] - b[axis])
  if (bounds.length < (command === 'distribute' ? 3 : 2)) return rows
  const first = bounds[0][axis]
  const last = Math.max(...bounds.map(item => item[axis] + item[length]))
  const gap = (last - first - bounds.reduce((sum, item) => sum + item[length], 0)) / (bounds.length - 1)
  let cursor = first
  const positions = new Map()
  for (const box of bounds) {
    const desired = command === 'distribute' ? cursor
      : edge === 'end' ? last - box[length]
      : edge === 'center' ? (first + last - box[length]) / 2 : first
    positions.set(box.row.id, clamp(round(box.row[axis] + desired - box[axis]), 0, 50000))
    cursor += box[length] + gap
  }
  return rows.map(row => positions.has(row.id) ? { ...row, [axis]: positions.get(row.id) } : row)
}

export function resizePicture(row, handle, dx, dy, proportional) {
  const angle = row.rotation * Math.PI / 180
  const cos = Math.cos(angle), sin = Math.sin(angle)
  const horizontal = handle.includes('w') ? -1 : 1
  const vertical = handle.includes('n') ? -1 : 1
  const localX = dx * cos + dy * sin, localY = -dx * sin + dy * cos
  let w = clamp(row.w + localX * horizontal, 8, 10000)
  let h = clamp(row.h + localY * vertical, 8, 10000)
  if (proportional || row.locked || ['circle', 'square'].includes(row.shape)) {
    const scale = Math.abs(w / row.w - 1) > Math.abs(h / row.h - 1) ? w / row.w : h / row.h
    const fit = clamp(scale, Math.max(8 / row.w, 8 / row.h), Math.min(10000 / row.w, 10000 / row.h))
    w = row.w * fit
    h = row.h * fit
  }
  const centerX = (w - row.w) / 2 * horizontal, centerY = (h - row.h) / 2 * vertical
  return { ...row, w: round(w), h: round(h),
    x: clamp(round(row.x + (row.w - w) / 2 + centerX * cos - centerY * sin), 0, 50000),
    y: clamp(round(row.y + (row.h - h) / 2 + centerX * sin + centerY * cos), 0, 50000) }
}

const esc = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])

export function pictureSvg(row, src, prefix = 'af-picture-preview-') {
  const { w, h } = row
  const clip = prefix + esc(row.id)
  const geometry = row.shape === 'triangle' ? ['polygon', `points="${w / 2},0 ${w},${h} 0,${h}"`]
    : row.shape === 'ellipse' || row.shape === 'circle' ? ['ellipse', `cx="${w / 2}" cy="${h / 2}" rx="${w / 2}" ry="${h / 2}"`]
      : ['rect', `width="${w}" height="${h}" rx="${row.shape === 'rounded' ? Math.min(row.radius, w / 2, h / 2) : 0}"`]
  const [tag, attributes] = geometry
  const ratio = (row.fit === 'fit' ? Math.min : Math.max)(w / row.naturalW, h / row.naturalH) * row.zoom
  const iw = row.naturalW * ratio, ih = row.naturalH * ratio
  const size = Math.min(48, Math.min(w, h) * 0.44)
  const content = row.asset === 'placeholder' ? `
    <${tag} ${attributes} fill="#e5e5e5"/>
    <svg x="${(w - size) / 2}" y="${(h - size) / 2}" width="${size}" height="${size}" viewBox="0 0 24 24"
      fill="none" stroke="#737373" stroke-width="1.5" stroke-linejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="m3 17 5-4 3 3 4-6 6 7"/>
    </svg>` : `<image href="${esc(src)}" x="${-iw / 2}" y="${-ih / 2}" width="${iw}" height="${ih}"
      preserveAspectRatio="none" transform="translate(${w / 2 + row.panX} ${h / 2 + row.panY}) scale(${row.flipX ? -1 : 1} ${row.flipY ? -1 : 1})"
      style="filter:brightness(${row.brightness}%) contrast(${row.contrast}%) saturate(${row.saturation}%)"/>`
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" aria-hidden="true"
      style="display:block;width:100%;height:100%;pointer-events:none;opacity:${row.opacity / 100};filter:drop-shadow(0 ${row.shadow / 3}px ${row.shadow}px #0005)">
      <defs><clipPath id="${clip}"><${tag} ${attributes}/></clipPath></defs>
      <g clip-path="url(#${clip})">${content}
      <${tag} ${attributes} fill="none" stroke="${esc(row.color)}" stroke-width="${row.border * 2}"/></g>
    </svg>`
}

export function pictureMarkup(row, src, selected, crop) {
  const controls = selected && !crop ? ['nw', 'ne', 'sw', 'se', 'rotate'].map(handle =>
    `<i class="__af_picture_handle" data-picture-handle="${handle}"></i>`).join('') : ''
  return `<div data-picture-id="${esc(row.id)}" class="__af_picture_item${selected ? ' __af_picture_selected' : ''}${crop ? ' __af_picture_crop' : ''}"
    style="left:${row.x}px;top:${row.y}px;width:${row.w}px;height:${row.h}px;transform:rotate(${row.rotation}deg)">
    ${pictureSvg(row, src)}${controls}</div>`
}
