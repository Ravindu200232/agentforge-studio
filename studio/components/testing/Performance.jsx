'use client'

import { Badge, Empty, Table, TR, TH, TD } from '../ui'

export default function Performance({ qa }) {
  const load = qa?.load
  const browser = qa?.performance
  const hasBrowser = Object.keys(browser?.scores || {}).length > 0
  if (!load && !hasBrowser) return <Empty>No performance measurement has been recorded yet.</Empty>
  return <div className="space-y-5">
    <section className="rounded-none border border-line bg-panel p-4">
      <div className="flex flex-wrap items-center gap-2"><h3 className="text-sm font-semibold text-ink">HTTP load sample</h3>
        <Badge tone={load?.status === 'completed' ? 'ok' : load?.status === 'failed' ? 'bad' : 'mute'}>{load?.status || 'not run'}</Badge></div>
      {load?.reason && <p className="mt-2 text-xs text-muted">{load.reason}</p>}
      {!load && <p className="mt-2 text-xs text-muted">A separate HTTP load sample was not part of this saved verification. The browser performance audit below did run; it measures page experience, not concurrent-user capacity.</p>}
      {load?.requests != null && <>
        <p className="mt-2 break-all font-mono text-[11px] text-muted">GET {load.url}</p>
        <Table><thead><TR><TH>measurement</TH><TH>result</TH></TR></thead><tbody>
          <TR><TD>Tool and scope</TD><TD>{load.tool} · {load.scope}</TD></TR>
          <TR><TD>Sample</TD><TD>{load.durationSeconds}s · {load.connections} connections · {load.requests} requests</TD></TR>
          <TR><TD>Throughput</TD><TD>{load.requestsPerSecond} requests/s</TD></TR>
          <TR><TD>Latency p50 / p97.5 / p99</TD><TD>{load.latencyMs?.p50 ?? '—'} / {load.latencyMs?.p97_5 ?? '—'} / {load.latencyMs?.p99 ?? '—'} ms</TD></TR>
          <TR><TD>Errors / timeouts</TD><TD>{load.errors} / {load.timeouts}</TD></TR>
          <TR><TD>HTTP status counts</TD><TD>{Object.entries(load.statusCodeStats || {}).map(([code, value]) => `${code}: ${value?.count ?? value}`).join(', ') || 'none recorded'}</TD></TR>
        </tbody></Table>
        <p className="mt-2 text-[11px] text-muted">A short local endpoint sample, not proof of peak capacity or an end-to-end user load test. {load.measuredAt && `Recorded ${new Date(load.measuredAt).toLocaleString()}.`}</p>
      </>}
    </section>
    {hasBrowser && <section className="rounded-none border border-line bg-panel p-4">
      <h3 className="mb-2 text-sm font-semibold text-ink">Browser performance</h3>
      {browser.runtimeError && <p className="text-xs text-bad">{browser.runtimeError}</p>}
      <Table><thead><TR><TH>metric</TH><TH>value</TH></TR></thead><tbody>
        {Object.entries(browser.scores).map(([key, value]) => <TR key={key}><TD>{key}</TD><TD>{value}</TD></TR>)}
        {Object.entries(browser.metrics || {}).map(([key, value]) => <TR key={key}><TD>{key}</TD><TD>{String(value)}</TD></TR>)}
      </tbody></Table>
      {browser.measured_on && <p className="mt-2 text-[11px] text-muted">Measured via {browser.measured_on}.</p>}
    </section>}
  </div>
}
