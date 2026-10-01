'use client'

/**
 * The journeys running in parallel, and how far each one has got.
 *
 * Each lane used to reserve most of its card for a screenshot of its own
 * browser. There is one browser now and it streams into the preview, so that
 * space was a black rectangle that never filled in — and it pushed the step
 * the lane is actually on down to a line of small print.
 *
 * The step is the card now.
 */

import { useStore } from '@/lib/store'

function tone(state, ok) {
  if (state === 'step_failed' || ok === false) return 'border-rose-500/30 bg-rose-500/5 shadow-rose-500/5'
  if (state === 'journey_done') return 'border-emerald-500/30 bg-emerald-500/5 shadow-emerald-500/5'
  if (state === 'step' || state === 'step_done' || state === 'journey_start') {
    return 'border-blue-500/30 bg-blue-500/5 shadow-blue-500/5'
  }
  return 'border-black/10 bg-panel/80'
}

function label(state) {
  if (state === 'journey_start') return 'starting'
  if (state === 'journey_done') return 'done'
  if (state === 'step_failed') return 'failed'
  if (state === 'step_done') return 'running'
  if (state === 'step') return 'running'
  return 'idle'
}

export default function E2ELiveLanes() {
  const e2e = useStore(s => s.e2eParallel)
  const workers = Math.max(1, Math.min(4, e2e?.workers || 4))
  const lanes = (e2e?.lanes || []).slice(0, workers)
  const active = lanes.some(x => x.title || x.state !== 'idle')

  if (!active && !e2e?.active) return null

  return (
    <div className="flex h-full min-h-0 flex-col p-4">
      <div className="mb-3 flex shrink-0 items-center gap-2.5">
        <span className="size-2 animate-pulse rounded-full bg-accent shadow-[0_0_8px_rgba(191, 185, 255,0.8)]" />
        <span className="text-[13px] font-bold text-ink tracking-wide">Parallel E2E</span>
        <span className="font-mono text-[11px] text-muted">
          {workers} lanes{e2e?.waves ? ` · wave ${e2e.wave || 1}/${e2e.waves}` : ''}
        </span>
      </div>

      <div className="grid min-h-0 flex-1 auto-rows-min grid-cols-1 gap-3 overflow-y-auto sm:grid-cols-2">
        {lanes.map((lane, i) => {
          const pct = lane.total ? Math.min(100, Math.round((lane.index / lane.total) * 100)) : 0
          return (
            <section key={lane.lane || i + 1}
                     className={`flex min-h-0 flex-col overflow-hidden rounded-none border shadow-xl backdrop-blur-xl transition-all duration-200 ${tone(lane.state, lane.ok)}`}>
              <div className="flex shrink-0 items-center gap-2.5 border-b border-black/5 px-4 py-2.5">
                <b className="font-mono text-[11px] font-bold text-accent">LANE {lane.lane || i + 1}</b>
                <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-ink">
                  {lane.title || 'Waiting for a journey'}
                </span>
                <span className="rounded-full border border-black/10 bg-black/5 px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wider text-muted">{label(lane.state)}</span>
              </div>

              <div className="space-y-2.5 px-4 py-3">
                <p className={`text-[12px] leading-relaxed ${lane.message ? 'text-rose-400' : 'text-ink'}`}>
                  {lane.message || lane.label || 'Waiting for a browser lane'}
                </p>
                <div className="flex items-center gap-2 text-[10.5px] text-muted">
                  <span className="truncate">{lane.role || 'browser'}</span>
                  <span>·</span>
                  <code className="min-w-0 flex-1 truncate font-mono text-ink">{lane.route || '/'}</code>
                  <span className="tabular-nums font-semibold text-ink">{lane.total ? `${lane.index}/${lane.total}` : ''}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-black/10">
                  <div className={`h-full rounded-full transition-[width] duration-300 ${
                    lane.ok === false ? 'bg-rose-500' : 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]'}`}
                       style={{ width: `${pct}%` }} />
                </div>
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
