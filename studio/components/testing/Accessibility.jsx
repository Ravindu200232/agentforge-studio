'use client'

import { Badge, Empty, Panel } from '../ui'

export default function Accessibility({ qa }) {
  const result = qa?.accessibility
  if (!result) return <Empty>No automated accessibility test has been recorded yet.</Empty>
  return <div className="space-y-4">
    <Panel className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-ink">axe-core accessibility</h3>
        <Badge tone={result.status === 'passed' ? 'ok' : result.status === 'failed' ? 'bad' : 'mute'}>{result.status}</Badge>
      </div>
      <p className="mt-2 text-xs text-muted">{result.audited || 0}/{result.totalRoutes || 0} routes audited · {result.passed || 0} passed · {result.failed || 0} with violations. Automated WCAG checks do not replace manual keyboard and screen-reader review.</p>
    </Panel>
    {(result.pages || []).map((page, i) => <Panel key={`${page.route}-${i}`} className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <code className="text-xs text-ink">{page.route}</code>
        <Badge tone={page.status === 'passed' ? 'ok' : page.status === 'failed' ? 'bad' : 'mute'}>{page.status}</Badge>
        {page.passedRules != null && <span className="text-[11px] text-muted">{page.passedRules} rules passed · {(page.incomplete || []).length} needs review</span>}
      </div>
      {page.reason && <p className="mt-2 text-xs text-muted">{page.reason}</p>}
      {(page.violations || []).map(v => <div key={v.id} className="mt-3 rounded-none border border-[#FF5630]/30 p-3">
        <p className="text-xs font-semibold text-ink">{v.impact || 'unknown'} · {v.id} — {v.description}</p>
        {(v.nodes || []).map((node, j) => <p key={j} className="mt-1 break-all font-mono text-[11px] text-muted">{(node.target || []).join(' ')} · {node.summary}</p>)}
        {v.helpUrl && <a href={v.helpUrl} target="_blank" rel="noreferrer" className="text-[11px] text-accent underline">Rule guidance</a>}
      </div>)}
      {(page.incomplete || []).map(item => <p key={item.id} className="mt-2 text-xs text-muted">Manual review: {item.id} ({item.count} nodes)</p>)}
    </Panel>)}
    {!result.pages?.length && <Empty>No route was audited. Check the preview, route list and browser availability.</Empty>}
  </div>
}
