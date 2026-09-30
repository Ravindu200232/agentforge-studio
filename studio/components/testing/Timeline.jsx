'use client'

import { Badge, Empty, Table, TR, TH, TD } from '../ui'
import { cn } from '@/lib/utils'


export default function Timeline({ qa }) {
  const timeline = qa?.timeline || []
  const history = qa?.resultHistory || []
  if (timeline.length || history.length) return (
    <div className="space-y-6">
      {history.length > 0 && <section>
        <div className="mb-3 rounded-none border border-line bg-panel px-4 py-3">
          <p className="text-[12px] font-semibold text-ink">Saved result history</p>
          <p className="mt-1 text-[11.5px] text-muted">These are immutable snapshots from earlier Testing runs and approved chat changes. The current result remains in the other Testing tabs; a new feature, bug fix or repair cannot replace these records.</p>
        </div>
        <Table><thead><TR><TH>Saved</TH><TH>Run / change</TH><TH>Unit tests</TH><TH>Browser / E2E</TH></TR></thead>
          <tbody>{history.map((row, index) => {
            const unit = row.counts?.unit
            const browser = row.counts?.browser
            return <TR key={`${row.id || row.at}-${index}`}>
              <TD className="whitespace-nowrap text-muted">{row.at ? new Date(row.at).toLocaleString() : 'Time not recorded'}</TD>
              <TD><p className="text-ink">{row.label || row.kind || 'Saved test record'}</p><span className="text-[10px] text-muted2">{row.source === 'version' ? 'before approved chat change' : row.kind}</span></TD>
              <TD>{unit ? <Badge tone={unit.failed ? 'bad' : 'ok'}>{unit.passed}/{unit.total} passed</Badge> : <span className="text-muted2">not recorded</span>}</TD>
              <TD>{browser ? <Badge tone={browser.failed ? 'bad' : 'ok'}>{browser.passed}/{browser.total} passed</Badge> : <span className="text-muted2">not recorded</span>}</TD>
            </TR>
          })}</tbody>
        </Table>
      </section>}
      {timeline.length > 0 && <section>
      <p className="mb-4 text-[11.5px] text-muted">Recorded checks in time order. Retry attempts remain visible; saved artifacts use their recorded timestamps.</p>
      <Table><thead><TR><TH>When</TH><TH>Stage</TH><TH>Check / source</TH><TH>Result</TH></TR></thead>
        <tbody>{timeline.map((row, index) => (
          <TR key={index}>
            <TD className="whitespace-nowrap text-muted">{row.at ? new Date(row.at).toLocaleString() : 'Time not recorded'}</TD>
            <TD>{row.kind}</TD>
            <TD><p className="text-ink">{row.suite}</p><code className="break-all text-[10px] text-muted2">{row.command || row.source}</code></TD>
            <TD><Badge tone={row.status === 'failed' ? 'bad' : row.status === 'passed' ? 'ok' : 'mute'}>{row.status}</Badge></TD>
          </TR>
        ))}</tbody>
      </Table>
      </section>}
    </div>
  )
  const rows = qa?.history || []
  if (!rows.length) {
    return <Empty>No history yet — it starts at the next build.</Empty>
  }
  const floor = rows[rows.length - 1].floor ?? 90

  return (
    <div>
      <p className="mb-3 text-[11px] text-muted">
        Each bar is one build&apos;s round-one pass rate. The dashed line is the
        {' '}{floor}% floor.
      </p>

      <div className="relative mb-4 flex h-[150px] items-end gap-1.5 border-b
                      border-dashed border-line pb-0">
        <div className="pointer-events-none absolute inset-x-0 border-t border-dashed
                        border-warn/60"
             style={{ top: `${100 - floor}%` }} />
        {rows.map((r, i) => (
          <div key={i} title={`${r.passed}/${r.cases} — ${r.at}`}
               className="flex h-full max-w-[46px] flex-1 flex-col items-center
                          justify-end">
            <div className={cn('w-full rounded-none',
                               r.rate < floor ? 'bg-bad' : 'bg-ok')}
                 style={{ height: `${r.rate}%`, minHeight: 2 }} />
            <span className="mt-1 font-mono text-[9px] text-muted2">{r.rate}%</span>
          </div>
        ))}
      </div>

      <Table>
        <thead>
          <TR>
            <TH>when</TH><TH>cases</TH><TH>passed</TH><TH>failed</TH>
            <TH>rate</TH><TH>largest class</TH>
          </TR>
        </thead>
        <tbody>
          {rows.slice().reverse().map((r, i) => (
            <TR key={i} className={r.rate < (r.floor ?? floor) ? 'bg-bad/[0.06]' : ''}>
              <TD className="font-mono text-muted">
                {String(r.at || '').replace('T', ' ').replace('+00:00', '')}
              </TD>
              <TD className="font-mono">{r.cases}</TD>
              <TD className="font-mono text-ok">{r.passed}</TD>
              <TD className={cn('font-mono', r.failed ? 'text-bad' : 'text-muted2')}>
                {r.failed}
              </TD>
              <TD><b className="font-mono text-ink">{r.rate}%</b></TD>
              <TD className="text-muted">
                {(r.top || [])[0] ? `${r.top[0].count} × ${r.top[0].class}` : '—'}
              </TD>
            </TR>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
