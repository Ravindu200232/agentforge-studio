'use client'

/** The wireframe: one low-fidelity React app, shown a page at a time, and the user journeys through it. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Loader2,
  ArrowLeft,
  Sparkles,
  Monitor,
  Tablet,
  Smartphone,
} from 'lucide-react'

import { api, isJobCancelled } from '@/lib/api'
import { useStore } from '@/lib/store'
import { attachPicker, pickedFrom } from '@/lib/picker'
import { cn } from '@/lib/utils'
import { Button, Empty, Modal } from '../ui'
import AppPreview from '../AppPreview'
import { AppThumbnail } from '../AppPreview'
import AppTextEdit from '../AppTextEdit'
import WireframeInspector from './WireframeInspector'

const VIEWPORTS = [
  { id: 'desktop', label: 'Desktop', Icon: Monitor },
  { id: 'tablet', label: 'Tablet', Icon: Tablet },
  { id: 'mobile', label: 'Mobile', Icon: Smartphone },
]

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

/** One page, rendered small and not interactive; while the app is being built, a note instead. */
function Thumbnail({ srsId, page, waiting, stamp }) {
  if (!srsId || !page.has_html) {
    const building = page.drawing || waiting
    return (
      <div className="relative flex h-full w-full flex-col items-center justify-center overflow-hidden bg-panel">
        <div className="absolute inset-0 opacity-15 bg-[radial-gradient(var(--accent)_1px,transparent_1px)] [background-size:12px_12px]" />
        {building ? (
          <div className="relative z-10 flex flex-col items-center gap-2 text-center p-3">
            <Loader2 className="size-5 animate-spin text-accent" />
            <span className="text-[11px] font-semibold text-ink tracking-wide">Building the wireframe…</span>
          </div>
        ) : (
          <span className="relative z-10 text-[11px] text-muted2">not built yet</span>
        )}
      </div>
    )
  }
  return <AppThumbnail project={srsId} kind="wireframe" route={page.route} stamp={stamp}
                       title={page.page_name || page.route} />
}

/** The wireframe app, full size: the page list, the page, and the few tools that change it. */
export function WireframeEditor({ owner, page, onClose, onSaved, srsId: given = '' }) {
  const resolved = useSrsId(owner)
  const srsId = given || resolved
  const stamp = useStore(state => state.wireframeStamp[srsId] || 0)

  const [pages, setPages] = useState([page])
  const [viewport, setViewport] = useState('desktop')
  const [mode, setMode] = useState('')                // '' | 'pick' | 'text'
  const [route, setRoute] = useState(page.route)
  const [loaded, setLoaded] = useState(0)
  const [aiOpen, setAiOpen] = useState(false)
  const [aiPrompt, setAiPrompt] = useState('')
  const [element, setElement] = useState('')
  const [updating, setUpdating] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [problem, setProblem] = useState('')
  const [reload, setReload] = useState(0)
  const frame = useRef(null)

  useEffect(() => {
    if (!owner) return
    let live = true
    api.wireframes(owner)
      .then(found => { if (live && found?.pages?.length) setPages(found.pages) })
      .catch(() => {})
    return () => { live = false }
  }, [owner, stamp])

  // Picking: click an element and it travels with the request, so "make this bigger" says what "this" is.
  useEffect(() => {
    const f = frame.current
    if (mode !== 'pick' || !f) return undefined
    return attachPicker(f, (el) => {
      const info = pickedFrom(f, el, viewport)
      const said = `Selected element <${info.tag}>${info.text ? ` — “${info.text.slice(0, 60)}”` : ''}`
      setElement(info.outerHTML || '')
      setAiPrompt(previous => previous.includes(said) ? previous
        : previous.trim() ? `${previous.trim()}\n\n${said}` : said)
      setAiOpen(true)
      setMode('')
    })
  }, [mode, loaded, viewport])

  async function updateWithAi() {
    const request = aiPrompt.trim()
    if (!request || !srsId || updating) return
    setUpdating(true); setProblem('')
    try {
      await api.aiEditWireframe(srsId, request, route, element)
      setAiPrompt(''); setElement(''); setAiOpen(false)
      onSaved?.(null)
    } catch (failure) {
      if (!isJobCancelled(failure)) setProblem(failure?.message || 'The AI could not update the wireframe.')
    } finally {
      setUpdating(false)
    }
  }

  async function regenerate() {
    if (!srsId || regenerating) return
    setRegenerating(true); setProblem('')
    try {
      await api.generateWireframe(srsId)
    } catch (failure) {
      if (!isJobCancelled(failure)) setProblem(failure?.message || 'The wireframe could not be built.')
    } finally {
      setRegenerating(false)
    }
  }

  const busy = updating || regenerating
  const active = pages.find(p => p.route === route) || page

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-none border border-black/10 bg-panel/90 shadow-2xl backdrop-blur-xl">
      <div className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-black/10 bg-black/30 px-3 backdrop-blur-md">
        <div className="flex min-w-0 items-center gap-2">
          <Button variant="outline" size="icon-sm" onClick={onClose} title="Back to wireframes" aria-label="Back to wireframes"
            className="rounded-lg border-black/10 bg-black/[.05] text-ink">
            <ArrowLeft className="size-3.5" />
          </Button>
          <span className="min-w-0">
            <span className="block truncate text-[12px] font-semibold text-ink">
              {active.page_name || active.route}
            </span>
            <span className="block truncate font-mono text-[9.5px] text-muted2">
              {route}{active.roles?.length ? ` · ${active.roles.join(', ')}` : ''}
            </span>
          </span>
        </div>
        <div className="flex items-center gap-1 rounded-full border border-line/80 bg-panel/80 p-1 shadow-sm">
          {VIEWPORTS.map(({ id, label, Icon }) => (
            <button key={id} type="button" title={label} aria-label={label} aria-pressed={viewport === id}
              onClick={() => setViewport(id)}
              className={cn('grid h-7 place-items-center rounded-full px-3 text-ink transition-colors',
                viewport === id ? 'bg-accent shadow-sm' : 'hover:bg-ink/[.06]')}>
              <Icon className="size-3.5" />
            </button>
          ))}
        </div>
      </div>

      {problem ? (
        <p role="alert" className="shrink-0 border-b border-rose-400/20 bg-rose-500/10 px-4 py-2 text-[11.5px] text-rose-300">
          {problem}
        </p>
      ) : null}

      {srsId && (page.has_html || pages.some(p => p.has_html)) ? (
        <AppPreview
          key={reload}
          project={srsId} kind="wireframe" pages={pages} stamp={stamp} viewport={viewport}
          route={page.route} frameRef={frame} onRoute={setRoute}
          onLoaded={() => setLoaded(n => n + 1)}
          frameClassName={cn('transition-all duration-500', busy && 'pointer-events-none scale-[0.99] opacity-40 blur-[6px]')}
        >
          <WireframeInspector
            mode={mode}
            onMode={setMode}
            aiOpen={aiOpen}
            onOpenAi={() => setAiOpen(open => !open)}
            onReload={() => setReload(n => n + 1)}
            onRegenerate={regenerate}
            regenerating={busy}
          />
          {(mode === 'pick' || mode === 'text') && (
            <p className="pointer-events-none absolute inset-x-0 bottom-5 z-30 mx-auto w-fit rounded-full bg-ink/85 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-lg">
              {mode === 'pick' ? 'Click anything on the page — it goes into your request'
                               : 'Click any words on the page and retype them'}
            </p>
          )}
          <AppTextEdit
            frameRef={frame} active={mode === 'text'} loaded={loaded} project={srsId} kind="wireframe"
            onSaved={() => { setMode(''); onSaved?.(null) }}
            onAskAi={({ old, value }) => {
              setAiPrompt(`Change the text “${old}” to “${value}”.`)
              setMode(''); setAiOpen(true)
            }}
          />
          {aiOpen && (
            <form
              onSubmit={event => { event.preventDefault(); updateWithAi() }}
              className="absolute bottom-4 left-1/2 z-40 w-[min(680px,calc(100%-6rem))] -translate-x-1/2 rounded-xl border border-line bg-panel p-3 shadow-2xl"
            >
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <Sparkles className="size-4 shrink-0 text-accent" />
                  <div>
                    <p className="text-[11px] font-semibold text-ink">Update this wireframe with AI</p>
                    <p className="text-[10px] text-muted">The agent edits the app's source. You are on {route}.</p>
                  </div>
                </div>
                <button type="button" onClick={() => setAiOpen(false)} className="text-[11px] text-muted hover:text-ink">Close</button>
              </div>
              <div className="flex items-end gap-2">
                <textarea
                  autoFocus
                  value={aiPrompt}
                  onChange={event => setAiPrompt(event.target.value)}
                  placeholder="Describe any change to this page or the whole wireframe…"
                  rows={2}
                  className="min-h-[48px] flex-1 resize-none rounded-lg border border-line bg-white px-3 py-2 text-[11px] text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
                />
                <Button variant="solid" size="sm" disabled={!aiPrompt.trim() || busy} className="h-9 rounded-lg text-[11px]">
                  {updating ? <><Loader2 className="size-3 animate-spin" /> Sending</> : <><Sparkles className="size-3" /> Send</>}
                </Button>
              </div>
            </form>
          )}
          {busy && (
            <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-panel/85 backdrop-blur-md">
              <Loader2 className="size-8 animate-spin text-accent" />
              <h3 className="mt-4 text-[15px] font-bold tracking-tight text-ink">
                {regenerating ? 'Building the wireframe…' : 'The AI is updating the wireframe…'}
              </h3>
              <p className="mt-1 max-w-sm text-center text-[12px] leading-relaxed text-ink">
                {regenerating ? 'Every page is built again from the specification.'
                              : 'It edits the app, then the preview is built again.'}
              </p>
            </div>
          )}
        </AppPreview>
      ) : (
        <div className="flex min-h-0 flex-1 items-center justify-center bg-panel text-[12px] text-muted">
          {srsId ? 'The wireframe is not built yet.' : 'This project has no specification to build from.'}
        </div>
      )}
    </div>
  )
}

/** The modal the workspace opens a page in. */
function PageEditor({ owner, page, onClose, onSaved, srsId = '' }) {
  return (
    <Modal
      onClose={onClose}
      overlayClassName="!p-0 backdrop-blur-none"
      style={{ maxWidth: 'none', width: '100%', height: '100%', maxHeight: '100%' }}
      className="overflow-hidden rounded-none border-0 p-0"
    >
      <div className="flex h-full min-h-0 gap-4 bg-panel p-5">
        <WireframeEditor owner={owner} srsId={srsId} page={page}
          onClose={onClose} onSaved={onSaved} />
      </div>
    </Modal>
  )
}

export function Wireframes({ srs, onEditPage, onApprove, onRetryPrototype,
                             generating = false, approving = false }) {
  const owner = srs?.project || srs?.srs_id || srs?.id || ''
  const srsId = useSrsId(owner)
  const srsStamp = useStore(state => state.srsStamp[owner] || 0)
  const stamp = useStore(state => state.wireframeStamp[srsId] || 0)
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(null)
  const [error, setError] = useState('')
  const [building, setBuilding] = useState(false)
  const [designApproved, setDesignApproved] = useState(false)

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

  // A chat/feature update may rewrite the SRS or the wireframe without remounting
  // this tab. Refresh only this data view; never reload the whole Studio app.
  useEffect(() => { load() }, [load, srsStamp])

  /** Poll the status periodically while the app is being built. */
  const waiting = generating || Boolean(data?.drawing)
  useEffect(() => {
    if (!waiting) return
    load()
    const again = setInterval(load, 2000)
    return () => clearInterval(again)
  }, [waiting, load])

  useEffect(() => { if (!generating) load() }, [generating, load])

  /** Build the whole app again from the specification. */
  async function regenerate() {
    if (!srsId) return
    setBuilding(true); setError('')
    try {
      await api.generateWireframe(srsId)
      load()
    } catch (failure) {
      if (!isJobCancelled(failure)) setError(failure?.message || 'The wireframe could not be built.')
    } finally {
      setBuilding(false)
    }
  }

  const pages = data?.pages || []
  if (error && !data) return <Empty>{error}</Empty>
  if (!data) return <Empty>Reading the wireframes…</Empty>
  if (!pages.length) return <Empty>{waiting
    ? 'Reading the approved plan and preparing the wireframe pages…'
    : 'No pages in the specification yet, so there is nothing to build.'}</Empty>

  const built = Boolean(data?.app?.built)
  const busy = waiting || building

  return (
    <div className="space-y-3">
      {error && <p role="alert" className="text-xs text-rose-400">{error}</p>}
      {/* Progress while the wireframe app is being built. */}
      {waiting && (
        <p className="flex items-center gap-2.5 rounded-none border border-accent/30 bg-accent
                      px-3.5 py-2.5 text-[11.5px] leading-relaxed text-ink">
          <Loader2 className="size-3.5 shrink-0 animate-spin text-accent" />
          <span>
            Building the wireframe — the agent writes one React app for all {pages.length} pages, and
            they appear here when it is built. You can carry on; this keeps going without you.
          </span>
        </p>
      )}
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <p className="text-[11.5px] text-muted">
          {pages.length} page{pages.length === 1 ? '' : 's'}, low fidelity, in one React app.
          Open one to click through it, retype text, or ask for a change.
          {built ? '' : ' Not built yet.'}
        </p>
        <div className="flex items-center gap-2">
          {onApprove && (designApproved ? (
            <Button variant="solid" disabled={busy || approving || !built}
                    onClick={onRetryPrototype} title="Generate the prototype again using the approved design">
              {approving ? <><Loader2 className="mr-1.5 size-3.5 animate-spin" />Planning prototype…</>
                         : 'Regenerate prototype'}
            </Button>
          ) : (
            <Button variant="solid" disabled={busy || approving || !built}
                    onClick={onApprove}
                    title={built ? 'Approve the wireframe and choose the design'
                                 : 'Build the wireframe before approving it'}>
              Approve wireframes → Design
            </Button>
          ))}
          <Button variant="outline" disabled={busy || !srsId} onClick={regenerate}>
            {busy
              ? <><Loader2 className="mr-1 size-3 animate-spin" /> Building…</>
              : built ? 'Build again' : 'Build the wireframe'}
          </Button>
        </div>
      </div>
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(260px,1fr))]">
        {pages.map((page, index) => (
          <div key={`${page.route || 'wireframe'}-${index}`} className="group relative">
            <button type="button"
              onClick={() => (onEditPage ? onEditPage(page) : setOpen(page))}
              className="w-full overflow-hidden rounded-none border border-line text-left transition hover:border-accent cursor-pointer">
              <span className="block aspect-[16/11] overflow-hidden border-b border-line bg-white">
                <Thumbnail srsId={srsId} page={page} waiting={waiting} stamp={stamp} />
              </span>
              <span className="block space-y-1 p-3">
                <span className="truncate block text-[12px] font-medium text-ink">{page.page_name}</span>
                <span className="block truncate font-mono text-[10px] text-muted2">{page.route}</span>
                <span className="block truncate text-[10px] text-muted2">
                  {page.roles?.length ? page.roles.join(', ') : 'public'}
                </span>
                {page.error && <span className="block text-[10px] text-rose-400" title={page.error}>Build failed · build again</span>}
              </span>
            </button>
          </div>
        ))}
      </div>
      {open && (
        <PageEditor owner={owner} srsId={srsId} page={open}
          onClose={() => setOpen(null)}
          onSaved={() => { load() }} />
      )}
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
