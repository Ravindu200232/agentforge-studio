'use client'

import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, HelpCircle, Loader2, PenLine } from 'lucide-react'
import { Empty } from '../ui'
import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { cn } from '@/lib/utils'

/**
 * The specification's open decisions, one question each: choose an answer (the first keeps what the specification assumed) or
 * write your own. A settled decision leaves the list and the "decisions needed" count goes down; an answer that could not be
 * written into the specification comes back here, saying so, to be answered again.
 */
export default function Decisions({ srs }) {
  const openProject = useStore(s => s.project)
  const project = srs?.project || openProject || ''
  const stamp = useStore(s => s.srsStamp[project] || 0)
  const [data, setData] = useState(null)
  const [preparing, setPreparing] = useState(false)
  const [problem, setProblem] = useState('')
  const [picked, setPicked] = useState({})        // id -> option index
  const [typed, setTyped] = useState({})          // id -> own words
  const [saving, setSaving] = useState('')

  const read = useCallback(async () => {
    if (!project) return null
    const listing = await api.srs(`/projects/${encodeURIComponent(project)}/decisions`)
    setData(listing)
    return listing
  }, [project])

  // The first look also has the questions written for the decisions that have none yet (a model writes them, once).
  useEffect(() => {
    let alive = true
    read().then(listing => {
      if (!alive || !listing?.open?.some(d => (d.options || []).length < 2)) return
      setPreparing(true)
      api.srs(`/projects/${encodeURIComponent(project)}/decisions`, {})
        .then(next => { if (alive) setData(next) })
        .catch(e => { if (alive) setProblem(e.message) })
        .finally(() => { if (alive) setPreparing(false) })
    }).catch(e => { if (alive) setProblem(e.message) })
    return () => { alive = false }
  }, [project, read])

  // Something changed the specification (an answer was written in, or could not be): look again.
  useEffect(() => { if (stamp) read().catch(() => {}) }, [stamp, read])

  async function save(decision) {
    const own = (typed[decision.id] || '').trim()
    const index = picked[decision.id]
    const answer = own || (index != null ? decision.options[index] : '')
    if (!answer) return
    setSaving(decision.id)
    setProblem('')
    try {
      const next = await api.srs(`/projects/${encodeURIComponent(project)}/decisions/${encodeURIComponent(decision.id)}`,
        { answer, option: own ? null : index })
      setData(next)
      setPicked(p => ({ ...p, [decision.id]: undefined }))
      setTyped(t => ({ ...t, [decision.id]: '' }))
    } catch (e) {
      setProblem(e.message || 'The answer could not be saved.')
    }
    setSaving('')
  }

  if (!srs?.have?.document) return <Empty>No specification has been adopted yet for this project.</Empty>
  if (!data) return <Empty>{problem || 'Reading the decisions…'}</Empty>

  const open = data.open || []
  const settled = data.settled || []

  return (
    <div className="mx-auto w-full max-w-[920px] space-y-5 pb-16 text-ink">
      <header className={cn('rounded-2xl border p-5',
        open.length ? 'border-amber-500/25 bg-amber-500/[.07]' : 'border-emerald-500/25 bg-emerald-500/[.07]')}>
        <div className="flex items-center gap-2">
          {open.length ? <HelpCircle className="size-4 text-amber-600" /> : <CheckCircle2 className="size-4 text-emerald-600" />}
          <span className="text-[10px] font-bold uppercase tracking-[.14em] text-muted2">Decisions</span>
        </div>
        <p className="mt-2 font-display text-[19px] font-bold">
          {open.length ? `${open.length} decision${open.length === 1 ? '' : 's'} needed` : 'Every decision is settled'}
        </p>
        <p className="mt-1 text-[12px] leading-relaxed text-muted">
          {open.length
            ? 'Choose an answer for each one, or write your own. The first answer keeps what the specification assumed.'
            : 'The specification follows your answers.'}
        </p>
        {preparing && (
          <p className="mt-2 flex items-center gap-1.5 text-[11.5px] text-muted">
            <Loader2 className="size-3 animate-spin" /> Writing the questions…
          </p>
        )}
        {problem && <p className="mt-2 text-[11.5px] text-bad">{problem}</p>}
      </header>

      {open.map(decision => {
        const own = (typed[decision.id] || '').trim()
        const ready = Boolean(own) || picked[decision.id] != null
        return (
          <section key={decision.id} className="rounded-2xl border border-line bg-panel p-5 shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-panel2 px-1.5 py-0.5 font-mono text-[10.5px] text-muted">{decision.id}</span>
              {decision.area && <span className="text-[11px] font-semibold uppercase tracking-[.1em] text-muted2">{decision.area}</span>}
            </div>
            <h3 className="mt-2 text-[14.5px] font-semibold leading-snug">{decision.question}</h3>
            {decision.issue && decision.issue !== decision.question && (
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{decision.issue}</p>
            )}
            {decision.error && <p className="mt-2 text-[12px] leading-relaxed text-amber-700">{decision.error}</p>}

            <div className="mt-3 space-y-1.5">
              {(decision.options || []).map((option, index) => (
                <button key={index} type="button" onClick={() => {
                  setPicked(p => ({ ...p, [decision.id]: index }))
                  setTyped(t => ({ ...t, [decision.id]: '' }))
                }}
                        className={cn('flex w-full items-start gap-2.5 rounded-xl border px-3 py-2 text-left text-[12.5px] leading-relaxed transition-colors',
                          picked[decision.id] === index && !own ? 'border-accent bg-accent/10 text-ink' : 'border-line2 bg-panel hover:border-accent/60')}>
                  <span className={cn('mt-1 size-3 shrink-0 rounded-full border',
                    picked[decision.id] === index && !own ? 'border-accent bg-accent' : 'border-muted2')} />
                  <span className="min-w-0">
                    {option}
                    {index === 0 && <span className="ml-1.5 text-[10.5px] text-muted2">(what the specification assumed)</span>}
                  </span>
                </button>
              ))}
            </div>

            <label className="mt-3 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[.12em] text-muted2">
              <PenLine className="size-3" /> Or write your own answer
            </label>
            <textarea value={typed[decision.id] || ''} rows={2}
                      onChange={e => setTyped(t => ({ ...t, [decision.id]: e.target.value }))}
                      className="mt-1 w-full resize-y rounded-xl border border-line bg-panel px-3 py-2 text-[12.5px] text-ink outline-none placeholder:text-muted2 focus:border-accent/60"
                      placeholder="Your answer, in your own words" />

            <div className="mt-3 flex justify-end">
              <button type="button" disabled={!ready || saving === decision.id} onClick={() => save(decision)}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-3.5 py-2 text-[12px] font-semibold text-ink transition-colors hover:bg-press disabled:opacity-40">
                {saving === decision.id && <Loader2 className="size-3.5 animate-spin" />}
                Save answer
              </button>
            </div>
          </section>
        )
      })}

      {settled.length > 0 && (
        <section className="rounded-2xl border border-line bg-panel p-5">
          <h3 className="text-[11px] font-bold uppercase tracking-[.14em] text-muted2">Settled ({settled.length})</h3>
          <ul className="mt-2 divide-y divide-line">
            {settled.map(decision => (
              <li key={decision.id} className="py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-panel2 px-1.5 py-0.5 font-mono text-[10.5px] text-muted">{decision.id}</span>
                  <span className="text-[12.5px] font-medium">{decision.question}</span>
                </div>
                <p className="mt-1 flex items-start gap-1.5 text-[12px] text-muted">
                  <CheckCircle2 className="mt-0.5 size-3 shrink-0 text-emerald-600" />
                  <span>{decision.answer}</span>
                </p>
                {decision.applying && (
                  <p className="mt-1 flex items-center gap-1.5 text-[11px] text-muted2">
                    <Loader2 className="size-3 animate-spin" /> Being written into the specification…
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
