'use client'

/** The wireframes: a low-fidelity React app the agent built, shown as it is, with its pages listed and a box to ask for a change. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ExternalLink, Loader2, RotateCw, Send } from 'lucide-react'

import { api, isJobCancelled } from '@/lib/api'
import { useStore } from '@/lib/store'
import { cn } from '@/lib/utils'
import { Button, Empty } from '../ui'

/** The `prj_…` id the drawings live under, whichever way the owner is named. */
function useSrsId(owner) {
  const [srsId, setSrsId] = useState(() => (/^prj_/.test(owner || '') ? owner : ''))
  useEffect(() => {
    if (!owner) return
    if (/^prj_/.test(owner)) { setSrsId(owner); return }
    // A built project owns its pages by name; `link.json` is the only thing
    // that knows both names, and the studio reads it through `srs-results`.
    let live = true
    api.srsResults(owner)
      .then(found => { if (live) setSrsId(found?.link?.srs_id || '') })
      .catch(() => {})
    return () => { live = false }
  }, [owner])
  return srsId
}

/** Whether the address `here` (`/orders/7`) is the route `pattern` (`/orders/[id]`). */
function same(pattern, here) {
  const a = String(pattern || '').split('/').filter(Boolean)
  const b = String(here || '').split('?')[0].split('/').filter(Boolean)
  return a.length === b.length && a.every((part, i) => /^\[.+\]$|^:/.test(part) || part === b[i])
}

export function Wireframes({ srs, onApprove, onRetryPrototype, generating = false, approving = false }) {
  const owner = srs?.project || srs?.srs_id || srs?.id || ''
  const srsId = useSrsId(owner)
  const srsStamp = useStore(state => state.srsStamp[owner] || 0)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [drawing, setDrawing] = useState(false)
  const [route, setRoute] = useState('')
  const [asking, setAsking] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [designApproved, setDesignApproved] = useState(false)
  const frame = useRef(null)

  useEffect(() => {
    if (!srsId) return
    let active = true
    api.designSpec(srsId).then(answer => {
      if (active) setDesignApproved(Boolean(answer?.customizer_approved))
    }).catch(() => {})
    return () => { active = false }
  }, [srsId])

  const load = useCallback(() => {
    if (!owner) return
    api.wireframes(owner)
      .then(result => { setData(result); setError('') })
      .catch(failure => setError(failure?.message || 'The wireframes could not be read.'))
  }, [owner])

  // A chat/feature update may rewrite the SRS or the wireframes without remounting
  // this tab. Refresh only this data view; never reload the whole Studio app.
  useEffect(() => { load() }, [load, srsStamp])

  /** Poll while the agent is drawing, so the pages light up as their files are written. */
  const waiting = generating || Boolean(data?.drawing)
  useEffect(() => {
    if (!waiting) return
    load()
    const again = setInterval(load, 2500)
    return () => clearInterval(again)
  }, [waiting, load])

  useEffect(() => { if (!generating) load() }, [generating, load])

  const pages = data?.pages || []
  const built = Boolean(data?.built)
  const drawn = pages.filter(p => p.has_html).length

  // The page on show: the first drawn one until a page is picked.
  useEffect(() => {
    if (!pages.length) return
    if (!route || !pages.some(p => p.route === route)) setRoute((pages.find(p => p.has_html) || pages[0]).route)
  }, [pages, route])

  // A link inside the wireframes moves the frame to another page: follow it in the list.
  useEffect(() => {
    if (!built) return
    const id = setInterval(() => {
      try {
        const hash = frame.current?.contentWindow?.location?.hash?.slice(1)
        if (!hash) return
        const found = pages.find(p => p.route === hash) || pages.find(p => same(p.route, hash))
        if (found && found.route !== route) setRoute(found.route)
      } catch { /* the frame is not on our own address yet */ }
    }, 500)
    return () => clearInterval(id)
  }, [built, pages, route])

  const src = useMemo(
    () => (srsId && built ? api.webUrl(srsId, 'wireframe', route, data?.version) : ''),
    [srsId, built, route, data?.version],
  )

  /** Draw every page again, from the start. */
  async function drawAll() {
    if (!srsId) return
    setDrawing(true); setError('')
    try {
      await api.buildWireframes(srsId)
      load()
    } catch (failure) {
      if (!isJobCancelled(failure)) setError(failure?.message || 'The wireframes could not be drawn.')
    } finally {
      setDrawing(false)
    }
  }

  async function ask(event) {
    event?.preventDefault()
    const request = prompt.trim()
    if (!srsId || !request || asking) return
    setAsking(true); setError('')
    try {
      await api.editWireframe(srsId, request, route)
      setPrompt('')
      load()
    } catch (failure) {
      if (!isJobCancelled(failure)) setError(failure?.message || 'The change could not be made.')
    } finally {
      setAsking(false)
    }
  }

  if (error && !data) return <Empty>{error}</Empty>
  if (!data) return <Empty>Reading the wireframes…</Empty>
  if (!pages.length) return <Empty>{waiting
    ? 'Reading the approved plan and preparing the wireframes…'
    : 'No pages in the specification yet, so there is nothing to draw.'}</Empty>

  const busy = drawing || waiting || asking
  const current = pages.find(p => p.route === route)

  return (
    <div className="flex h-full min-h-[520px] flex-col gap-3">
      {error && <p role="alert" className="text-xs text-rose-400">{error}</p>}
      {waiting && (
        <p className="flex items-center gap-2.5 rounded-none border border-accent/30 bg-accent px-3.5 py-2.5 text-[11.5px] leading-relaxed text-ink">
          <Loader2 className="size-3.5 shrink-0 animate-spin text-accent" />
          <span>
            The agent is drawing the wireframes: one React page for each screen, then the app is bundled. {drawn} of {pages.length} pages
            written so far. You can carry on; this keeps going without you.
          </span>
        </p>
      )}
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <p className="text-[11.5px] text-muted">
          {pages.length} page{pages.length === 1 ? '' : 's'} as a low-fidelity React app (shadcn/ui, Tailwind), with sample data. Click
          through them, or ask for a change.
          {drawn === pages.length ? ' All drawn.' : ` ${drawn} of ${pages.length} drawn so far.`}
        </p>
        <div className="flex items-center gap-2">
          {onApprove && (designApproved ? (
            <Button variant="solid" disabled={busy || approving || drawn === 0}
                    onClick={onRetryPrototype} title="Generate the prototype again using the approved design">
              {approving ? <><Loader2 className="mr-1.5 size-3.5 animate-spin" />Planning prototype…</>
                         : 'Regenerate prototype'}
            </Button>
          ) : (
            <Button variant="solid" disabled={busy || approving || drawn === 0} onClick={onApprove}
                    title={drawn === 0 ? 'Draw the wireframes before approving them' : 'Approve the wireframes and choose the design'}>
              Approve wireframes → Design
            </Button>
          ))}
          <Button variant="outline" disabled={busy || !srsId} onClick={drawAll}>
            {drawing || waiting
              ? <><Loader2 className="mr-1 size-3 animate-spin" /> Drawing…</>
              : drawn ? 'Draw them again' : 'Draw the wireframes'}
          </Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 [grid-template-columns:230px_minmax(0,1fr)]">
        <ul className="min-h-0 space-y-1 overflow-y-auto pr-1" aria-label="Wireframe pages">
          {pages.map((page, index) => (
            <li key={`${page.route || 'wireframe'}-${index}`}>
              <button type="button" onClick={() => setRoute(page.route)}
                className={cn('w-full rounded-none border px-3 py-2 text-left transition',
                  page.route === route ? 'border-accent bg-accent' : 'border-line hover:border-accent')}>
                <span className="flex items-center gap-2">
                  <span className={cn('size-1.5 shrink-0 rounded-full', page.has_html ? 'bg-ok' : page.drawing ? 'animate-pulse bg-accent' : 'bg-muted2')} />
                  <span className="truncate text-[12px] font-medium text-ink">{page.page_name}</span>
                </span>
                <span className="mt-0.5 block truncate font-mono text-[10px] text-muted2">{page.route}</span>
                <span className="block truncate text-[10px] text-muted2">{page.roles?.length ? page.roles.join(', ') : 'public'}</span>
              </button>
            </li>
          ))}
        </ul>

        <div className="flex min-h-0 min-w-0 flex-col gap-2">
          <div className="relative min-h-[420px] flex-1 overflow-hidden rounded-none border border-line bg-white">
            {src ? (
              <iframe ref={frame} key={data?.version} title="wireframes" src={src} className="absolute inset-0 h-full w-full border-0" />
            ) : (
              <div className="absolute inset-0 grid place-items-center bg-panel p-6 text-center text-[12px] text-muted">
                {waiting ? 'Drawing…' : data?.pages?.[0]?.error || 'The wireframes are not drawn yet.'}
              </div>
            )}
            {src && (
              <div className="absolute right-2 top-2 flex gap-1">
                <button type="button" title="Reload" onClick={() => frame.current?.contentWindow?.location.reload()}
                  className="grid size-7 place-items-center rounded-md bg-black/60 text-white hover:bg-black/80"><RotateCw className="size-3.5" /></button>
                <a href={src} target="_blank" rel="noreferrer" title="Open in its own window"
                  className="grid size-7 place-items-center rounded-md bg-black/60 text-white hover:bg-black/80"><ExternalLink className="size-3.5" /></a>
              </div>
            )}
          </div>
          <form onSubmit={ask} className="flex items-center gap-2">
            <input value={prompt} onChange={event => setPrompt(event.target.value)} disabled={busy || !built}
              placeholder={current ? `Ask for a change${current.page_name ? ` to ${current.page_name}` : ''}…` : 'Ask for a change…'}
              className="min-w-0 flex-1 rounded-none border border-line bg-panel px-3 py-2 text-[12px] text-ink outline-none focus:border-accent disabled:opacity-50" />
            <Button variant="outline" type="submit" disabled={busy || !built || !prompt.trim()}>
              {asking ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}

export function UserJourney({ srs }) {
  const owner = srs?.project || srs?.srs_id || srs?.id || ''
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!owner) return
    api.wireframes(owner).then(setData).catch(() => setData({ journeys: [] }))
  }, [owner])

  const journeys = data?.journeys || []
  const routes = useMemo(
    () => new Map((data?.pages || []).map(p => [p.route, p.page_name])), [data])

  if (!data) return <Empty>Reading the journeys…</Empty>
  if (!journeys.length) return <Empty>No workflows in the specification yet.</Empty>

  return (
    <div className="space-y-4">
      <p className="text-[11.5px] text-muted">
        {journeys.length} journey{journeys.length === 1 ? '' : 's'} through the product, each step
        on the screen it happens on. A step marked <span className="text-muted2">carried</span> did
        not name a screen itself — it continues on the one before it.
      </p>
      {journeys.map(flow => (
        <div key={flow.workflow_name} className="rounded-none border border-line bg-panel p-4">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h3 className="text-[13px] font-semibold text-ink">{flow.workflow_name}</h3>
            {flow.who && <span className="text-[11px] text-muted2">{flow.who}</span>}
          </div>
          <ol className="mt-3 space-y-0">
            {flow.steps.map((step, i) => (
              <li key={i} className="relative flex gap-3 pb-4 last:pb-0">
                <span className="relative flex flex-col items-center">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full
                                   border border-line bg-panel2 font-mono text-[10px] text-muted">
                    {i + 1}
                  </span>
                  {i < flow.steps.length - 1 && (
                    <span className="mt-1 w-px flex-1 bg-line" />
                  )}
                </span>
                <span className="min-w-0 flex-1 pb-1">
                  <span className="block text-[11.5px] text-ink">{step.step}</span>
                  {step.route && (
                    <span className="mt-0.5 flex flex-wrap items-baseline gap-2">
                      <code className="font-mono text-[10px] text-accent">{step.route}</code>
                      <span className="text-[10px] text-muted2">
                        {routes.get(step.route) || ''}{step.named === false ? ' · carried' : ''}
                      </span>
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  )
}
