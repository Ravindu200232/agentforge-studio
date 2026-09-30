'use client'

import { Badge, Empty, Panel } from '../ui'

const number = value => Number.isFinite(Number(value)) ? Number(value) : 0
const severityTone = value => {
  const level = String(value || '').toLowerCase()
  if (level.includes('high') || level.includes('critical')) return 'bad'
  if (level.includes('medium') || level.includes('low')) return 'warn'
  return 'mute'
}

export default function Security({ qa }) {
  const security = qa?.security || qa?.report?.security
  if (!security) return <Empty>No security scan evidence has been saved for this project.</Empty>
  const zap = security.zap || {}
  const findings = [...(security.findings || []), ...(zap.findings || [])]
  const counts = zap.counts || {}
  const high = number(counts.high) || findings.filter(item => /high|critical/i.test(String(item.severity || item.risk))).length
  const medium = number(counts.medium) || findings.filter(item => /medium/i.test(String(item.severity || item.risk))).length
  const low = number(counts.low) || findings.filter(item => /low/i.test(String(item.severity || item.risk))).length
  const informational = number(counts.informational) || findings.filter(item => /informational/i.test(String(item.severity || item.risk))).length
  const needsAttention = high > 0 || medium > 0 || low > 0

  return <div className="space-y-3">
    <Panel className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-ink">Security baseline</h3>
        <Badge tone={zap.status === 'passed' ? 'ok' : zap.status === 'failed' ? 'bad' : 'warn'}>{zap.status === 'passed' ? 'baseline completed' : zap.status || 'not run'}</Badge>
        {needsAttention && <Badge tone="warn">action needed</Badge>}
      </div>
      <p className="mt-2 text-xs text-muted">
        {needsAttention
          ? `${high} high, ${medium} medium and ${low} low findings need review before a public launch.`
          : 'No high, medium or low findings were recorded by the completed baseline.'}
      </p>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[[high, 'high'], [medium, 'medium'], [low, 'low'], [informational, 'informational']].map(([count, label]) => (
          <div key={label} className="rounded-none border border-line bg-panel2/50 p-3">
            <p className={`text-xl font-bold ${count && label !== 'informational' ? 'text-amber-600' : 'text-ink'}`}>{count}</p>
            <p className="text-[11px] text-muted">{label}</p>
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-muted">{zap.reason || 'The scan is counted only when a local-server report was saved.'}</p>
      {zap.activeScan === false && <p className="mt-2 text-xs text-amber-700">Scope: passive baseline only. No active attack scan was run, so this is not a full security sign-off.</p>}
      {zap.report && <p className="mt-2 break-all font-mono text-[11px] text-muted">Saved report: {zap.report}</p>}
    </Panel>

    {security.audit && <Panel className="p-4"><h3 className="text-sm font-semibold text-ink">Dependency audit</h3>
      <p className="mt-2 text-xs text-muted">{security.audit.summary || 'A dependency audit result was recorded.'}</p></Panel>}

    {findings.map((item, index) => <Panel key={`${item.name || item.code || item.title}-${index}`} className="p-4">
      <div className="flex flex-wrap gap-2"><Badge tone={severityTone(item.severity || item.risk)}>{item.severity || item.risk || 'finding'}</Badge><b className="text-xs text-ink">{item.name || item.code || item.title}</b></div>
      <p className="mt-2 text-xs text-muted">{item.what || item.description || item.detail}</p>
    </Panel>)}
    {!findings.length && <p className="text-xs text-muted">No findings are recorded. This is not proof of a clean scan unless the baseline completed successfully.</p>}
  </div>
}
