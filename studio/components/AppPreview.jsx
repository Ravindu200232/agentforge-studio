'use client'

/**
 * The wireframe and the prototype are React apps. This frames one, one page at a time, and lists its pages on the side:
 * click a page to open it, click inside the app and the list follows. What the frame may do is the preview's own
 * rule (see lib/preview-guard.js); a button in the app can go to another page of it and nowhere else.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { ShieldAlert } from 'lucide-react'

import { api } from '@/lib/api'
import { FRAME_SANDBOX, attachGuard, confinedTo, goTo, routeMatches } from '@/lib/preview-guard'
import { cn } from '@/lib/utils'

export const VIEWPORT_WIDTHS = { desktop: null, tablet: 834, mobile: 390 }

/** The frame itself: sandboxed, guarded, and brought back to the page the app was on after a reload. */
export function AppFrame({
  project, kind, route = '/', stamp = 0, title, className, style, frameRef,
  onRoute, onBlocked, onLoaded, ...rest
}) {
  const own = useRef(null)
  const ref = frameRef || own
  const detach = useRef(null)
  const current = useRef(route)
  const callbacks = useRef({})
  callbacks.current = { onRoute, onBlocked, onLoaded }

  // Only a new build (or another project) changes the address, never the page: moving between pages sets the hash.
  const src = useMemo(() => api.appUrl(project, kind, current.current, stamp), [project, kind, stamp])

  useEffect(() => {
    current.current = route
    goTo(ref.current, route)
  }, [route, ref])

  useEffect(() => () => detach.current?.(), [])

  function loaded() {
    detach.current?.()
    detach.current = null
    const frame = ref.current
    if (!frame) return
    // A script that assigned location.href carried the frame off: put the app back.
    if (!confinedTo(frame, src)) {
      callbacks.current.onBlocked?.({ what: 'navigation', href: '' })
      frame.src = src
      return
    }
    detach.current = attachGuard(frame, {
      onBlocked: (blocked) => callbacks.current.onBlocked?.(blocked),
      onRoute: (next) => { current.current = next; callbacks.current.onRoute?.(next) },
    })
    callbacks.current.onLoaded?.(frame)
  }

  return (
    <iframe
      ref={ref}
      key={`${project}:${kind}`}
      title={title || `${kind} preview`}
      src={src}
      sandbox={FRAME_SANDBOX}
      onLoad={loaded}
      className={cn('block border-0 bg-white', className)}
      style={style}
      {...rest}
    />
  )
}

/** One page of an app, small and not interactive, for the grid of pages. */
export function AppThumbnail({ project, kind, route, stamp, title }) {
  return (
    <div className="relative h-full w-full overflow-hidden bg-white">
      <AppFrame
        project={project} kind={kind} route={route} stamp={stamp} title={title}
        loading="lazy" tabIndex={-1} aria-hidden="true"
        className="pointer-events-none origin-top-left"
        style={{ width: '1280px', height: '1000px', transform: 'scale(0.23)' }}
      />
    </div>
  )
}

/** The frame with its page list. `children` is drawn over the frame (tools, notices). */
export default function AppPreview({
  project, kind, pages = [], stamp = 0, viewport = 'desktop', route: wanted,
  frameRef, onRoute, onLoaded, onBlocked, children, className, frameClassName,
}) {
  const [route, setRoute] = useState(wanted || pages[0]?.route || '/')
  const [note, setNote] = useState('')
  const timer = useRef(null)
  const width = VIEWPORT_WIDTHS[viewport] || null

  useEffect(() => { if (wanted) setRoute(wanted) }, [wanted])
  useEffect(() => () => clearTimeout(timer.current), [])

  function blocked(what) {
    onBlocked?.(what)
    const where = what?.href ? ` (${String(what.href).slice(0, 60)})` : ''
    setNote(what?.what === 'popup' ? 'A new window was blocked — the preview stays in this frame.'
      : `That link leaves the app${where}, so it was blocked.`)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setNote(''), 3500)
  }

  return (
    <div className={cn('flex min-h-0 min-w-0 flex-1', className)}>
      <nav aria-label="Pages" className="flex w-52 shrink-0 flex-col overflow-y-auto border-r border-line bg-panel">
        <p className="shrink-0 border-b border-line px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted2">
          Pages · {pages.length}
        </p>
        {pages.map((page) => {
          const on = routeMatches(page.route, route)
          return (
            <button
              key={page.route}
              type="button"
              aria-current={on ? 'page' : undefined}
              onClick={() => setRoute(page.route)}
              className={cn(
                'block w-full cursor-pointer border-b border-line/60 px-3 py-2 text-left transition-colors',
                on ? 'bg-accent text-ink' : 'text-muted hover:bg-ink/[.05] hover:text-ink',
              )}
            >
              <span className="block truncate text-[12px] font-medium">{page.page_name || page.route}</span>
              <span className="block truncate font-mono text-[10px] text-muted2">{page.route}</span>
            </button>
          )
        })}
      </nav>
      <div className="relative flex min-h-0 min-w-0 flex-1 justify-center overflow-hidden bg-[#F2F0EF]">
        <div
          className={cn('relative h-full max-w-full overflow-hidden bg-white', width && 'border-x border-black/10 shadow-2xl')}
          style={{ width: width ? `${width}px` : '100%' }}
        >
          <AppFrame
            project={project} kind={kind} route={route} stamp={stamp} frameRef={frameRef}
            onRoute={(next) => { setRoute(next); onRoute?.(next) }}
            onBlocked={blocked} onLoaded={onLoaded}
            className={cn('absolute inset-0 h-full w-full', frameClassName)}
          />
        </div>
        {note && (
          <p role="status" className="pointer-events-none absolute inset-x-0 bottom-5 z-20 mx-auto flex w-fit max-w-[80%] items-center gap-2 rounded-full bg-ink/90 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-lg">
            <ShieldAlert className="size-3.5 shrink-0" /> {note}
          </p>
        )}
        {children}
      </div>
    </div>
  )
}
