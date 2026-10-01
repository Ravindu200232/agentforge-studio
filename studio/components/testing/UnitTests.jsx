'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react'
import { Badge, Empty } from '../ui'
import { Summary, Stat } from './TestingResult'
import { cn } from '@/lib/utils'
import { unitTestStatus } from '@/lib/test-counts'

export default function UnitTests({ qa }) {
  const [open, setOpen] = useState(() => new Set())

  const v = qa?.vitest || qa?.savedVitest
  if (!v) {
    return <Empty>No saved unit-test report for this project yet.</Empty>
  }

  const suites = (v.testResults || []).map(t => ({
    file: shortPath(t.name),
    cases: t.assertionResults || [],
  })).sort((a, b) => {
    const af = a.cases.some(c => c.status === 'failed')
    const bf = b.cases.some(c => c.status === 'failed')
    return (bf - af) || a.file.localeCompare(b.file)
  })

  const skipped = suites.flatMap(s => s.cases)
    .filter(c => ['skipped', 'pending', 'todo'].includes(c.status))
  const unit = unitTestStatus(v)

  if (v.fileResults) return (
    <div className="space-y-4">
      <Summary>
        <Stat n={`${unit.passed}/${unit.total}`} label="files passed" tone="text-ok" />
        <Stat n={unit.failed} label="files failed" tone={unit.failed ? 'text-bad' : undefined} />
      </Summary>
      <p className="text-[12px] text-ink">{v.note}</p>
      <p className="font-mono text-[10px] text-muted2">Vitest cache · {new Date(v.recordedAt).toLocaleString()}</p>
      <div className="space-y-2">{v.fileResults.map(row => (
        <div key={row.file} className="flex items-center gap-3 rounded-none border border-line bg-panel px-4 py-3 shadow-lg backdrop-blur-xl">
          <code className="min-w-0 flex-1 break-all font-mono text-[12px] text-ink">{row.file}</code>
          <span className="font-mono text-[11px] text-muted">{row.duration == null ? '—' : `${Math.round(row.duration)}ms`}</span>
          <Badge tone={row.status === 'failed' ? 'bad' : 'ok'}>{row.status}</Badge>
        </div>
      ))}</div>
    </div>
  )

  return (
    <div className="space-y-4">
      {qa.unitEvidenceStatus === 'outdated' && (
        <div className="flex items-center gap-2.5 rounded-none border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-[12px] text-amber-200 shadow-lg backdrop-blur-xl">
          <AlertTriangle className="size-4 shrink-0 text-amber-400" />
          <span>These saved unit results precede the latest code changes.</span>
        </div>
      )}
      {/* The last run tested what the last request changed. The suite is
          everything proved so far, and this says how much of it is not from
          the run that just finished. */}
      {v.carriedForward > 0 && (
        <div className="rounded-none border border-line bg-panel px-4 py-3 text-[12px] text-ink backdrop-blur-xl">
          <b className="font-semibold text-ink">{v.carriedForward}</b> of these {unit.files} files last ran in an earlier
          verification — the newest run covered the rest.
        </div>
      )}
      <Summary>
        <Stat n={unit.passed} label="passing" tone="text-ok" />
        <Stat n={unit.failed} label="failing" tone={unit.failed ? 'text-bad' : undefined} />
        {skipped.length > 0 && (
          <Stat n={skipped.length} label="never ran" tone="text-warn" />
        )}
        <Stat n={unit.files} label="files" />
        <span className="ml-auto font-mono text-[11px] text-muted2">
          {v.startTime ? new Date(v.startTime).toLocaleString() : ''}
        </span>
      </Summary>
      {!suites.length && <p className="text-[12px] text-muted">Saved runner totals. Individual assertion details were not saved.</p>}

      {skipped.length > 0 && (
        <div className="rounded-none border border-warn/30 bg-warn/10 px-4 py-3 text-[12px] text-amber-200">
          <b>{skipped.length}</b> case(s) are marked <code>it.skip</code> and never ran. They are not passing.
        </div>
      )}

      {qa?.report?.unit?.deleted ? (
        <div className="rounded-none border border-bad/30 bg-bad/10 px-4 py-3 text-[12px] text-rose-300">
          <b>{qa.report.unit.deleted}</b> case(s) present when the stage started are no longer in the suite. The numbers above are over what is left.
        </div>
      ) : null}

      <div className="space-y-2.5">
        {suites.map(s => {
          const failed = s.cases.filter(c => c.status === 'failed').length
          const isOpen = open.has(s.file) || failed > 0
          const passed = s.cases.filter(c => c.status === 'passed').length
          return (
            <section key={s.file}
                     className="overflow-hidden rounded-none border border-line bg-panel shadow-xl backdrop-blur-xl transition-all duration-200 hover:border-black/20">
              <button onClick={() => {
                        const next = new Set(open)
                        next.has(s.file) ? next.delete(s.file) : next.add(s.file)
                        setOpen(next)
                      }}
                      className="flex w-full items-center gap-3 bg-panel px-4 py-3 text-left transition-colors hover:bg-black/[0.03]">
                {isOpen ? <ChevronDown className="size-3.5 text-muted" />
                        : <ChevronRight className="size-3.5 text-muted" />}
                <span className={cn('size-2 rounded-full',
                                    failed ? 'bg-bad shadow-[0_0_8px_rgba(255,86,48,0.6)]' : 'bg-ok shadow-[0_0_8px_rgba(34,197,94,0.6)]')} />
                <span className="flex-1 truncate font-mono text-[12px] font-semibold text-ink">
                  {s.file}
                </span>
                <Badge tone={failed ? 'bad' : 'mute'}>
                  {passed}/{s.cases.length}
                </Badge>
              </button>
              {isOpen && (
                <ul className="divide-y divide-line border-t border-line bg-panel">
                  {s.cases.map((c, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-3 py-2.5 pl-10 pr-4 text-[12px] transition-colors hover:bg-black/[0.02]">
                      <span className="flex-1 text-ink">{c.title || c.fullName}</span>
                      <span className={cn('font-mono text-[10px] font-bold uppercase tracking-wider',
                                          TONE[c.status] || 'text-muted2')}>
                        {LABEL[c.status] || c.status}
                      </span>
                      {c.duration != null && (
                        <span className="font-mono text-[10px] text-muted2">
                          {Math.round(c.duration)}ms
                        </span>
                      )}
                      {c.status === 'failed' && (c.failureMessages || []).length > 0 && (
                        <pre className="mt-2 w-full overflow-x-auto whitespace-pre-wrap rounded-none border border-rose-500/20 bg-rose-500/10 p-3 font-mono text-[11px] leading-relaxed text-rose-300">
                          {firstLines(c.failureMessages[0])}
                        </pre>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}

const LABEL = { passed: 'pass', failed: 'fail', pass: 'pass', fail: 'fail',
                warn: 'warn', skipped: 'skipped', pending: 'skipped', todo: 'todo' }
const TONE = { passed: 'text-ok', pass: 'text-ok', failed: 'text-bad',
               fail: 'text-bad', warn: 'text-warn', skipped: 'text-warn',
               pending: 'text-warn' }

// A suite's path is absolute; show it from the test folder down (`test/` or `tests/`).
const shortPath = (p) => String(p || '').replace(/\\/g, '/').replace(/^.*\/(?=tests?\/)/, '')
const firstLines = (m) => String(m || '').split('\n').slice(0, 6).join('\n')
