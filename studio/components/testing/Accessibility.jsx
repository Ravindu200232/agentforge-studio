'use client'

import { Badge, Empty, Panel } from '../ui'

export default function Accessibility({ qa }) {
  const result = qa?.accessibility
  if (!result) return <Empty>No automated accessibility test has been recorded yet.</Empty>
  const detailedAudited = Number(result.audited || 0)
  const recordedAudited = Math.max(detailedAudited, Number(result.declaredAudited || 0), Number(result.totalRoutes || 0))
  const recordedPassed = Math.max(Number(result.passed || 0), Number(result.declaredPassed || 0))
  const automatedPassed = result.status === 'passed' && recordedAudited > 0 && recordedPassed >= recordedAudited
  return <div className="space-y-4">
    <Panel className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-ink">Accessibility — what was checked</h3>
        <Badge tone={automatedPassed ? 'ok' : result.status === 'failed' ? 'bad' : 'mute'}>{automatedPassed ? 'automated checks passed' : result.status}</Badge>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-none border border-line bg-panel2/50 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[.1em] text-muted">Automated WCAG</p>
          <p className="mt-1 text-xl font-bold text-ink">{recordedPassed}/{recordedAudited || '—'}</p>
          <p className="mt-1 text-[11px] text-muted">public screens passed</p>
        </div>
        <div className="rounded-none border border-line bg-panel2/50 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[.1em] text-muted">Keyboard journey</p>
          <p className="mt-1 text-xl font-bold text-ink">{result.keyboard === 'passed' ? 'Passed' : 'Not recorded'}</p>
          <p className="mt-1 text-[11px] text-muted">keyboard-only browser flow</p>
        </div>
        <div className="rounded-none border border-line bg-panel2/50 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[.1em] text-muted">Manual review</p>
          <p className="mt-1 text-xl font-bold text-amber-600">Needed</p>
          <p className="mt-1 text-[11px] text-muted">screen reader and human check</p>
        </div>
      </div>
      <p className="mt-4 text-xs text-muted">{result.failed || 0} automated violations recorded. {result.declaredDetail || `${detailedAudited}/${result.totalRoutes || detailedAudited} detailed route records are available.`} Automated WCAG checks do not replace a manual screen-reader and keyboard review.</p>
    </Panel>
    {(result.pages || []).map((page, i) => <Panel key={`${page.route}-${i}`} className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <code className="text-xs text-ink">{page.route}</code>
        <Badge tone={page.status === 'passed' ? 'ok' : page.status === 'failed' ? 'bad' : 'mute'}>{page.status}</Badge>
        {page.passedRules != null && <span className="text-[11px] text-muted">{page.passedRules} rules passed · {(page.incomplete || []).length} needs review</span>}
      </div>
      {page.reason && <p className="mt-2 text-xs text-muted">{page.reason}</p>}
      {(page.violations || []).map(v => <div key={v.id} className="mt-3 rounded-none border border-bad/30 p-3">
        <p className="text-xs font-semibold text-ink">{v.impact || 'unknown'} · {v.id} — {v.description}</p>
        {(v.nodes || []).map((node, j) => <p key={j} className="mt-1 break-all font-mono text-[11px] text-muted">{(node.target || []).join(' ')} · {node.summary}</p>)}
        {v.helpUrl && <a href={v.helpUrl} target="_blank" rel="noreferrer" className="text-[11px] text-accent underline">Rule guidance</a>}
      </div>)}
      {(page.incomplete || []).map(item => <p key={item.id} className="mt-2 text-xs text-muted">Manual review: {item.id} ({item.count} nodes)</p>)}
    </Panel>)}
    {!result.pages?.length && <Empty>No route was audited. Check the preview, route list and browser availability.</Empty>}
  </div>
}
