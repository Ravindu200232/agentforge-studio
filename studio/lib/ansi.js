/**
 * Terminal output as coloured pieces: the SGR codes dev servers print (`\x1b[32m`, bold, 256 and true colour) become
 * styles, every other control sequence (cursor moves, line clears) is dropped, and a carriage return inside a line
 * keeps only what was written after it, the way a progress line overwrites itself.
 */

const BASIC = ['#4b5263', '#ff6b6b', '#5fd38d', '#f5c451', '#6cb6ff', '#c792ea', '#56d4dd', '#d8dee9']
const BRIGHT = ['#7f8796', '#ff8f8f', '#8ce99a', '#ffe066', '#91c8ff', '#e0b0ff', '#99e9f2', '#ffffff']

function xterm(n) {
  if (n < 8) return BASIC[n]
  if (n < 16) return BRIGHT[n - 8]
  if (n < 232) {
    const i = n - 16
    const level = v => (v ? 55 + v * 40 : 0)
    return `rgb(${level(Math.floor(i / 36))},${level(Math.floor(i / 6) % 6)},${level(i % 6)})`
  }
  const grey = 8 + (n - 232) * 10
  return `rgb(${grey},${grey},${grey})`
}

/** The style after one `ESC[...m`. */
function apply(style, codes) {
  const next = { ...style }
  const list = codes.length ? codes : [0]
  for (let i = 0; i < list.length; i++) {
    const code = list[i]
    if (code === 0) { Object.keys(next).forEach(key => delete next[key]) }
    else if (code === 1) next.bold = true
    else if (code === 2) next.dim = true
    else if (code === 3) next.italic = true
    else if (code === 4) next.underline = true
    else if (code === 22) { delete next.bold; delete next.dim }
    else if (code === 23) delete next.italic
    else if (code === 24) delete next.underline
    else if (code >= 30 && code <= 37) next.color = BASIC[code - 30]
    else if (code >= 90 && code <= 97) next.color = BRIGHT[code - 90]
    else if (code === 39) delete next.color
    else if (code >= 40 && code <= 47) next.background = BASIC[code - 40]
    else if (code >= 100 && code <= 107) next.background = BRIGHT[code - 100]
    else if (code === 49) delete next.background
    else if ((code === 38 || code === 48) && list[i + 1] === 5) {
      next[code === 38 ? 'color' : 'background'] = xterm(list[i + 2] ?? 0); i += 2
    } else if ((code === 38 || code === 48) && list[i + 1] === 2) {
      next[code === 38 ? 'color' : 'background'] = `rgb(${list[i + 2] ?? 0},${list[i + 3] ?? 0},${list[i + 4] ?? 0})`; i += 4
    }
  }
  return next
}

// SGR, then any other CSI sequence, then OSC (titles, links) up to BEL or ST.
const SEQUENCE = /\x1b\[([0-9;]*)m|\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-_]/g

/** `[{ text, style }]` pieces per line, with the style carried from line to line. */
export function ansiLines(text) {
  let style = {}
  return String(text || '').split('\n').map(raw => {
    let line = raw.endsWith('\r') ? raw.slice(0, -1) : raw
    const cr = line.lastIndexOf('\r')
    if (cr >= 0) line = line.slice(cr + 1)
    const pieces = []
    let last = 0
    line.replace(SEQUENCE, (match, sgr, offset) => {
      if (offset > last) pieces.push({ text: line.slice(last, offset), style })
      if (sgr !== undefined) style = apply(style, sgr.split(';').filter(Boolean).map(Number))
      last = offset + match.length
      return match
    })
    if (last < line.length) pieces.push({ text: line.slice(last), style })
    return pieces
  })
}

/** The inline style of one piece. */
export function cssOf(style) {
  if (!style) return undefined
  const css = {}
  if (style.color) css.color = style.color
  if (style.background) css.background = style.background
  if (style.bold) css.fontWeight = 600
  if (style.dim) css.opacity = 0.7
  if (style.italic) css.fontStyle = 'italic'
  if (style.underline) css.textDecoration = 'underline'
  return css
}

/** The plain text of some output, for copying. */
export const plain = text => ansiLines(text).map(line => line.map(piece => piece.text).join('')).join('\n')
