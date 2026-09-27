'use client'

/**
 * One command line tool's answer, live: opening it runs the command in the project's folder and shows the output as it
 * is written. A command that follows (logs) keeps streaming until stopped; the others run again every few seconds while
 * the page is open, so what is on screen is what the provider says now.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, Copy, Loader2, Play, Square, Terminal } from 'lucide-react'

import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

const POLL_MS = 600
const REFRESH_MS = 15000

const STATUS = {
  starting: { label: 'Starting', tone: 'text-[#6B7280]' },
  running: { label: 'Running', tone: 'text-[#BFB9FF]' },
  done: { label: 'Finished', tone: 'text-ink' },
  failed: { label: 'Failed', tone: 'text-[#FF5630]' },
  stopped: { label: 'Stopped', tone: 'text-[#6B7280]' },
  timeout: { label: 'Timed out', tone: 'text-[#FFAB00]' },
  gone: { label: 'Gone', tone: 'text-[#6B7280]' },
}

export default function CliMonitor({ project, item }) {
  const [display, setDisplay] = useState(item.display)
  const [lines, setLines] = useState([])
  const [state, setState] = useState({ status: 'starting', exit: null, seconds: 0 })
  const [auto, setAuto] = useState(!item.follow)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const job = useRef({ id: '', since: 0 })
  const poll = useRef(null)
  const again = useRef(null)
  const alive = useRef(true)
  const fresh = useRef([])
  const view = useRef(null)
  const atBottom = useRef(true)
  const autoRef = useRef(auto)
  autoRef.current = auto

  const stopJob = useCallback(() => {
    clearTimeout(poll.current)
    const id = job.current.id
    job.current = { id: '', since: 0 }
    if (id) api.cliMonitorStop(id).catch(() => {})
  }, [])

  /** Run it. `keep` leaves what is on screen until the new answer is complete (a refresh, not a new look). */
  const run = useCallback(async (keep = false) => {
    clearTimeout(again.current)
    stopJob()
    setError('')
    if (keep) { setRefreshing(true); fresh.current = [] }
    else { setLines([]); fresh.current = []; setState({ status: 'starting', exit: null, seconds: 0 }) }
    let started
    try {
      started = await api.cliMonitorStart(project, item.id)
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
      } catch (e) {
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
      job.current = { id: '', since: 0 }
      if (autoRef.current && !item.follow) again.current = setTimeout(() => run(true), REFRESH_MS)
    }
    tick()
  }, [project, item.id, item.follow, stopJob])

  // Opening it runs it; leaving it (or choosing another) stops it, so nothing is left running behind the page.
  useEffect(() => {
    alive.current = true
    run(false)
    return () => { alive.current = false; clearTimeout(again.current); stopJob() }
  }, [run, stopJob])

  useEffect(() => {
    if (!auto) clearTimeout(again.current)
    else if (state.status !== 'running' && state.status !== 'starting' && !item.follow) {
      clearTimeout(again.current)
      again.current = setTimeout(() => run(true), REFRESH_MS)
    }
  }, [auto])            // eslint-disable-line react-hooks/exhaustive-deps

  // Follow the end of the output unless the reader has scrolled up.
  useEffect(() => {
    const el = view.current
    if (el && atBottom.current) el.scrollTop = el.scrollHeight
  }, [lines])

  const running = state.status === 'running' || state.status === 'starting'
  const status = STATUS[state.status] || STATUS.done
  const copy = async () => {
    try { await navigator.clipboard.writeText(lines.join('\n')); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* no clipboard */ }
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-[rgba(145,158,171,0.16)] bg-[#F2F0EF] shadow-[0_0_2px_0_rgba(145,158,171,0.2),0_12px_24px_-4px_rgba(0,0,0,0.16)]">
      <div className="flex flex-wrap items-center gap-2 border-b border-[rgba(145,158,171,0.14)] bg-[#F2F0EF] px-3.5 py-2.5">
        <Terminal className="size-3.5 shrink-0 text-[#6B7280]" />
        <code className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-ink" title={display}>$ {display}</code>
        <span className={cn('flex shrink-0 items-center gap-1.5 text-[11px] font-semibold', status.tone)}>
          {running || refreshing ? <Loader2 className="size-3 animate-spin" /> : state.status === 'done' ? <Check className="size-3" /> : null}
          {status.label}
          {state.status === 'failed' && state.exit != null ? ` · exit ${state.exit}` : ''}
          {state.seconds ? <span className="font-mono font-normal text-[#6B7280]">{state.seconds}s</span> : null}
        </span>
      </div>

      <div ref={view} onScroll={e => { const el = e.currentTarget; atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40 }}
           className="max-h-[62vh] min-h-[220px] overflow-auto px-3.5 py-3">
        {error && <p className="mb-2 text-[12px] text-[#FF5630]">{error}</p>}
        <pre className="whitespace-pre-wrap break-words font-mono text-[11.5px] leading-[1.55] text-ink">
          {lines.length ? lines.join('\n') : (running ? 'Waiting for the first line…' : error ? '' : '(no output)')}
        </pre>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-[rgba(145,158,171,0.14)] bg-[#F2F0EF] px-3 py-2">
        {running ? (
          <button type="button" onClick={() => { stopJob(); setState(s => ({ ...s, status: 'stopped' })); setRefreshing(false) }}
                  className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-[rgba(145,158,171,0.2)] px-2.5 text-[11px] font-semibold text-ink hover:bg-black/5">
            <Square className="size-3" /> Stop
          </button>
        ) : (
          <button type="button" onClick={() => run(false)}
                  className="inline-flex h-7 items-center gap-1.5 rounded-lg bg-[#BFB9FF] px-2.5 text-[11px] font-semibold text-ink hover:bg-[#9B94E8]">
            <Play className="size-3" /> Run again
          </button>
        )}
        <button type="button" onClick={copy} disabled={!lines.length}
                className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-[rgba(145,158,171,0.2)] px-2.5 text-[11px] font-semibold text-ink hover:bg-black/5 disabled:opacity-40">
          {copied ? <Check className="size-3 text-ink" /> : <Copy className="size-3" />} {copied ? 'Copied' : 'Copy'}
        </button>
        {!item.follow && (
          <label className="ml-1 flex cursor-pointer items-center gap-1.5 text-[11px] text-[#6B7280]">
            <input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)} className="accent-[#BFB9FF]" />
            Refresh every {REFRESH_MS / 1000} s
          </label>
        )}
        {item.follow && <span className="ml-1 text-[11px] text-[#6B7280]">Streams until you stop it or leave this page.</span>}
        <span className="ml-auto font-mono text-[10.5px] text-[#6B7280]">{lines.length} line{lines.length === 1 ? '' : 's'}</span>
      </div>
    </div>
  )
}
