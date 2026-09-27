'use client'

/** Displays SRS revision history and provides prompt input to request document revisions. */
import { useEffect, useRef, useState } from 'react'
import { ArrowUp, History, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { loadSrsView } from '@/lib/srs-view'
import { Button, TextArea } from '../ui'
import { cn } from '@/lib/utils'

export function SrsRevisions({ srsId, onRevised, onRequestChange, onPickVersion, current, className, working, refreshKey }) {
  const addLog = useStore(s => s.addLog)
  const [versions, setVersions] = useState([])
  const [prompt, setPrompt] = useState('')
  const [thread, setThread] = useState([])
  const [busy, setBusy] = useState('')
  const [waited, setWaited] = useState(0)
  const box = useRef(null)

  async function load() {
    if (!srsId) return
    try {
      const spec = await loadSrsView(srsId)
      const vers = spec?.versions || []
      setVersions(vers)

      // Reconstruct and preserve chat stream from saved versions so prompts are never lost
      if (vers.length > 1) {
        setThread(prev => {
          if (prev.length > 0) return prev
          const reconstructed = []
          for (const v of vers) {
            if (v.prompt || (v.label && v.label.startsWith('Customized:'))) {
              const userPrompt = v.prompt || v.label.replace(/^Customized:\s*/, '')
              reconstructed.push({ role: 'you', text: userPrompt })
              const diffText = (v.diff_summary || []).join('\n') || 'The specification was updated.'
              reconstructed.push({ role: 'srs', text: diffText, version: v.version })
            }
          }
          if (reconstructed.length && THREAD_KEY) {
            try { localStorage.setItem(THREAD_KEY, JSON.stringify(reconstructed.slice(-60))) } catch { }
          }
          return reconstructed.length ? reconstructed : prev
        })
      }
    } catch {
      // A project whose specification cannot be read still shows its composer;
      // the list is the part that is missing, and it says so by being empty.
    }
  }

  useEffect(() => { load() }, [srsId, refreshKey])

  useEffect(() => {
    if (!busy) return
    setWaited(0)
    const tick = setInterval(() => setWaited(w => w + 1), 1000)
    return () => clearInterval(tick)
  }, [busy])

  // Persist the chat thread per srsId so user prompts are not lost on reload.
  const THREAD_KEY = srsId ? `srs-thread:${srsId}` : null

  useEffect(() => {
    if (!THREAD_KEY) return
    try {
      const saved = JSON.parse(localStorage.getItem(THREAD_KEY) || '[]')
      if (Array.isArray(saved) && saved.length) setThread(saved)
    } catch { /* corrupt entry – ignore */ }
  }, [THREAD_KEY])

  function appendThread(msg) {
    setThread(prev => {
      const next = [...prev, msg]
      if (THREAD_KEY) {
        try { localStorage.setItem(THREAD_KEY, JSON.stringify(next.slice(-60))) } catch { }
      }
      return next
    })
  }

  async function revise() {
    const text = prompt.trim()
    if (!text || busy || !srsId) return
    setPrompt('')
    onPickVersion?.(null)
    appendThread({ role: 'you', text })
    setBusy(onRequestChange ? 'verifying' : 'revising')
    try {
      if (onRequestChange) {
        const prepared = await onRequestChange(text)
        if (prepared?.answer) {
          const answer = prepared.answer
          const said = answer?.diff_summary || []
          appendThread({ role: 'srs', text: said.length ? said.join('\n') : 'The specification was updated.', version: answer?.version })
          addLog('INFO', `SRS revised — v${answer?.version || '?'}`)
          await load()
          await onRevised?.(answer, text)
        } else if (prepared?.started) {
          appendThread({ role: 'status', text: 'SRS validated. No Prototype or Builder dependency was detected, so the specification update started without an unnecessary popup.' })
        } else {
          appendThread({ role: 'status', text: 'SRS validated. Review the detected Prototype/Builder impact in the approval popup; approved branches will start together.' })
        }
      } else {
        const answer = await api.srs(`/projects/${srsId}/customize`, { prompt: text })
        const said = answer?.diff_summary || []
        appendThread({
          role: 'srs',
          text: said.length ? said.join('\n') : 'The specification was updated.',
          version: answer?.version,
        })
        addLog('INFO', `SRS revised — v${answer?.version || '?'}`)
        await load()
        await onRevised?.(answer, text)
      }
    } catch (e) {
      appendThread({ role: 'error', text: e.message })
    } finally {
      setBusy('')
    }
  }

  return (
    <aside className={cn('flex min-h-0 flex-col overflow-hidden', className)}>
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <History className="size-3.5 text-accent" />
        <span className="font-display text-[12px] font-bold uppercase tracking-wider text-ink">Revisions</span>
        <span className="flex-1" />
        <span className="rounded-full bg-panel2 px-2 py-0.5 font-mono text-[10px] text-muted">{versions.length}</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {versions.map((v, i) => (
          <button key={v.id || i}
            onClick={() => onPickVersion?.(i === versions.length - 1 ? null : v)}
            disabled={!onPickVersion}
            className={cn('mb-1.5 w-full rounded-none border px-3 py-2 text-left transition-all',
              current === v.version
                ? 'border-accent/40 bg-accent text-ink shadow-sm'
                : 'border-transparent bg-black/[.02] text-muted',
              onPickVersion && 'hover:bg-black/[.05] hover:text-ink')}>
            <span className="flex items-baseline gap-2">
              <span className={cn('font-mono text-[10.5px] font-semibold', current === v.version ? 'text-ink' : 'text-accent')}>v{v.version}</span>
              {v.source && (
                <span className="text-[9.5px] uppercase tracking-wider text-muted2">
                  {v.source}
                </span>
              )}
            </span>
            <span className="mt-0.5 block text-[11.5px] leading-snug">{v.prompt ? `Customized: ${v.prompt}` : (v.label || 'Revision')}</span>
            {/* Summarized change bullets recorded for this revision. */}
            {(v.diff_summary || []).length > 0 && (
              <span className="mt-1 block space-y-0.5">
                {v.diff_summary.slice(0, 4).map((line, n) => (
                  <span key={n} className="block text-[10.5px] leading-snug text-muted2">
                    · {line}
                  </span>
                ))}
                {v.diff_summary.length > 4 && (
                  <span className="block text-[10px] text-muted2">
                    and {v.diff_summary.length - 4} more
                  </span>
                )}
              </span>
            )}
          </button>
        ))}

        {thread.map((m, i) => (
          <div key={`t${i}`}
            className={cn('mb-2 rounded-none p-3 text-[11.5px] leading-relaxed',
              m.role === 'you' ? 'ml-6 border border-accent/30 bg-accent font-medium text-ink'
                : m.role === 'error' ? 'border border-red-500/30 bg-red-500/10 text-red-300'
                  : 'border border-black/5 bg-black/[.03] text-ink')}>
            {m.role === 'you' && (
              <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-ink">you</span>
            )}
            {m.text}
          </div>
        ))}

        {Boolean(busy) && (
          <div className="flex items-center gap-2 px-2.5 py-2 text-[11.5px] text-muted">
            <Loader2 className="size-3 animate-spin text-accent" />
            {busy === 'verifying' ? 'Verifying update scope…' : 'Rewriting specification…'} {waited}s
          </div>
        )}

        {working && !busy && (
          <div className="flex items-center gap-2 px-2.5 py-2 text-[11.5px] text-muted">
            <Loader2 className="size-3 animate-spin text-accent" />
            Carrying the change into the prototype and the app…
          </div>
        )}
      </div>

      <div className="border-t border-black/10 bg-black/20 p-3">
        <TextArea value={prompt} rows={3} ref={box} disabled={Boolean(busy) || working || !srsId}
          placeholder="Describe a change — “add a refunds page only the manager can open”…"
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) revise() }}
          className="w-full resize-none rounded-none border border-black/10 bg-black/[.04] p-2.5 text-[12px]
                     leading-relaxed text-ink caret-accent outline-none focus:border-accent/50
                     placeholder:text-muted2 disabled:opacity-50" />
        <div className="mt-2 flex items-center gap-2">
          {/* The diagrams really are redrawn on every revision — `customize`
              runs the diagram node after the edit — so this says what happens. */}
          <span className="flex-1 font-mono text-[9.5px] text-muted2">
            {working ? 'updating the prototype and the app…' : 'diagrams update too'}
          </span>
          <Button variant="solid" size="icon"
            className="size-7 rounded-none bg-accent text-ink shadow hover:bg-accent"
            disabled={!prompt.trim() || Boolean(busy) || working || !srsId} onClick={revise}>
            {busy || working ? <Loader2 className="size-3.5 animate-spin" /> : <ArrowUp className="size-3.5" />}
          </Button>
        </div>
      </div>
    </aside>
  )
}

export default SrsRevisions
