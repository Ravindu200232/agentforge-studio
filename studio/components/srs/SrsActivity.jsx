'use client'

import { useEffect, useMemo, useState } from 'react'
import { Check, Loader2, Sparkles } from 'lucide-react'

const PLAN_STEPS = [
  ['Reading the product brief', 'Understanding the goal, constraints and attached context.'],
  ['Mapping actors and workflows', 'Separating each user journey and the business actions inside it.'],
  ['Finding data and access rules', 'Identifying records, ownership, authentication and role boundaries.'],
  ['Checking requirement gaps', 'Finding the few details that need a human decision before implementation.'],
  ['Preparing the interview', 'Turning uncertain requirements into concise questions.'],
]

const REVIEW_STEPS = [
  ['Creating the product blueprint', 'Turning interview answers into screens, roles, records and workflows.'],
  ['Connecting requirements', 'Making every requested capability traceable to an implementation area.'],
  ['Checking architecture boundaries', 'Resolving data, API, security and ownership responsibilities.'],
  ['Preparing plan review', 'Organising the approved structure before specification generation.'],
]

const SRS_STEPS = [
  ['Creating the SRS', 'Writing the approved product and functional requirements.'],
  ['Creating use cases', 'Expanding actor goals, conditions, actions and outcomes.'],
  ['Defining data and API contracts', 'Connecting records, ownership rules, routes and business operations.'],
  ['Drawing system diagrams', 'Building the architecture, flow, state, data and deployment views.'],
  ['Checking traceability', 'Making sure requirements, screens, workflows and tests agree.'],
  ['Preparing Builder handoff', 'Packaging the specification so Builder receives one consistent source of truth.'],
]

export default function SrsActivity({ phase = 'planning', message = '', seconds = 0 }) {
  const steps = useMemo(() => phase === 'generating' ? SRS_STEPS : phase === 'reviewing' ? REVIEW_STEPS : PLAN_STEPS, [phase])
  const [shown, setShown] = useState(1)

  useEffect(() => {
    setShown(1)
    const timer = setInterval(() => setShown(n => Math.min(steps.length, n + 1)), 8000)
    return () => clearInterval(timer)
  }, [phase, steps.length])

  const rows = steps.slice(0, shown).slice(-5)
  return (
    <section className="mt-6 overflow-hidden rounded-none border border-black/75 bg-black/68 shadow-[0_22px_64px_rgba(31,42,69,.09)] backdrop-blur-xl dark:border-black/[.05] dark:bg-black/[.035]">
      <div className="grid min-h-[430px] gap-0 lg:grid-cols-[.86fr_1.14fr]">
        <div className="flex flex-col p-6">
          <div className="flex items-center gap-2.5">
            <span className="grid size-9 place-items-center rounded-none bg-accent text-ink"><Sparkles className="size-4" /></span>
            <div><p className="text-[13px] font-semibold text-ink">SRS agent activity</p><p className="text-[10.5px] text-muted">{message || 'Working through the specification pipeline…'}{seconds ? ` · ${seconds}s` : ''}</p></div>
          </div>
          <div className="mt-7 flex flex-1 flex-col justify-end gap-3">
            {rows.map(([title, detail], index) => {
              const absolute = Math.max(0, shown - rows.length) + index
              const active = absolute === shown - 1 && shown < steps.length
              const done = absolute < shown - 1 || shown === steps.length
              return <article key={title} className="max-w-[96%] px-1 py-3.5">
                <div className="flex items-center gap-2">
                  <span className={`grid size-6 place-items-center rounded-full ${done ? 'bg-ok-tint text-ok' : 'bg-accent text-ink'}`}>
                    {done ? <Check className="size-3" /> : <Loader2 className="size-3 animate-spin" />}
                  </span>
                  <p className="text-[12px] font-semibold text-ink">{title}</p>
                </div>
                <p className="mt-1.5 pl-8 text-[10.5px] leading-relaxed text-muted">{detail}</p>
              </article>
            })}
          </div>
          <p className="mt-5 border-t border-line/60 pt-4 text-[10px] text-muted"><span className="mr-2 inline-block size-1.5 animate-pulse rounded-full bg-accent" />Activity is paced so long model calls still feel alive instead of frozen.</p>
        </div>
        <div className="relative grid min-h-[360px] place-items-center overflow-hidden border-t border-line/55 bg-black/50 p-6 dark:bg-black/10 lg:border-l lg:border-t-0">
          <span className="absolute left-5 top-5 rounded-full bg-black/82 px-3 py-1.5 text-[10px] font-medium text-muted shadow-sm ring-1 ring-line/60 backdrop-blur dark:bg-black/25">Planner → SRS</span>
          <img src="/__agentforge/srs-planner.gif" alt="SRS and planner activity" className="h-auto max-h-[390px] w-full max-w-[570px] select-none object-contain" />
        </div>
      </div>
    </section>
  )
}
