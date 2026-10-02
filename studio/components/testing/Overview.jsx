'use client'

import { Empty } from '../ui'
import { Stat } from './TestingResult'
import { cn } from '@/lib/utils'
import { e2eStageSummary } from '@/lib/e2e-rate'
import { unitTestStatus } from '@/lib/test-counts'
import { FileCheck2, Layers, Compass, AlertCircle, ShieldAlert, Gauge, Terminal, CheckCircle2, Info } from 'lucide-react'

export default function Overview({ qa, live }) {
  const last = (qa?.history || []).slice(-1)[0]
  const r = qa?.report
  const v = qa?.vitest || qa?.savedVitest
  if (!last && !r && !v) {
    return <Empty>Nothing has been recorded for this project yet.</Empty>
  }
  // Display real-time verification metrics for both active and completed test runs.
  const partial = qa && qa.complete === false
  const ran = qa?.stages || []

  const perf = qa?.performance?.scores || {}
  const runtime = qa?.runtimeStatus
  const sec = r?.security?.findings || []
  const unresolved = r?.suite?.unresolved || []
  const e2e = e2eStageSummary(r?.e2e)
  const unit = unitTestStatus(v)
  const unitTotal = Number(unit?.total || 0)
  const unitPassed = Number(unit?.passed || 0)
  const unitRate = unitTotal ? Math.round(unitPassed * 100 / unitTotal) : 0
  const history = (qa?.history || []).filter(x => Number.isFinite(Number(x?.rate)))
  const roundAverage = history.length ? Math.round(history.reduce((sum, x) => sum + Number(x.rate || 0), 0) / history.length) : null

  return (
    <div className="space-y-4">
      {partial && (
        <div className="flex items-center gap-3 rounded-none border border-blue-500/30 bg-blue-500/10 px-4 py-3 text-[12px] text-ink shadow-lg shadow-blue-500/5 backdrop-blur-xl">
          <Info className="size-4 shrink-0 text-blue-400" />
          <div>
            <b className="font-semibold text-ink">{live?.running ? 'Verification in progress.' : 'Partial saved report.'}</b>{' '}
            <span className="text-ink">
              {ran.length
                ? `${ran.join(' and ')} ${ran.length === 1 ? 'has' : 'have'} run so far.`
                : 'No stage has finished yet.'}{' '}
              Only saved evidence is shown below.
            </span>
          </div>
        </div>
      )}

      <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(300px,1fr))]">
        <Card title="Saved verification" hint="results already recorded for this project" icon={FileCheck2}>
          <div className="flex items-center gap-2">
            <span className={cn('size-2 rounded-full', qa.complete ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]' : live?.running ? 'animate-pulse bg-blue-400' : 'bg-amber-400')} />
            <p className={cn('text-[13px] font-semibold', qa.complete ? 'text-ok' : 'text-ink')}>{qa.complete ? 'Verification finished' : live?.running ? 'Verification in progress' : 'Partial saved report'}</p>
          </div>
          <p className="mt-2 text-[11px] text-muted">{qa.provenance || 'Results are saved as each check finishes.'}</p>
          <div className="mt-4 flex flex-wrap gap-4 border-t border-black/5 pt-3">
            <Stat n={qa.timeline?.length || qa.history?.length || 0} label="timeline entries" />
            <Stat n={qa.screenshots?.length || 0} label="screenshots" />
          </div>
        </Card>

        {/* Test results are incrementally merged into the overall suite report. */}
        <Card title="The suite now" hint="every test file, at its latest result" icon={Layers}>
          {qa.unitEvidenceStatus === 'outdated' && (
            <p className="mb-2.5 rounded-none border border-amber-500/20 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-300">
              Saved results precede the latest code changes.
            </p>
          )}
          {v ? (
            <div className="flex flex-col gap-2">
              <div className="mb-2 flex items-center gap-3.5">
                <div 
                  className="grid size-16 shrink-0 place-items-center rounded-full p-[5px] shadow-[0_0_20px_rgba(0,0,0,0.4)]"
                  style={{ 
                    background: `conic-gradient(#10b981 0deg ${unitRate * 3.6}deg, rgba(0,0,0,0.08) ${unitRate * 3.6}deg 360deg)` 
                  }}
                >
                  <div className="grid size-full place-items-center rounded-full bg-panel">
                    <b className={cn('font-display text-[16px] font-black', unitRate === 100 ? 'text-ok' : unitRate >= 80 ? 'text-amber-400' : 'text-rose-400')}>
                      {unitRate}%
                    </b>
                  </div>
                </div>
                <div className="text-[11px] leading-relaxed text-muted">
                  <b className="text-ink">{unit.unit === 'files' ? 'Saved file pass rate' : 'Recorded test pass rate'}</b>
                  {roundAverage != null && (
                    <>
                      <br />Round-one average: <b className="text-ink">{roundAverage}%</b> across {history.length} run{history.length === 1 ? '' : 's'}
                    </>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 border-t border-black/5 pt-2.5">
                <Stat n={unit.passed} label={unit.unit === 'files' ? 'files passing' : 'cases passing'} tone="text-ok" />
                <Stat n={unit.failed} label={unit.unit === 'files' ? 'files failing' : 'cases failing'} tone={unit.failed ? 'text-rose-400' : 'text-muted'} />
              </div>
              <div className="border-t border-black/5 pt-2">
                <Stat n={unit.files} label="files" />
              </div>
              {r?.unit?.deleted ? (
                <p className="mt-1 text-[11px] text-rose-400">
                  <b>{r.unit.deleted}</b> case(s) that existed when the stage started are gone from the suite — this is not 100%.
                </p>
              ) : null}
              {r?.unit?.skipped ? (
                <p className="mt-1 text-[11px] text-amber-400">
                  <b>{r.unit.skipped}</b> case(s) are marked <code>it.skip</code> and never ran.
                </p>
              ) : null}
            </div>
          ) : <Empty>The suite has not run.</Empty>}
        </Card>

        <Card title="End-to-end proof" hint="all final browser journey stages, not repair retries" icon={Compass}>
          {e2e.total ? (
            <div className="flex items-center gap-4">
              <div 
                className="relative grid size-20 shrink-0 place-items-center rounded-full p-[6px] shadow-[0_0_25px_rgba(0,0,0,0.45)]"
                style={{ 
                  background: `conic-gradient(#10b981 0deg ${e2e.rate * 3.6}deg, rgba(0,0,0,0.08) ${e2e.rate * 3.6}deg 360deg)` 
                }}
              >
                <div className="grid size-full place-items-center rounded-full bg-panel">
                  <b className={cn('font-display text-[20px] font-black', e2e.rate === 100 ? 'text-ok' : e2e.rate >= 80 ? 'text-amber-400' : 'text-rose-400')}>
                    {e2e.rate}%
                  </b>
                </div>
              </div>
              <div className="space-y-1">
                <Stat n={`${e2e.passed}/${e2e.total}`} label="stages passed" tone={e2e.passed === e2e.total ? 'text-ok' : 'text-amber-400'} />
                <p className="text-[11px] text-muted">{e2e.failed} failed · {e2e.notReached} not reached</p>
              </div>
            </div>
          ) : <Empty>No saved step trace. {r?.e2e?.recordedOutcomes?.length || 0} historical journey outcome(s) available in Integration (E2E).</Empty>}
        </Card>

        <Card title="Left unresolved" hint="cases repair could not make pass" icon={AlertCircle}>
          {r ? (
            unresolved.length ? (
              <ul className="space-y-2 text-[11px] text-ink">
                {unresolved.slice(0, 6).map((u, i) => (
                  <li key={i} className="rounded-none border border-line bg-panel p-2">
                    <code className="font-mono text-ink">{shortFile(u.file)}</code>
                    <span className="text-muted"> — {u.case}</span>
                    {u.diagnosis && (
                      <span className="mt-1 block rounded bg-black/5 px-2 py-0.5 text-[10px] text-amber-300 border border-amber-500/20">
                        {u.diagnosis}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex items-center gap-2 text-[12px] font-medium text-ink">
                <CheckCircle2 className="size-4" />
                <span>No unresolved failures recorded.</span>
              </div>
            )
          ) : <Empty>No report — this project was built before results were kept.</Empty>}
        </Card>

        <Card title="Security" hint="six checks over the generated source" icon={ShieldAlert}>
          {r?.security ? (
            sec.length ? (
              <ul className="space-y-2 text-[11px] text-ink">
                {sec.slice(0, 6).map((f, i) => (
                  <li key={i} className="flex items-center gap-2 rounded-none border border-line bg-panel p-2">
                    <span className={cn('rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider',
                      f.severity === 'blocker' ? 'border border-rose-500/30 bg-rose-500/20 text-rose-300'
                        : f.severity === 'major' ? 'border border-amber-500/30 bg-amber-500/20 text-amber-300'
                        : 'border border-black/10 bg-black/5 text-muted')}>
                      {f.severity}
                    </span>
                    <code className="truncate font-mono text-[11px] text-ink">{f.path}</code>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex items-center gap-2 text-[12px] font-medium text-ink">
                <CheckCircle2 className="size-4" />
                <span>Nothing found.</span>
              </div>
            )
          ) : <Empty>The security stage has no record here.</Empty>}
        </Card>

        <Card title="Performance" hint={qa?.performance?.measured_on || "E2E in-flight metrics & audits"} icon={Gauge}>
          {Object.keys(perf).length ? (
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(perf).map(([k, n]) => (
                <div key={k} className="rounded-none border border-line bg-panel2/50 p-2.5">
                  <Stat n={n} label={k.replace(/-/g, ' ')}
                        tone={n >= 90 ? 'text-ink' : n >= 50 ? 'text-amber-400' : 'text-rose-400'} />
                </div>
              ))}
            </div>
          ) : <Empty>Performance has not run.</Empty>}
        </Card>

        <Card title="Runtime" hint="what the browser probe saw" icon={Terminal}>
          {runtime ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-[12px] font-medium text-ink">
                <span className={cn('size-2 rounded-full', runtime.status === 'running' ? 'bg-emerald-400' : runtime.status === 'failed' ? 'bg-rose-400' : 'bg-amber-400')} />
                <span>Current preview: {runtime.status}</span>
              </div>
              {runtime.url && <p className="break-all font-mono text-[10.5px] text-muted">{runtime.url}</p>}
              {runtime.detail && <p className="text-[11px] text-muted">{runtime.detail}</p>}
              <p className="text-[10.5px] text-muted2">This is the Studio-managed preview state, not a claim that a runtime-error test ran.</p>
            </div>
          ) : ran.includes('runtime') ? (
            (r.runtime || []).length ? (
              <ul className="space-y-1.5 text-[11px] text-rose-400">
                {r.runtime.slice(0, 6).map((e, i) => (
                  <li key={i} className="truncate rounded border border-rose-500/20 bg-rose-500/10 px-2 py-1 font-mono text-[10.5px]">
                    {String(e).split('\n')[0]}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex items-center gap-2 text-[12px] font-medium text-ink">
                <CheckCircle2 className="size-4" />
                <span>No runtime errors.</span>
              </div>
            )
          ) : <Empty>No record.</Empty>}
        </Card>
      </div>
    </div>
  )
}

const Card = ({ title, hint, icon: Icon, children }) => (
  <div className="flex flex-col rounded-none border border-black/10 bg-panel/80 p-5 shadow-xl backdrop-blur-xl transition-all duration-200 hover:border-black/20 hover:bg-panel">
    <div className="mb-2.5 flex items-center justify-between gap-2">
      <h3 className="text-[13px] font-bold tracking-wide text-ink">{title}</h3>
      {Icon && <Icon className="size-4 text-muted2" />}
    </div>
    {hint && <p className="-mt-1 mb-3 text-[11px] text-muted">{hint}</p>}
    <div className="flex-1">{children}</div>
  </div>
)

const shortFile = (p) => String(p || '').split('/').pop()
