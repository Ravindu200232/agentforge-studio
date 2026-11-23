'use client'

import { useEffect, useState } from 'react'
import { Check, CircleAlert, Loader2 } from 'lucide-react'
import { useStore } from '@/lib/store'

const TITLES = {
  planning: 'Preparing your interview',
  reviewing: 'Generating your plan',
  generating: 'Writing your specification',
}

export default function SrsActivity({ projectId, phase = 'planning', title = '', message = '', seconds, compact = false }) {
  const session = useStore(s => s.projectSessions[projectId]?.developer)
  const startedAt = session?.runStartedAt
  const [now, setNow] = useState(0)
  const generating = phase === 'generating'
  const reviewing = phase === 'reviewing'
  useEffect(() => {
    if (!generating || !startedAt || seconds !== undefined) return
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [generating, startedAt, seconds])

  const phases = session?.phases || []
  const runPhases = generating && session?.runId === 'srs' && startedAt
    ? phases.filter(event => event.kind === 'srs-progress' && event.at >= startedAt)
    : []
  const parts = runPhases.filter(event => event.phase).sort((a, b) => a.phase - b.phase)
  const current = reviewing
    ? phases.find(event => event.key === 'plan:draft' && event.status === 'active')
    : runPhases.findLast(event => !event.phase)
  const detail = current ? current.detail : message
  const elapsed = seconds ?? (startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0)
  const finished = parts.filter(event => event.status === 'complete').length

  return (
    <div className={compact ? 'flex flex-col items-center py-4 text-center' : 'flex flex-col items-center px-6 py-10 text-center'}>
      <Loader2 aria-hidden="true" className={compact ? 'size-4 animate-spin text-accent' : 'size-7 animate-spin text-accent'} />
      <div role="status" aria-live="polite">
        <h2 className={compact ? 'mt-2 text-[13px] font-semibold text-ink' : 'mt-4 font-display text-[18px] font-bold text-ink'}>
          {title || TITLES[phase] || TITLES.planning}
        </h2>
        {current && generating && <p className="mt-2 text-[12px] font-semibold text-ink">{current.title}</p>}
        {detail && <p className="mt-1.5 max-w-md text-[12px] leading-relaxed text-muted">{detail}</p>}
        {parts.length > 0 && (
          <ul className="mt-4 grid max-w-md gap-1.5 text-left text-[11.5px] text-muted">
            {parts.map(part => {
              const complete = part.status === 'complete'
              const failed = part.status === 'failed'
              const queued = part.status === 'queued'
              const Icon = complete ? Check : failed ? CircleAlert : Loader2
              const status = { queued: 'Queued', complete: 'Done', failed: 'Could not validate', retrying: 'Retrying' }[part.status] || 'Writing'
              return (
                <li key={part.key} className="flex items-center gap-2">
                  <Icon aria-hidden="true" className={`size-3.5 shrink-0 ${complete ? 'text-ok' : failed ? 'text-warn' : queued ? 'text-muted2' : 'animate-spin text-accent'}`} />
                  <span className="flex-1">{part.title}</span>
                  <span className="shrink-0 text-muted2">{status}</span>
                </li>
              )
            })}
          </ul>
        )}
      </div>
      {(parts.length > 0 || elapsed > 0) && (
        <p aria-live="off" className="mt-3 text-[10.5px] font-medium tabular-nums text-muted2">
          {parts.length > 0 && `${finished}/${parts.length} sections ready`}{parts.length > 0 && elapsed > 0 && ' · '}
          {elapsed > 0 && `${elapsed}s elapsed`}
        </p>
      )}
    </div>
  )
}
