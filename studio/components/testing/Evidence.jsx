'use client'

/**
 * The verification ledger, exactly as the engine recorded it.
 *
 * Every other view here is an interpretation — a rate, a chart, a grouping.
 * This one is the raw claim: what the run promised to prove, which command or
 * journey proved it, and what is still unproved. When a number elsewhere looks
 * wrong, this is the page that says why.
 */

import { Badge, Empty, Table, Tag, TD, TH, TR } from '../ui'
import { cn } from '@/lib/utils'

const STATUS_TONE = {
  passed: 'ok',
  outdated: 'mute',
  failed: 'bad',
  interrupted: 'bad',
  running: 'mute',
}

export default function Evidence({ qa }) {
  const evidence = qa?.report?.evidence
  if (qa?.recovered) return (
    <div className="space-y-4">
      <div className="rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
        <Badge tone="mute">Saved artifacts · partial evidence</Badge>
        <p className="mt-3 text-[12px] text-ink">{qa.provenance}</p>
      </div>
      <div className="overflow-hidden rounded-none border border-line bg-panel shadow-xl backdrop-blur-xl">
        <Table>
          <thead><TR><TH>Evidence</TH><TH>Source</TH><TH>What was saved</TH></TR></thead>
          <tbody>
            {qa.vitest && <TR><TD className="font-medium text-ink">Unit testing</TD><TD className="font-mono text-muted">{qa.vitest.source === 'vitest-cache' ? 'node_modules/.vite/vitest/results.json' : qa.vitest.source}</TD><TD className="text-ink">{qa.vitest.fileResults ? `${qa.vitest.fileResults.length} file outcomes; assertion details unavailable` : 'Vitest assertion report'}</TD></TR>}
            {(qa.report?.e2e?.recordedOutcomes || []).map((r, i) => <TR key={i}><TD className="font-medium text-ink">E2E · {r.suite}</TD><TD className="font-mono text-muted">{r.source}</TD><TD className="text-ink">{r.detail} · step trace unavailable</TD></TR>)}
            {(qa.screenshots || []).map(r => <TR key={r.path}><TD className="font-medium text-ink">Screenshot</TD><TD className="break-all font-mono text-muted">{r.path}</TD><TD className="text-ink">{r.width} × {r.height} · {r.status}</TD></TR>)}
          </tbody>
        </Table>
      </div>
      {qa.report?.unit?.coverage && (
        <div className="rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Saved source coverage · informational, no percentage requirement</p>
          <p className="mt-2 text-[13px] font-medium text-ink">{Object.entries(qa.report.unit.coverage).filter(([, v]) => typeof v?.pct === 'number').map(([k, v]) => `${k}: ${v.pct}%`).join(' · ')}</p>
        </div>
      )}
    </div>
  )
  if (!evidence || !Object.keys(evidence).length) {
    return <Empty>This project has no verification ledger yet.</Empty>
  }

  const scope = evidence.scope
  const suites = evidence.suites || []
  const uncovered = evidence.missingRequirements || []
  const limitations = Object.entries(evidence.limitations || {})
  const unit = evidence.coverage?.unit
  const e2e = evidence.coverage?.e2e

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3.5 rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
        <Badge tone={evidence.ready ? 'ok' : 'bad'}>
          {evidence.ready ? 'every required layer proved' : 'evidence incomplete'}
        </Badge>
        <span className="text-[12px] text-ink">
          revision <b className="text-ink">{evidence.revision}</b> · requires {(evidence.requiredKinds || []).join(', ') || 'nothing'}
        </span>
        {evidence.scopeOpen && (
          <Badge tone="bad">scope still open</Badge>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
          <p className="text-[11px] font-semibold uppercase tracking-[.16em] text-muted">
            Unit source coverage
          </p>
          {unit ? (
            <>
              <p className={cn('mt-1.5 font-display text-[26px] font-bold tracking-tight',
                unit.required === false ? 'text-muted' : unit.status === 'passed' ? 'text-ok' : 'text-rose-400')}>
                {unit.status === 'missing' ? 'no report' : unit.status}
              </p>
              <p className="mt-1 text-[11.5px] text-muted">
                {unit.required === false ? 'Informational · no percentage requirement' : `floor ${unit.target}%`}
                {unit.metrics && ' · ' + Object.entries(unit.metrics)
                  .map(([name, m]) => `${name} ${m.pct}%`).join(', ')}
              </p>
              {(unit.failures || []).map((why, i) => (
                <p key={i} className="mt-1 text-[11.5px] text-rose-400">{why}</p>
              ))}
            </>
          ) : <Empty>Not measured.</Empty>}
        </div>

        <div className="rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
          <p className="text-[11px] font-semibold uppercase tracking-[.16em] text-muted">
            Requirement coverage (E2E)
          </p>
          {e2e ? (
            <>
              <p className={cn('mt-1.5 font-display text-[26px] font-bold tracking-tight',
                e2e.status === 'passed' ? 'text-ok' : 'text-rose-400')}>
                {e2e.covered}/{e2e.total}
              </p>
              <p className="mt-1 text-[11.5px] text-muted">
                {e2e.percent}% covered · floor {e2e.target}%
              </p>
            </>
          ) : <Empty>Not measured.</Empty>}
        </div>
      </div>

      {scope?.requirements?.length > 0 && (
        <div className="overflow-hidden rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
          <h3 className="mb-1 text-[13px] font-bold tracking-wide text-ink">
            What this run promised to prove
          </h3>
          <p className="mb-3 text-[11px] text-muted">
            Sealed before the tests ran, so the scope cannot be narrowed once a
            flow turns out to be hard.
          </p>
          <div className="overflow-x-auto rounded-none border border-line bg-panel">
            <Table>
              <thead><TR><TH>id</TH><TH>behaviour</TH><TH>evidence needed</TH></TR></thead>
              <tbody>
                {scope.requirements.map(req => {
                  const open = uncovered.filter(u => u.id === req.id).map(u => u.kind)
                  return (
                    <TR key={req.id} className={open.length ? 'bg-rose-500/10' : ''}>
                      <TD><code className="font-mono text-ink">{req.id}</code></TD>
                      <TD className="text-ink">{req.description}</TD>
                      <TD>
                        <span className="flex flex-wrap gap-1.5">
                          {req.evidence.map(kind => (
                            <Tag key={kind} tone={open.includes(kind) ? 'bad' : 'mute'}>
                              {kind}
                            </Tag>
                          ))}
                        </span>
                      </TD>
                    </TR>
                  )
                })}
              </tbody>
            </Table>
          </div>
        </div>
      )}

      {suites.length > 0 && (
        <div className="overflow-hidden rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
          <h3 className="mb-1 text-[13px] font-bold tracking-wide text-ink">What actually ran</h3>
          <p className="mb-3 text-[11px] text-muted">
            Command exit status and browser journey outcomes. A pass recorded
            before the last edit shows as <b className="text-ink">outdated</b>, not as missing.
          </p>
          <div className="overflow-x-auto rounded-none border border-line bg-panel">
            <Table>
              <thead>
                <TR><TH>layer</TH><TH>suite</TH><TH>result</TH><TH>command</TH><TH>covers</TH></TR>
              </thead>
              <tbody>
                {suites.map((s, i) => (
                  <TR key={`${s.kind}-${s.suite}-${i}`}>
                    <TD><Tag>{s.kind}</Tag></TD>
                    <TD className="font-medium text-ink">{s.suite}</TD>
                    <TD>
                      <Badge tone={STATUS_TONE[s.status] || 'mute'}>{s.status}</Badge>
                      {s.exitCode != null && (
                        <span className="ml-1.5 font-mono text-[10px] text-muted2">
                          exit {s.exitCode}
                        </span>
                      )}
                    </TD>
                    <TD className="max-w-[280px] truncate font-mono text-[11px] text-muted"
                        title={s.command}>
                      {s.command}
                    </TD>
                    <TD className="font-mono text-[11px] text-muted">
                      {(s.covers || []).join(', ') || '—'}
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </div>
          {suites.filter(s => s.reason).map((s, i) => (
            <div key={i} className="mt-3 rounded-none border border-rose-500/30 bg-rose-500/10 p-3.5">
              <p className="text-[12px] font-semibold text-rose-300">{s.kind} / {s.suite}</p>
              <p className="mt-1 text-[11.5px] text-ink">{s.reason}</p>
            </div>
          ))}
        </div>
      )}

      {(evidence.visuals || []).length > 0 && (
        <div className="overflow-hidden rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
          <h3 className="mb-2 text-[13px] font-bold tracking-wide text-ink">Screens reviewed</h3>
          <div className="overflow-x-auto rounded-none border border-line bg-panel">
            <Table>
              <thead><TR><TH>view</TH><TH>width</TH><TH>result</TH><TH>findings</TH></TR></thead>
              <tbody>
                {evidence.visuals.map((v, i) => (
                  <TR key={i}>
                    <TD className="font-medium text-ink">{v.view}</TD>
                    <TD className="font-mono text-[11px] text-muted">{v.width}px</TD>
                    <TD><Badge tone={STATUS_TONE[v.status] || 'mute'}>{v.status}</Badge></TD>
                    <TD className="text-ink">{v.findings}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </div>
        </div>
      )}

      {limitations.length > 0 && (
        <div className="overflow-hidden rounded-none border border-line bg-panel p-5 shadow-xl backdrop-blur-xl">
          <h3 className="mb-1 text-[13px] font-bold tracking-wide text-ink">Recorded as unverified</h3>
          <p className="mb-3 text-[11px] text-muted">
            Not passes. These are the things the run could not prove here, with
            the reason it gave.
          </p>
          <div className="space-y-2.5">
            {limitations.map(([kind, why]) => (
              <div key={kind} className="rounded-none border border-amber-500/20 bg-amber-500/5 p-3.5">
                <Tag tone="bad">{kind}</Tag>
                <p className="mt-1.5 text-[12px] text-ink">{why}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
