'use client'

import { Badge, Empty, Panel } from '../ui'

export default function AutoRepair({ qa }) {
  const trace = qa?.repairs
  const buildRepairs = qa?.buildRepairs
  if (!trace && buildRepairs) return <div className="space-y-4">
    <Panel className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-ink">Build repairs already completed</h3>
        <Badge tone="ok">{buildRepairs.status}</Badge>
      </div>
      <p className="mt-2 text-xs text-muted">The initial build found and repaired the issues below, then recorded its checks. The separate Testing-stage repair loop did not run, so this is build evidence rather than a new repair attempt.</p>
    </Panel>
    {buildRepairs.items.map((item, index) => <Panel key={index} className="p-4">
      <p className="text-xs font-semibold text-ink">{item.where}</p>
      <p className="mt-2 text-xs text-muted">{item.problem}</p>
      <p className="mt-2 text-xs text-emerald-700"><span className="font-semibold">Repaired:</span> {item.fix}</p>
    </Panel>)}
  </div>
  if (!trace) return <Empty>No repair cycle was needed or recorded after testing. Build-time repair evidence will appear here when it exists.</Empty>
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
      {round.reason && <p className="mt-1 text-xs text-warn">{round.reason}</p>}
      {(round.changedFiles || []).length > 0 && <p className="mt-1 text-xs text-muted">Unit rechecked: {round.unitRechecked ? 'yes' : 'no'} · browser journeys rechecked: {round.e2eRechecked ? 'yes' : 'no'}</p>}
      {(round.after || []).length > 0 && <div className="mt-3 space-y-1">
        <p className="text-xs font-semibold text-ink">Still open</p>
        {round.after.map((item, i) => <p key={i} className="break-all text-[11px] text-muted">{item.kind} · {item.route || item.file || item.id} · {typeof item.detail === 'string' ? item.detail : JSON.stringify(item.detail)}</p>)}
      </div>}
    </Panel>)}
    {!trace.rounds?.length && <p className="text-xs text-muted">No actionable findings were measured, so the LLM made no changes.</p>}
  </div>
}
