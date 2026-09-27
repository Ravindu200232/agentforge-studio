/**
 * Presentation-only cleanup for natural-language agent messages.
 *
 * The backend stream is evidence and must remain byte-for-byte intact in the
 * store. This module only prepares ordinary prose for display. Command and
 * command-output turns deliberately never call it.
 */

const MOJIBAKE = [
  ['ï»¿', ''], ['Â·', '·'], ['Â©', '©'], ['Â®', '®'], ['Â ', ' '],
  ['â€™', '’'], ['â€˜', '‘'], ['â€œ', '“'], ['â€\u009d', '”'],
  ['â€“', '–'], ['â€”', '—'], ['â€¦', '…'], ['â†’', '→'], ['â†', '←'],
]

const ANSI = /\u001b\[[0-?]*[ -/]*[@-~]/g
const PRINTED_ANSI = /\^\[\[[0-9;?]*[ -/]*[A-Za-z]/g
const EMOJI_PREFIX = /^\s*[\p{Extended_Pictographic}\uFE0F\u200D]+\s*/u

function decoded(value) {
  let text = String(value ?? '')
    .replace(ANSI, '')
    .replace(PRINTED_ANSI, '')
    .replace(/[\uFEFF\u200B\u200C]/g, '')
    .replace(/\r\n?/g, '\n')
    .replace(/\u00a0/g, ' ')
  for (const [bad, good] of MOJIBAKE) text = text.replaceAll(bad, good)
  return text
}

/** Remove display syntax while retaining the words it decorated. */
export function cleanChatProse(value) {
  let text = decoded(value)
  const protectedText = []
  const protect = content => {
    const marker = `CHATDISPLAYTOKEN${protectedText.length}ENDTOKEN`
    protectedText.push(String(content))
    return marker
  }

  // Keep inline code and unquoted glob paths exact while their display marks
  // are removed. A path such as **/*.test.js is not Markdown emphasis.
  text = text.replace(/(`+)([^\n]*?)\1/g, (_all, _ticks, body) => protect(body))
  text = text.replace(/\*\*\/[\w*?./\\-]+/g, match => protect(match))

  text = text
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/§\s*(\d+)/g, 'section $1')
    .split('\n')
    .map(line => {
      if (/^\s*(?:={3,}|-{3,}|\*{3,}|_{3,}|~{3,})\s*$/.test(line)) return ''
      let next = line
        .replace(/^\s{0,3}#{1,6}\s+/, '')
        .replace(/^\s*>+\s?/, '')
        .replace(/^\s*={3,}\s*/, '')
        .replace(/\s*={3,}\s*$/, '')
        .replace(EMOJI_PREFIX, '')
        .replace(/\*\*|__|~~/g, '')
        .replace(/\*([^*\n]+)\*/g, '$1')
        .replace(/[ \t]+/g, ' ')
      return next.trimEnd()
    })
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()

  protectedText.forEach((content, index) => {
    text = text.replaceAll(`CHATDISPLAYTOKEN${index}ENDTOKEN`, content)
  })
  return text
}

function proseBlocks(text) {
  const cleaned = cleanChatProse(text)
  if (!cleaned) return []
  const blocks = []
  let paragraph = []
  let list = []

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ kind: 'paragraph', text: paragraph.join('\n') })
    paragraph = []
  }
  const flushList = () => {
    if (list.length) blocks.push({ kind: 'list', items: list })
    list = []
  }

  for (const line of cleaned.split('\n')) {
    const item = /^\s*(?:[-*•▪◦]|\d+[.)])\s+(.+)$/.exec(line)
    if (item) {
      flushParagraph()
      list.push(item[1].trim())
    } else if (!line.trim()) {
      flushParagraph()
      flushList()
    } else {
      flushList()
      paragraph.push(line.trim())
    }
  }
  flushParagraph()
  flushList()
  return blocks
}

/** Split prose and fenced code without ever cleaning code contents. */
export function chatDisplayBlocks(value) {
  const source = decoded(value)
  const blocks = []
  const fence = /```([^\n`]*)\n?([\s\S]*?)(?:```|$)/g
  let cursor = 0
  let match
  while ((match = fence.exec(source))) {
    blocks.push(...proseBlocks(source.slice(cursor, match.index)))
    blocks.push({ kind: 'code', language: match[1].trim(), text: match[2].replace(/\n$/, '') })
    cursor = fence.lastIndex
    if (!match[0].endsWith('```')) break
  }
  blocks.push(...proseBlocks(source.slice(cursor)))
  return blocks
}

