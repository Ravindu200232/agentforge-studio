'use client'

/**
 * Ports: every part of the app its preview starts (the client a browser opens, a gateway, each service, or just the one
 * server of a single-server app), its port, and whether something listens there now. A part that is not listening has
 * a Start button: it sends the agent a silent request, with no plan, to start that part with its own commands and fix
 * what stops it; the Studio then restarts the preview and checks the part answers.
 */

import { useCallback, useEffect, useState } from 'react'
import { Bot, EthernetPort, ExternalLink, Loader2, Play, RefreshCw } from 'lucide-react'

import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { send } from '@/lib/ws'
import { cn } from '@/lib/utils'

const POLL_MS = 2000
const KIND = { client: 'Client', gateway: 'Gateway', service: 'Service', server: 'API server', app: 'App' }

function Dot({ state }) {
  return <span className={cn('size-2.5 shrink-0 rounded-full',
    state === 'up' ? 'bg-ok' : state === 'starting' ? 'animate-pulse bg-warn' : 'bg-bad')} />
}

export default function PortsPane() {
  const project = useStore(s => s.project)
  const busy = useStore(s => s.busy)
  const busyProject = useStore(s => s.busyProject)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [asked, setAsked] = useState('')
  const [opening, setOpening] = useState(false)
  const working = busy && (!busyProject || busyProject === project)

  const read = useCallback(async () => {
    if (!project) return
    try { setData(await api.previewPorts(project)); setError('') } catch (e) { setError(e.message || 'Could not read the ports.') }
  }, [project])

  useEffect(() => {
    let alive = true
    let timer
    const tick = async () => { await read(); if (alive) timer = setTimeout(tick, POLL_MS) }
    tick()
    return () => { alive = false; clearTimeout(timer) }
  }, [read])

  useEffect(() => { if (!working) setAsked('') }, [working])

  /** The silent request: no chat message, no plan; the agent starts this part and fixes what stops it. */
  function startPart(row) {
    if (working) return
    const st = useStore.getState()
    setAsked(row.name)
    st.setBusy(true)
    st.addLog('INFO', `The agent is starting ${row.name === 'app' ? 'the app' : row.name} and fixing what stops it`)
    send({ type: 'preview_start', project, agent: 'developer', part: row.name,
           model: st.models.builder || st.models.agent, builder_model: st.models.builder || st.models.agent,
           thinking_level: st.thinkingLevel })
  }

  async function startApp() {
    setOpening(true)
    try { useStore.getState().setRuntime(await api.open(project)) } catch (e) { setError(e.message) }
    setOpening(false)
    read()
  }

  if (!project) return <div className="min-h-0 flex-1 p-5 text-[12px] text-muted">Open a project first.</div>

  const rows = data?.ports || []
  const status = data?.status || 'stopped'
  const up = rows.filter(row => row.listening).length
  const stateOf = row => (row.listening ? 'up' : status === 'starting' ? 'starting' : 'down')

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top_right,rgba(191,185,255,.08),transparent_30%)]">
      <div className="mx-auto max-w-[1080px] space-y-4 p-5">
        <header className="flex flex-wrap items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-ink"><EthernetPort className="size-5" /></span>
          <div className="min-w-0 flex-1">
            <h1 className="text-[17px] font-semibold text-ink">Ports</h1>
            <p className="mt-0.5 max-w-[720px] text-[12px] leading-relaxed text-muted">
              Every part of this app the preview starts, and whether it is listening now. Start on a part that is not sends the
              agent a silent request — no chat message, no plan — to start it with its own commands and fix what stops it;
              the preview then restarts.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {status === 'stopped' && (
              <button type="button" onClick={startApp} disabled={opening || working} title="Start the whole app the usual way"
                      className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-3 text-[11.5px] font-semibold text-ink disabled:opacity-50">
                {opening ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />} Start app
              </button>
            )}
            <button type="button" onClick={read} title="Look again"
                    className="grid size-8 place-items-center rounded-lg text-muted ring-1 ring-inset ring-black/10 hover:bg-black/5">
              <RefreshCw className="size-3.5" />
            </button>
          </div>
        </header>

        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          {[
            ['App', <span key="s" className="capitalize">{status}</span>, status === 'running' ? 'text-ok' : status === 'failed' ? 'text-bad' : 'text-ink'],
            ['Listening', `${up} / ${rows.length || 0}`, rows.length && up === rows.length ? 'text-ok' : up ? 'text-warn' : 'text-bad'],
            ['Address', data?.url ? data.url.replace(/^https?:\/\//, '').replace(/\/$/, '') : '—', 'text-ink'],
            ['Parts', rows.length || '—', 'text-ink'],
          ].map(([label, value, tone]) => (
            <div key={label} className="rounded-xl border border-black/[.07] bg-panel px-3.5 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[.12em] text-muted">{label}</p>
              <p className={cn('mt-1 truncate text-[17px] font-semibold', tone)}>{value}</p>
            </div>
          ))}
        </div>

        {error && <p className="rounded-xl border border-bad/25 bg-bad/[.06] px-3.5 py-2.5 text-[12px] text-bad">{error}</p>}
        {status === 'failed' && data?.detail && (
          <p className="rounded-xl border border-bad/25 bg-bad/[.06] px-3.5 py-2.5 text-[12px] text-bad">{data.detail}</p>
        )}
        {data && !data.current && rows.length > 1 && status !== 'stopped' && (
          <p className="rounded-xl border border-warn/30 bg-warn/[.07] px-3.5 py-2.5 text-[11.5px] text-muted">
            These parts are from an earlier run: the app's runner has not listed this run's parts yet.
          </p>
        )}

        <div className="overflow-hidden rounded-2xl border border-black/[.07] bg-panel shadow-[0_12px_24px_-12px_rgba(0,0,0,0.35)]">
          {!data ? (
            <p className="flex items-center gap-2 px-4 py-6 text-[12px] text-muted"><Loader2 className="size-3.5 animate-spin" /> Looking at the ports…</p>
          ) : rows.map(row => {
            const state = stateOf(row)
            const mine = working && asked === row.name
            return (
              <div key={`${row.name}:${row.port}`} className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-black/[.05] px-4 py-3 last:border-0">
                <Dot state={state} />
                <div className="min-w-[180px] flex-1">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[13px] font-semibold text-ink">{row.name}</span>
                    <span className="rounded-full bg-black/[.06] px-2 py-[1px] text-[10px] font-semibold text-muted">{KIND[row.kind] || row.kind}</span>
                    {row.main && <span className="rounded-full bg-accent/20 px-2 py-[1px] text-[10px] font-semibold text-deep">browser opens this</span>}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-[10.5px] text-muted2" title={row.command ? `${row.cwd} · ${row.command}` : ''}>
                    {row.command ? `${row.cwd} · ${row.command}` : 'the preview command'}
                  </p>
                </div>
                <span className="w-[86px] font-mono text-[15px] font-semibold text-ink">{row.port ? `:${row.port}` : '—'}</span>
                <span className={cn('w-[92px] text-[11.5px] font-semibold', state === 'up' ? 'text-ok' : state === 'starting' ? 'text-warn' : 'text-bad')}>
                  {state === 'up' ? 'Listening' : state === 'starting' ? 'Starting…' : 'Not started'}
                </span>
                <span className="w-[72px] font-mono text-[10.5px] text-muted2">{row.pid ? `pid ${row.pid}` : ''}</span>
                <div className="flex w-[150px] justify-end">
                  {row.listening ? (
                    <a href={row.url} target="_blank" rel="noreferrer"
                       className="inline-flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-[11px] font-semibold text-ink ring-1 ring-inset ring-black/10 hover:bg-black/5">
                      <ExternalLink className="size-3" /> Open
                    </a>
                  ) : mine ? (
                    <span className="inline-flex h-7 items-center gap-1.5 text-[11px] font-semibold text-deep">
                      <Loader2 className="size-3 animate-spin" /> Agent is starting it
                    </span>
                  ) : state === 'starting' ? null : (
                    <button type="button" onClick={() => startPart(row)} disabled={working}
                            title={working ? 'This project is already working — wait for it to finish' : `Ask the agent to start ${row.name} and fix what stops it`}
                            className="inline-flex h-7 items-center gap-1.5 rounded-lg bg-accent px-2.5 text-[11px] font-semibold text-ink hover:bg-press disabled:opacity-40">
                      <Bot className="size-3" /> Start
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {data?.written_at && (
          <p className="px-1 text-[10.5px] text-muted2">Parts as the app's runner listed them at {new Date(data.written_at).toLocaleString()}.</p>
        )}
      </div>
    </div>
  )
}
