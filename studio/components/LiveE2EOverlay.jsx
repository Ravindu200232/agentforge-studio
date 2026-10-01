'use client'

import { CheckCircle2, Loader2, MousePointer2, UserRound } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * What the running test is doing, as a slim strip along the bottom of the preview and a thin progress
 * line along the top. The website itself stays what is on screen.
 */
export default function LiveE2EOverlay({ event }) {
  if (!event) return null
  const done = event.state === 'journey_done'
  const failed = event.state === 'step_failed' || (done && event.ok === false)
  const total = Number(event.total || 0)
  const index = Number(event.index || 0)
  const pct = total ? Math.max(3, Math.min(100, Math.round(index / total * 100))) : 6

  return (
    <>
      <div className="pointer-events-none absolute inset-x-3 top-3 z-[25] h-[3px] overflow-hidden rounded-full bg-black/20">
        <div className={cn('h-full rounded-full transition-all duration-500', failed ? 'bg-rose-500' : 'bg-blue-500')}
             style={{ width: `${pct}%` }} />
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-4 z-[25] flex justify-center px-4">
        <div className="flex max-w-full items-center gap-2.5 rounded-full border border-black/15 bg-panel/90 py-1.5 pl-2.5 pr-4 shadow-[0_10px_30px_rgba(0,0,0,0.45)] backdrop-blur-xl">
          <span className={cn('grid size-6 shrink-0 place-items-center rounded-full',
            failed ? 'bg-rose-500/25 text-rose-300' : done ? 'bg-emerald-500/25 text-ink' : 'bg-blue-500/25 text-blue-300')}>
            {failed ? <MousePointer2 className="size-3" />
              : done ? <CheckCircle2 className="size-3" />
              : <Loader2 className="size-3 animate-spin" />}
          </span>
          <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[.16em] text-accent">Live test</span>
          {event.role && <span className="hidden shrink-0 items-center gap-1 text-[10.5px] text-muted sm:flex"><UserRound className="size-3" />{event.role}</span>}
          <span className="min-w-0 truncate text-[12px] font-semibold text-ink">{event.title || 'End-to-end journey'}</span>
          <span className={cn('hidden min-w-0 truncate text-[11.5px] md:block', failed ? 'text-rose-300' : done ? 'text-ink' : 'text-muted')}>
            {done ? (failed ? (event.message || 'Failed') : 'Passed')
              : failed ? (event.message || event.label || 'The browser found a problem')
              : friendlyStep(event)}
          </span>
          {total > 0 && (
            <span className="shrink-0 rounded-full border border-black/10 bg-black/5 px-2 py-0.5 font-mono text-[10.5px] font-semibold text-ink">
              {Math.min(index, total)}/{total}
            </span>
          )}
        </div>
      </div>
    </>
  )
}

function friendlyStep(event) {
  const verb = String(event.verb || '').toUpperCase()
  const value = String(event.value || '')
  if (verb === 'GOTO') return `Opening ${friendlyRoute(value || event.route)}`
  if (verb === 'CLICK') return `Clicking ${clean(event.label)}`
  if (verb === 'FILL') return `Entering ${clean(event.label)}`
  if (verb === 'SELECT') return `Choosing ${clean(event.label)}`
  if (verb.startsWith('EXPECT')) return `Checking ${clean(event.label)}`
  return clean(event.label) || 'Using the app like a real user'
}

function clean(s) {
  return String(s || '').replace(/\s+/g, ' ').replace(/^(CLICK|FILL|SELECT|EXPECT_[A-Z_]+|GOTO)\s*::?\s*/i, '').slice(0, 100)
}

function friendlyRoute(route) {
  const cleanRoute = String(route || '').split('?')[0].replace(/^\/+|\/+$/g, '')
  if (!cleanRoute) return 'the home page'
  const parts = cleanRoute.split('/').filter(x => x && !/^[0-9a-f]{8,}$/i.test(x))
  const words = parts.map(x => x.replace(/[-_]+/g, ' ')).filter(Boolean)
  if (!words.length) return 'the next page'
  const last = words.at(-1)
  if (words[0] === 'admin') return `${last.replace(/\b\w/g, c => c.toUpperCase())} management`
  return `${last.replace(/\b\w/g, c => c.toUpperCase())} page`
}
