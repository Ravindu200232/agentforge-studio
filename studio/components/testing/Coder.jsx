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
                step.status === 'failed' ? 'text-[#FF5630]'
                  : step.status === 'passed' ? 'text-ink' : 'text-muted2')}>
                {step.status === 'failed' ? '✕' : step.status === 'passed' ? '✓' : '·'}
              </span>
              <span className={cn('min-w-0 break-all',
                step.status === 'failed' ? 'text-[#FF5630]' : 'text-ink')}>
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
  const tests = qa?.tests || {}
  const names = Object.keys(tests).sort()
  const flows = ((qa?.report?.e2e || {}).flows || []).filter(f => f?.title)
  const [sel, setSel] = useState(null)

  if (!names.length && !flows.length) {
    return <Empty>No test files or recorded journeys for this project.</Empty>
  }

  const items = [
    ...names.map(n => ({ key: `unit:${n}`, kind: 'unit', name: n })),
    ...flows.map((f, i) => ({ key: `e2e:${f.title}:${i}`, kind: 'e2e', name: f.title, flow: f })),
  ]
  const current = items.find(i => i.key === sel) || items[0]

  const Row = ({ item }) => (
    <button onClick={() => setSel(item.key)}
            className={cn('block w-full rounded-none px-2 py-1.5 text-left transition-colors',
              item.key === current.key ? 'bg-accent' : 'hover:bg-panel2')}>
      <span className="block truncate font-mono text-[11px] text-ink">
        {item.kind === 'unit' ? item.name.split('/').pop() : item.name}
      </span>
      <span className="block truncate text-[9px] text-muted2">
        {item.kind === 'unit'
          ? item.name.replace(/\/[^/]+$/, '')
          : `${(item.flow.stages || []).length} steps`}
      </span>
      {item.kind === 'unit' && item.name.includes('/quarantine/') && <Tag tone="bad">set aside</Tag>}
      {item.kind === 'e2e' && (item.flow.stages || []).some(s => s.status === 'failed') && (
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
        {names.length > 0 && <Heading count={names.length}>Unit tests</Heading>}
        {items.filter(i => i.kind === 'unit').map(item => <Row key={item.key} item={item} />)}
        {flows.length > 0 && <Heading count={flows.length}>Browser journeys</Heading>}
        {items.filter(i => i.kind === 'e2e').map(item => <Row key={item.key} item={item} />)}
      </aside>

      {current.kind === 'e2e' ? <Journey flow={current.flow} /> : (
        <pre className="min-w-0 flex-1 overflow-auto rounded-none bg-code p-3.5
                        font-mono text-[11px] leading-[1.7] text-ink">
          {tests[current.name]}
        </pre>
      )}
    </div>
  )
}
