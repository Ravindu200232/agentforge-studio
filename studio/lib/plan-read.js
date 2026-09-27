/**
 * A plan, as something a person reads rather than a file they scan.
 *
 * The planner writes Markdown for the build pass: headings, bullets, inline
 * backticks, the occasional table. Shown raw in a monospace block it reads as
 * output rather than as a proposal — and this is the one moment someone is
 * being asked to approve it, so it has to be legible at a glance.
 *
 * Deliberately small: headings, list items, paragraphs and code. A full
 * Markdown parser would bring more than this needs, and the planner's own
 * prompt fixes the shape of what it writes.
 */

const HEADING = /^(#{1,6})\s+(.*)$/
const BULLET = /^\s*[-*+]\s+(.+)$/
const NUMBERED = /^\s*(\d+)[.)]\s+(.+)$/
const FENCE = /^\s*```/
const DIVIDER = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/
const TABLE_ROW = /^\s*\|.*\|\s*$/

/** The plan as blocks: heading, para, bullets, steps, code. */
export function readPlan(markdown) {
  const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n')
  const blocks = []
  let paragraph = []
  let list = null
  let code = null

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ kind: 'para', text: paragraph.join(' ').trim() })
    paragraph = []
  }
  const flushList = () => {
    if (list?.items.length) blocks.push(list)
    list = null
  }
  const flush = () => { flushParagraph(); flushList() }

  for (const raw of lines) {
    if (FENCE.test(raw)) {
      if (code) { blocks.push(code); code = null } else { flush(); code = { kind: 'code', text: '' } }
      continue
    }
    if (code) {
      code.text += (code.text ? '\n' : '') + raw
      continue
    }

    if (!raw.trim()) { flush(); continue }
    if (DIVIDER.test(raw)) { flush(); continue }

    // A table is rare in a plan and never the interesting part; keep its rows
    // as plain lines rather than pretending to render a table badly.
    if (TABLE_ROW.test(raw)) {
      const cells = raw.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())
      if (cells.every(cell => /^:?-{2,}:?$/.test(cell))) continue
      flushParagraph()
      list = list?.kind === 'bullets' ? list : (flushList(), { kind: 'bullets', items: [] })
      list.items.push(cells.filter(Boolean).join(' — '))
      continue
    }

    const heading = raw.match(HEADING)
    if (heading) {
      flush()
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2].trim() })
      continue
    }

    const numbered = raw.match(NUMBERED)
    if (numbered) {
      flushParagraph()
      if (list?.kind !== 'steps') { flushList(); list = { kind: 'steps', items: [] } }
      list.items.push(numbered[2].trim())
      continue
    }

    const bullet = raw.match(BULLET)
    if (bullet) {
      flushParagraph()
      if (list?.kind !== 'bullets') { flushList(); list = { kind: 'bullets', items: [] } }
      list.items.push(bullet[1].trim())
      continue
    }

    flushList()
    paragraph.push(raw.trim())
  }
  flush()
  if (code) blocks.push(code)
  return blocks
}

/**
 * Inline markup as parts, so `**bold**` and `` `code` `` render rather than
 * showing their own punctuation.
 */
export function readInline(text) {
  const parts = []
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*|_[^_]+_)/g
  let at = 0
  let match
  while ((match = pattern.exec(String(text || ''))) !== null) {
    if (match.index > at) parts.push({ kind: 'text', text: text.slice(at, match.index) })
    const token = match[0]
    if (token.startsWith('**')) parts.push({ kind: 'strong', text: token.slice(2, -2) })
    else if (token.startsWith('`')) parts.push({ kind: 'code', text: token.slice(1, -1) })
    else parts.push({ kind: 'em', text: token.slice(1, -1) })
    at = match.index + token.length
  }
  if (at < String(text || '').length) parts.push({ kind: 'text', text: String(text).slice(at) })
  return parts
}

/** A one-line summary for the dialog's header. */
export function planHeadline(markdown) {
  for (const block of readPlan(markdown)) {
    if (block.kind === 'para') return block.text
    if (block.kind === 'bullets' || block.kind === 'steps') return block.items[0]
  }
  return ''
}
