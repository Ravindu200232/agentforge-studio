'use client'

import { CircleCheck, CircleX, CircleDashed, ShieldAlert } from 'lucide-react'
import { Badge, Empty } from '../ui'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { e2eStageSummary, journeyStageSummary } from '@/lib/e2e-rate'

export default function EndToEnd({ qa }) {
  const e2e = qa?.report?.e2e
  if (!e2e || !Object.keys(e2e).length) {
    return <Empty>The end-to-end stage has no record for this project.</Empty>
  }
  const failures = e2e.failures || []
  const failed = e2e.failed ?? failures.length
  const score = e2eStageSummary(e2e)
  const flows = e2e.flows || []
  const savedSuites = qa?.report?.evidence?.suites || []

  return (
    <div className="space-y-4">
      <div className="grid gap-3 lg:grid-cols-[240px_1fr]">
        <ScoreCard score={score} />
        <div className="rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[.16em] text-muted">Final browser proof</p>
              <h3 className="mt-1 font-display text-[22px] font-bold tracking-tight text-ink">
                {score.total ? `${score.passed}/${score.total} stages passed` : 'E2E step results unavailable'}
              </h3>
              <p className="mt-1.5 max-w-[720px] text-[12px] leading-relaxed text-muted">
                {score.total
                  ? 'Only the latest accepted run of each journey is counted. Repair and re-author retries never inflate the score.'
                  : 'A pass rate cannot be calculated without saved step results. Any saved journey outcomes are listed below.'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge tone={failed ? 'bad' : score.total ? 'ok' : 'mute'}>
                {failed ? `${failed} failure(s)` : score.total ? 'recorded stages passed' : 'step evidence unavailable'}
              </Badge>
              {score.notReached ? <Badge tone="warn">{score.notReached} not reached</Badge> : null}
              {e2e.fixed ? <Badge tone="ok">{e2e.fixed} repaired file(s)</Badge> : null}
            </div>
          </div>
        </div>
      </div>

      {!e2e.ran && (
        <div className="rounded-none border border-line bg-panel p-5 text-[12px] text-muted backdrop-blur-xl">
          No complete browser-stage trace was saved for this project.
        </div>
      )}

      {(e2e.recordedOutcomes || []).map((row, index) => (
        <div key={index} className="rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
          <div className="flex flex-wrap items-center gap-2.5">
            <Badge tone="mute">historical outcome</Badge>
            <b className="text-[13px] font-semibold text-ink">{row.suite}</b>
          </div>
          <p className="mt-2 text-[12px] text-ink">{row.detail}</p>
          <p className="mt-1 font-mono text-[10.5px] text-muted2">{row.at} · {row.source}. Individual steps were not saved.</p>
        </div>
      ))}

      {flows.length > 0 && (
        <div className="grid gap-2.5">
          {flows.map((flow, i) => <Journey key={`${flow.title}-${i}`} flow={flow} project={qa.project}
                                           journeys={e2e.journeyCoverage?.journeys || []} />)}
        </div>
      )}

      {e2e.global_integrity?.ran && (
        <div className="flex items-center justify-between gap-3 rounded-none border border-line bg-panel p-4 shadow-xl backdrop-blur-xl">
          <div>
            <p className="text-[13px] font-semibold text-ink">Global route & role integrity</p>
            <p className="mt-0.5 text-[11.5px] text-muted">One final proof after the user journeys: route health, auth boundaries and role separation.</p>
          </div>
          <Badge tone={e2e.global_integrity.passed ? 'ok' : 'bad'}>
            {e2e.global_integrity.passed ? 'pass' : `${e2e.global_integrity.failures || 1} failure(s)`}
          </Badge>
        </div>
      )}

      {failures.length > 0 && (
        <div className="rounded-none border border-rose-500/20 bg-panel/80 p-5 shadow-xl backdrop-blur-xl">
          <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[.14em] text-rose-400">
            <ShieldAlert className="size-4" />
            <span>Failure evidence</span>
          </div>
          <ul className="space-y-2.5">
            {failures.map((f, i) => (
              <li key={i} className="rounded-none border border-rose-500/20 bg-rose-500/5 p-3.5 text-[12px]">
                <div className="flex items-baseline gap-2">
                  <code className="font-mono font-semibold text-rose-300">{f.target || f.file || f.case}</code>
                  <span className="text-ink"> — {f.case || f.message}</span>
                </div>
                <DiagnosticEvidence suite={f.case} suites={savedSuites} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function DiagnosticEvidence({ suite, suites }) {
  const output = suites.find(row => row.kind === 'e2e' && row.suite === suite)?.output || ''
  const marker = 'Browser diagnostics during this journey:'
  const start = output.indexOf(marker)
  if (start < 0) return null
  return (
    <details className="mt-3 rounded-none border border-line bg-panel2 px-3.5 py-2.5">
      <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-[.1em] text-muted hover:text-ink">
        Browser console & network evidence
      </summary>
      <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-ink">
        {output.slice(start)}
      </pre>
    </details>
  )
}

function ScoreCard({ score }) {
  if (!score.total) return (
    <div className="flex items-center gap-4 rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
      <div className="grid size-20 shrink-0 place-items-center rounded-full border-4 border-black/10 text-muted2">
        <CircleDashed className="size-8" />
      </div>
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[.14em] text-muted">E2E pass rate</p>
        <p className="mt-1 font-display text-[19px] font-bold text-ink">Not available</p>
        <p className="mt-1 text-[11px] text-muted2">Step details were not saved.</p>
      </div>
    </div>
  )
  const deg = Math.max(0, Math.min(360, score.rate * 3.6))
  return (
    <div className="flex items-center gap-4 rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
      <div 
        className="relative grid size-24 shrink-0 place-items-center rounded-full p-[6px] shadow-[0_0_25px_rgba(0,0,0,0.45)]"
        style={{ background: `conic-gradient(var(--green) 0deg ${deg}deg, rgba(0,0,0,0.08) ${deg}deg 360deg)` }}
      >
        <div className="grid size-full place-items-center rounded-full bg-panel">
          <div className="text-center">
            <div className={cn('font-display text-[24px] font-black leading-none', score.rate === 100 ? 'text-ok' : score.rate >= 80 ? 'text-warn' : 'text-bad')}>
              {score.rate}%
            </div>
            <div className="mt-1 text-[9px] font-bold uppercase tracking-[.14em] text-muted">E2E</div>
          </div>
        </div>
      </div>
      <div className="min-w-0">
        <div className="font-display text-[22px] font-extrabold tracking-tight text-ink">{score.passed}/{score.total}</div>
        <div className="text-[11.5px] text-muted">all final E2E stages</div>
        <div className="mt-2.5 flex gap-3 text-[11px] font-semibold">
          <span className="text-ok">{score.passed} pass</span>
          <span className="text-bad">{score.failed} fail</span>
        </div>
      </div>
    </div>
  )
}

/** The journey (from the SRS's user-journey contract) a stage's `[UJ-001]` title proves. */
const journeyFor = (label, journeys) => {
  const id = String(label || '').match(/\bUJ-\d+\b/i)?.[0]?.toUpperCase()
  return id ? journeys.find(j => String(j.id).toUpperCase() === id) : null
}

function Journey({ flow, journeys, project }) {
  const score = journeyStageSummary(flow)
  const stages = flow.stages || []
  return (
    <section className="overflow-hidden rounded-none border border-line bg-panel shadow-xl backdrop-blur-xl">
      <header className="flex flex-wrap items-center gap-4 border-b border-line px-5 py-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h3 className="text-[15px] font-bold text-ink">{flow.title || flow.flow || 'Journey'}</h3>
            {flow.role ? <Badge tone="mute">{flow.role}</Badge> : null}
            {flow.blocked_upstream ? <Badge tone="bad">blocked</Badge> : null}
          </div>
          <p className="mt-1 text-[12px] text-muted">
            {score.total ? `${score.passed}/${score.total} stages passed · ${score.rate}%` : 'No measurable browser stages'}
          </p>
        </div>
        {score.total > 0 && (
          <div className="w-32">
            <div className="mb-1.5 flex justify-between text-[10px] font-medium text-muted">
              <span>proof</span>
              <span className="font-semibold text-ink">{score.rate}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-black/10">
              <div className="h-full rounded-full bg-ok transition-all duration-500" style={{ width: `${score.rate}%` }} />
            </div>
          </div>
        )}
      </header>
      {stages.length ? (
        <ol className="divide-y divide-line">
          {stages.map((stage, i) => <Stage key={`${stage.index}-${i}`} project={project}
                                           stage={{ ...stage, index: stage.index || i + 1 }}
                                           journey={journeyFor(stage.label || stage.name, journeys)} />)}
        </ol>
      ) : <p className="px-5 py-4 text-[11.5px] text-muted2">This older run has no stage ledger.</p>}
    </section>
  )
}

function Stage({ stage, journey, project }) {
  stage = { ...stage, label: stage.label || stage.name,
            status: ({ passed: 'pass', failed: 'fail' })[stage.status] || stage.status }
  const tone = stage.status === 'pass' ? 'text-ok' : stage.status === 'fail' ? 'text-bad' : 'text-muted2'
  const Icon = stage.status === 'pass' ? CircleCheck : stage.status === 'fail' ? CircleX : CircleDashed
  const shot = stage.screenshot ? api.qaScreenshotUrl(project, stage.screenshot) : ''
  return (
    <li className="flex gap-3.5 px-5 py-4">
      <Icon className={cn('mt-0.5 size-5 shrink-0', tone)} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-mono text-[11px] text-muted2">{String(stage.index || '').padStart(2, '0')}</span>
          <p className={cn('min-w-0 flex-1 text-[13.5px] font-semibold leading-snug', stage.status === 'not_reached' ? 'text-muted2' : 'text-ink')}>
            {stage.label}
          </p>
          <span className={cn('shrink-0 text-[10.5px] font-bold uppercase tracking-wider', tone)}>
            {String(stage.status || '').replace('_', ' ')}{stage.seconds != null ? ` · ${stage.seconds}s` : ''}
          </span>
        </div>
        {journey && (
          <div className="mt-3 border border-line bg-panel2/60 p-3.5">
            <p className="text-[11px] font-semibold uppercase tracking-[.12em] text-muted">
              {journey.workflow_name}{journey.who ? ` · as ${journey.who}` : ''}
            </p>
            {!!journey.steps?.length && (
              <ol className="mt-2 space-y-1.5">
                {journey.steps.map((step, i) => (
                  <li key={i} className="flex gap-2.5 text-[12px] leading-relaxed text-ink">
                    <span className="mt-px shrink-0 font-mono text-[10.5px] text-muted2">{i + 1}.</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
        {shot && (
          <a href={shot} target="_blank" rel="noreferrer" className="mt-3 block max-w-md">
            <img src={shot} alt={`The screen when this stage ended: ${stage.label}`} loading="lazy"
                 className="max-h-56 w-full border border-line object-cover object-top" />
          </a>
        )}
      </div>
    </li>
  )
}

