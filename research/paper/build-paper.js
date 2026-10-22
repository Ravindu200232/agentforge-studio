// Builds the paper as an IEEE-style two-column A4 .docx from content.js and references.js.
//   NODE_PATH=$(npm root -g) node research/paper/build-paper.js
// Then, for a PDF:  soffice --headless --convert-to pdf --outdir research/paper research/paper/AgentForge_ICAC2026_Paper.docx
const fs = require('fs')
const path = require('path')
const {
  AlignmentType, BorderStyle, Document, ImageRun, Packer, Paragraph, SectionType, Tab, Table, TableCell, TableRow,
  TabStopType, TextRun, VerticalAlign, WidthType,
} = require('docx')

const { title, abstract, indexTerms, body, tables, figures } = require('./content')
const REFERENCES = require('./references')

const OUT = path.join(__dirname, 'AgentForge_ICAC2026_Paper.docx')

// A4, IEEE conference margins (top 19 mm, sides 14.32 mm), columns 88.9 mm with a 4.22 mm gap. Units: twentieths of a point.
const PAGE = { width: 11906, height: 16838 }
const MARGIN = { top: 1077, bottom: 1134, left: 812, right: 812 }
const GAP = 239
const COLUMN = Math.floor((PAGE.width - MARGIN.left - MARGIN.right - GAP) / 2)   // 5021
const FONT = 'Times New Roman'
const PT = (n) => n * 2                                                           // half-points

// --- citations: numbered in order of first use ---------------------------------------------------------------------
const order = []
function cite(key) {
  if (!REFERENCES[key]) throw new Error('unknown reference ' + key)
  if (!order.includes(key)) order.push(key)
  return order.indexOf(key) + 1
}
function scan(text) { for (const m of String(text).matchAll(/\{([a-z0-9]+)\}/g)) cite(m[1]) }
for (const block of body) {
  if (block.p) scan(block.p)
  if (block.list) block.list.forEach(scan)
  if (block.table) {
    const t = tables[block.table]
    ;[t.caption, ...t.header, ...t.rows.flat(), t.note || ''].forEach(scan)
  }
  if (block.figure) scan(figures[block.figure].caption)
}
const unused = Object.keys(REFERENCES).filter((k) => !order.includes(k))
if (unused.length) throw new Error('references never cited: ' + unused.join(', '))

// --- inline text: *italic*, **bold**, {cite} ------------------------------------------------------------------------
function runs(text, base = {}) {
  const out = []
  const parts = String(text).split(/(\*\*[^*]+\*\*|\*[^*]+\*|\{[a-z0-9]+\})/g)
  for (const part of parts) {
    if (!part) continue
    if (part.startsWith('**')) out.push(new TextRun({ ...base, text: part.slice(2, -2), bold: true }))
    else if (part.startsWith('*')) out.push(new TextRun({ ...base, text: part.slice(1, -1), italics: !base.italics }))
    else if (/^\{[a-z0-9]+\}$/.test(part)) out.push(new TextRun({ ...base, text: '[' + cite(part.slice(1, -1)) + ']' }))
    else out.push(new TextRun({ ...base, text: part }))
  }
  return out
}

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
const LETTERS = 'ABCDEFGHIJKLMNOP'
let h1 = 0
let h2 = 0
let tableNo = 0
let figureNo = 0
const tableNumber = {}
const figureNumber = {}

function heading1(text, numbered = true) {
  const label = numbered ? ROMAN[h1++] + '. ' : ''
  h2 = 0
  return new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 200, after: 100 }, keepNext: true,
    children: [new TextRun({ text: label + text, smallCaps: true, size: PT(10) })],
  })
}

function heading2(text) {
  return new Paragraph({
    spacing: { before: 120, after: 60 }, keepNext: true,
    children: [new TextRun({ text: LETTERS[h2++] + '. ' + text, italics: true, size: PT(10) })],
  })
}

function para(text, opts = {}) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: opts.noIndent ? 0 : 245 },
    spacing: { after: 0, line: 240 },
    children: runs(text, { size: PT(10) }),
  })
}

function listItems(items) {
  return items.map((item, i) => new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { left: 360, hanging: 245 },
    tabStops: [{ type: TabStopType.LEFT, position: 360 }],
    spacing: { after: 0 },
    children: [new TextRun({ text: (i + 1) + ')', size: PT(10) }), new TextRun({ children: [new Tab()], size: PT(10) }),
      ...runs(item, { size: PT(10) })],
  }))
}

const thin = { style: BorderStyle.SINGLE, size: 4, color: '000000' }
const BORDERS = { top: thin, bottom: thin, left: thin, right: thin, insideHorizontal: thin, insideVertical: thin }

function table(key) {
  const t = tables[key]
  tableNumber[key] = ++tableNo
  const total = t.widths.reduce((a, b) => a + b, 0)
  if (total !== COLUMN) throw new Error(`table ${key} widths add to ${total}, not ${COLUMN}`)
  const size = header => PT(header ? (t.headerSize || t.size || 8) : (t.size || 8))
  const cell = (text, width, header, first) => new TableCell({
    width: { size: width, type: WidthType.DXA },
    margins: { top: 20, bottom: 20, left: 45, right: 45 },
    verticalAlign: VerticalAlign.CENTER,
    children: String(text).split('\n').map((line) => new Paragraph({
      alignment: header || (t.center && !first) ? AlignmentType.CENTER : AlignmentType.LEFT,
      spacing: { after: 0 },
      children: runs(line, { size: size(header), bold: header }),
    })),
  })
  const rows = [
    new TableRow({ tableHeader: true, children: t.header.map((h, i) => cell(h, t.widths[i], true, i === 0)) }),
    ...t.rows.map((row) => new TableRow({ cantSplit: true, children: row.map((c, i) => cell(c, t.widths[i], false, i === 0)) })),
  ]
  const out = [
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 160, after: 80 }, keepNext: true,
      children: [new TextRun({ text: 'TABLE ' + ROMAN[tableNo - 1] + '.  ', size: PT(8), smallCaps: true }),
        ...runs(t.caption, { size: PT(8), smallCaps: true })],
    }),
    new Table({ width: { size: COLUMN, type: WidthType.DXA }, columnWidths: t.widths, borders: BORDERS, rows }),
  ]
  if (t.note) {
    out.push(new Paragraph({
      alignment: AlignmentType.JUSTIFIED, spacing: { before: 40, after: 120 },
      children: runs(t.note, { size: PT(7), italics: true }),
    }))
  } else {
    out.push(new Paragraph({ spacing: { after: 80 }, children: [] }))
  }
  return out
}

function pngSize(file) {
  const data = fs.readFileSync(file)
  return { data, width: data.readUInt32BE(16), height: data.readUInt32BE(20) }
}

function figure(key) {
  const f = figures[key]
  figureNumber[key] = ++figureNo
  const img = pngSize(path.join(__dirname, f.file))
  const width = Math.floor(COLUMN / 1440 * 96)       // column width in pixels at 96 dpi
  const height = Math.round(width * img.height / img.width)
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, keepNext: true,
      children: [new ImageRun({ type: 'png', data: img.data, transformation: { width, height } })],
    }),
    new Paragraph({
      alignment: AlignmentType.JUSTIFIED, spacing: { after: 140 },
      children: [new TextRun({ text: 'Fig. ' + figureNo + '.  ', size: PT(8) }), ...runs(f.caption, { size: PT(8) })],
    }),
  ]
}

function equation(text, n) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    tabStops: [{ type: TabStopType.CENTER, position: Math.floor(COLUMN / 2) }, { type: TabStopType.RIGHT, position: COLUMN }],
    children: [
      new TextRun({ children: [new Tab()] }),
      new TextRun({ text, font: 'Cambria Math', size: PT(10) }),
      new TextRun({ children: [new Tab(), `(${n})`], size: PT(10) }),
    ],
  })
}

// --- the document ---------------------------------------------------------------------------------------------------
const front = [
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 0, after: 240 },
    children: [new TextRun({ text: title, size: PT(24) })],
  }),
  new Paragraph({
    alignment: AlignmentType.JUSTIFIED, spacing: { after: 80 },
    children: [new TextRun({ text: 'Abstract—', bold: true, italics: true, size: PT(9) }),
      new TextRun({ text: abstract, bold: true, size: PT(9) })],
  }),
  new Paragraph({
    alignment: AlignmentType.JUSTIFIED, spacing: { after: 160 },
    children: [new TextRun({ text: 'Index Terms—', bold: true, italics: true, size: PT(9) }),
      new TextRun({ text: indexTerms, bold: true, size: PT(9) })],
  }),
]

const columns = []
for (const block of body) {
  if (block.h1) columns.push(heading1(block.h1))
  else if (block.h2) columns.push(heading2(block.h2))
  else if (block.p) columns.push(para(block.p, block))
  else if (block.list) columns.push(...listItems(block.list))
  else if (block.table) columns.push(...table(block.table))
  else if (block.figure) columns.push(...figure(block.figure))
  else if (block.eq) columns.push(equation(block.eq, block.n))
}
columns.push(heading1('References', false))
order.forEach((key, i) => {
  columns.push(new Paragraph({
    alignment: AlignmentType.LEFT,
    indent: { left: 400, hanging: 400 },
    tabStops: [{ type: TabStopType.LEFT, position: 400 }],
    spacing: { after: 0 },
    children: [new TextRun({ text: `[${i + 1}]`, size: PT(8) }), new TextRun({ children: [new Tab()], size: PT(8) }),
      ...runs(REFERENCES[key], { size: PT(8) })],
  }))
})

const page = { size: PAGE, margin: MARGIN }
const doc = new Document({
  creator: 'AgentForge authors',
  title,
  styles: { default: { document: { run: { font: FONT, size: PT(10) } } } },
  sections: [
    { properties: { page }, children: front },
    { properties: { type: SectionType.CONTINUOUS, page, column: { count: 2, space: GAP, equalWidth: true } }, children: columns },
  ],
})

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(OUT, buffer)
  console.log(`wrote ${path.relative(process.cwd(), OUT)}: ${order.length} references, ${tableNo} tables, ${figureNo} figures`)
})
