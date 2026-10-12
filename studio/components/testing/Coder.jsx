'use client'

import { useState } from 'react'
import { Empty, Tag } from '../ui'
import { cn } from '@/lib/utils'

/** "textIncludes textIncludes: page text contains 'x'" -> the part worth reading. */
function stepLabel(step) {
  const text = String(step?.label || step?.name || '').trim()
  return text.replace(/^(\w+)\s+\1(?=[:\s])/, '$1')
}

/**
 * A browser journey has no file to open, so show the steps it ran instead.
 *
 * The unit column answers "what does this test say"; without this the E2E
 * column answered only "how many passed", and the steps a journey actually
 * drove - the ones a failure has to be read against - were nowhere on screen.
 */
function Journey({ flow }) {
  const stages = flow?.stages || []
  return (
    <div className="min-w-0 flex-1 overflow-auto rounded-none bg-code p-3.5">
      <div className="mb-3 border-b border-line pb-3 font-mono text-[11px] leading-[1.9]">
        <div><span className="text-muted2">journey</span> <span className="text-ink">{flow.title}</span></div>
        {flow.role && <div><span className="text-muted2">role</span> <span className="text-ink">{flow.role}</span></div>}
        {flow.flow && <div><span className="text-muted2">driver</span> <span className="text-ink">{flow.flow}</span></div>}
      </div>
      {stages.length === 0 ? (
        <p className="font-mono text-[11px] text-muted">No steps were recorded for this journey.</p>
      ) : (
        <ol className="space-y-1">
          {stages.map((step, i) => (
            <li key={i} className="flex gap-3 font-mono text-[11px] leading-[1.7]">
              <span className="w-6 shrink-0 text-right text-muted2">{step.index ?? i + 1}</span>
              <span className={cn('w-4 shrink-0',
                step.status === 'failed' ? 'text-bad'
                  : step.status === 'passed' ? 'text-ok' : 'text-muted2')}>
                {step.status === 'failed' ? '✕' : step.status === 'passed' ? '✓' : '·'}
              </span>
              <span className={cn('min-w-0 break-all',
                step.status === 'failed' ? 'text-bad' : 'text-ink')}>
                {stepLabel(step)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

export default function Coder({ qa }) {
  const legacyTests = qa?.tests || {}
  const sources = Array.isArray(qa?.testSources) && qa.testSources.length
    ? qa.testSources
    : Object.keys(legacyTests).sort().map(path => ({ path, kind: path.startsWith('e2e/') ? 'e2e' : 'unit', code: legacyTests[path] }))
  const unitSources = sources.filter(source => source.kind === 'unit')
  const e2eSources = sources.filter(source => source.kind === 'e2e')
  const supportSources = sources.filter(source => source.kind === 'support')
  const flows = ((qa?.report?.e2e || {}).flows || []).filter(f => f?.title)
  const [sel, setSel] = useState(null)

  if (!sources.length && !flows.length) {
    return <Empty>No test files or recorded journeys for this project.</Empty>
  }

  const items = [
    ...unitSources.map(source => ({ key: `source:${source.path}`, kind: 'unit', name: source.path, source })),
    ...e2eSources.map(source => ({ key: `source:${source.path}`, kind: 'e2e', name: source.path, source })),
    ...supportSources.map(source => ({ key: `source:${source.path}`, kind: 'support', name: source.path, source })),
    ...flows.map((flow, index) => ({ key: `journey:${flow.title}:${index}`, kind: 'journey', name: flow.title, flow })),
  ]
  const current = items.find(i => i.key === sel) || items[0]

  const Row = ({ item }) => (
    <button onClick={() => setSel(item.key)}
            className={cn('block w-full rounded-none px-2 py-1.5 text-left transition-colors',
              item.key === current.key ? 'bg-accent' : 'hover:bg-panel2')}>
      <span className="block truncate font-mono text-[11px] text-ink">
        {item.kind === 'journey' ? item.name : item.name.split('/').pop()}
      </span>
      <span className="block truncate text-[9px] text-muted2">
        {item.kind === 'journey'
          ? `${(item.flow.stages || []).length} recorded steps`
          : item.kind === 'support'
            ? 'test configuration'
            : item.name.replace(/\/[^/]+$/, '')}
      </span>
      {item.kind === 'unit' && item.name.includes('/quarantine/') && <Tag tone="bad">set aside</Tag>}
      {item.kind === 'journey' && (item.flow.stages || []).some(s => s.status === 'failed') && (
        <Tag tone="bad">failed</Tag>
      )}
    </button>
  )

  const Heading = ({ children, count }) => (
    <p className="px-2 pb-1 pt-3 text-[9px] uppercase tracking-wider text-muted2 first:pt-0">
      {children} <span className="text-muted2/70">{count}</span>
    </p>
  )

  return (
    <div className="flex h-full min-h-[420px] gap-3">
      <aside className="w-[240px] shrink-0 overflow-y-auto border-r border-line pr-1">
        {unitSources.length > 0 && <Heading count={unitSources.length}>Unit test code</Heading>}
        {items.filter(i => i.kind === 'unit').map(item => <Row key={item.key} item={item} />)}
        {e2eSources.length > 0 && <Heading count={e2eSources.length}>E2E test code</Heading>}
        {items.filter(i => i.kind === 'e2e').map(item => <Row key={item.key} item={item} />)}
        {supportSources.length > 0 && <Heading count={supportSources.length}>Test setup</Heading>}
        {items.filter(i => i.kind === 'support').map(item => <Row key={item.key} item={item} />)}
        {flows.length > 0 && <Heading count={flows.length}>Recorded journeys</Heading>}
        {items.filter(i => i.kind === 'journey').map(item => <Row key={item.key} item={item} />)}
      </aside>

      {current.kind === 'journey' ? <Journey flow={current.flow} /> : (
        <pre className="min-w-0 flex-1 overflow-auto rounded-none bg-code p-3.5
                        font-mono text-[11px] leading-[1.7] text-ink">
          {current.source?.code || legacyTests[current.name]}
        </pre>
      )}
    </div>
  )
}
