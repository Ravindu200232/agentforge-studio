'use client'

import { Badge, Empty, Panel } from '../ui'

export default function Security({ qa }) {
  const security = qa?.security || qa?.report?.security
  if (!security) return <Empty>No security scan evidence has been saved for this project.</Empty>
  const zap = security.zap || {}
  const findings = [...(security.findings || []), ...(zap.findings || [])]
  return <div className="space-y-3">
    <Panel className="p-4">
      <div className="flex flex-wrap items-center gap-2"><h3 className="text-sm font-semibold text-ink">OWASP ZAP</h3>
        <Badge tone={zap.status === 'passed' ? 'ok' : zap.status === 'failed' ? 'bad' : 'warn'}>{zap.status || 'not run'}</Badge></div>
      <p className="mt-2 text-xs text-muted">{zap.reason || zap.detail || 'The scan is counted only when an actual local-server ZAP report was saved.'}</p>
      {zap.report && <p className="mt-2 break-all font-mono text-xs text-muted">Report: {zap.report}</p>}
    </Panel>
    {security.audit && <Panel className="p-4"><h3 className="text-sm font-semibold text-ink">Dependency audit</h3>
      <pre className="mt-2 overflow-auto text-xs text-muted">{JSON.stringify(security.audit, null, 2)}</pre></Panel>}
    {findings.map((item, i) => <Panel key={i} className="p-4"><div className="flex gap-2"><Badge tone="bad">{item.severity || item.risk || 'finding'}</Badge><b className="text-xs text-ink">{item.name || item.code || item.title}</b></div>
      <p className="mt-2 text-xs text-muted">{item.what || item.description || item.detail}</p></Panel>)}
    {!findings.length && <p className="text-xs text-muted">No findings are recorded. This is not proof of a clean scan unless ZAP completed successfully.</p>}
  </div>
}
