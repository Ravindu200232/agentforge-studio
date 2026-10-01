// Markdown into a printable PDF, with the headless browser the Studio already runs for Mermaid.
//
//   node render-pdf.mjs <input.md> <output.pdf> <title> <baseDir>
//
// `marked` and `puppeteer` are the Studio's own (studio/node_modules), found from STUDIO_ROOT.
// The browser is PDF_BROWSER when the Studio found a system Chrome/Edge, otherwise Puppeteer's.
// Relative links (an SRS's diagrams/*.svg) resolve against <baseDir>.
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const [input, output, title = 'Document', baseDir = path.dirname(input)] = process.argv.slice(2)
const require = createRequire(path.join(process.env.STUDIO_ROOT || process.cwd(), 'package.json'))
const { marked } = require('marked')
const loaded = require('puppeteer')
const puppeteer = loaded.default || loaded

const STYLE = `
  @page { size: A4; }
  * { box-sizing: border-box; }
  body { font: 11pt/1.55 "Segoe UI", Arial, Helvetica, sans-serif; color: #16181d; margin: 0; }
  h1 { font-size: 22pt; margin: 0 0 6pt; }
  h2 { font-size: 15pt; margin: 22pt 0 6pt; padding-bottom: 3pt; border-bottom: 1px solid #d9dce3; break-after: avoid; }
  h3 { font-size: 12.5pt; margin: 14pt 0 4pt; break-after: avoid; }
  h4 { font-size: 11pt; margin: 10pt 0 3pt; break-after: avoid; }
  p, li { orphans: 3; widows: 3; }
  table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9.5pt; }
  th, td { border: 1px solid #d9dce3; padding: 4pt 6pt; text-align: left; vertical-align: top; }
  th { background: #f2f4f7; }
  tr { break-inside: avoid; }
  code { font: 9pt Consolas, "Courier New", monospace; background: #f2f4f7; padding: 0 2pt; border-radius: 2pt; }
  pre { background: #f2f4f7; padding: 6pt 8pt; white-space: pre-wrap; word-break: break-word; }
  pre code { background: none; padding: 0; }
  img { max-width: 100%; height: auto; display: block; margin: 6pt auto; break-inside: avoid; }
  blockquote { margin: 6pt 0; padding: 2pt 10pt; border-left: 3px solid #c9cdd6; color: #4a5060; }
  hr { border: 0; border-top: 1px solid #d9dce3; margin: 14pt 0; }
`

const escape = text => String(text).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const body = marked.parse(fs.readFileSync(input, 'utf8'), { gfm: true })
const base = pathToFileURL(path.resolve(baseDir) + path.sep).href
const page = path.join(path.dirname(path.resolve(output)), 'document.html')
fs.writeFileSync(page, `<!doctype html><html><head><meta charset="utf-8"><base href="${base}">
<title>${escape(title)}</title><style>${STYLE}</style></head><body>${body}</body></html>`, 'utf8')

const browser = await puppeteer.launch({
  headless: true,
  executablePath: process.env.PDF_BROWSER || undefined,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--allow-file-access-from-files'],
})
try {
  const tab = await browser.newPage()
  // A file:// page (not setContent): only a page loaded from disk may load the diagrams beside it.
  await tab.goto(pathToFileURL(page).href, { waitUntil: 'load', timeout: 120_000 })
  await tab.pdf({
    path: output,
    format: 'A4',
    printBackground: true,
    margin: { top: '16mm', bottom: '18mm', left: '15mm', right: '15mm' },
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: `<div style="width:100%;font-size:8px;color:#666;text-align:center;">
      ${escape(title)} — <span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
  })
} finally {
  await browser.close()
}
