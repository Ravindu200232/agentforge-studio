'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight, CircleCheck, CircleX, CircleDashed, ShieldAlert, Sparkles, Terminal } from 'lucide-react'
import { Badge, Empty } from '../ui'
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
        <div className="rounded-none border border-line bg-[#F2F0EF] p-5 shadow-xl backdrop-blur-xl">
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
        <div className="rounded-none border border-line bg-[#F2F0EF] p-5 text-[12px] text-muted backdrop-blur-xl">
          No complete browser-stage trace was saved for this project.
        </div>
      )}

      {(e2e.recordedOutcomes || []).map((row, index) => (
        <div key={index} className="rounded-none border border-line bg-[#F2F0EF] p-5 shadow-xl backdrop-blur-xl">
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
          {flows.map((flow, i) => <Journey key={`${flow.title}-${i}`} flow={flow} />)}
        </div>
      )}

      {e2e.global_integrity?.ran && (
        <div className="flex items-center justify-between gap-3 rounded-none border border-line bg-[#F2F0EF] p-4 shadow-xl backdrop-blur-xl">
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
        <div className="rounded-none border border-rose-500/20 bg-[#F2F0EF]/80 p-5 shadow-xl backdrop-blur-xl">
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
    <details className="mt-3 rounded-none border border-black/10 bg-black/40 px-3.5 py-2.5">
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
    <div className="flex items-center gap-4 rounded-none border border-line bg-[#F2F0EF] p-5 shadow-xl backdrop-blur-xl">
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
    <div className="flex items-center gap-4 rounded-none border border-line bg-[#F2F0EF] p-5 shadow-xl backdrop-blur-xl">
      <div 
        className="relative grid size-24 shrink-0 place-items-center rounded-full p-[6px] shadow-[0_0_25px_rgba(0,0,0,0.45)]"
        style={{ background: `conic-gradient(#22C55E 0deg ${deg}deg, rgba(0,0,0,0.08) ${deg}deg 360deg)` }}
      >
        <div className="grid size-full place-items-center rounded-full bg-[#F2F0EF]">
          <div className="text-center">
            <div className={cn('font-display text-[24px] font-black leading-none', score.rate === 100 ? 'text-ink' : score.rate >= 80 ? 'text-[#FFAB00]' : 'text-[#FF5630]')}>
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
          <span className="text-ink">{score.passed} pass</span>
          <span className="text-[#FF5630]">{score.failed} fail</span>
        </div>
      </div>
    </div>
  )
}

function Journey({ flow }) {
  const [open, setOpen] = useState(false)
  const score = journeyStageSummary(flow)
  const stages = flow.stages || []
  return (
    <div className="overflow-hidden rounded-none border border-line bg-[#F2F0EF] shadow-xl backdrop-blur-xl transition-all duration-200 hover:border-black/20">
      <button onClick={() => setOpen(v => !v)} className="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-black/[0.03]">
        {open ? <ChevronDown className="size-4 text-muted" /> : <ChevronRight className="size-4 text-muted" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="truncate text-[13px] font-bold text-ink">{flow.title || flow.flow || 'Journey'}</span>
            {flow.role ? <Badge tone="mute">{flow.role}</Badge> : null}
            {flow.blocked_upstream ? <Badge tone="bad">blocked</Badge> : null}
          </div>
          <div className="mt-1 text-[11.5px] text-muted">
            {score.total ? `${score.passed}/${score.total} stages passed · ${score.rate}%` : 'No measurable browser stages'}
          </div>
        </div>
        {score.total > 0 && (
          <div className="w-32">
            <div className="mb-1.5 flex justify-between text-[10px] font-medium text-muted">
              <span>proof</span>
              <span className="font-semibold text-ink">{score.rate}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-black/10">
              <div className="h-full rounded-full bg-[#22C55E] transition-all duration-500" style={{ width: `${score.rate}%` }} />
            </div>
          </div>
        )}
      </button>
      {open && (
        <div className="border-t border-black/5 bg-black/25 px-5 py-3.5">
          {stages.length ? (
            <ol className="divide-y divide-black/5">
              {stages.map((stage, i) => <Stage key={`${stage.index}-${i}`} stage={{ ...stage, index: stage.index || i + 1 }} />)}
            </ol>
          ) : <p className="text-[11.5px] text-muted2">This older run has no stage ledger.</p>}
        </div>
      )}
    </div>
  )
}

function Stage({ stage }) {
  stage = { ...stage, label: stage.label || stage.name,
            status: ({ passed: 'pass', failed: 'fail' })[stage.status] || stage.status }
  const Icon = stage.status === 'pass' ? CircleCheck : stage.status === 'fail' ? CircleX : CircleDashed
  return (
    <li className="flex items-center gap-3 py-2 text-[11.5px]">
      <Icon className={cn('size-4 shrink-0', stage.status === 'pass' ? 'text-ink' : stage.status === 'fail' ? 'text-[#FF5630]' : 'text-muted2')} />
      <span className="w-5 shrink-0 font-mono text-muted2">{String(stage.index || '').padStart(2, '0')}</span>
      <code className={cn('break-all font-mono', stage.status === 'not_reached' ? 'text-muted2' : 'text-ink')}>{stage.label}</code>
      <span className={cn('ml-auto shrink-0 text-[10px] font-bold uppercase tracking-wider', stage.status === 'pass' ? 'text-ink' : stage.status === 'fail' ? 'text-[#FF5630]' : 'text-muted2')}>{String(stage.status || '').replace('_', ' ')}</span>
    </li>
  )
}

