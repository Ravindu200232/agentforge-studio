// Every page of the app, photographed whole at the desktop and the mobile size, before the journeys run.
//
// The Studio owns this file: it puts it in place before it looks at the pages, and it is not edited by hand. Each page is
// opened as someone who may open it - a page anyone can open, signed out; a page for a role, signed in through the app's
// own sign-in page as that role's demo account (.agentforge/prototype/demo-accounts.json). A page that needs a record
// (`/orders/[id]`) is opened on the first record its list page (`/orders`) links to. The Studio's screen review looks at
// the pictures, has what is wrong fixed, and photographs only the pages that changed again; the journeys run after that,
// once. A page fails here only for not opening (an error it threw, a server error), never for how it looks.
import fs from 'node:fs'
import path from 'node:path'
import { test as base, expect } from '@playwright/test'

function read(file, fallback) {
  try {
    const text = fs.readFileSync(path.join(process.cwd(), file), 'utf8')
    return JSON.parse(text.charCodeAt(0) === 0xfeff ? text.slice(1) : text)
  } catch {
    return fallback
  }
}

// Pages do not depend on each other: they are shared out over every worker (each signs in once per account).
base.describe.configure({ mode: 'parallel' })

const DYNAMIC = /^\[.+\]$|^:.+$/
const demo = read('.agentforge/prototype/demo-accounts.json', {}) || {}
const accounts = Array.isArray(demo.accounts) ? demo.accounts.filter(row => row && row.email && row.password) : []
const listed = read('e2e/routes.json', null)
const prototype = read('.agentforge/prototype/routes.json', {}) || {}
const seen = new Set()
const rows = (Array.isArray(listed) ? listed : Array.isArray(prototype.routes) ? prototype.routes : [])
  .filter(row => row && typeof row.route === 'string' && row.route.startsWith('/') && !seen.has(row.route) && seen.add(row.route))
const SIGN_IN = demo.sign_in || rows.find(row => /log-?in|sign-?in/i.test(row.route))?.route || '/login'

const word = value => String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '')
const isProtected = row => row.auth === true || (Array.isArray(row.roles) && row.roles.length > 0)
const opens = (account, route) => (account.can_open || account.canOpen || [])
  .some(item => (typeof item === 'string' ? item : item && item.route) === route)

/** The demo account a page is opened as: none for a page anyone can open, else one that may open it. */
function accountFor(row) {
  if (!isProtected(row)) return null
  const roles = (row.roles || []).map(word)
  return accounts.find(account => opens(account, row.route))
    || accounts.find(account => roles.includes(word(account.role_key)) || roles.includes(word(account.role)))
    || accounts[0]
    || undefined
}

// One sign-in per demo account in each worker, through the app's own sign-in page; a page then opens with that session.
const sessions = new Map()

async function signIn(browser, account, baseURL) {
  const context = await browser.newContext({ baseURL })
  const page = await context.newPage()
  try {
    await page.goto(SIGN_IN, { waitUntil: 'domcontentloaded' })
    const email = page.locator('input[type="email"], input[name*="email" i], input[id*="email" i], '
      + 'input[autocomplete="username"], input[autocomplete="email"], input[name*="user" i], input[id*="user" i]').first()
    await email.waitFor({ state: 'visible', timeout: 20_000 })
    await email.fill(account.email)
    const password = page.locator('input[type="password"]').first()
    await password.fill(account.password)
    const form = password.locator('xpath=ancestor::form[1]')
    const submit = (await form.count())
      ? form.locator('button[type="submit"], input[type="submit"], button:not([type])').first()
      : page.locator('button[type="submit"], input[type="submit"]').first()
    const before = new URL(page.url()).pathname
    if (await submit.count()) await submit.click()
    else await password.press('Enter')
    await page.waitForURL(url => url.pathname !== before, { timeout: 30_000 })
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {})
    return { state: await context.storageState() }
  } catch (error) {
    return { problem: `could not sign in as ${account.role || account.email} on ${SIGN_IN}: ${String(error.message || error).split('\n')[0]}` }
  } finally {
    await context.close().catch(() => {})
  }
}

const test = base.extend({
  account: [null, { option: true }],
  signedIn: async ({ browser, account, baseURL }, use) => {
    if (!account) return use({})
    const key = account.email
    if (!sessions.has(key)) sessions.set(key, await signIn(browser, account, baseURL))
    await use(sessions.get(key))
  },
  storageState: async ({ signedIn }, use) => use(signedIn.state),
})

/** Where a page that needs a record is opened: the first record its list page links to, or '' when it links to none. */
async function sample(page, row) {
  const parts = row.route.split('/').filter(Boolean)
  const at = parts.findIndex(part => DYNAMIC.test(part))
  const prefix = parts.slice(0, at)
  const rest = parts.slice(at + 1)
  if (!prefix.length || rest.some(part => DYNAMIC.test(part))) return ''
  // `/items/new` lives beside `/items/[id]`: a link to it is not a record.
  const siblings = new Set(rows.map(other => other.route.split('/').filter(Boolean))
    .filter(bits => bits.length > at && bits.slice(0, at).join('/') === prefix.join('/') && !DYNAMIC.test(bits[at]))
    .map(bits => bits[at]))
  await page.goto('/' + prefix.join('/'), { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {})
  const hrefs = await page.$$eval('a[href]', links => links.map(link => link.getAttribute('href')))
  for (const href of hrefs) {
    let bits
    try {
      bits = new URL(href, page.url()).pathname.split('/').filter(Boolean)
    } catch {
      continue
    }
    if (bits.length < at + 1 || bits.slice(0, at).join('/') !== prefix.join('/')) continue
    const value = bits[at]
    if (value && !siblings.has(value)) return '/' + [...prefix, value, ...rest].join('/')
  }
  return ''
}

const groups = new Map()
for (const row of rows) {
  const account = accountFor(row)
  const key = account === null ? 'signed out' : account ? `as ${account.role || account.email}` : 'as nobody'
  if (!groups.has(key)) groups.set(key, { account, rows: [] })
  groups.get(key).rows.push(row)
}

for (const [label, group] of groups) {
  test.describe(`@pages ${label}`, () => {
    test.use({ account: group.account || null })
    for (const row of group.rows) {
      test(`${row.name || row.route} (${row.route})`, async ({ page, signedIn }, testInfo) => {
        test.skip(group.account === undefined, 'there is no demo account to sign in with')
        test.skip(Boolean(signedIn.problem), signedIn.problem)
        const problems = []
        page.on('pageerror', error => problems.push(`page error: ${error.message}`))
        page.on('response', response => {
          if (response.status() >= 500) problems.push(`HTTP ${response.status()} ${response.url()}`)
        })
        const url = row.route.split('/').some(part => DYNAMIC.test(part)) ? await sample(page, row) : row.route
        test.skip(!url, 'no record to open it on: its list page links to none')
        const response = await page.goto(url, { waitUntil: 'domcontentloaded' })
        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})
        await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {})
        await page.waitForTimeout(300)
        const landed = new URL(page.url()).pathname
        testInfo.annotations.push({ type: 'opened', description: `${url} ${label}${landed !== url ? `, landed on ${landed}` : ''}` })
        const file = testInfo.outputPath('page.png')
        // One pixel per CSS pixel: a phone's 2.6x screen made a page 1082 x 10973, too tall for a model to read.
        await page.screenshot({ path: file, fullPage: true, animations: 'disabled', scale: 'css' })
        await testInfo.attach('screenshot', { path: file, contentType: 'image/png' })
        expect(response?.status() ?? 200, `${url} answered`).toBeLessThan(500)
        expect(problems, 'the page reported problems').toEqual([])
      })
    }
  })
}
