'use client'

/** Renders and edits in-place HTML wireframes and their associated user journeys. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Loader2,
  Trash2,
  ArrowLeft,
  Sparkles,
} from 'lucide-react'

import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { cn } from '@/lib/utils'
import { Button, Empty, Modal } from '../ui'
import WireframeInspector from './WireframeInspector'

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

/** One page, rendered small and not interactive, with generation animation when drawing. */
function Thumbnail({ srsId, page, waiting }) {
  const isGenerating = page.drawing || (waiting && !page.has_html)
  if (!srsId || !page.has_html) {
    return (
      <div className="relative flex h-full w-full flex-col items-center justify-center overflow-hidden bg-panel">
        <div className="absolute inset-0 opacity-15 bg-[radial-gradient(var(--accent)_1px,transparent_1px)] [background-size:12px_12px]" />
        {isGenerating ? (
          <div className="relative z-10 flex flex-col items-center gap-2 text-center p-3">
            <Loader2 className="size-5 animate-spin text-accent" />
            <span className="text-[11px] font-semibold text-ink tracking-wide">Drawing wireframe…</span>
            <span className="text-[9px] text-muted2">Synthesizing blueprint layout</span>
          </div>
        ) : (
          <span className="relative z-10 text-[11px] text-muted2">not drawn yet</span>
        )}
      </div>
    )
  }
  return (
    <div className="relative h-full w-full overflow-hidden bg-white">
      <iframe
        title={page.page_name || page.route}
        src={api.wireframeHtmlUrl(srsId, page.route)}
        sandbox="allow-same-origin"
        loading="lazy"
        tabIndex={-1}
        aria-hidden="true"
        className={cn(
          "pointer-events-none origin-top-left border-0 transition-all duration-500",
          isGenerating && "filter blur-[4px] opacity-40 scale-[0.98]"
        )}
        style={{ width: '1280px', height: '1000px', transform: 'scale(0.23)' }}
      />
      {isGenerating && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-panel/75 backdrop-blur-[2px] z-10 transition-all">
          <Loader2 className="size-5 animate-spin text-accent" />
          <span className="mt-2 text-[11px] font-semibold text-ink tracking-wide">Updating…</span>
          <span className="text-[9px] text-muted font-mono">Redrawing wireframe</span>
        </div>
      )}
    </div>
  )
}

/* Interactive full-size wireframe editor canvas with Figma positioning and editing tools. */
export function WireframeEditor({ owner, page, onClose, onSaved, srsId: given = '' }) {
  const resolved = useSrsId(owner)
  const srsId = given || resolved

  const [drawing, setDrawing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState('')
  const [stamp, setStamp] = useState(page.has_html ? 1 : 0)
  const [stale, setStale] = useState(Boolean(page.html_stale))
  const [dirty, setDirty] = useState(false)
  const [selectionKey, setSelectionKey] = useState(0)
  const [aiOpen, setAiOpen] = useState(false)
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiUpdating, setAiUpdating] = useState(false)
  const [selectionMode, setSelectionMode] = useState(false)
  const frame = useRef(null)
  const editor = useRef(null)
  const selectionModeRef = useRef(false)
  const editorUrl = useMemo(
    () => (srsId ? api.wireframeHtmlUrl(srsId, page.route) : 'about:blank'),
    [srsId, page.route],
  )

  // Query server directly for current wireframe HTML existence.
  useEffect(() => {
    if (!srsId) return
    let live = true
    fetch(api.wireframeHtmlUrl(srsId, page.route))
      .then(r => { if (live && r.ok) setStamp(n => n || 1) })
      .catch(() => {})
    return () => { live = false }
  }, [srsId, page.route])

  useEffect(() => { selectionModeRef.current = selectionMode }, [selectionMode])

  const attach = useCallback(() => {
    editor.current?.detach?.()
    const iframe = frame.current
    if (!iframe) return

    // If generated markup managed to activate a link before the editor guard
    // attached, recover the canvas immediately instead of leaving a Studio 404
    // in the frame. Hash-only changes are harmless; route/query changes are not.
    if (editorUrl !== 'about:blank') {
      try {
        const expected = new URL(editorUrl, window.location.href)
        const actual = iframe.contentWindow?.location
        if (actual && (actual.pathname !== expected.pathname || actual.search !== expected.search)) {
          iframe.src = editorUrl
          return
        }
      } catch {
        iframe.src = editorUrl
        return
      }
    }

    import('@/lib/wireframe-html-editor').then(({ attachEditor }) => {
      editor.current = attachEditor(iframe, {
        onSelect: () => setSelectionKey(key => key + 1),
        onSelection: details => {
          if (!selectionModeRef.current || !details) return
          const preview = details.text ? ` — “${details.text}”` : ''
          const attachment = `Selected element <${details.tag}>${preview}`
          setAiPrompt(previous => previous.includes(attachment)
            ? previous
            : previous.trim() ? `${previous.trim()}\n\n${attachment}` : attachment)
          setAiOpen(true)
        },
        onDirty: setDirty,
      })
      if (!editor.current) setProblem('This page cannot be edited in place here.')
    })
  }, [editorUrl])

  useEffect(() => () => editor.current?.detach?.(), [])

  async function draw() {
    setDrawing(true); setProblem('')
    try {
      await api.drawWireframeHtml(srsId, page.route)
      setStamp(n => n + 1)
      setStale(false); setDirty(false)
    } catch (failure) {
      setProblem(failure?.message || 'The page could not be drawn.')
    } finally {
      setDrawing(false)
    }
  }

  async function save() {
    if (!editor.current) return
    setSaving(true); setProblem('')
    try {
      editor.current.editText(false)
      const edits = editor.current.changes?.() || []
      await api.saveWireframeHtml(srsId, page.route, editor.current.serialize())
      editor.current.saved()
      setAiUpdating(true)
      const list = edits.length ? edits.map(item => `- ${item}`).join('\n') : '- Reviewed the current page edits'
      await api.aiEditWireframeHtml(srsId, page.route,
        `The user directly edited this wireframe page. Review the saved page and faithfully apply these changes in the source. Keep the result low-fidelity and preserve all unaffected content.\n\nEdit list:\n${list}`)
      setStamp(n => n + 1)
      onSaved?.(null)
    } catch (failure) {
      setProblem(failure?.message || 'That layout could not be updated.')
    } finally {
      setAiUpdating(false)
      setSaving(false)
    }
  }

  async function updateWithAi() {
    const request = aiPrompt.trim()
    if (!request || !srsId || aiUpdating) return
    setAiUpdating(true); setProblem('')
    try {
      editor.current?.editText(false)
      // Keep the AI's source buffer in sync with any direct edits the user has
      // made in the canvas. The AI endpoint intentionally reads only this page.
      if (dirty && editor.current) {
        await api.saveWireframeHtml(srsId, page.route, editor.current.serialize())
        editor.current.saved()
      }
      await api.aiEditWireframeHtml(srsId, page.route, request)
      setStamp(n => n + 1)
      setDirty(false)
      setAiPrompt(''); setAiOpen(false)
    } catch (failure) {
      setProblem(failure?.message || 'The AI could not update this page.')
    } finally {
      setAiUpdating(false)
    }
  }

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
              {page.page_name || page.route}
            </span>
            <span className="block truncate font-mono text-[9.5px] text-muted2">
              {page.route}{page.roles?.length ? ` · ${page.roles.join(', ')}` : ''}
            </span>
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {dirty && (
            <Button variant="solid" size="sm" onClick={save} disabled={saving}
              className="h-7 rounded-lg bg-accent hover:bg-accent text-[10.5px] text-ink">
              {saving ? <><Loader2 className="mr-1 size-3 animate-spin" /> {aiUpdating ? 'Editing…' : 'Saving…'}</> : 'Save page'}
            </Button>
          )}
        </div>
      </div>


      {stale && stamp ? (
        <p className="shrink-0 border-b border-amber-400/20 bg-amber-400/10 px-4 py-2 text-[11.5px] text-amber-200">
          The specification has changed since this page was drawn — draw it again to bring it up to date.
        </p>
      ) : null}
      {problem ? (
        <p role="alert" className="shrink-0 border-b border-rose-400/20 bg-rose-500/10 px-4 py-2 text-[11.5px] text-rose-300">
          {problem}
        </p>
      ) : null}

      {stamp ? (
        <div className="flex min-h-0 flex-1">
          <div className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden bg-white">
            <WireframeInspector
              editor={editor.current}
              selectionKey={selectionKey}
              onRedraw={draw}
              redrawing={drawing || !srsId}
              onOpenAi={() => setAiOpen(true)}
              selectionMode={selectionMode}
              onSelectionMode={setSelectionMode}
              onChange={() => {
                setDirty(true)
                setSelectionKey(key => key + 1)
              }}
              onUndo={() => {
                if (!editor.current?.undo?.()) return
                setDirty(editor.current?.hasHistory?.() ?? false)
                setSelectionKey(key => key + 1)
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
                      <p className="text-[10px] text-muted">Only {page.route} changes. No plan or other page is touched.</p>
                    </div>
                  </div>
                  <button type="button" onClick={() => setAiOpen(false)} className="text-[11px] text-muted hover:text-ink">Close</button>
                </div>
                <div className="flex items-end gap-2">
                  <textarea
                    autoFocus
                    value={aiPrompt}
                    onChange={event => setAiPrompt(event.target.value)}
                    placeholder="Describe any page change or redesign…"
                    rows={2}
                    className="min-h-[48px] flex-1 resize-none rounded-lg border border-line bg-white px-3 py-2 text-[11px] text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
                  />
                  <Button variant="solid" size="sm" disabled={!aiPrompt.trim() || aiUpdating} className="h-9 rounded-lg text-[11px]">
                    {aiUpdating ? <><Loader2 className="size-3 animate-spin" /> Sending</> : <><Sparkles className="size-3" /> Send</>}
                  </Button>
                </div>
              </form>
            )}
            {(drawing || aiUpdating) && (
              <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-panel/85 backdrop-blur-md transition-all duration-300">
                <div className="absolute inset-0 opacity-15 bg-[radial-gradient(var(--accent)_1px,transparent_1px)] [background-size:20px_20px]" />
                <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-[var(--accent)] to-transparent animate-pulse shadow-[0_0_20px_var(--accent)]" />
                <div className="relative z-10 flex flex-col items-center rounded-none border border-black/15 bg-black/[0.04] p-8 shadow-2xl backdrop-blur-2xl text-center max-w-sm">
                  <div className="relative flex size-14 items-center justify-center rounded-none bg-accent border border-accent/40 shadow-[0_0_35px_rgba(191, 185, 255,0.4)]">
                    <Sparkles className="size-7 text-ink animate-spin" style={{ animationDuration: '7s' }} />
                    <div className="absolute inset-0 rounded-none border-2 border-accent animate-ping opacity-30" />
                  </div>
                  <h3 className="mt-4 text-[15px] font-bold tracking-tight text-ink">{aiUpdating ? 'AI is updating this page…' : 'Updating Wireframe…'}</h3>
                  <p className="mt-1 text-[12px] leading-relaxed text-ink">
                    {aiUpdating ? 'Reading the current page and writing the requested wireframe update for ' : 'Generating updated layout structure and blueprint components for '}<span className="font-mono text-accent font-semibold">{page.route}</span>.
                  </p>
                  <div className="mt-4 flex items-center gap-2 rounded-full border border-accent/30 bg-accent px-3 py-1 font-mono text-[10.5px] text-ink">
                    <Loader2 className="size-3 animate-spin text-ink" />
                    <span>{aiUpdating ? 'Updating this page…' : 'Drawing wireframe…'}</span>
                  </div>
                </div>
              </div>
            )}
            <iframe
              key={stamp}
              ref={frame}
              onLoad={attach}
              title={`${page.page_name || page.route} wireframe`}
              src={editorUrl}
              sandbox="allow-same-origin"
              className={cn(
                "min-h-0 min-w-0 flex-1 border-0 bg-white transition-all duration-500",
                (drawing || aiUpdating) && "filter blur-[6px] scale-[0.99] opacity-40 pointer-events-none"
              )}
            />
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 items-center justify-center bg-panel text-[12px] text-muted">
          {srsId ? `Nothing drawn for ${page.route} yet.`
                 : 'This project has no specification to draw from.'}
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
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(null)
  const [error, setError] = useState('')
  const [drawing, setDrawing] = useState(false)
  const [selectedForDel, setSelectedForDel] = useState([])
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
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

  // A chat/feature update may rewrite the SRS or a wireframe without remounting
  // this tab. Refresh only this data view; never reload the whole Studio app.
  useEffect(() => { load() }, [load, srsStamp])

  /** Poll wireframes status periodically while page drawings are being generated. */
  const waiting = generating || Boolean(data?.drawing)
  useEffect(() => {
    if (!waiting) return
    load()
    const again = setInterval(load, 2000)
    return () => clearInterval(again)
  }, [waiting, load])

  useEffect(() => { if (!generating) load() }, [generating, load])

  /** Draw every page that has no drawing yet, and redraw the rest. */
  async function drawAll() {
    if (!srsId) return
    setDrawing(true); setError('')
    try {
      await api.drawWireframeHtml(srsId)
      load()
    } catch (failure) {
      setError(failure?.message || 'The pages could not be drawn.')
    } finally {
      setDrawing(false)
    }
  }

  function openDeleteModal(routesToSelect = []) {
    setSelectedForDel(routesToSelect)
    setDeleteModalOpen(true)
  }

  function toggleDelRoute(route) {
    setSelectedForDel(prev =>
      prev.includes(route) ? prev.filter(r => r !== route) : [...prev, route]
    )
  }

  function selectAllForDel() {
    const drawnRoutes = pages.filter(p => p.has_html).map(p => p.route)
    setSelectedForDel(drawnRoutes)
  }

  function deselectAllForDel() {
    setSelectedForDel([])
  }

  /** Delete selected wireframes by clearing their HTML. */
  async function deleteSelectedWireframes() {
    if (!srsId || !selectedForDel.length) return
    setDeleting(true)
    try {
      await Promise.all(
        selectedForDel.map(route => api.saveWireframeHtml(srsId, route, ''))
      )
      load()
      setDeleteModalOpen(false)
      setSelectedForDel([])
    } catch (failure) {
      setError(failure?.message || 'The selected wireframes could not be deleted.')
    } finally {
      setDeleting(false)
    }
  }

  const pages = data?.pages || []
  if (error && !data) return <Empty>{error}</Empty>
  if (!data) return <Empty>Reading the wireframes…</Empty>
  if (!pages.length) return <Empty>{waiting
    ? 'Reading the approved plan and preparing the wireframe pages…'
    : 'No pages in the specification yet, so there is nothing to draw.'}</Empty>

  const drawn = pages.filter(p => p.has_html).length

  return (
    <div className="space-y-3">
      {error && <p role="alert" className="text-xs text-rose-400">{error}</p>}
      {/* Visual progress indicator displayed while wireframe pages are being drawn. */}
      {waiting && (
        <p className="flex items-center gap-2.5 rounded-none border border-accent/30 bg-accent
                      px-3.5 py-2.5 text-[11.5px] leading-relaxed text-ink">
          <Loader2 className="size-3.5 shrink-0 animate-spin text-accent" />
          <span>
            Drawing the pages — each one is drawn on its own, so they appear as
            they finish. {drawn} of {pages.length} so far. You can carry on; this
            keeps going without you.
          </span>
        </p>
      )}
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <p className="text-[11.5px] text-muted">
          {pages.length} HTML page{pages.length === 1 ? '' : 's'}, black and white, with sample data.
          Open one to move things, retype them, or ask for a change.
          {drawn === pages.length
            ? ' All drawn.'
            : ` ${drawn} of ${pages.length} drawn so far.`}
        </p>
        <div className="flex items-center gap-2">
          {onApprove && (designApproved ? (
            <Button variant="solid" disabled={waiting || drawing || deleting || approving || drawn === 0}
                    onClick={onRetryPrototype} title="Generate the prototype again using the approved design">
              {approving ? <><Loader2 className="mr-1.5 size-3.5 animate-spin" />Planning prototype…</>
                         : 'Regenerate prototype'}
            </Button>
          ) : (
            <Button variant="solid" disabled={waiting || drawing || deleting || approving || drawn === 0}
                    onClick={onApprove}
                    title={drawn === 0
                      ? 'Draw at least one wireframe before approving'
                      : drawn < pages.length
                        ? `Approve ${drawn} ready wireframe${drawn === 1 ? '' : 's'}; missing pages will use the SRS`
                        : 'Approve wireframes and choose the design'}>
              {drawn < pages.length
                ? `Approve ${drawn} ready wireframe${drawn === 1 ? '' : 's'} → Design`
                : 'Approve wireframes → Design'}
            </Button>
          ))}
          {pages.some(p => p.has_html) && (
            <Button
              variant="outline"
              disabled={drawing || waiting || deleting || !srsId}
              onClick={() => openDeleteModal(pages.filter(p => p.has_html).map(p => p.route))}
              className="border-rose-500/30 text-rose-300 hover:bg-rose-500/10 hover:border-rose-500/50"
            >
              <Trash2 className="mr-1.5 size-3.5 text-rose-400" />
              Delete wireframes…
            </Button>
          )}
          <Button variant="outline" disabled={drawing || waiting || !srsId} onClick={drawAll}>
            {drawing || waiting
              ? <><Loader2 className="mr-1 size-3 animate-spin" /> Drawing…</>
              : drawn ? 'Draw them again' : 'Draw every page'}
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
                <Thumbnail srsId={srsId} page={page} waiting={waiting} />
              </span>
              <span className="block space-y-1 p-3">
                <span className="truncate block text-[12px] font-medium text-ink">{page.page_name}</span>
                <span className="block truncate font-mono text-[10px] text-muted2">{page.route}</span>
                <span className="block truncate text-[10px] text-muted2">
                  {page.roles?.length ? page.roles.join(', ') : 'public'}
                  {page.html_stale ? ' · out of date' : ''}
                </span>
                {page.error && <span className="block text-[10px] text-rose-400" title={page.error}>Drawing failed · open to retry</span>}
              </span>
            </button>
            {/* Delete button — visible on hover, opens confirmation dialog with page ticked */}
            {page.has_html && (
              <button
                type="button"
                title="Delete wireframe"
                onClick={e => { e.stopPropagation(); openDeleteModal([page.route]) }}
                className="absolute right-2 top-2 z-10 flex items-center justify-center rounded-none
                           bg-black/60 p-1.5 text-muted opacity-0 transition
                           hover:bg-rose-600 hover:text-ink
                           group-hover:opacity-100 cursor-pointer"
              >
                <Trash2 className="size-3.5" />
              </button>
            )}
          </div>
        ))}
      </div>
      {open && (
        <PageEditor owner={owner} srsId={srsId} page={open}
          onClose={() => setOpen(null)}
          onSaved={() => { load(); setOpen(null) }} />
      )}
      {/* Delete confirmation modal with checkboxes (tick marks) */}
      {deleteModalOpen && (
        <Modal onClose={() => !deleting && setDeleteModalOpen(false)}>
          <div className="space-y-4 max-w-lg w-full">
            <div className="flex items-start gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-rose-500/15">
                <Trash2 className="size-4 text-rose-400" />
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="text-[15px] font-bold text-ink">Delete wireframe pages?</h3>
                <p className="mt-1 text-[12px] leading-relaxed text-muted">
                  Select which wireframe HTML layouts to delete. Ticked pages will be cleared and reset to ungenerated status. This action cannot be undone.
                </p>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="flex items-center justify-between border-y border-line py-2 text-[11.5px]">
              <span className="font-medium text-muted">
                {selectedForDel.length} of {pages.filter(p => p.has_html).length} selected
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={selectAllForDel}
                  className="text-accent hover:underline cursor-pointer"
                >
                  Select all
                </button>
                <span className="text-muted2">·</span>
                <button
                  type="button"
                  onClick={deselectAllForDel}
                  className="text-muted hover:text-ink cursor-pointer"
                >
                  Clear selection
                </button>
              </div>
            </div>

            {/* Scrollable list with checkboxes */}
            <div className="max-h-[300px] overflow-y-auto space-y-1.5 pr-1">
              {pages.filter(p => p.has_html).map(p => {
                const checked = selectedForDel.includes(p.route)
                return (
                  <label
                    key={p.route}
                    className={cn(
                      "flex items-center gap-3 rounded-none border p-2.5 transition cursor-pointer select-none",
                      checked
                        ? "border-rose-500/50 bg-rose-500/10 text-ink"
                        : "border-line bg-panel2/40 text-muted hover:bg-panel2 hover:text-ink"
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleDelRoute(p.route)}
                      className="size-4 rounded accent-rose-600 cursor-pointer"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="font-semibold text-[12.5px] truncate text-ink">
                          {p.page_name || p.route}
                        </span>
                        <code className="text-[10px] font-mono text-muted2 shrink-0">
                          {p.route}
                        </code>
                      </div>
                      <span className="text-[10.5px] text-muted2 block truncate">
                        {p.roles?.length ? p.roles.join(', ') : 'public'}
                      </span>
                    </div>
                  </label>
                )
              })}
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-line">
              <Button
                variant="outline"
                onClick={() => setDeleteModalOpen(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button
                variant="solid"
                onClick={deleteSelectedWireframes}
                disabled={deleting || selectedForDel.length === 0}
                className="bg-rose-600 hover:bg-rose-500 text-ink shadow-sm"
              >
                {deleting ? (
                  <><Loader2 className="mr-1.5 size-3 animate-spin" />Deleting…</>
                ) : (
                  `Delete ${selectedForDel.length} wireframe${selectedForDel.length === 1 ? '' : 's'}`
                )}
              </Button>
            </div>
          </div>
        </Modal>
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
