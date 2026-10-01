'use client'

import { cloneElement } from 'react'
import { api } from '@/lib/api'
import { Badge, Empty, Panel, Table, Tag, TD, TH, TR } from '../ui'
import { unitTestStatus } from '@/lib/test-counts'

const TOOLS = [
  {
    name: 'Vitest',
    svg: (
      <svg viewBox="0 0 24 24" fill="#00FF74"><path d="M11.545 23.3a.613.613 0 0 1-.895.197L.252 15.936A.61.61 0 0 1 0 15.439V6.325c0-.502.569-.792.975-.497l6.358 4.624c.594.433 1.432.25 1.793-.39L14.393.7a.62.62 0 0 1 .535-.314h8.455a.613.613 0 0 1 .537.916z" /></svg>
    ),
  },
  {
    name: 'Playwright',
    svg: (
      <svg viewBox="0 0 400 400">
        <path d="M136.444 221.556C123.558 225.213 115.104 231.625 109.535 238.032C114.869 233.364 122.014 229.08 131.652 226.348C141.51 223.554 149.92 223.574 156.869 224.915V219.481C150.941 218.939 144.145 219.371 136.444 221.556ZM108.946 175.876L61.0895 188.484C61.0895 188.484 61.9617 189.716 63.5767 191.36L104.153 180.668C104.153 180.668 103.578 188.077 98.5847 194.705C108.03 187.559 108.946 175.876 108.946 175.876ZM149.005 288.347C81.6582 306.486 46.0272 228.438 35.2396 187.928C30.2556 169.229 28.0799 155.067 27.5 145.928C27.4377 144.979 27.4665 144.179 27.5336 143.446C24.04 143.657 22.3674 145.473 22.7077 150.721C23.2876 159.855 25.4633 174.016 30.4473 192.721C41.2301 233.225 76.8659 311.273 144.213 293.134C158.872 289.185 169.885 281.992 178.152 272.81C170.532 279.692 160.995 285.112 149.005 288.347ZM161.661 128.11V132.903H188.077C187.535 131.206 186.989 129.677 186.447 128.11H161.661Z" fill="#2D4552" />
        <path d="M193.981 167.584C205.861 170.958 212.144 179.287 215.465 186.658L228.711 190.42C228.711 190.42 226.904 164.623 203.57 157.995C181.741 151.793 168.308 170.124 166.674 172.496C173.024 167.972 182.297 164.268 193.981 167.584ZM299.422 186.777C277.573 180.547 264.145 198.916 262.535 201.255C268.89 196.736 278.158 193.031 289.837 196.362C301.698 199.741 307.976 208.06 311.307 215.436L324.572 219.212C324.572 219.212 322.736 193.41 299.422 186.777ZM286.262 254.795L176.072 223.99C176.072 223.99 177.265 230.038 181.842 237.869L274.617 263.805C282.255 259.386 286.262 254.795 286.262 254.795ZM209.867 321.102C122.618 297.71 133.166 186.543 147.284 133.865C153.097 112.156 159.073 96.0203 164.029 85.204C161.072 84.5953 158.623 86.1529 156.203 91.0746C150.941 101.747 144.212 119.124 137.7 143.45C123.586 196.127 113.038 307.29 200.283 330.682C241.406 341.699 273.442 324.955 297.323 298.659C274.655 319.19 245.714 330.701 209.867 321.102Z" fill="#2D4552" />
        <path d="M161.661 262.296V239.863L99.3324 257.537C99.3324 257.537 103.938 230.777 136.444 221.556C146.302 218.762 154.713 218.781 161.661 220.123V128.11H192.869C189.471 117.61 186.184 109.526 183.423 103.909C178.856 94.612 174.174 100.775 163.545 109.665C156.059 115.919 137.139 129.261 108.668 136.933C80.1966 144.61 57.179 142.574 47.5752 140.911C33.9601 138.562 26.8387 135.572 27.5049 145.928C28.0847 155.062 30.2605 169.224 35.2445 187.928C46.0272 228.433 81.663 306.481 149.01 288.342C166.602 283.602 179.019 274.233 187.626 262.291H161.661V262.296ZM61.0848 188.484L108.946 175.876C108.946 175.876 107.551 194.288 89.6087 199.018C71.6614 203.743 61.0848 188.484 61.0848 188.484Z" fill="#E2574C" />
        <path d="M341.786 129.174C329.345 131.355 299.498 134.072 262.612 124.185C225.716 114.304 201.236 97.0224 191.537 88.8994C177.788 77.3834 171.74 69.3802 165.788 81.4857C160.526 92.163 153.797 109.54 147.284 133.866C133.171 186.543 122.623 297.706 209.867 321.098C297.093 344.47 343.53 242.92 357.644 190.238C364.157 165.917 367.013 147.5 367.799 135.625C368.695 122.173 359.455 126.078 341.786 129.174ZM166.497 172.756C166.497 172.756 180.246 151.372 203.565 158C226.899 164.628 228.706 190.425 228.706 190.425L166.497 172.756ZM223.42 268.713C182.403 256.698 176.077 223.99 176.077 223.99L286.262 254.796C286.262 254.791 264.021 280.578 223.42 268.713ZM262.377 201.495C262.377 201.495 276.107 180.126 299.422 186.773C322.736 193.411 324.572 219.208 324.572 219.208L262.377 201.495Z" fill="#2EAD33" />
        <path d="M139.88 246.04L99.3324 257.532C99.3324 257.532 103.737 232.44 133.607 222.496L110.647 136.33L108.663 136.933C80.1918 144.611 57.1742 142.574 47.5704 140.911C33.9554 138.563 26.834 135.572 27.5001 145.929C28.08 155.063 30.2557 169.224 35.2397 187.929C46.0225 228.433 81.6583 306.481 149.005 288.342L150.989 287.719L139.88 246.04ZM61.0848 188.485L108.946 175.876C108.946 175.876 107.551 194.288 89.6087 199.018C71.6615 203.743 61.0848 188.485 61.0848 188.485Z" fill="#D65348" />
        <path d="M225.27 269.163L223.415 268.712C182.398 256.698 176.072 223.99 176.072 223.99L232.89 239.872L262.971 124.281L262.607 124.185C225.711 114.304 201.232 97.0224 191.532 88.8994C177.783 77.3834 171.735 69.3802 165.783 81.4857C160.526 92.163 153.797 109.54 147.284 133.866C133.171 186.543 122.623 297.706 209.867 321.097L211.655 321.5L225.27 269.163ZM166.497 172.756C166.497 172.756 180.246 151.372 203.565 158C226.899 164.628 228.706 190.425 228.706 190.425L166.497 172.756Z" fill="#1D8D22" />
        <path d="M141.946 245.451L131.072 248.537C133.641 263.019 138.169 276.917 145.276 289.195C146.513 288.922 147.74 288.687 149 288.342C152.302 287.451 155.364 286.348 158.312 285.145C150.371 273.361 145.118 259.789 141.946 245.451ZM137.7 143.451C132.112 164.307 127.113 194.326 128.489 224.436C130.952 223.367 133.554 222.371 136.444 221.551L138.457 221.101C136.003 188.939 141.308 156.165 147.284 133.866C148.799 128.225 150.318 122.978 151.832 118.085C149.393 119.637 146.767 121.228 143.776 122.867C141.759 129.093 139.722 135.898 137.7 143.451Z" fill="#C04B41" />
      </svg>
    ),
  },
  {
    name: 'OWASP ZAP',
    bg: '#00549E',
    svg: (
      <svg viewBox="0 0 77.58 77.61" fill="#fff">
        <path d="M49.48 21.64a3.46 3.46 0 0 1 .44 3 3.38 3.38 0 0 1-2.16 2.14l-1.17.38 10.74 13.56a3.39 3.39 0 0 1-1.83 5.41l-2 .5L68 65A37.78 37.78 0 0 0 39.85 2c-1.34 0-2.66.07-4 .2zM23.33 48.26a3.4 3.4 0 0 1 .45-6.09L25 41.7l-13.81-10a3.4 3.4 0 0 1 .62-5.86l.2-.09-5.47-3.84a37.79 37.79 0 0 0 55.32 48.6z" />
        <path d="M67.84 69.48L49 45.59a.55.55 0 0 1 .28-.87l5.55-1.36a.58.58 0 0 0 .23-.13.48.48 0 0 0 .09-.11.62.62 0 0 0 .08-.24.58.58 0 0 0 0-.26.54.54 0 0 0-.07-.13L42.29 26.37a.75.75 0 0 1-.07-.12.55.55 0 0 1 .31-.74l4.35-1.4a.54.54 0 0 0 .26-.83L30.92.22a.5.5 0 0 0-.61-.22L.32 13a.55.55 0 0 0-.1.94l16.72 11.88a.52.52 0 0 1 .22.49.45.45 0 0 1-.09.26.48.48 0 0 1-.09.11l-.13.08-3.93 1.72a.55.55 0 0 0-.29.31v.13a.59.59 0 0 0 .22.5l8.62 6.22 8.61 6.21a.55.55 0 0 1 0 .87.57.57 0 0 1-.13.08l-5.11 2a.55.55 0 0 0-.28.75.56.56 0 0 0 .21.22l42.43 24.5a.53.53 0 0 0 .64-.79z" />
      </svg>
    ),
  },
  {
    name: 'Lighthouse',
    svg: (
      <svg viewBox="0 0 24 24" fill="#F44B21"><path d="M12 0l5.5 3.5v5H20v3h-2.25l2 12.5H4.25l2-12.5H4v-3h2.5V3.53zm2.94 13.25l-6.22 2.26L8 20.04l7.5-2.75zM12 3.56L9.5 5.17V8.5h5V5.15Z" /></svg>
    ),
  },
]

/** The real logos of the tools this evidence is drawn from. */
function ToolLogos() {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {TOOLS.map(t => (
        <span key={t.name} className="inline-flex items-center gap-1.5 rounded-none border border-line bg-panel px-2.5 py-1.5">
          <span className="grid size-5 shrink-0 place-items-center overflow-hidden rounded-none"
                style={{ background: t.bg || 'transparent' }}>
            {cloneElement(t.svg, { className: 'size-4' })}
          </span>
          <span className="text-[11px] font-semibold text-ink">{t.name}</span>
        </span>
      ))}
    </div>
  )
}

const list = value => Array.isArray(value) ? value : []
const okState = value => /^(pass|passed|met|ok|success|complete|recorded|true)$/i.test(String(value))
const badState = value => /^(fail|failed|error|unmet|false)$/i.test(String(value))
const tone = value => okState(value) ? 'ok' : badState(value) ? 'bad' : 'warn'
const when = value => { const d = value ? new Date(value) : null; return d && !Number.isNaN(+d) ? d.toLocaleString() : '' }
const shortFile = path => String(path || '').replace(/\\/g, '/').split('/').pop()

const status = value => typeof value === 'object' && value !== null ? value.status || 'recorded' : value || 'not run'

function Result({ title, value, detail }) {
  const state = status(value)
  return <section className="rounded-none border border-line bg-panel p-4">
    <div className="flex items-center justify-between gap-3"><h3 className="font-semibold text-ink">{title}</h3>
      <Badge tone={/pass|complete|success/i.test(state) ? 'ok' : /fail|error/i.test(state) ? 'bad' : 'warn'}>{state}</Badge></div>
    {detail && <p className="mt-2 text-xs text-muted">{detail}</p>}
    {value && typeof value === 'object' && <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-all rounded-none bg-panel2 p-3 text-[11px] text-muted">{JSON.stringify(value, null, 2)}</pre>}
  </section>
}

function Section({ title, hint, right, children }) {
  return <section className="space-y-3">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <div><h3 className="text-[13px] font-bold tracking-wide text-ink">{title}</h3>
        {hint && <p className="mt-0.5 text-[11px] text-muted">{hint}</p>}</div>
      {right}
    </div>
    {children}
  </section>
}

function Tile({ label, value, sub, bad }) {
  return <div className="rounded-none border border-line bg-panel p-4">
    <p className="text-[10.5px] font-semibold uppercase tracking-[.12em] text-muted">{label}</p>
    <p className={`mt-1 font-display text-[22px] font-bold ${bad ? 'text-rose-400' : 'text-ink'}`}>{value}</p>
    {sub && <p className="mt-0.5 text-[11px] text-muted">{sub}</p>}
  </div>
}

/** A row list that opens to show what is inside it. */
function Fold({ head, right, children }) {
  return <details className="group overflow-hidden rounded-none border border-line bg-panel">
    <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-2.5 text-[12px] hover:bg-ink/[.03]">
      <span className="text-muted transition-transform group-open:rotate-90">›</span>
      <span className="min-w-0 flex-1 truncate font-mono font-semibold text-ink">{head}</span>{right}
    </summary>
    <div className="border-t border-line bg-panel2/40">{children}</div>
  </details>
}

function Gaps({ gaps }) {
  if (!gaps.length) return null
  return <Section title="Not proven — recorded gaps"
                  hint="Things the build could not or did not verify, with the reason it gave and what you answered when it asked. None of these is counted as a pass.">
    <div className="grid gap-2.5 md:grid-cols-2">
      {gaps.map((g, i) => <div key={i} className="rounded-none border border-amber-500/25 bg-amber-500/5 p-3.5">
        <div className="flex flex-wrap items-center gap-2"><Tag tone={/known|out_of_scope/.test(g.status) ? 'mute' : 'warn'}>{String(g.status || 'gap').replace(/_/g, ' ')}</Tag>
          <b className="text-[12px] text-ink">{g.item}</b></div>
        <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">{g.reason}</p>
        {g.asked && <p className="mt-2 border-t border-amber-500/20 pt-2 text-[11.5px] leading-relaxed text-muted">
          <span className="font-semibold text-ink">Asked:</span> {g.asked}
          {g.answer && <><br /><span className="font-semibold text-ink">Answer:</span> {g.answer}</>}</p>}
      </div>)}
    </div>
  </Section>
}

function Commands({ commands }) {
  if (!commands.length) return null
  return <Section title="Commands and exit codes" hint="Every command the build ran to prove its work, exactly as it recorded them.">
    <Panel className="overflow-hidden"><Table>
      <thead><TR><TH>Command</TH><TH>Exit</TH><TH>What it showed</TH></TR></thead>
      <tbody>{commands.map((c, i) => <TR key={i}>
        <TD className="max-w-[340px] break-all font-mono text-[11px] text-ink">{c.command}</TD>
        <TD><Badge tone={c.exit_code === 0 ? 'ok' : 'bad'}>exit {String(c.exit_code)}</Badge></TD>
        <TD className="text-[11.5px] text-muted">{c.note}</TD>
      </TR>)}</tbody>
    </Table></Panel>
  </Section>
}

function UnitTests({ vitest }) {
  const suites = list(vitest?.testResults)
  if (!vitest || !suites.length) return null
  const unit = unitTestStatus(vitest)
  return <Section title="Unit & integration tests (Vitest)"
                  hint={`${unit.passed}/${unit.total} test cases passed across ${unit.files} files${vitest.startTime ? ' · ' + when(vitest.startTime) : ''}`}
                  right={<Badge tone={vitest.success ? 'ok' : 'bad'}>{vitest.success ? 'all passed' : `${unit.failed} failed`}</Badge>}>
    <div className="space-y-2">{suites.map((s, i) => {
      const cases = list(s.assertionResults)
      const passed = cases.filter(c => c.status === 'passed').length
      return <Fold key={i} head={shortFile(s.name)} right={<Badge tone={passed === cases.length ? 'ok' : 'bad'}>{passed}/{cases.length}</Badge>}>
        <ul className="divide-y divide-line">{cases.map((c, j) => <li key={j} className="flex items-center gap-3 px-4 py-2 text-[11.5px]">
          <span className="min-w-0 flex-1 text-muted">{[...list(c.ancestorTitles), c.title].filter(Boolean).join(' › ')}</span>
          {c.duration != null && <span className="font-mono text-[10px] text-muted2">{Math.round(c.duration)}ms</span>}
          <Badge tone={tone(c.status)}>{c.status}</Badge>
        </li>)}</ul>
      </Fold>
    })}</div>
  </Section>
}

const UNIT_KINDS = { page: 'Pages', route: 'Routes', component: 'Components', middleware: 'Middleware', module: 'Modules', special: 'Layouts and framework files (optional)' }

/** Every page, route and component, and the unit tests that use it (`npm run qa:inventory`). */
function UnitInventory({ inventory, coverage }) {
  const units = list(inventory?.units)
  if (!inventory || !units.length) return null
  const required = units.filter(u => !u.optional)
  const open = required.filter(u => u.status !== 'covered')
  const files = list(coverage?.files)
  return <Section title="Unit-test inventory — every page, route and component"
                  hint={`${required.length - open.length}/${required.length} have a unit test that imports and uses them${inventory.generated_at ? ' · ' + when(inventory.generated_at) : ''}`}
                  right={<Badge tone={open.length ? 'bad' : 'ok'}>{open.length ? `${open.length} untested` : 'all tested'}</Badge>}>
    <div className="space-y-2">{Object.keys(UNIT_KINDS).filter(kind => units.some(u => u.kind === kind)).map(kind => {
      const rows = units.filter(u => u.kind === kind)
      const covered = rows.filter(u => u.status === 'covered').length
      return <Fold key={kind} head={UNIT_KINDS[kind]} right={<Badge tone={covered === rows.length ? 'ok' : 'warn'}>{covered}/{rows.length}</Badge>}>
        <ul className="divide-y divide-line">{rows.map((u, i) => <li key={i} className="flex flex-wrap items-center gap-3 px-4 py-2 text-[11.5px]">
          <span className="min-w-0 flex-1"><span className="font-mono text-ink">{u.file}</span>
            {u.route && <span className="ml-2 text-muted2">{u.route}</span>}
            {list(u.missing).length > 0 && <span className="ml-2 text-rose-400">needs a test for: {list(u.missing).join(', ')}</span>}</span>
          <span className="font-mono text-[10px] text-muted2">{list(u.tests).map(shortFile).join(', ')}</span>
          <Badge tone={u.status === 'covered' ? 'ok' : u.status === 'partial' ? 'warn' : 'bad'}>{u.status === 'uncovered' ? 'untested' : u.status}</Badge>
        </li>)}</ul>
      </Fold>
    })}
      {coverage && files.length > 0 && <Fold head={`Measured coverage — ${coverage.lines}% of lines`}
             right={<span className="font-mono text-[10px] text-muted2">{[coverage.statements != null && `statements ${coverage.statements}%`, coverage.functions != null && `functions ${coverage.functions}%`, coverage.branches != null && `branches ${coverage.branches}%`].filter(Boolean).join(' · ')}</span>}>
        <ul className="divide-y divide-line">{files.map((f, i) => <li key={i} className="flex items-center gap-3 px-4 py-2 text-[11.5px]">
          <span className="min-w-0 flex-1 truncate font-mono text-muted">{f.file}</span>
          <Badge tone={f.lines == null ? 'mute' : f.lines >= 80 ? 'ok' : f.lines > 0 ? 'warn' : 'bad'}>{f.lines == null ? 'n/a' : `${f.lines}%`}</Badge>
        </li>)}</ul>
      </Fold>}
    </div>
  </Section>
}

function BrowserTests({ runs }) {
  const tests = list(runs?.tests)
  if (!runs || !tests.length) return null
  const groups = new Map()
  for (const t of tests) {
    const key = `${t.file}||${t.project}`
    if (!groups.has(key)) groups.set(key, { file: t.file, project: t.project, rows: [] })
    groups.get(key).rows.push(t)
  }
  const hint = `${runs.passed}/${runs.total} passed${runs.failed ? ` · ${runs.failed} failed` : ''}${runs.flaky ? ` · ${runs.flaky} flaky` : ''}${runs.skipped ? ` · ${runs.skipped} skipped` : ''}${runs.seconds ? ` · ${Math.round(runs.seconds)}s` : ''} · from ${runs.source}${runs.at ? ' · ' + when(runs.at) : ''}`
  return <Section title="Browser tests (Playwright — journeys, accessibility, visual)" hint={hint}
                  right={<Badge tone={runs.failed ? 'bad' : runs.passed === runs.total ? 'ok' : 'warn'}>{runs.failed ? `${runs.failed} failed` : runs.passed === runs.total ? 'all passed' : 'partial'}</Badge>}>
    <div className="space-y-2">{[...groups.values()].map((g, i) => {
      const passed = g.rows.filter(r => r.status === 'passed').length
      return <Fold key={i} head={`${shortFile(g.file)}${g.project ? ' · ' + g.project : ''}`}
                   right={<Badge tone={passed === g.rows.length ? 'ok' : 'warn'}>{passed}/{g.rows.length}</Badge>}>
        <ul className="divide-y divide-line">{g.rows.map((t, j) => <li key={j} className="flex items-center gap-3 px-4 py-2 text-[11.5px]">
          <span className="min-w-0 flex-1 text-muted">{t.suite ? `${t.suite} › ` : ''}{t.title}</span>
          <Badge tone={tone(t.status)}>{t.status}</Badge>
        </li>)}</ul>
      </Fold>
    })}</div>
  </Section>
}

function RouteProbe({ probe }) {
  const rows = list(probe?.results)
  if (!rows.length) return null
  const matched = rows.filter(r => r.matched).length
  return <Section title="Route checks" hint={`${matched}/${rows.length} routes answered as specified${probe.measured_at ? ' · ' + when(probe.measured_at) : ''}`}
                  right={<Badge tone={matched === rows.length ? 'ok' : 'bad'}>{matched === rows.length ? 'all matched' : 'mismatch'}</Badge>}>
    <Panel className="overflow-hidden"><Table>
      <thead><TR><TH>Route</TH><TH>Expected</TH><TH>Observed</TH><TH>Result</TH></TR></thead>
      <tbody>{rows.map((r, i) => <TR key={i}>
        <TD className="font-mono text-[11.5px] text-ink">{r.route}</TD>
        <TD className="text-[11.5px] text-muted">{r.expected}</TD>
        <TD className="text-[11.5px] text-muted">{r.observed}</TD>
        <TD><Badge tone={r.matched ? 'ok' : 'bad'}>{r.matched ? 'matched' : 'mismatch'}</Badge></TD>
      </TR>)}</tbody>
    </Table></Panel>
  </Section>
}

function Lighthouse({ data }) {
  const results = list(data?.results)
  if (!results.length) return null
  const min = data.thresholds || {}
  return <Section title="Lighthouse" hint={`${results.length} route${results.length === 1 ? '' : 's'} audited${data.audited_at ? ' · ' + when(data.audited_at) : ''}`}>
    <div className="space-y-3">{results.map((r, i) => <Panel key={i} className="p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2"><code className="text-[12px] font-semibold text-ink">{r.route}</code>
        <span className="break-all font-mono text-[10px] text-muted2">{r.url}</span></div>
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(130px,1fr))]">
        {Object.entries(r.scores || {}).map(([k, v]) => {
          const floor = min[k]?.min != null ? Math.round(min[k].min * 100) : null
          return <div key={k} className="rounded-none border border-line bg-panel2/50 p-3">
            <p className="text-[10.5px] uppercase tracking-[.1em] text-muted">{k.replace(/-/g, ' ')}</p>
            <p className={`font-display text-[22px] font-bold ${v >= 90 ? 'text-ink' : v >= 50 ? 'text-amber-400' : 'text-rose-400'}`}>{v}</p>
            {floor != null && <p className="text-[10px] text-muted2">floor {floor} · {min[k].level}</p>}
          </div>
        })}
      </div>
      {Object.keys(r.metrics || {}).length > 0 && <p className="mt-3 text-[11.5px] text-muted">
        {Object.entries(r.metrics).map(([k, v]) => `${k.replace(/_/g, ' ')} ${String(v).replace(/\s+/g, ' ')}`).join(' · ')}</p>}
    </Panel>)}</div>
  </Section>
}

function SecurityScan({ scan }) {
  if (!scan) return null
  const zap = scan.engine === 'zap'
  const rows = [...list(scan.failing), ...list(scan.warnings)]
  return <Section title="Security scan" hint={`${scan.target || ''}${scan.date ? ' · ' + when(scan.date) : ''}`}
                  right={<div className="flex gap-2"><Badge tone={zap ? 'ok' : 'warn'}>{zap ? 'OWASP ZAP' : 'built-in baseline (not ZAP)'}</Badge>
                    <Badge tone={scan.status === 'passed' ? 'ok' : scan.status === 'failed' ? 'bad' : 'warn'}>{scan.status}</Badge></div>}>
    <Panel className="space-y-3 p-4">
      <p className="text-[11.5px] text-muted">{scan.reason || scan.note}</p>
      <div className="flex flex-wrap gap-2 text-[11px] text-muted">
        {Object.entries(scan.counts || {}).map(([k, v]) => <Badge key={k} tone={k === 'high' && v ? 'bad' : 'mute'}>{v} {k}</Badge>)}
        {scan.urls_checked != null && <Badge tone="mute">{scan.urls_checked} pages · {scan.requests} requests</Badge>}
        {scan.rules && <Badge tone="mute">rules: {scan.rules}</Badge>}
      </div>
      {rows.length > 0 && <ul className="space-y-1.5">{rows.map((a, i) => <li key={i} className="flex flex-wrap items-baseline gap-2 text-[11.5px]">
        <Badge tone={a.action === 'FAIL' ? 'bad' : 'warn'}>{a.action}</Badge>
        <span className="font-mono text-[10.5px] text-muted2">{a.id}</span>
        <span className="text-ink">{a.name}</span><span className="text-muted">{a.risk} · {a.count}×</span></li>)}</ul>}
    </Panel>
  </Section>
}

function Requirements({ build, scope }) {
  const reqs = list(build?.requirements)
  if (!reqs.length) return null
  const text = Object.fromEntries(list(scope).map(r => [r.id, r.description]))
  const met = reqs.filter(r => r.status === 'met').length
  return <Section title="Requirements" hint={`${met}/${reqs.length} met — each with the evidence the build cites`}
                  right={<Badge tone={met === reqs.length ? 'ok' : 'warn'}>{met}/{reqs.length} met</Badge>}>
    <Panel className="overflow-hidden"><Table>
      <thead><TR><TH>ID</TH><TH>Requirement</TH><TH>Status</TH><TH>Evidence</TH></TR></thead>
      <tbody>{reqs.map((r, i) => <TR key={i}>
        <TD className="whitespace-nowrap font-mono text-[11.5px] text-ink">{r.id}</TD>
        <TD className="max-w-[320px] text-[11.5px] text-ink">{text[r.id] || ''}</TD>
        <TD><Badge tone={r.status === 'met' ? 'ok' : 'warn'}>{String(r.status || '').replace(/_/g, ' ')}</Badge></TD>
        <TD className="text-[11.5px] text-muted">{r.evidence}</TD>
      </TR>)}</tbody>
    </Table></Panel>
  </Section>
}

function Checked({ build }) {
  const verified = list(build?.verified)
  const routes = list(build?.routes)
  const collections = list(build?.collections)
  const notes = list(build?.notes)
  if (!verified.length && !routes.length && !collections.length && !notes.length) return null
  return <>
    {routes.length > 0 && <Section title="Routes and endpoints" hint="What the build says each one does, and how it measured it.">
      <Panel className="overflow-hidden"><Table>
        <thead><TR><TH>Route</TH><TH>Status</TH><TH>How it was verified</TH></TR></thead>
        <tbody>{routes.map((r, i) => <TR key={i}>
          <TD className="whitespace-nowrap font-mono text-[11.5px] text-ink">{r.method ? `${r.method} ` : ''}{r.route}</TD>
          <TD>{r.status_when_measured != null ? <Badge tone="mute">{r.status_when_measured}</Badge> : null}{' '}<Badge tone={r.verified ? 'ok' : 'warn'}>{r.verified ? 'verified' : 'unverified'}</Badge></TD>
          <TD className="text-[11.5px] text-muted">{r.how}</TD>
        </TR>)}</tbody>
      </Table></Panel>
    </Section>}
    {verified.length > 0 && <Section title="Behaviours verified" hint="Only what the build reports it actually loaded or exercised.">
      <ul className="grid gap-1.5 md:grid-cols-2">{verified.map((v, i) => <li key={i} className="flex gap-2 rounded-none border border-line bg-panel px-3 py-2 text-[11.5px] text-muted">
        <span className="text-ink">✓</span><span>{v}</span></li>)}</ul>
    </Section>}
    {collections.length > 0 && <Section title="Data">
      <div className="grid gap-2.5 md:grid-cols-2">{collections.map((c, i) => <Panel key={i} className="p-3.5">
        <b className="font-mono text-[12px] text-ink">{c.name}</b>
        <p className="mt-1 font-mono text-[10.5px] text-muted2">{list(c.fields).join(' · ')}</p>
        {c.verified && <p className="mt-1.5 text-[11.5px] text-muted">{c.verified}</p>}
      </Panel>)}</div>
    </Section>}
    {notes.length > 0 && <Section title="Build notes">
      <ul className="space-y-1.5">{notes.map((n, i) => <li key={i} className="rounded-none border border-line bg-panel px-3 py-2 text-[11.5px] text-muted">{n}</li>)}</ul>
    </Section>}
  </>
}

/** Everything the build proved (and what it did not), in full; then the Testing stage's own runner report. */
export default function Verification({ qa }) {
  const raw = qa?.runnerReport || qa
  const build = raw?.build
  const legacy = raw?.unit || raw?.journeys || raw?.coverage
  const has = build || legacy || raw?.vitest || raw?.playwright || raw?.browserRuns || raw?.performance || raw?.zapSummary || raw?.unitInventory
  if (!has) return <Empty>No scaffold test evidence has been saved yet.</Empty>

  const shots = list(raw.screenshots)
  const commands = list(build?.commands)
  const gaps = list(build?.gaps)
  const unit = raw.vitest ? unitTestStatus(raw.vitest) : null
  const runs = raw.browserRuns
  const probe = raw.routeProbe
  const lh = list(raw.lighthouse?.results)
  const reqs = list(build?.requirements)
  const met = reqs.filter(r => r.status === 'met').length
  const matched = list(probe?.results).filter(r => r.matched).length
  const units = list(raw.unitInventory?.units).filter(u => !u.optional)
  const unitsTested = units.filter(u => u.status === 'covered').length

  return <div className="space-y-7">
    <ToolLogos />
    <Panel className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">{build?.app ? `${build.app} — build verification` : 'Build verification'}</h2>
          <p className="mt-1 max-w-[760px] text-xs text-muted">{raw.provenance || 'Only saved runner results count. Unavailable or skipped checks remain visible, not passed.'}</p>
          {build && <p className="mt-1 font-mono text-[10.5px] text-muted2">{[build.stack, (raw.recordedAt || build.built_at) && `recorded ${when(raw.recordedAt || build.built_at)}`].filter(Boolean).join(' · ')}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={raw.complete ? 'ok' : 'warn'}>{raw.complete ? 'Testing stage recorded' : build ? 'Build evidence only' : 'Partial'}</Badge>
          <Badge tone="ok">{raw.summary?.pass || 0} passed</Badge>
          <Badge tone={raw.summary?.fail ? 'bad' : 'mute'}>{raw.summary?.fail || 0} failed</Badge>
          <Badge tone="warn">{raw.summary?.warn || 0} warnings</Badge>
        </div>
      </div>
      <div className="mt-4 grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(150px,1fr))]">
        {unit && <Tile label="Unit tests" value={`${unit.passed}/${unit.total}`} sub={`${unit.files} files`} bad={unit.failed > 0} />}
        {units.length > 0 && <Tile label="Units with a test" value={`${unitsTested}/${units.length}`} sub="pages, routes, components" bad={unitsTested < units.length} />}
        {raw.codeCoverage?.lines != null && <Tile label="Line coverage" value={`${raw.codeCoverage.lines}%`} sub="measured by the unit tests" />}
        {runs && <Tile label="Browser tests" value={`${runs.passed}/${runs.total}`} sub={runs.failed ? `${runs.failed} failed` : 'desktop + mobile'} bad={runs.failed > 0} />}
        {reqs.length > 0 && <Tile label="Requirements" value={`${met}/${reqs.length}`} sub="met" bad={met < reqs.length} />}
        {probe && <Tile label="Route checks" value={`${matched}/${list(probe.results).length}`} sub="as specified" bad={matched < list(probe.results).length} />}
        {lh.length > 0 && <Tile label="Lighthouse (lowest)" value={Math.min(...Object.values(lh[0].scores || { x: 0 }))} sub={Object.entries(lh[0].scores || {}).map(([k, v]) => `${k.replace('best-practices', 'practices')} ${v}`).join(' · ')} />}
        <Tile label="Screenshots" value={shots.length} sub="saved" />
        {gaps.length > 0 && <Tile label="Gaps" value={gaps.length} sub="recorded, not passed" bad />}
      </div>
    </Panel>

    <Gaps gaps={gaps} />
    <Commands commands={commands} />
    <UnitTests vitest={raw.vitest} />
    <UnitInventory inventory={raw.unitInventory} coverage={raw.codeCoverage} />
    <BrowserTests runs={runs} />
    <RouteProbe probe={probe} />
    <Lighthouse data={raw.lighthouse} />
    <SecurityScan scan={raw.zapSummary} />
    <Requirements build={build} scope={raw.report?.evidence?.scope?.requirements} />
    <Checked build={build} />

    {!!shots.length && <Section title={`Saved screenshots (${shots.length})`}>
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(180px,1fr))]">{shots.map(shot =>
        <a key={shot.path} href={api.qaScreenshotUrl(qa.project, shot.path, shot.at)} target="_blank" rel="noreferrer" className="overflow-hidden rounded-none border border-line bg-panel">
          <img src={api.qaScreenshotUrl(qa.project, shot.path, shot.at)} alt={shot.name || shot.route || shot.path} loading="lazy" className="h-32 w-full object-contain object-top" />
          <span className="block truncate p-2 text-xs text-muted">{shot.path.replace(/^(e2e\/__screenshots__|test-results)\//, '')}</span>
        </a>)}</div>
    </Section>}

    {legacy && <Section title="Testing stage report" hint="What the separate Testing run recorded.">
      <div className="grid gap-3 md:grid-cols-2">
        <Result title="Unit & integration" value={raw.unit} />
        <Result title="Journeys" value={raw.journeys} />
        <Result title="Requirement coverage" value={raw.coverage} />
        {!!raw.bugs?.length && <Result title="Open findings" value={raw.bugs} />}
      </div>
    </Section>}

    {build && <details className="rounded-none border border-line bg-panel">
      <summary className="cursor-pointer px-4 py-3 text-[12px] font-semibold text-muted hover:text-ink">Raw build report (.agentforge/build/report.json)</summary>
      <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-all border-t border-line p-4 text-[11px] text-muted">{JSON.stringify(build, null, 2)}</pre>
    </details>}
  </div>
}
