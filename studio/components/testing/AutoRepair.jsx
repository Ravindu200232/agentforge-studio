'use client'

import { Badge, Empty, Panel } from '../ui'

export default function AutoRepair({ qa }) {
  const trace = qa?.repairs
  if (!trace) return <Empty>No tool-driven repair record exists for this run.</Empty>
  return <div className="space-y-4">
    <Panel className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-ink">Tool findings → LLM fix → re-test</h3>
        <Badge tone={trace.status === 'fixed' || trace.status === 'not_needed' ? 'ok' : 'warn'}>{trace.status}</Badge>
      </div>
      <p className="mt-2 text-xs text-muted">Up to {trace.maxRounds || 2} repair rounds. The measured checks decide whether a fix worked; the model cannot mark its own changes as passing.</p>
    </Panel>
    {(trace.rounds || []).map(round => <Panel key={round.round} className="p-4">
      <div className="flex flex-wrap items-center gap-2"><b className="text-xs text-ink">Round {round.round}</b>
        <Badge tone={round.status === 'fixed' ? 'ok' : 'warn'}>{round.status}</Badge>
        <span className="text-[11px] text-muted">LLM: {round.agentStatus} · {(round.before || []).length} before → {(round.after || []).length} after</span></div>
      <p className="mt-2 text-xs text-muted">Changed files: {(round.changedFiles || []).length ? round.changedFiles.join(', ') : 'none'}</p>
      {round.reason && <p className="mt-1 text-xs text-[#FFAB00]">{round.reason}</p>}
      {(round.changedFiles || []).length > 0 && <p className="mt-1 text-xs text-muted">Unit rechecked: {round.unitRechecked ? 'yes' : 'no'} · browser journeys rechecked: {round.e2eRechecked ? 'yes' : 'no'}</p>}
      {(round.after || []).length > 0 && <div className="mt-3 space-y-1">
        <p className="text-xs font-semibold text-ink">Still open</p>
        {round.after.map((item, i) => <p key={i} className="break-all text-[11px] text-muted">{item.kind} · {item.route || item.file || item.id} · {typeof item.detail === 'string' ? item.detail : JSON.stringify(item.detail)}</p>)}
      </div>}
    </Panel>)}
    {!trace.rounds?.length && <p className="text-xs text-muted">No actionable findings were measured, so the LLM made no changes.</p>}
  </div>
}
