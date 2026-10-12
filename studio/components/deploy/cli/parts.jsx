'use client'

/**
 * What every command's own page is made of: the hook that runs it, the frame around it (title, live status, formatted or
 * raw), and the pieces a page lays its answer out with (facts, tables, pills, stats and a few diagrams).
 * A command's page is a small file that says which of these to use for its answer.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, CircleAlert, Copy, ExternalLink, Loader2, Play, Search, Square, Terminal as TerminalIcon } from 'lucide-react'

import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

const POLL_MS = 600
const REFRESH_MS = 15000

// ---- reading values -------------------------------------------------------------------------------------------

/** A JSON answer, even with progress lines before or after it (the tools print those beside it). */
export function parseJson(text) {
  const trimmed = String(text || '').trim()
  if (!trimmed) return null
  try { return JSON.parse(trimmed) } catch { /* look for the start of it */ }
  const lines = trimmed.split('\n')
  for (let i = 0; i < lines.length; i++) {
    if (!/^\s*[[{]/.test(lines[i])) continue
    for (let j = lines.length, tries = 0; j > i && tries < 300; j--, tries++) {
      try { return JSON.parse(lines.slice(i, j).join('\n')) } catch { /* shorter */ }
    }
    return null
  }
  return null
}

/** Rows from a plain-text table: the first line names the columns, and two or more spaces (or `|`) separate them. */
export function parseTable(text) {
  const all = String(text || '').split('\n')
  // A `Name | Size` table ruled with `-----|-----` under its header.
  const rule = all.findIndex(line => /^\s*-{2,}(\|-{2,})+\s*$/.test(line.replace(/\s/g, '')) || /^\s*-+(\s*\|\s*-+)+\s*$/.test(line))
  if (rule > 0 && all[rule - 1].includes('|')) {
    const split = line => line.split('|').map(cell => cell.trim())
    const columns = split(all[rule - 1])
    const rows = all.slice(rule + 1).filter(line => line.includes('|')).map(split)
      .map(cells => Object.fromEntries(columns.map((name, i) => [name, cells[i] ?? ''])))
    return { columns, rows }
  }
  const lines = all.filter(line => line.trim() && !/claude-code-hint|^Vercel CLI|^>|^Retrieving|^Fetching/.test(line))
  const head = lines.findIndex(line => /\S+\s{2,}\S+/.test(line))
  if (head < 0) return { columns: [], rows: [] }
  const columns = lines[head].trim().split(/\s{2,}/)
  const rows = lines.slice(head + 1).map(line => line.trim().split(/\s{2,}/))
    .filter(cells => cells.length > 1).map(cells => Object.fromEntries(columns.map((name, i) => [name, cells[i] ?? ''])))
  return { columns, rows }
}

export const human = key => String(key || '').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').replace(/^\w/, c => c.toUpperCase())

const asDate = value => {
  if (value == null || value === '') return null
  const number = typeof value === 'number' ? value : (/^\d{10,13}$/.test(String(value)) ? Number(value) : null)
  const date = number != null ? new Date(number < 1e12 ? number * 1000 : number) : new Date(value)
  return Number.isNaN(+date) ? null : date
}

export function ago(value) {
  const date = asDate(value)
  if (!date) return ''
  const seconds = Math.round((Date.now() - +date) / 1000)
  const future = seconds < 0
  const span = Math.abs(seconds)
  const [n, unit] = span < 60 ? [span, 's'] : span < 3600 ? [Math.round(span / 60), 'm'] : span < 86400 ? [Math.round(span / 3600), 'h'] : [Math.round(span / 86400), 'd']
  return future ? `in ${n}${unit}` : `${n}${unit} ago`
}

export const stamp = value => { const date = asDate(value); return date ? date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '' }
export const duration = value => {
  const ms = Number(value)
  if (!Number.isFinite(ms)) return ''
  if (ms < 1000) return `${Math.round(ms)} ms`
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}
export const bytes = value => {
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = n, i = 0
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++ }
  return `${size >= 10 || i === 0 ? Math.round(size) : size.toFixed(1)} ${units[i]}`
}

const GOOD = /^(ready|success|succeeded|completed|complete|active|ok|enabled|running|in[_ ]?service|available|healthy|passed|pass|online|live|deployed|create_complete|update_complete|attached|associated|exists|true)$/i
const BAD = /(fail|error|cancel|crash|unhealthy|impaired|denied|rollback|delete|timed[_ ]?out|stopped|inactive|disabled|offline|alarm|blocked)/i
const WARN = /(warn|pending|degraded|draining|stale|expir|insufficient|skipped|neutral|unknown)/i
const RUN = /(build|queue|progress|initial|provision|creating|updating|starting|deploy|waiting|requested)/i

/** ok | bad | warn | run | mute, from a status word. */
export function tone(value) {
  const text = String(value ?? '').trim()
  if (!text) return 'mute'
  if (GOOD.test(text)) return 'ok'
  if (BAD.test(text)) return 'bad'
  if (WARN.test(text)) return 'warn'
  if (RUN.test(text)) return 'run'
  return 'mute'
}

const TONE = {
  ok: 'bg-ok/15 text-ink ring-ok/30',
  bad: 'bg-bad/15 text-bad ring-bad/30',
  warn: 'bg-warn/15 text-bad ring-warn/30',
  run: 'bg-info/15 text-ok ring-info/30',
  mute: 'bg-black/[.06] text-muted ring-black/10',
}
export const TONE_TEXT = { ok: 'text-ink', bad: 'text-bad', warn: 'text-bad', run: 'text-ok', mute: 'text-muted' }
export const TONE_FILL = { ok: 'var(--green)', bad: 'var(--red)', warn: 'var(--yellow)', run: 'var(--info)', mute: 'var(--muted2)' }

// ---- running a command ----------------------------------------------------------------------------------------

/** Runs the command when the page opens and reads its output as it is written. Leaving the page stops it. */
export function useCommand(project, item) {
  const [lines, setLines] = useState([])
  const [state, setState] = useState({ status: 'starting', exit: null, seconds: 0 })
  const [display, setDisplay] = useState(item.display)
  const [auto, setAuto] = useState(!item.follow)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState(0)
  const job = useRef({ id: '', since: 0 })
  const poll = useRef(null)
  const again = useRef(null)
  const alive = useRef(true)
  const fresh = useRef([])
  const autoRef = useRef(auto)
  autoRef.current = auto

  const stop = useCallback(() => {
    clearTimeout(poll.current)
    const id = job.current.id
    job.current = { id: '', since: 0 }
    if (id) api.cliMonitorStop(id).catch(() => {})
  }, [])

  const run = useCallback(async (keep = false) => {
    clearTimeout(again.current)
    stop()
    setError('')
    if (keep) { setRefreshing(true); fresh.current = [] }
    else { setLines([]); fresh.current = []; setState({ status: 'starting', exit: null, seconds: 0 }) }
    let started
    try {
      started = await api.cliMonitorStart(project, item.id, item.scope)
    } catch (e) {
      if (!alive.current) return
      setRefreshing(false)
      setError(e.message || 'Could not run that.')
      setState({ status: 'failed', exit: null, seconds: 0 })
      return
    }
    if (!alive.current) { api.cliMonitorStop(started.job).catch(() => {}); return }
    job.current = { id: started.job, since: 0 }
    setDisplay(started.display)
    setState(current => (keep ? current : { status: 'running', exit: null, seconds: 0 }))

    const tick = async () => {
      const mine = job.current.id
      if (!mine || !alive.current) return
      let answer
      try {
        answer = await api.cliMonitorPoll(mine, job.current.since)
      } catch {
        if (alive.current && job.current.id === mine) poll.current = setTimeout(tick, POLL_MS * 2)
        return
      }
      if (!alive.current || job.current.id !== mine) return
      job.current.since = answer.next
      if (keep) fresh.current = fresh.current.concat(answer.lines)
      else if (answer.lines.length) setLines(current => current.concat(answer.lines))
      setState({ status: answer.status, exit: answer.exit_code, seconds: answer.seconds })
      if (answer.status === 'running') { poll.current = setTimeout(tick, POLL_MS); return }
      if (keep) { setLines(fresh.current); setRefreshing(false) }
      setUpdated(Date.now())
      job.current = { id: '', since: 0 }
      if (autoRef.current && !item.follow) again.current = setTimeout(() => run(true), REFRESH_MS)
    }
    tick()
  }, [project, item.id, item.scope, item.follow, stop])

  useEffect(() => {
    alive.current = true
    run(false)
    return () => { alive.current = false; clearTimeout(again.current); stop() }
  }, [run, stop])

  useEffect(() => {
    if (!auto) clearTimeout(again.current)
    else if (state.status !== 'running' && state.status !== 'starting' && !item.follow) {
      clearTimeout(again.current)
      again.current = setTimeout(() => run(true), REFRESH_MS)
    }
  }, [auto])            // eslint-disable-line react-hooks/exhaustive-deps

  const running = state.status === 'running' || state.status === 'starting'
  const text = useMemo(() => lines.join('\n'), [lines])
  const json = useMemo(() => (running && !item.follow ? null : parseJson(text)), [text, running, item.follow])
  const halt = () => { stop(); setState(s => ({ ...s, status: 'stopped' })); setRefreshing(false) }
  return { lines, text, json, ...state, display, running, refreshing, error, auto, setAuto, run, halt, follow: item.follow, updated }
}

// ---- the frame ------------------------------------------------------------------------------------------------

const STATUS = {
  starting: ['Starting', 'mute'], running: ['Running', 'run'], done: ['Finished', 'ok'], failed: ['Failed', 'bad'],
  stopped: ['Stopped', 'mute'], timeout: ['Timed out', 'warn'], gone: ['Gone', 'mute'],
}

export function Pill({ tone: kind = 'mute', children, className }) {
  return <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-[2px] text-[10.5px] font-semibold ring-1 ring-inset', TONE[kind] || TONE.mute, className)}>{children}</span>
}

/** A status word as a coloured pill, its colour chosen from its meaning. */
export function Status({ value }) {
  return value == null || value === '' ? <span className="text-muted2">—</span> : <Pill tone={tone(value)}>{String(value)}</Pill>
}

export function Terminal({ lines, running, error }) {
  const view = useRef(null)
  const bottom = useRef(true)
  useEffect(() => { const el = view.current; if (el && bottom.current) el.scrollTop = el.scrollHeight }, [lines])
  return (
    <div ref={view} onScroll={e => { const el = e.currentTarget; bottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40 }}
         className="max-h-[62vh] min-h-[200px] overflow-auto rounded-xl bg-panel px-3.5 py-3">
      {error && <p className="mb-2 text-[12px] text-bad">{error}</p>}
      <pre className="whitespace-pre-wrap break-words font-mono text-[11.5px] leading-[1.55] text-ink">
        {lines.length ? lines.join('\n') : (running ? 'Waiting for the first line…' : '(no output)')}
      </pre>
    </div>
  )
}

/**
 * The page of one command: its title and what it shows, the live status and controls, and the answer laid out by the
 * page (or, one click away, exactly what the tool printed).
 */
export function View({ project, item, title, about, icon: Icon, children, wide }) {
  const cmd = useCommand(project, item)
  const [mode, setMode] = useState('formatted')
  const [copied, setCopied] = useState(false)
  const [label, kind] = STATUS[cmd.status] || STATUS.done
  const failed = (cmd.status === 'failed' || cmd.status === 'timeout') && !cmd.json
  const copy = async () => { try { await navigator.clipboard.writeText(cmd.text); setCopied(true); setTimeout(() => setCopied(false), 1400) } catch { /* none */ } }
  const Head = Icon || TerminalIcon

  return (
    <section className={cn('mx-auto space-y-3', wide ? 'max-w-[1180px]' : 'max-w-[980px]')}>
      <header className="flex flex-wrap items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-accent text-ink"><Head className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
          {about && <p className="mt-0.5 max-w-[640px] text-[11.5px] leading-relaxed text-muted">{about}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={kind}>{cmd.running || cmd.refreshing ? <Loader2 className="size-3 animate-spin" /> : cmd.status === 'done' ? <Check className="size-3" /> : null}
            {label}{cmd.status === 'failed' && cmd.exit != null ? ` · exit ${cmd.exit}` : ''}{cmd.seconds ? ` · ${cmd.seconds}s` : ''}</Pill>
          <div className="flex overflow-hidden rounded-lg ring-1 ring-inset ring-black/10">
            {['formatted', 'raw'].map(name => (
              <button key={name} type="button" onClick={() => setMode(name)}
                      className={cn('px-2.5 py-1 text-[11px] font-semibold capitalize', mode === name ? 'bg-accent text-ink' : 'text-muted hover:bg-black/5')}>{name}</button>
            ))}
          </div>
          {cmd.running
            ? <Ctl onClick={cmd.halt}><Square className="size-3" /> Stop</Ctl>
            : <Ctl onClick={() => cmd.run(false)}><Play className="size-3" /> Run again</Ctl>}
          <Ctl onClick={copy} disabled={!cmd.text}>{copied ? <Check className="size-3 text-ink" /> : <Copy className="size-3" />} {copied ? 'Copied' : 'Copy'}</Ctl>
        </div>
      </header>

      {mode === 'raw' ? <Terminal lines={cmd.lines} running={cmd.running} error={cmd.error} />
        : cmd.running && !cmd.lines.length ? <Skeleton />
        : failed ? <Failed cmd={cmd} />
        : (children({ json: cmd.json, text: cmd.text, lines: cmd.lines, cmd }) || <Unreadable text={cmd.text} />)}

      <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-muted2">
        <code className="min-w-0 max-w-full truncate font-mono" title={cmd.display}>$ {cmd.display}</code>
        {!item.follow && (
          <label className="ml-auto flex cursor-pointer items-center gap-1.5">
            <input type="checkbox" checked={cmd.auto} onChange={e => cmd.setAuto(e.target.checked)} className="accent-[var(--accent)]" />
            refresh every {REFRESH_MS / 1000} s{cmd.updated ? ` · updated ${ago(cmd.updated)}` : ''}
          </label>
        )}
        {item.follow && <span className="ml-auto">streams until you stop it or leave this page</span>}
      </footer>
    </section>
  )
}

const Ctl = ({ onClick, disabled, children }) => (
  <button type="button" onClick={onClick} disabled={disabled}
          className="inline-flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-[11px] font-semibold text-muted ring-1 ring-inset ring-black/10 hover:bg-black/5 disabled:opacity-40">
    {children}
  </button>
)

function Skeleton() {
  return (
    <div className="space-y-2 rounded-2xl border border-black/[.07] bg-panel p-4">
      {[70, 92, 55, 80].map((w, i) => <div key={i} className="h-3 animate-pulse rounded bg-black/[.07]" style={{ width: `${w}%` }} />)}
    </div>
  )
}

function Failed({ cmd }) {
  return (
    <div className="space-y-2.5 rounded-2xl border border-bad/25 bg-bad/[.06] p-4">
      <p className="flex items-center gap-2 text-[12.5px] font-semibold text-bad"><CircleAlert className="size-4" />
        {cmd.status === 'timeout' ? 'It did not finish in time.' : 'The tool reported a problem.'}</p>
      <Terminal lines={cmd.lines} running={false} error={cmd.error} />
    </div>
  )
}

function Unreadable({ text }) {
  return (
    <div className="space-y-2 rounded-2xl border border-black/[.07] bg-panel p-4">
      <p className="text-[11.5px] text-muted">This answer is not in a form this page can lay out. It is shown as printed.</p>
      <pre className="max-h-[50vh] overflow-auto whitespace-pre-wrap break-words font-mono text-[11.5px] text-ink">{text || '(no output)'}</pre>
    </div>
  )
}

// ---- the pieces a page lays its answer out with ---------------------------------------------------------------

export function Card({ title, right, children, className, pad = true }) {
  return (
    <div className={cn('overflow-hidden rounded-2xl border border-black/[.07] bg-panel shadow-[0_12px_24px_-12px_rgba(0,0,0,0.35)]', className)}>
      {(title || right) && (
        <div className="flex items-center gap-2 border-b border-black/[.06] px-4 py-2.5">
          <h3 className="flex-1 text-[11px] font-semibold uppercase tracking-[.12em] text-muted">{title}</h3>
          {right}
        </div>
      )}
      <div className={pad ? 'p-4' : ''}>{children}</div>
    </div>
  )
}

export function Empty({ title = 'Nothing here', hint }) {
  return (
    <div className="rounded-2xl border border-dashed border-black/10 px-6 py-10 text-center">
      <p className="text-[13px] font-semibold text-ink">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-[420px] text-[11.5px] leading-relaxed text-muted">{hint}</p>}
    </div>
  )
}

export function Stats({ items }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
      {items.filter(Boolean).map((row, i) => (
        <div key={i} className="rounded-xl border border-black/[.07] bg-panel px-3.5 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[.12em] text-muted">{row.label}</p>
          <p className={cn('mt-1 font-semibold', String(row.value).length > 13 ? 'break-all text-[13px] leading-snug' : 'truncate text-[18px]', TONE_TEXT[row.tone] || 'text-ink')} title={String(row.value)}>{row.value}</p>
          {row.sub && <p className="mt-0.5 truncate text-[10.5px] text-muted2">{row.sub}</p>}
        </div>
      ))}
    </div>
  )
}

export function Chips({ items, tone: kind = 'mute' }) {
  const list = (Array.isArray(items) ? items : [items]).filter(item => item != null && item !== '')
  return list.length ? <span className="flex flex-wrap gap-1">{list.map((item, i) => <Pill key={i} tone={kind}>{String(item)}</Pill>)}</span> : <span className="text-muted2">—</span>
}

export const Link = ({ href, children }) => (
  <a href={href} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 text-deep hover:underline">
    <span className="truncate">{children ?? href}</span><ExternalLink className="size-2.5 shrink-0" />
  </a>
)

/** One value, shown by its kind: date, link, status, mono, chips, bytes, duration, yes/no, or text. */
export function Value({ v, kind }) {
  if (v == null || v === '' || (Array.isArray(v) && !v.length)) return <span className="text-muted2">—</span>
  switch (kind) {
    case 'date': return <span title={stamp(v)}>{ago(v) || String(v)}</span>
    case 'datetime': return <span>{stamp(v)} <span className="text-muted2">· {ago(v)}</span></span>
    case 'link': return <Link href={String(v).startsWith('http') ? v : `https://${v}`}>{String(v).replace(/^https?:\/\//, '')}</Link>
    case 'status': return <Status value={v} />
    case 'mono': return <code className="break-all font-mono text-[11px] text-ink">{String(v)}</code>
    case 'chips': return <Chips items={v} />
    case 'bytes': return <span>{bytes(v)}</span>
    case 'duration': return <span>{duration(v)}</span>
    case 'yesno': return <Pill tone={v ? 'ok' : 'mute'}>{v ? 'Yes' : 'No'}</Pill>
    case 'json': return <code className="break-all font-mono text-[10.5px] text-muted">{JSON.stringify(v)}</code>
    default:
      if (typeof v === 'boolean') return <Pill tone={v ? 'ok' : 'mute'}>{v ? 'Yes' : 'No'}</Pill>
      if (Array.isArray(v)) return <Chips items={v.map(x => (typeof x === 'object' ? JSON.stringify(x) : x))} />
      if (typeof v === 'object') return <code className="break-all font-mono text-[10.5px] text-muted">{JSON.stringify(v)}</code>
      return <span className="break-words">{String(v)}</span>
  }
}

/** Labelled facts: `items` is `[label, value, kind]`; empty ones are left out unless `all`. */
export function Facts({ items, all, columns = 2 }) {
  const rows = items.filter(Boolean).filter(([, value]) => all || !(value == null || value === '' || (Array.isArray(value) && !value.length)))
  return (
    <dl className={cn('grid gap-x-8 gap-y-3', columns === 1 ? 'grid-cols-1' : 'sm:grid-cols-2')}>
      {rows.map(([label, value, kind]) => (
        <div key={label} className="min-w-0">
          <dt className="text-[10px] font-semibold uppercase tracking-[.12em] text-muted2">{label}</dt>
          <dd className="mt-0.5 text-[12.5px] text-ink"><Value v={value} kind={kind} /></dd>
        </div>
      ))}
    </dl>
  )
}

/** Rows and columns, with a filter box when there are many. A column is `{ label, key | get, kind, mono }`.
 *  `onRow`, when given, makes each row a button (`rowTitle` says what clicking it does). */
export function Table({ rows, columns, empty = 'Nothing here.', filter, limit = 200, onRow, rowTitle }) {
  const [query, setQuery] = useState('')
  const list = Array.isArray(rows) ? rows : []
  const cell = (row, col) => (col.get ? col.get(row) : row?.[col.key])
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    const found = q ? list.filter(row => columns.some(col => String(cell(row, col) ?? '').toLowerCase().includes(q))) : list
    return found.slice(0, limit)
  }, [list, query, columns, limit])
  if (!list.length) return <Empty title={empty} />
  return (
    <Card pad={false}>
      {(filter ?? list.length > 8) && (
        <div className="flex items-center gap-2 border-b border-black/[.06] px-3 py-2">
          <Search className="size-3 text-muted2" />
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter…"
                 className="min-w-0 flex-1 bg-transparent text-[12px] text-ink outline-none placeholder:text-muted2" />
          <span className="font-mono text-[10.5px] text-muted2">{shown.length}{shown.length !== list.length ? ` of ${list.length}` : ''}</span>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse text-left text-[12px]">
          <thead>
            <tr className="border-b border-black/[.06] text-[10px] uppercase tracking-[.1em] text-muted2">
              {columns.map(col => <th key={col.label} className="whitespace-nowrap px-3.5 py-2 font-semibold">{col.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, i) => (
              <tr key={i} onClick={onRow ? () => onRow(row) : undefined} title={onRow ? rowTitle : undefined}
                  tabIndex={onRow ? 0 : undefined}
                  onKeyDown={onRow ? e => { if (e.key === 'Enter') onRow(row) } : undefined}
                  className={cn('border-b border-black/[.04] last:border-0 hover:bg-black/[.025]',
                    onRow && 'cursor-pointer focus:bg-accent/10 focus:outline-none')}>
                {columns.map(col => (
                  <td key={col.label} className={cn('max-w-[340px] px-3.5 py-2 align-top text-ink', col.mono && 'font-mono text-[11px]')}>
                    <Value v={cell(row, col)} kind={col.mono ? 'mono' : col.kind} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

/** Text lines, coloured by level, with a filter and a search: for build and runtime logs. */
export function LogView({ lines, follow }) {
  const [level, setLevel] = useState('all')
  const [query, setQuery] = useState('')
  const view = useRef(null)
  const bottom = useRef(true)
  const parsed = useMemo(() => lines.map(line => {
    const kind = /\b(error|fatal|failed|exception)\b/i.test(line) ? 'bad' : /\b(warn|warning|deprecated)\b/i.test(line) ? 'warn' : 'ok'
    const time = line.match(/^(\d{4}-\d{2}-\d{2}T[\d:.]+Z?|\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+/)
    return { line, kind, time: time?.[1] || '', body: time ? line.slice(time[0].length) : line }
  }), [lines])
  const shown = parsed.filter(row => (level === 'all' || row.kind === level) && (!query || row.line.toLowerCase().includes(query.toLowerCase())))
  const counts = { bad: parsed.filter(r => r.kind === 'bad').length, warn: parsed.filter(r => r.kind === 'warn').length }
  useEffect(() => { const el = view.current; if (el && follow && bottom.current) el.scrollTop = el.scrollHeight }, [shown.length, follow])
  return (
    <Card pad={false}>
      <div className="flex flex-wrap items-center gap-2 border-b border-black/[.06] px-3 py-2">
        {[['all', 'All'], ['bad', `Errors ${counts.bad}`], ['warn', `Warnings ${counts.warn}`]].map(([id, name]) => (
          <button key={id} type="button" onClick={() => setLevel(id)}
                  className={cn('rounded-md px-2 py-0.5 text-[11px] font-semibold', level === id ? 'bg-accent text-ink' : 'text-muted hover:bg-black/5')}>{name}</button>
        ))}
        <span className="flex-1" />
        <Search className="size-3 text-muted2" />
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search the log…"
               className="w-[180px] bg-transparent text-[12px] text-ink outline-none placeholder:text-muted2" />
        <span className="font-mono text-[10.5px] text-muted2">{shown.length} lines</span>
      </div>
      <div ref={view} onScroll={e => { const el = e.currentTarget; bottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40 }}
           className="max-h-[60vh] overflow-auto bg-panel py-1.5">
        {shown.map((row, i) => (
          <div key={i} className="flex gap-3 px-3.5 py-[1px] font-mono text-[11.5px] leading-[1.5] hover:bg-black/[.03]">
            {row.time && <span className="w-[92px] shrink-0 text-muted2">{row.time.replace(/^\d{4}-\d{2}-\d{2}T/, '').replace(/Z$/, '')}</span>}
            <span className={cn('min-w-0 whitespace-pre-wrap break-words', row.kind === 'bad' || row.kind === 'warn' ? 'text-bad' : 'text-ink')}>{row.body}</span>
          </div>
        ))}
        {!shown.length && <p className="px-4 py-6 text-center text-[12px] text-muted2">Nothing matches.</p>}
      </div>
    </Card>
  )
}

// ---- diagrams -------------------------------------------------------------------------------------------------

/** Steps left to right with an arrow between: a pipeline, a request path, a release. A step is `{ label, sub, tone, icon }`. */
export function Flow({ steps, title }) {
  const list = steps.filter(Boolean)
  return (
    <Card title={title}>
      <div className="flex flex-wrap items-stretch gap-y-3">
        {list.map((step, i) => (
          <div key={i} className="flex items-center">
            <div className={cn('min-w-[118px] max-w-[190px] rounded-xl px-3 py-2.5 ring-1 ring-inset', TONE[step.tone || 'mute'])}>
              <p className="flex items-center gap-1.5 text-[12px] font-semibold">{step.icon}{step.label}</p>
              {step.sub && <p className="mt-0.5 break-words text-[10.5px] opacity-80">{step.sub}</p>}
            </div>
            {i < list.length - 1 && (
              <svg width="34" height="14" viewBox="0 0 34 14" className="mx-0.5 shrink-0 text-muted2" aria-hidden="true">
                <path d="M2 7h26M23 2l6 5-6 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}

/** Horizontal bars: `{ label, value, tone, sub }`, scaled to the largest value. */
export function Bars({ items, format = String, title }) {
  const max = Math.max(1, ...items.map(row => Number(row.value) || 0))
  return (
    <Card title={title}>
      <div className="space-y-1.5">
        {items.map((row, i) => (
          <div key={i} className="flex items-center gap-3 text-[11.5px]">
            <span className="w-[34%] min-w-[110px] max-w-[280px] truncate text-ink" title={row.label}>{row.label}</span>
            <span className="h-3 flex-1 overflow-hidden rounded bg-black/[.05]">
              <span className="block h-full rounded" style={{ width: `${Math.max(2, ((Number(row.value) || 0) / max) * 100)}%`, background: TONE_FILL[row.tone || 'run'] }} />
            </span>
            <span className="w-[64px] shrink-0 text-right font-mono text-[10.5px] text-muted">{format(row.value)}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}

/** A vertical line of events with a dot each: `{ title, sub, time, tone, badges }`. */
export function Timeline({ events, title }) {
  return (
    <Card title={title} pad={false}>
      <ol className="relative px-4 py-3">
        <span className="absolute bottom-4 left-[22px] top-4 w-px bg-black/10" />
        {events.map((event, i) => (
          <li key={i} className="relative flex gap-3 py-1.5 pl-6">
            <span className="absolute left-[4px] top-[11px] size-[9px] rounded-full ring-4 ring-panel" style={{ background: TONE_FILL[event.tone || 'mute'] }} />
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-ink">
                <span className="min-w-0 break-words">{event.title}</span>
                {(event.badges || []).map((badge, j) => <Pill key={j} tone={badge.tone || 'mute'}>{badge.label}</Pill>)}
              </p>
              {event.sub && <p className="mt-0.5 break-words text-[11px] text-muted">{event.sub}</p>}
            </div>
            {event.time && <span className="shrink-0 pt-0.5 font-mono text-[10.5px] text-muted2" title={stamp(event.time)}>{ago(event.time)}</span>}
          </li>
        ))}
      </ol>
    </Card>
  )
}


export function Note({ tone: kind = 'mute', children }) {
  return <p className={cn('rounded-xl px-3.5 py-2.5 text-[11.5px] leading-relaxed ring-1 ring-inset', TONE[kind] || TONE.mute)}>{children}</p>
}

/** A line of commits, newest first, each a dot on the line with its branch and tag labels: `{ short, subject, author, date, refs }`. */
export function CommitGraph({ commits, title }) {
  return (
    <Card title={title} pad={false}>
      <ol className="relative py-2">
        <span className="absolute bottom-5 left-[27px] top-5 w-px bg-black/10" />
        {commits.map((commit, i) => (
          <li key={commit.short + i} className="relative flex gap-3 py-2 pl-12 pr-4 hover:bg-black/[.02]">
            <span className="absolute left-[22px] top-[15px] size-[11px] rounded-full ring-4 ring-panel" style={{ background: i === 0 ? TONE_FILL.ok : TONE_FILL.run }} />
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-ink">
                <span className="min-w-0 break-words font-medium">{commit.subject}</span>
                {(commit.refs || []).map(ref => <Pill key={ref} tone={/^HEAD/.test(ref) ? 'ok' : /^tag:/.test(ref) ? 'warn' : /origin\//.test(ref) ? 'run' : 'mute'}>{ref}</Pill>)}
              </p>
              <p className="mt-0.5 text-[11px] text-muted">{commit.author} · <span title={stamp(commit.date)}>{ago(commit.date)}</span></p>
            </div>
            <code className="shrink-0 pt-0.5 font-mono text-[11px] text-deep">{commit.short}</code>
          </li>
        ))}
      </ol>
    </Card>
  )
}

/** One bar split into shares, with a key: `{ label, value }`, coloured in turn. */
export function StackedBar({ items, title, format = String }) {
  const total = items.reduce((sum, row) => sum + (Number(row.value) || 0), 0) || 1
  const colours = ['var(--accent)', 'var(--green)', 'var(--yellow)', 'var(--red)', 'var(--accent)', 'var(--info)', 'var(--muted2)']
  return (
    <Card title={title}>
      <div className="flex h-3 overflow-hidden rounded-full bg-black/[.05]">
        {items.map((row, i) => <span key={row.label} style={{ width: `${((Number(row.value) || 0) / total) * 100}%`, background: colours[i % colours.length] }} title={`${row.label}: ${format(row.value)}`} />)}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {items.map((row, i) => (
          <span key={row.label} className="flex items-center gap-1.5 text-[11.5px] text-ink">
            <span className="size-2 rounded-full" style={{ background: colours[i % colours.length] }} />{row.label}
            <span className="font-mono text-[10.5px] text-muted">{Math.round(((Number(row.value) || 0) / total) * 100)}%</span>
          </span>
        ))}
      </div>
    </Card>
  )
}

/** Lays out any JSON: a list of objects becomes a table, an object becomes facts and sections. For answers whose shape is not known in advance. */
export function Auto({ json, empty = 'Nothing to show.' }) {
  if (json == null) return null
  if (Array.isArray(json)) {
    if (!json.length) return <Empty title={empty} />
    if (typeof json[0] !== 'object') return <Card><Chips items={json} /></Card>
    const keys = [...new Set(json.flatMap(row => Object.keys(row || {})))].filter(key => json.some(row => row?.[key] == null || typeof row[key] !== 'object' || Array.isArray(row[key]))).slice(0, 7)
    return <Table rows={json} columns={keys.map(key => ({ label: human(key), key, kind: /_at$|At$|date/i.test(key) ? 'date' : /url$/i.test(key) ? 'link' : /state|status/i.test(key) ? 'status' : undefined }))} />
  }
  if (typeof json !== 'object') return <Card><Value v={json} /></Card>
  const scalars = Object.entries(json).filter(([, value]) => value == null || typeof value !== 'object' || (Array.isArray(value) && value.every(x => typeof x !== 'object')))
  const nested = Object.entries(json).filter(([, value]) => value && typeof value === 'object' && !scalars.some(([key]) => value === json[key]))
  return (<>
    {scalars.length > 0 && <Card><Facts items={scalars.map(([key, value]) => [human(key), value, /_at$|At$|date/i.test(key) ? 'datetime' : /url$/i.test(key) ? 'link' : /state|status/i.test(key) ? 'status' : undefined])} /></Card>}
    {nested.map(([key, value]) => <div key={key} className="space-y-2"><h3 className="px-1 text-[11px] font-semibold uppercase tracking-[.12em] text-muted">{human(key)}</h3><Auto json={value} /></div>)}
  </>)
}
