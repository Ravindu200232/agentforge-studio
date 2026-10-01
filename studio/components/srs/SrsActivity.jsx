'use client'

import { useEffect, useMemo, useRef } from 'react'
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
  const stream = useRef(null)

  useEffect(() => {
    const node = stream.current
    if (node) node.scrollTop = node.scrollHeight
  }, [message, phase])

  return (
    <section className="mt-6 overflow-hidden rounded-2xl border border-line bg-panel shadow-sm">
      <header className="flex items-center gap-2.5 border-b border-line px-4 py-3">
        <span className="grid size-8 place-items-center rounded-xl border border-line bg-white text-deep"><Sparkles className="size-3.5" /></span>
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-semibold text-ink">Planner stream</p>
          <p className="truncate text-[10.5px] text-muted">{message || 'Working through the specification pipeline…'}{seconds ? ` · ${seconds}s` : ''}</p>
        </div>
        <span className="size-1.5 animate-pulse rounded-full bg-accent" aria-label="Working" />
      </header>
      <div ref={stream} role="log" aria-live="polite" className="max-h-[min(360px,48dvh)] space-y-2 overflow-y-auto p-3 pr-2">
        <article className="rounded-xl border border-line bg-white px-3 py-2.5 text-[11px] leading-relaxed text-ink">
          {message || 'Planner is reading the project context.'}
        </article>
        {steps.map(([title, detail], index) => (
          <article key={title} className="flex gap-2.5 rounded-xl border border-line bg-panel px-3 py-2.5">
            <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border border-line bg-white text-deep">
              {index === 0 ? <Loader2 className="size-2.5 animate-spin" /> : <Check className="size-2.5" />}
            </span>
            <div>
              <p className="text-[11px] font-semibold text-ink">{title}</p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-muted">{detail}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
