'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  ArrowRight, CalendarDays, Gift, HelpCircle, Loader2, RefreshCw, ShieldCheck, Smile, Sparkles, Users, Wand2,
} from 'lucide-react'
import { Empty } from '../ui'
import { api } from '@/lib/api'
import { useStore } from '@/lib/store'

/**
 * The specification told for someone who is not technical: what the app is, who it is for, what you can do with it, a day with
 * it, how it feels to use, how it keeps things safe and what the business gets. A model writes it once from the specification
 * (`srs_agent/plain_summary.py`); it is written again when the specification changes.
 */
export default function Overview({ srs, onSelectView }) {
  const openProject = useStore(s => s.project)
  const project = srs?.project || openProject || ''
  const doc = srs?.document || {}
  const open = (Array.isArray(doc.ambiguities) ? doc.ambiguities : []).filter(a => a?.needs_clarification).length
  const [summary, setSummary] = useState(null)
  const [writing, setWriting] = useState(false)
  const [problem, setProblem] = useState('')

  const write = useCallback(async (again = false) => {
    setWriting(true)
    setProblem('')
    try {
      const made = await api.srs(`/projects/${encodeURIComponent(project)}/plain-summary`, { again })
      if (made?.status === 'failed') setProblem(made.reason || 'The summary could not be written.')
      else setSummary(made)
    } catch (e) {
      setProblem(e.message || 'The summary could not be written.')
    }
    setWriting(false)
  }, [project])

  useEffect(() => {
    if (!project || !srs?.have?.document) return
    let alive = true
    api.srs(`/projects/${encodeURIComponent(project)}/plain-summary`)
      .then(kept => {
        if (!alive) return
        if (kept?.status === 'ready' || kept?.status === 'stale') setSummary(kept)
        if (kept?.status !== 'ready') write()
      })
      .catch(() => { if (alive) write() })
    return () => { alive = false }
  }, [project, srs?.have?.document, write])

  if (!srs?.have?.document) return <Empty>No specification has been adopted yet for this project.</Empty>

  const name = doc.app_summary?.app_name || doc.project_name || 'The app'

  if (!summary) {
    return (
      <div className="mx-auto flex max-w-[640px] flex-col items-center gap-3 py-20 text-center text-ink">
        {writing ? <Loader2 className="size-6 animate-spin text-accent" /> : <Wand2 className="size-6 text-accent" />}
        <p className="font-display text-[18px] font-bold">{writing ? `Explaining ${name} in plain words…` : 'No summary yet'}</p>
        <p className="text-[12.5px] text-muted">
          {problem || 'A short, plain explanation of the app is being written from the specification. It takes a minute.'}
        </p>
        {problem && !writing && <TryAgain onClick={() => write()} />}
      </div>
    )
  }

  return (
    <article className="mx-auto w-full min-w-0 max-w-[980px] space-y-8 pb-20 text-ink">
      {/* What it is */}
      <header className="relative overflow-hidden rounded-3xl border border-accent/25 bg-panel p-6 shadow-[0_24px_60px_-38px_rgba(0,0,0,.8)] sm:p-10">
        <div className="pointer-events-none absolute -right-28 -top-32 size-80 rounded-full bg-accent/15 blur-3xl" />
        <div className="relative z-10">
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[.18em] text-accent">
            <Sparkles className="size-3.5" /> {name}
          </div>
          <h2 className="mt-3 max-w-3xl font-display text-[26px] font-black leading-[1.15] tracking-[-.02em] sm:text-[32px]">
            {summary.headline}
          </h2>
          <div className="mt-5 max-w-3xl space-y-3.5">
            {(summary.story || []).map((paragraph, i) => (
              <p key={i} className="text-[14.5px] leading-[1.8] text-ink/90">{paragraph}</p>
            ))}
          </div>
          {(writing || summary.status === 'stale') && (
            <p className="mt-4 flex items-center gap-1.5 text-[11.5px] text-muted">
              <Loader2 className="size-3 animate-spin" /> The specification changed: this summary is being brought up to date.
            </p>
          )}
        </div>
      </header>

      {summary.people?.length > 0 && (
        <Part icon={Users} title="Who it is for">
          <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
            {summary.people.map((person, i) => (
              <div key={i} className="rounded-2xl border border-line bg-panel2/40 p-4">
                <p className="text-[14px] font-semibold">{person.who}</p>
                <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{person.does}</p>
              </div>
            ))}
          </div>
        </Part>
      )}

      {summary.what_you_can_do?.length > 0 && (
        <Part icon={Wand2} title="What you can do with it">
          <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(300px,1fr))]">
            {summary.what_you_can_do.map((area, i) => (
              <div key={i} className="rounded-2xl border border-line bg-panel p-5 shadow-sm">
                <p className="font-display text-[15px] font-bold">{area.area}</p>
                <ul className="mt-2.5 space-y-2">
                  {(area.points || []).map((point, j) => (
                    <li key={j} className="flex gap-2 text-[13px] leading-relaxed text-ink/90">
                      <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-accent" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Part>
      )}

      {summary.a_day_with_it?.length > 0 && (
        <Part icon={CalendarDays} title="A day with the app">
          <div className="space-y-3.5">
            {summary.a_day_with_it.map((day, i) => (
              <div key={i} className="rounded-2xl border border-line bg-panel2/30 p-5">
                <p className="font-display text-[15px] font-bold">{day.title}</p>
                <ol className="mt-3 space-y-2">
                  {(day.steps || []).map((step, j) => (
                    <li key={j} className="flex gap-3 text-[13px] leading-relaxed">
                      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent/15 text-[11px] font-bold text-accent">{j + 1}</span>
                      <span className="pt-0.5">{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </Part>
      )}

      {summary.how_it_feels?.length > 0 && (
        <Part icon={Smile} title="How it feels to use">
          <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
            {summary.how_it_feels.map((item, i) => (
              <div key={i} className="rounded-2xl border border-line bg-panel p-4">
                <p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">{item.topic}</p>
                <p className="mt-1.5 text-[13px] leading-relaxed">{item.plain}</p>
              </div>
            ))}
          </div>
        </Part>
      )}

      {summary.keeping_safe?.length > 0 && (
        <Part icon={ShieldCheck} title="Keeping things safe">
          <Points items={summary.keeping_safe} />
        </Part>
      )}

      {summary.what_the_business_gets?.length > 0 && (
        <Part icon={Gift} title="What the business gets">
          <Points items={summary.what_the_business_gets} />
        </Part>
      )}

      {open > 0 && (
        <button type="button" onClick={() => onSelectView?.('decisions')}
                className="flex w-full items-center gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/[.07] p-4 text-left transition-colors hover:border-amber-500/55">
          <HelpCircle className="size-5 shrink-0 text-amber-600" />
          <span className="min-w-0 flex-1">
            <span className="block text-[14px] font-semibold">
              {open} question{open === 1 ? ' is' : 's are'} still open
            </span>
            <span className="block text-[12px] text-muted">Answer them in Decisions so the app is built the way you want.</span>
          </span>
          <ArrowRight className="size-4 shrink-0 text-amber-700" />
        </button>
      )}

      <div className="flex justify-end">
        <button type="button" onClick={() => write(true)} disabled={writing}
                className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3 py-1.5 text-[11.5px] text-muted transition-colors hover:border-accent hover:text-accent disabled:opacity-40">
          {writing ? <Loader2 className="size-3 animate-spin" /> : <RefreshCw className="size-3" />} Write the summary again
        </button>
      </div>
      {problem && <p className="text-right text-[11.5px] text-bad">{problem}</p>}
    </article>
  )
}

function Part({ icon: Icon, title, children }) {
  return (
    <section className="space-y-3.5">
      <h3 className="flex items-center gap-2.5 font-display text-[19px] font-bold tracking-tight">
        <span className="grid size-9 place-items-center rounded-xl bg-accent/10 text-accent"><Icon className="size-[18px]" /></span>
        {title}
      </h3>
      {children}
    </section>
  )
}

function Points({ items }) {
  return (
    <ul className="space-y-2.5 rounded-2xl border border-line bg-panel p-5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed">
          <span className="mt-[8px] size-1.5 shrink-0 rounded-full bg-accent" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function TryAgain({ onClick }) {
  return (
    <button type="button" onClick={onClick}
            className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-3.5 py-2 text-[12px] font-semibold text-ink hover:bg-press">
      <RefreshCw className="size-3.5" /> Try again
    </button>
  )
}
