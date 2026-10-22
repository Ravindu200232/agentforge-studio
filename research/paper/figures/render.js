// Renders the figure HTML files to PNG at 4x scale (about 570 dpi at single-column width).
//   NODE_PATH=$(npm root -g) node research/paper/figures/render.js
const path = require('path')
const { chromium } = require('playwright')

const FIGURES = ['fig1-architecture', 'fig2-build-test']

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 500, height: 400 }, deviceScaleFactor: 4 })
  for (const name of FIGURES) {
    await page.goto('file://' + path.join(__dirname, name + '.html'))
    const body = await page.$('body')
    await body.screenshot({ path: path.join(__dirname, name + '.png') })
    console.log('wrote', name + '.png')
  }
  await browser.close()
})()
