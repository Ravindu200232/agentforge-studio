'use client'

/**
 * The plan, laid out to be read.
 *
 * This is the one moment someone is asked to approve what is about to be
 * built, and it used to arrive as raw Markdown in a monospace block — the
 * shape of a file, not of a proposal. Headings become headings, bullets
 * become bullets, and the parts that matter are legible at a glance.
 */

import { readInline, readPlan } from '@/lib/plan-read'
import { cn } from '@/lib/utils'

function Inline({ text }) {
  return readInline(text).map((part, i) => {
    if (part.kind === 'strong') return <b key={i} className="font-semibold text-ink">{part.text}</b>
    if (part.kind === 'em') return <i key={i} className="text-ink">{part.text}</i>
    if (part.kind === 'code') {
      return (
        <code key={i} className="rounded-md border border-black/10 bg-black/[0.06] px-1.5 py-0.5 font-mono text-[11px] text-cyan-300">
          {part.text}
        </code>
      )
    }
    return <span key={i}>{part.text}</span>
  })
}

export default function PlanReading({ plan, className }) {
  const blocks = readPlan(plan)
  if (!blocks.length) {
    return <p className={cn('text-xs text-muted', className)}>The planner returned nothing to read.</p>
  }

  return (
    <div className={cn('space-y-4', className)}>
      {blocks.map((block, i) => {
        if (block.kind === 'heading') {
          return (
            <h3 key={i} className={cn('flex items-center gap-2', block.level <= 1
              ? 'pt-2 text-[14px] font-bold text-ink tracking-tight'
              : 'pt-2 text-[11px] font-bold uppercase tracking-[.12em] text-accent')}>
              {block.level <= 1 && <span className="size-1.5 rounded-full bg-accent shadow-[0_0_8px_rgba(191, 185, 255,0.8)]" />}
              <Inline text={block.text} />
            </h3>
          )
        }

        if (block.kind === 'bullets') {
          return (
            <ul key={i} className="space-y-2">
              {block.items.map((item, j) => (
                <li key={j} className="flex items-start gap-3 text-[12.5px] leading-relaxed text-ink">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent shadow-[0_0_8px_rgba(191, 185, 255,0.8)]" />
                  <span className="min-w-0"><Inline text={item} /></span>
                </li>
              ))}
            </ul>
          )
        }

        if (block.kind === 'steps') {
          return (
            <ol key={i} className="space-y-2">
              {block.items.map((item, j) => (
                <li key={j} className="flex items-start gap-3 text-[12.5px] leading-relaxed text-ink">
                  <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-lg border border-accent/30 bg-accent font-mono text-[10px] font-bold text-ink shadow-sm">
                    {j + 1}
                  </span>
                  <span className="min-w-0"><Inline text={item} /></span>
                </li>
              ))}
            </ol>
          )
        }

        if (block.kind === 'code') {
          return (
            <pre key={i} className="overflow-x-auto rounded-xl border border-black/10 bg-panel p-3 font-mono text-[11px] leading-relaxed text-ink shadow-inner">
              {block.text}
            </pre>
          )
        }

        return (
          <p key={i} className="text-[12.5px] leading-relaxed text-ink">
            <Inline text={block.text} />
          </p>
        )
      })}
    </div>
  )
}
