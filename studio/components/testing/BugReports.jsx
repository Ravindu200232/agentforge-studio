'use client'

import { Empty, Panel, Tag } from '../ui'

export default function BugReports({ qa }) {
  const r = qa?.report
  if (!r) {
    return <Empty>No report — this project was built before results were kept.</Empty>
  }
  const unresolved = r.suite?.unresolved || []
  const suspects = r.suite?.suspects || []
  const quarantined = r.suite?.quarantined || []
  const failures = r.suite?.failures || []
  const resolved = qa?.resolvedBugs || []

  if (!unresolved.length && !suspects.length && !quarantined.length && !failures.length && !resolved.length) {
    return <p className="text-[12px] text-muted">{qa.complete ? 'No unresolved failures recorded.' : 'No open failures in the saved partial report. Verification is incomplete.'}</p>
  }

  return (
    <div className="space-y-4">
      {resolved.length > 0 && <section className="space-y-2">
        <h3 className="text-[12px] font-semibold text-ink">Recorded fixes</h3>
        {resolved.map((row, index) => <Panel key={index} className="p-3.5">
          <div className="mb-2 flex flex-wrap gap-2"><Tag>historical fix</Tag><b className="text-[12px] text-ink">{row.problem}</b></div>
          <p className="text-[11px] text-muted">{row.cause}</p>
          <p className="mt-2 text-[11px] text-ink">{row.verification}</p>
          <p className="mt-1 text-[10px] text-muted2">{row.at} · .agent/knowledge.json</p>
        </Panel>)}
      </section>}
      {unresolved.length > 0 && (
        <div className="space-y-2">
          {unresolved.map((u, i) => (
            <Panel key={i} className="border-l-2 border-l-bad p-3.5">
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <Tag tone="bad">unresolved</Tag>
                <b className="text-[12px] text-ink">{u.case}</b>
                {u.diagnosis && <Tag>{u.diagnosis}</Tag>}
              </div>
              <p className="mb-1 font-mono text-[10.5px] text-muted">
                {u.file}{u.target ? ` → ${u.target}` : ''}
              </p>
              <p className="text-[11.5px] text-ink">{u.message}</p>
              {u.why && <p className="mt-1 text-[10.5px] text-muted2">{u.why}</p>}
            </Panel>
          ))}
        </div>
      )}

      {suspects.length > 0 && (
        <section>
          <h3 className="mb-1 text-[12px] font-semibold text-ink">
            Suspected bugs in the app
          </h3>
          <p className="mb-2 text-[10.5px] text-muted2">
            Left by the test author: the code looked wrong, but a test has to
            describe what the code does.
          </p>
          <ul className="space-y-1 text-[11.5px] text-muted">
            {suspects.map((s, i) => (
              <li key={i}>
                <code className="font-mono text-ink">{s.test}</code> — {s.note}
              </li>
            ))}
          </ul>
        </section>
      )}

      {quarantined.length > 0 && (
        <section>
          <h3 className="mb-1 text-[12px] font-semibold text-ink">Set aside</h3>
          <ul className="space-y-1 font-mono text-[11px] text-bad">
            {quarantined.map((q, i) => <li key={i}>{q}</li>)}
          </ul>
        </section>
      )}
    </div>
  )
}
