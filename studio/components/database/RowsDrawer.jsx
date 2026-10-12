'use client'

/**
 * The first rows of one table, or the newest documents of one collection, beside the page that listed it. Read-only,
 * read when opened, and masked on the server: a field whose name says it holds a credential shows as `<masked>`.
 */

import { useCallback, useEffect, useState } from 'react'
import { Braces, Check, Copy, Loader2, RefreshCw, Table2, X } from 'lucide-react'

import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Note, Pill } from '../deploy/cli/parts'

/** A MongoDB extended-JSON value as people write it, and anything else as compact text. */
function shown(value) {
  if (value === null || value === undefined) return null
  if (typeof value === 'object' && !Array.isArray(value)) {
    if ('$oid' in value) return `ObjectId(${value.$oid})`
    if ('$date' in value) return typeof value.$date === 'string' ? value.$date : JSON.stringify(value.$date)
    if ('$numberDecimal' in value) return String(value.$numberDecimal)
    if ('$numberLong' in value) return String(value.$numberLong)
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function Cell({ value }) {
  if (value === null || value === undefined) return <span className="italic text-muted2">null</span>
  if (value === '<masked>') return <Pill tone="warn">masked</Pill>
  if (typeof value === 'boolean') return <Pill tone={value ? 'ok' : 'mute'}>{String(value)}</Pill>
  const text = shown(value)
  const nested = typeof value === 'object' && !('$oid' in value) && !('$date' in value)
  return (
    <span title={text.length > 80 ? text : undefined}
          className={cn('block max-w-[320px] truncate', nested ? 'font-mono text-[10.5px] text-muted' : typeof value === 'number' ? 'font-mono' : '')}>
      {text}
    </span>
  )
}

export default function RowsDrawer({ project, target, onClose }) {
  const [state, setState] = useState({ loading: true, error: '', data: null })
  const [mode, setMode] = useState('table')
  const [copied, setCopied] = useState(false)
  const name = target.source === 'supabase' ? `${target.schema || 'public'}.${target.table}` : `${target.database ? `${target.database}.` : ''}${target.collection}`

  const load = useCallback(async () => {
    setState(s => ({ ...s, loading: true, error: '' }))
    try {
      const data = await api.databaseRows(project, target)
      setState({ loading: false, error: '', data })
    } catch (e) {
      setState({ loading: false, error: e.message || 'Could not read the rows.', data: null })
    }
  }, [project, target])
  useEffect(() => { load() }, [load])

  useEffect(() => {
    const key = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose])

  const data = state.data
  const rows = data?.rows || []
  const columns = (data?.columns?.length ? data.columns : [...new Set(rows.flatMap(row => Object.keys(row)))].map(n => ({ name: n })))
  const copy = async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(rows, null, 2)); setCopied(true); setTimeout(() => setCopied(false), 1400) } catch { /* none */ }
  }
  const total = data?.total == null ? '' : `${Number(data.total).toLocaleString()}${data.more ? '+' : ''}`

  return (
    <div className="absolute inset-0 z-30 flex justify-end bg-black/20 backdrop-blur-[1px]" onClick={onClose}>
      <aside role="dialog" aria-label={`Rows of ${name}`} onClick={e => e.stopPropagation()}
             className="flex h-full w-full max-w-[860px] flex-col border-l border-line bg-panel shadow-[-24px_0_48px_-24px_rgba(0,0,0,.45)] md:w-[78%]">
        <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-ink"><Table2 className="size-4" /></span>
          <div className="min-w-0 flex-1">
            <h2 className="truncate font-mono text-[13px] font-semibold text-ink" title={name}>{name}</h2>
            <p className="text-[11px] text-muted">
              {target.source === 'supabase' ? 'Supabase table' : 'MongoDB collection'}
              {data ? ` · showing ${rows.length}${total ? ` of ${total}` : ''} ${target.source === 'supabase' ? 'rows' : 'newest documents'}` : ''}
            </p>
          </div>
          <div className="flex overflow-hidden rounded-lg ring-1 ring-inset ring-black/10">
            {[['table', Table2], ['json', Braces]].map(([id, Icon]) => (
              <button key={id} type="button" onClick={() => setMode(id)} title={id === 'table' ? 'As a table' : 'As JSON'}
                      className={cn('grid h-7 w-8 place-items-center', mode === id ? 'bg-accent text-ink' : 'text-muted hover:bg-black/5')}>
                <Icon className="size-3.5" />
              </button>
            ))}
          </div>
          <button type="button" onClick={load} disabled={state.loading} title="Read again"
                  className="grid size-7 place-items-center rounded-lg text-muted ring-1 ring-inset ring-black/10 hover:bg-black/5 disabled:opacity-40">
            <RefreshCw className={cn('size-3.5', state.loading && 'animate-spin')} />
          </button>
          <button type="button" onClick={copy} disabled={!rows.length} title="Copy these rows as JSON"
                  className="grid size-7 place-items-center rounded-lg text-muted ring-1 ring-inset ring-black/10 hover:bg-black/5 disabled:opacity-40">
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          </button>
          <button type="button" onClick={onClose} title="Close (Esc)"
                  className="grid size-7 place-items-center rounded-lg text-muted ring-1 ring-inset ring-black/10 hover:bg-black/5">
            <X className="size-3.5" />
          </button>
        </header>

        {data?.masked?.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 border-b border-line bg-warn/[.06] px-4 py-2 text-[11px] text-muted">
            Hidden because they hold credentials: {data.masked.map(field => <Pill key={field} tone="warn">{field}</Pill>)}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-auto">
          {state.loading && !data ? (
            <div className="space-y-2 p-4">
              <p className="flex items-center gap-2 text-[12px] text-muted"><Loader2 className="size-3.5 animate-spin" /> Reading {name}…</p>
              {[88, 72, 94, 60, 80].map((w, i) => <div key={i} className="h-3 animate-pulse rounded bg-black/[.07]" style={{ width: `${w}%` }} />)}
            </div>
          ) : state.error ? (
            <div className="p-4"><Note tone="bad">{state.error}</Note></div>
          ) : !rows.length ? (
            <p className="px-4 py-10 text-center text-[12px] text-muted">{target.source === 'supabase' ? 'This table is empty.' : 'This collection is empty.'}</p>
          ) : mode === 'json' ? (
            <pre className="whitespace-pre-wrap break-words p-4 font-mono text-[11px] leading-[1.55] text-ink">{JSON.stringify(rows, null, 2)}</pre>
          ) : (
            <table className="w-max min-w-full border-collapse text-left text-[11.5px]">
              <thead className="sticky top-0 z-10 bg-panel">
                <tr className="border-b border-line">
                  <th className="px-3 py-2 text-right font-mono text-[10px] font-semibold text-muted2">#</th>
                  {columns.map(col => (
                    <th key={col.name} className="whitespace-nowrap px-3 py-2 align-bottom">
                      <span className="block text-[11px] font-semibold text-ink">{col.name}</span>
                      {col.type && <span className="block font-mono text-[9.5px] font-normal text-muted2">{col.type}</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i} className="border-b border-black/[.04] align-top hover:bg-black/[.025]">
                    <td className="px-3 py-1.5 text-right font-mono text-[10px] text-muted2">{i + 1}</td>
                    {columns.map(col => <td key={col.name} className="px-3 py-1.5 text-ink"><Cell value={row[col.name]} /></td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <footer className="border-t border-line px-4 py-2 text-[10.5px] text-muted2">
          Read-only. {target.source === 'supabase' ? 'Read with the Supabase CLI (db query).' : "Read with the project's own MongoDB driver."}
        </footer>
      </aside>
    </div>
  )
}
