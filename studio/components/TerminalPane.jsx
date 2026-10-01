'use client'

/**
 * The project's terminal. **App** is the running app's own output (the preview process the Studio started), live, in
 * colour, with Start / Restart / Stop. **Shell** runs what you type in the project's folder, with the same variables
 * the app's build and preview get, one command after another the way a terminal does. Output is masked on the server:
 * credentials print as `<hidden>`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Copy, CornerDownLeft, Eraser, ExternalLink, Loader2, Play, RotateCw, Square, SquareTerminal } from 'lucide-react'

import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { ansiLines, cssOf, plain } from '@/lib/ansi'
import { cn } from '@/lib/utils'

const APP_POLL_MS = 800
const SHELL_POLL_MS = 450
const MAX_TEXT = 400_000
const MARK = '── preview: '
const HISTORY = 60

const DOT = { running: 'bg-[#5fd38d]', starting: 'bg-[#f5c451] animate-pulse', failed: 'bg-[#ff6b6b]', stopped: 'bg-[#7f8796]' }

/** Output in colour, following the end unless the reader scrolled up. */
function Screen({ text, children, empty }) {
  const view = useRef(null)
  const bottom = useRef(true)
  const lines = useMemo(() => ansiLines(text), [text])
  useEffect(() => { const el = view.current; if (el && bottom.current) el.scrollTop = el.scrollHeight }, [lines, children])
  return (
    <div ref={view} onScroll={e => { const el = e.currentTarget; bottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48 }}
         className="min-h-0 flex-1 overflow-auto bg-[#0d1117] px-4 py-3 font-mono text-[12px] leading-[1.6] text-[#d8dee9]">
      {text ? lines.map((pieces, i) => (
        <div key={i} className={cn('min-h-[1.6em] whitespace-pre-wrap break-words', pieces.some(p => p.text.startsWith(MARK)) && 'mt-2 text-[#91c8ff]')}>
          {pieces.map((piece, j) => <span key={j} style={cssOf(piece.style)}>{piece.text}</span>)}
        </div>
      )) : !children && <p className="text-[#7f8796]">{empty}</p>}
      {children}
    </div>
  )
}

const Btn = ({ onClick, disabled, title, children, tone }) => (
  <button type="button" onClick={onClick} disabled={disabled} title={title}
          className={cn('inline-flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-[11px] font-semibold ring-1 ring-inset transition-colors disabled:opacity-40',
            tone === 'bad' ? 'text-[#ff8f8f] ring-[#ff6b6b]/40 hover:bg-[#ff6b6b]/10'
              : tone === 'go' ? 'bg-[#5fd38d]/15 text-[#8ce99a] ring-[#5fd38d]/40 hover:bg-[#5fd38d]/25'
                : 'text-[#d8dee9] ring-white/15 hover:bg-white/10')}>
    {children}
  </button>
)

// ---- App: the running app's output ------------------------------------------------------------------------------

function useAppLog(project, active) {
  const [log, setLog] = useState({ text: '', status: '', url: '', port: 0, detail: '', cwd: '' })
  const offset = useRef(-1)
  const timer = useRef(null)

  const read = useCallback(async () => {
    if (!project) return
    try {
      const since = offset.current
      const answer = await api.previewLog(project, since)
      offset.current = answer.next
      setLog(current => {
        // A fresh read (or a log that was replaced) starts over; otherwise the new lines are added.
        let text = since < 0 || answer.start !== since ? answer.text : current.text + answer.text
        const mark = text.lastIndexOf(MARK)
        if (mark > 0 && answer.text.includes(MARK)) text = text.slice(text.lastIndexOf('\n', mark) + 1)
        if (text.length > MAX_TEXT) text = text.slice(text.indexOf('\n', text.length - MAX_TEXT) + 1)
        return { text, status: answer.status, url: answer.url, port: answer.port, detail: answer.detail, cwd: answer.cwd }
      })
    } catch { /* the backend may be restarting: try again on the next tick */ }
  }, [project])

  useEffect(() => {
    offset.current = -1
    setLog({ text: '', status: '', url: '', port: 0, detail: '', cwd: '' })
  }, [project])

  useEffect(() => {
    if (!active) return
    let alive = true
    const tick = async () => { await read(); if (alive) timer.current = setTimeout(tick, APP_POLL_MS) }
    tick()
    return () => { alive = false; clearTimeout(timer.current) }
  }, [active, read])

  const clear = () => setLog(current => ({ ...current, text: '' }))
  return { ...log, clear, refresh: read }
}

function AppTab({ project, log }) {
  const runtime = useStore(s => s.runtimes[project])
  const [busy, setBusy] = useState('')
  const [copied, setCopied] = useState(false)
  const status = runtime?.status || log.status || 'stopped'
  const url = runtime?.previewUrl || runtime?.url || log.url

  async function act(kind) {
    setBusy(kind)
    try {
      if (kind !== 'start') useStore.getState().setRuntime(await api.stopPreview(project))
      if (kind !== 'stop') useStore.getState().setRuntime(await api.open(project))
    } catch (e) {
      useStore.getState().addLog('WARN', `Could not ${kind} the app: ${e.message}`)
    }
    setBusy('')
    log.refresh()
  }
  const copy = async () => {
    try { await navigator.clipboard.writeText(plain(log.text)); setCopied(true); setTimeout(() => setCopied(false), 1400) } catch { /* none */ }
  }
  const running = status === 'running' || status === 'starting'

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 border-b border-white/10 bg-[#161b22] px-3 py-2">
        <span className={cn('size-2 shrink-0 rounded-full', DOT[status] || DOT.stopped)} />
        <span className="text-[11.5px] font-semibold capitalize text-[#d8dee9]">{status}</span>
        {url && running && (
          <a href={url} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1 font-mono text-[11px] text-[#91c8ff] hover:underline">
            <span className="truncate">{url.replace(/^https?:\/\//, '')}</span><ExternalLink className="size-2.5 shrink-0" />
          </a>
        )}
        {status === 'failed' && log.detail && <span className="min-w-0 truncate text-[11px] text-[#ff8f8f]" title={log.detail}>{log.detail}</span>}
        <span className="flex-1" />
        {!running && <Btn tone="go" onClick={() => act('start')} disabled={Boolean(busy)} title="Start the app the way the preview does">
          {busy === 'start' ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />} Start</Btn>}
        {running && <Btn onClick={() => act('restart')} disabled={Boolean(busy)} title="Stop the app and start it again">
          {busy === 'restart' ? <Loader2 className="size-3 animate-spin" /> : <RotateCw className="size-3" />} Restart</Btn>}
        {running && <Btn tone="bad" onClick={() => act('stop')} disabled={Boolean(busy)} title="Stop this app's preview">
          {busy === 'stop' ? <Loader2 className="size-3 animate-spin" /> : <Square className="size-3" />} Stop</Btn>}
        <Btn onClick={log.clear} disabled={!log.text} title="Clear the screen (new output still shows)"><Eraser className="size-3" /> Clear</Btn>
        <Btn onClick={copy} disabled={!log.text} title="Copy the output">{copied ? <Check className="size-3" /> : <Copy className="size-3" />} Copy</Btn>
      </div>
      <Screen text={log.text} empty={running ? 'Waiting for the app to print something…' : 'The app is not running. Start it to see its output here.'} />
    </>
  )
}

// ---- Shell: commands typed in the project folder ------------------------------------------------------------------

function readHistory(project) {
  try { return JSON.parse(localStorage.getItem(`agentforge.terminal.${project}`) || '[]') } catch { return [] }
}
function keepHistory(project, list) {
  try { localStorage.setItem(`agentforge.terminal.${project}`, JSON.stringify(list.slice(-HISTORY))) } catch { /* not kept */ }
}

function ShellTab({ project, cwd, active }) {
  const [entries, setEntries] = useState([])
  const [input, setInput] = useState('')
  const [history, setHistory] = useState(() => readHistory(project))
  const [cursor, setCursor] = useState(-1)
  const box = useRef(null)
  const polls = useRef({})
  const running = entries.find(entry => entry.status === 'running' || entry.status === 'starting')

  useEffect(() => { if (active) box.current?.focus() }, [active])
  useEffect(() => () => Object.values(polls.current).forEach(clearTimeout), [])

  const patch = (id, change) => setEntries(list => list.map(entry => (entry.id === id ? { ...entry, ...(typeof change === 'function' ? change(entry) : change) } : entry)))

  async function run(e) {
    e?.preventDefault()
    const command = input.trim()
    if (!command || running) return
    if (command === 'clear' || command === 'cls') { setEntries([]); setInput(''); return }
    const next = [...history.filter(item => item !== command), command]
    setHistory(next); keepHistory(project, next); setCursor(-1); setInput('')
    const id = `${Date.now()}`
    setEntries(list => [...list, { id, command, text: '', status: 'starting', exit: null, seconds: 0, job: '' }])
    let started
    try {
      started = await api.terminalRun(project, command)
    } catch (error) {
      patch(id, { status: 'failed', text: `${error.message || 'Could not run that.'}\n` })
      return
    }
    patch(id, { job: started.job, status: 'running' })
    let since = 0
    const tick = async () => {
      let answer
      try { answer = await api.cliMonitorPoll(started.job, since) } catch { polls.current[id] = setTimeout(tick, SHELL_POLL_MS * 2); return }
      since = answer.next
      patch(id, entry => ({ text: entry.text + (answer.lines.length ? `${answer.lines.join('\n')}\n` : ''), status: answer.status,
                            exit: answer.exit_code, seconds: answer.seconds }))
      if (answer.status === 'running') polls.current[id] = setTimeout(tick, SHELL_POLL_MS)
      else delete polls.current[id]
    }
    tick()
  }

  function stop() {
    if (running?.job) api.cliMonitorStop(running.job).catch(() => {})
  }

  function key(e) {
    if (e.key === 'ArrowUp' && history.length) {
      e.preventDefault()
      const at = cursor < 0 ? history.length - 1 : Math.max(0, cursor - 1)
      setCursor(at); setInput(history[at])
    } else if (e.key === 'ArrowDown' && cursor >= 0) {
      e.preventDefault()
      const at = cursor + 1
      if (at >= history.length) { setCursor(-1); setInput('') } else { setCursor(at); setInput(history[at]) }
    } else if (e.key === 'c' && e.ctrlKey && running) {
      e.preventDefault(); stop()
    } else if (e.key === 'l' && e.ctrlKey) {
      e.preventDefault(); setEntries([])
    }
  }

  const prompt = `PS ${cwd || 'project'}>`
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 border-b border-white/10 bg-[#161b22] px-3 py-2 text-[11px] text-[#7f8796]">
        <span className="min-w-0 flex-1 truncate">Runs in <span className="font-mono text-[#d8dee9]">{cwd || 'the project folder'}</span> with the app's own variables · ↑ ↓ history · Ctrl+C stops · Ctrl+L clears</span>
        {running && <Btn tone="bad" onClick={stop} title="Stop the running command (Ctrl+C)"><Square className="size-3" /> Stop</Btn>}
        <Btn onClick={() => setEntries([])} disabled={!entries.length || Boolean(running)} title="Clear the screen (Ctrl+L)"><Eraser className="size-3" /> Clear</Btn>
      </div>
      <Screen text="" empty="">
        {!entries.length && <p className="text-[#7f8796]">Type a command below, for example <span className="text-[#d8dee9]">npm test</span>, <span className="text-[#d8dee9]">npm run build</span> or <span className="text-[#d8dee9]">git status</span>.</p>}
        {entries.map(entry => (
          <div key={entry.id} className="mb-2">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-[#5fd38d]">{prompt}</span>
              <span className="whitespace-pre-wrap break-all text-white">{entry.command}</span>
            </div>
            {ansiLines(entry.text.replace(/\n$/, '')).map((pieces, i) => (
              <div key={i} className="min-h-[1.6em] whitespace-pre-wrap break-words">
                {pieces.map((piece, j) => <span key={j} style={cssOf(piece.style)}>{piece.text}</span>)}
              </div>
            ))}
            <div className="text-[10.5px] text-[#7f8796]">
              {entry.status === 'running' || entry.status === 'starting'
                ? <span className="inline-flex items-center gap-1.5"><Loader2 className="size-3 animate-spin" /> running{entry.seconds ? ` · ${entry.seconds}s` : ''}</span>
                : <span className={entry.status === 'done' ? 'text-[#5fd38d]' : 'text-[#ff8f8f]'}>
                    {entry.status === 'done' ? '✓ done' : entry.status === 'stopped' ? '■ stopped' : entry.status === 'timeout' ? '⏱ timed out' : `✗ ${entry.exit != null ? `exit ${entry.exit}` : 'failed'}`}
                    {entry.seconds ? ` · ${entry.seconds}s` : ''}
                  </span>}
            </div>
          </div>
        ))}
      </Screen>
      <form onSubmit={run} className="flex items-center gap-2 border-t border-white/10 bg-[#0d1117] px-4 py-2.5 font-mono text-[12px]">
        <span className="max-w-[40%] shrink-0 truncate text-[#5fd38d]" title={prompt}>{prompt}</span>
        <input ref={box} value={input} onChange={e => { setInput(e.target.value); setCursor(-1) }} onKeyDown={key}
               disabled={Boolean(running)} spellCheck={false} autoComplete="off" aria-label="Command"
               placeholder={running ? 'A command is running — Ctrl+C or Stop to end it' : 'Type a command and press Enter'}
               className="min-w-0 flex-1 bg-transparent text-white caret-[#5fd38d] outline-none placeholder:text-[#4b5263] disabled:opacity-60" />
        <button type="submit" disabled={!input.trim() || Boolean(running)} title="Run (Enter)"
                className="grid size-7 place-items-center rounded-md text-[#d8dee9] ring-1 ring-inset ring-white/15 hover:bg-white/10 disabled:opacity-30">
          <CornerDownLeft className="size-3.5" />
        </button>
      </form>
    </>
  )
}

export default function TerminalPane({ hidden }) {
  const project = useStore(s => s.project)
  const [tab, setTab] = useState('app')
  const log = useAppLog(project, !hidden && Boolean(project))

  if (!project) return hidden ? null : <div className="min-h-0 flex-1 p-5 text-[12px] text-muted">Open a project first.</div>

  return (
    <div className={cn('flex min-h-0 flex-1 flex-col bg-[#0d1117]', hidden && 'hidden')}>
      <div className="flex h-[44px] shrink-0 items-center gap-1 border-b border-white/10 bg-[#161b22] px-2">
        <SquareTerminal className="mx-1.5 size-4 text-[#7f8796]" />
        {[['app', 'App output'], ['shell', 'Shell']].map(([id, label]) => (
          <button key={id} type="button" onClick={() => setTab(id)} aria-pressed={tab === id}
                  className={cn('h-8 rounded-lg px-3 text-[12px] font-semibold transition-colors',
                    tab === id ? 'bg-white/10 text-white' : 'text-[#7f8796] hover:bg-white/5 hover:text-[#d8dee9]')}>
            {label}
          </button>
        ))}
      </div>
      <div className={cn('flex min-h-0 flex-1 flex-col', tab !== 'app' && 'hidden')}><AppTab project={project} log={log} /></div>
      <div className={cn('flex min-h-0 flex-1 flex-col', tab !== 'shell' && 'hidden')}><ShellTab project={project} cwd={log.cwd} active={!hidden && tab === 'shell'} /></div>
    </div>
  )
}
