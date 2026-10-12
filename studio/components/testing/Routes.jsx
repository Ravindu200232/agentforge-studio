'use client'

import { Badge, Empty, Table, TR, TH, TD } from '../ui'

/**
 * Every API handler that has a test, and any route the probe found broken.
 *
 * Built from the manifest and the runtime record rather than guessed from the
 * file tree: a route that exists on disk and 500s is the interesting case, and
 * the file tree cannot tell you that.
 */
export default function Routes({ qa }) {
  if (qa?.contracts?.length) return (
    <div>
      <div className="mb-4 rounded-none border border-line bg-panel px-4 py-3">
        <p className="text-[12px] font-semibold text-ink">{qa.contracts.length} API handlers found in this project</p>
        <p className="mt-1 text-[11.5px] text-muted">This inventory is read from the built app’s handler files. A handler is linked to a <b>unit</b> test that imports it, and to an <b>e2e</b> test whose browser called it (with the method and the status it answered). A handler with neither is shown as a coverage gap, not hidden as an empty result.</p>
      </div>
      <Table><thead><TR><TH>Route / methods</TH><TH>Handler</TH><TH>Linked tests</TH></TR></thead>
        <tbody>{qa.contracts.map(row => (
          <TR key={row.handler}>
            <TD><code className="text-ink">{row.route}</code><p className="mt-1 text-[10px] text-muted">{row.methods.join(' · ') || 'Methods not resolved'}</p></TD>
            <TD className="break-all font-mono text-muted">{row.handler}</TD>
            <TD>{row.tests.length ? row.tests.map(test => (
              <div key={`${test.kind}-${test.file}-${test.title || ''}`} className="mb-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="mute">{test.kind || 'unit'}</Badge>
                  <code className="break-all text-[10px]">{test.file}</code>
                  <Badge tone={test.status === 'failed' ? 'bad' : test.status === 'passed' ? 'ok' : 'mute'}>{test.status}</Badge>
                </div>
                {test.title && <p className="mt-1 text-[10.5px] text-ink">{test.title}</p>}
                {!!test.calls?.length && <p className="mt-0.5 font-mono text-[10px] text-muted">called: {test.calls.join(' · ')}</p>}
              </div>
            )) : <Badge>no linked test record</Badge>}</TD>
          </TR>
        ))}</tbody>
      </Table>
    </div>
  )
  const runtime = qa?.report?.runtime || []
  const manifest = qa?.manifest || {}

  const tested = [...new Set(Object.values(manifest)
    .map(m => m?.target || '')
    .filter(t => t.startsWith('app/api/')))].sort()

  // A runtime error line names its route; pair them up so a broken one shows.
  const broken = {}
  for (const line of runtime) {
    const m = /Route (\/\S*)/.exec(String(line))
    if (m) broken[m[1]] = String(line).split('\n')[0]
  }

  if (!tested.length && !Object.keys(broken).length) {
    return <Empty>No route record for this project.</Empty>
  }

  return (
    <div>
      <p className="mb-3 text-[11px] text-muted">
        API handlers that have a test, and any route the browser probe found
        broken.
      </p>
      <Table>
        <thead>
          <TR><TH>route</TH><TH>handler</TH><TH>status</TH></TR>
        </thead>
        <tbody>
          {tested.map(t => (
            <TR key={t}>
              <TD>
                <code className="font-mono text-ink">
                  /{t.replace(/^app\//, '').replace(/\/route\.jsx?$/, '')}
                </code>
              </TD>
              <TD className="font-mono text-muted">{t}</TD>
              <TD><Badge tone="ok">tested</Badge></TD>
            </TR>
          ))}
          {Object.entries(broken).map(([route, why]) => (
            <TR key={route} className="bg-bad/[0.06]">
              <TD><code className="font-mono text-ink">{route}</code></TD>
              <TD className="text-muted2">—</TD>
              <TD><Badge tone="bad">{why}</Badge></TD>
            </TR>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
