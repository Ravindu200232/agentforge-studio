'use client'

import { useEffect, useState } from 'react'
import { ArrowLeft, Check, FileDown, FolderUp, ListTree, Loader2, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { loadSrsView, srsViewFromVersion } from '@/lib/srs-view'
import { Badge, Button, Empty, SubTab, SubTabs, Tag } from '../ui'
import { VIEWS, badgeFor } from './views'
import { WireframeEditor } from './Wireframes'
import { SrsRevisions } from './SrsRevisions'
import { cn } from '@/lib/utils'

export default function SrsReview({ projectId, onApproved, onKept, onBack, onNewProject }) {
  const addLog = useStore(s => s.addLog)
  const [handoffs, setHandoffs] = useState({})
  const [handoffOpen, setHandoffOpen] = useState('')
  const [srs, setSrs] = useState(null)
  const [state, setState] = useState('loading')
  const [error, setError] = useState('')
  const [sub, setSub] = useState('overview')
  const [specOpen, setSpecOpen] = useState(false)
  const [asking, setAsking] = useState(false)
  const [editingWireframe, setEditingWireframe] = useState(null)
  const [downloadingPdf, setDownloadingPdf] = useState(false)

  const [busy, setBusy] = useState('')
  const [viewing, setViewing] = useState(null)
  // What the editor said it changed, kept for the summary panel on the right.
  // The revision itself lives in `SrsRevisions`, which owns the composer.
  const [lastChange, setLastChange] = useState('')

  /** Throw this specification away and leave. */
  async function discard() {
    setBusy('discarding')
    try {
      await api.discardSrs(projectId)
      addLog('WARN', 'the specification was discarded')
      useStore.getState().resetSrs()
      useStore.getState().reset(null)
      if (onNewProject) onNewProject()
      else onBack?.()
    } catch (e) {
      addLog('WARN', `could not discard — ${e.message}`)
      setBusy('')
      setAsking(false)
    }
  }

  async function load() {
    setState('loading')
    try {
      await api.resumeSrs(`/projects/${projectId}/customize`)
      const [spec, handoff] = await Promise.all([loadSrsView(projectId), api.srs(`/projects/${projectId}/agent-handoff`)])
      setSrs(spec)
      setHandoffs(handoff.files || {})
      setState('ready')
    } catch (e) {
      // Clear stale project ID and navigate back when the specification is not found on this machine.
      if (e.status === 404 || /not found/i.test(e.message || '')) {
        addLog('WARN', 'that specification is no longer on this machine')
        useStore.getState().resetSrs()
        onBack?.()
        return
      }
      setError(e.message)
      setState('error')
    }
  }

  useEffect(() => { load()  }, [projectId])

  /** Approve the specification and proceed directly to build. */
  async function approve() {
    setBusy('approving')
    setError('')
    try {
      await api.srs(`/projects/${projectId}/approve`, {})
      addLog('INFO', 'SRS and agent handoffs approved - customize the design next')
      setBusy('')
      onApproved?.('Use the approved SRS handoff files.', projectId)
    } catch (e) {
      setError(e.message)
      setBusy('')
    }
  }

  async function downloadPdf() {
    setDownloadingPdf(true)
    setError('')
    try {
      const name = srs?.document?.project_name || srs?.document?.document_title || 'SRS'
      await api.downloadSrsPdf(projectId, `${name.replace(/[\\/:*?"<>|]/g, '-')}.pdf`)
      addLog('INFO', 'SRS PDF downloaded')
    } catch (e) {
      setError(`The SRS PDF could not be downloaded — ${e.message}`)
      addLog('WARN', `The SRS PDF could not be downloaded — ${e.message}`)
    } finally {
      setDownloadingPdf(false)
    }
  }

  if (state === 'loading' && !srs) {
    return <Centered><Loader2 className="mx-auto mb-3 size-5 animate-spin text-accent" />
      Reading the specification…</Centered>
  }
  if (state === 'error') {
    return <Centered bad>Could not read the specification — {error}</Centered>
  }

  const shown = viewing || srs
  const View = (VIEWS.find(v => v.id === sub) || VIEWS[0]).C

  const counts = viewing ? countOf(viewing.document) : (srs?.summary || {})

  const approved = srs?.status === 'approved'

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[radial-gradient(circle_at_top_right,rgba(191, 185, 255,.1),transparent_35%)] text-ink">

      <div className="flex shrink-0 items-center gap-3 border-b border-line px-6 py-3.5 backdrop-blur-md">
        <button onClick={onBack}
                className="flex items-center gap-1.5 rounded-none border border-line bg-panel2/60 px-2.5 py-1 text-[11.5px] font-medium text-muted hover:bg-raised hover:text-ink transition cursor-pointer">
          <ArrowLeft className="size-3" /> Plan
        </button>
        <div className="min-w-0">
          <p className="truncate font-display text-[14px] font-bold text-ink">
            {srs?.document?.project_name || srs?.document?.document_title || 'Specification'}
          </p>
        </div>
        {srs?.version && <Tag tone="accent">v{srs.version}</Tag>}
        {approved && <Tag tone="solid">approved</Tag>}
        <span className="flex-1" />
        {viewing ? (
          <span title="The PDF is only produced for the current version"
                className="flex h-[32px] cursor-not-allowed items-center gap-1.5
                           rounded-none border border-line px-3 font-display text-[11.5px]
                           font-semibold text-muted2 opacity-50">
            <FileDown className="size-3.5" /> PDF
          </span>
        ) : (
          <button type="button" onClick={downloadPdf} disabled={downloadingPdf}
                  className="flex h-[32px] items-center gap-1.5 rounded-none border border-line bg-panel2/60 px-3.5
                             text-[11.5px] font-semibold text-ink shadow-sm transition hover:bg-raised disabled:opacity-50">
            {downloadingPdf ? <Loader2 className="size-3.5 animate-spin text-accent" />
                            : <FileDown className="size-3.5 text-accent" />} PDF
          </button>
        )}

        <Button variant="solid" className="h-[32px] rounded-none bg-accent px-4 text-[12px] font-semibold text-ink shadow-sm hover:bg-press cursor-pointer"
                disabled={Boolean(busy) || Boolean(viewing)}
                title={viewing ? 'Go back to the latest revision to approve it.'
                               : 'Approve specification and customize the design.'}
                onClick={approve}>
          {busy === 'approving'
            ? <><Loader2 className="size-3.5 animate-spin" /> Approving…</>
            : <><Check className="size-3.5" /> Approve</>}
        </Button>

        <button
          type="button"
          onClick={async () => {
            setBusy('saving')
            try {
              const res = await api.keepSrs(projectId)
              addLog('SUCCESS', `Saved specification as project "${res.project || projectId}"`)
              useStore.getState().bumpProjects()
              onKept?.(res.project)
            } catch (err) {
              setError(err.message)
              setBusy('')
            }
          }}
          disabled={Boolean(busy)}
          title="Save this SRS specification as a project and view in Projects list"
          className="flex h-[32px] items-center gap-1.5 rounded-none border border-line bg-panel2/60 px-3.5 text-[11.5px] font-semibold text-ink shadow-sm transition hover:bg-raised disabled:opacity-50 cursor-pointer"
        >
          {busy === 'saving' ? <Loader2 className="size-3.5 animate-spin text-accent" /> : <FolderUp className="size-3.5 text-accent" />} Save to Projects
        </button>

        <button
          type="button"
          onClick={async () => {
            try {
              await api.keepSrs(projectId)
              useStore.getState().bumpProjects()
            } catch { }
            useStore.getState().resetSrs()
            useStore.getState().reset(null)
            if (onNewProject) onNewProject()
            else onBack?.()
          }}
          title="Save this specification and start a new project"
          className="flex h-[32px] items-center gap-1.5 rounded-none border border-line bg-panel2/60 px-3 text-[11.5px] font-semibold text-ink shadow-sm transition hover:bg-raised cursor-pointer"
        >
          <Plus className="size-3.5 text-accent" /> New Project
        </button>

        {asking ? (
          <span className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted">Discard it?</span>
            <Button variant="solid" className="h-[32px] rounded-none bg-bad px-3.5 hover:brightness-110"
                    disabled={busy === 'discarding'} onClick={discard}>
              {busy === 'discarding'
                ? <><Loader2 className="size-3.5 animate-spin" /> Discarding…</>
                : 'Yes'}
            </Button>
            <Button variant="outline" className="h-[32px] rounded-none border-line bg-panel2/60 px-3 text-ink hover:bg-raised"
                    disabled={busy === 'discarding'} onClick={() => setAsking(false)}>
              Keep it
            </Button>
          </span>
        ) : (
          <button onClick={() => setAsking(true)}
                  title="Throw this specification away and start fresh"
                  className="grid size-[32px] place-items-center rounded-none border border-line text-muted2 transition hover:bg-bad/10 hover:border-bad/30 hover:text-bad cursor-pointer">
            <Trash2 className="size-3.5" />
          </button>
        )}

        <button onClick={() => setSpecOpen(v => !v)}
                title="The specification at a glance"
                className={cn('flex h-[32px] items-center gap-1.5 rounded-none px-3.5 text-[11.5px] font-semibold transition cursor-pointer',
                  specOpen ? 'bg-accent text-ink shadow-sm'
                           : 'border border-line bg-panel2/60 text-ink hover:bg-raised')}>
          <ListTree className="size-3.5" /> Specification
        </button>
      </div>

      <div className="border-b border-line px-6 py-3">
        <p className="mb-2 text-xs text-muted">Generated by the SRS agent - review the handoffs before approval</p>
        <div className="flex flex-wrap gap-2">{Object.keys(handoffs).map(name => <button key={name} onClick={() => setHandoffOpen(handoffOpen === name ? '' : name)} className="rounded-none border border-line bg-panel2/60 px-3 py-1 text-xs text-ink hover:bg-raised cursor-pointer">{name}</button>)}</div>
        {handoffOpen && <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-none bg-panel2/80 p-4 text-xs text-ink border border-line">{handoffs[handoffOpen]}</pre>}
      </div>
      <div className="flex min-h-0 flex-1 gap-4 p-5">
        {sub === 'wireframe' && editingWireframe ? (
          <WireframeEditor
            owner={projectId}
            page={editingWireframe}
            onClose={() => setEditingWireframe(null)}
            onSaved={() => {
              setEditingWireframe(null)
              load()
            }}
          />
        ) : (
          <>
            {/* The same panel the workspace shows. Nothing here is specific to
                reviewing: it is the specification's history either way. */}
            <SrsRevisions srsId={projectId}
              className="w-[270px] shrink-0 rounded-none border border-line bg-panel shadow-xl backdrop-blur-xl"
              current={viewing?.version || srs?.version}
              onPickVersion={v => setViewing(v ? srsViewFromVersion(v, projectId) : null)}
              onRevised={answer => {
                const said = answer?.diff_summary || []
                setLastChange(said.length ? said.join('\n') : 'The specification was updated.')
                return load()
              }} />

            <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-none border border-black/10 bg-panel/90 shadow-2xl backdrop-blur-xl">
              <SubTabs>
                {VIEWS.map(v => {
                  const badge = badgeFor(v.id, shown)
                  return (
                    <SubTab key={v.id} on={sub === v.id} onClick={() => { setSub(v.id); setEditingWireframe(null); }}>
                      {v.label}
                      {badge && <Badge tone={badge.bad ? 'bad' : 'mute'}>{badge.n}</Badge>}
                    </SubTab>
                  )
                })}
              </SubTabs>

              {viewing && (
                <div className="mx-4 mt-3 flex shrink-0 items-center gap-2 rounded-none bg-accent px-4 py-2">
                  <span className="text-[11px] text-deep">
                    Showing v{viewing.version} — an earlier revision, read only.
                  </span>
                  <span className="flex-1" />
                  <Button variant="outline" onClick={() => setViewing(null)}>
                    <RotateCcw className="size-3" /> Back to the latest
                  </Button>
                </div>
              )}

              <div className="min-h-0 flex-1 overflow-y-auto p-5">
                {shown?.have && Object.values(shown.have).some(Boolean)
                  ? <View srs={shown} onSelectView={setSub} onEditPage={setEditingWireframe} />
                  : <Empty>Nothing was written for this version.</Empty>}
              </div>
            </div>
          </>
        )}

        <aside className={cn('flex shrink-0 flex-col overflow-hidden rounded-none',
          'bg-black/62 shadow-[0_16px_42px_rgba(15,23,42,.06)] ring-1 ring-line/70',
          'backdrop-blur-xl transition-[width,opacity] duration-300 dark:bg-black/[.035]',
          specOpen && !(sub === 'wireframe' && editingWireframe) ? 'w-[280px] opacity-100' : 'pointer-events-none w-0 opacity-0 ring-0')}>

          <div className="min-h-0 w-[280px] flex-1 overflow-y-auto p-3">
            <p className="label-xs mb-3 text-ink">
              The specification
            </p>
            <div>
              {[['requirements', counts.functional],
                ['qualities', counts.non_functional],
                ['roles', counts.roles],
                ['tables', counts.tables],
                ['modules', counts.modules],
                ['workflows', counts.use_cases],
                ['pages', pageCount(shown?.document)],
                ['diagrams', (shown?.diagrams || []).length]]
                .filter(([, n]) => n != null)
                .map(([label, n]) => (
                  <div key={label} className="mb-1 flex items-baseline justify-between rounded-none bg-black/[.025] px-2.5 py-2 dark:bg-black/[.035]">
                    <span className="text-[11.5px] capitalize text-muted">{label}</span>
                    <span className="font-mono text-[12px] text-ink">{n}</span>
                  </div>
                ))}
              {counts.open_ambiguities > 0 && (
                <div className="mt-1.5 flex items-baseline justify-between
                                border-l-[3px] border-accent bg-tint px-2 py-1">
                  <span className="text-[11.5px] text-deep">still unclear</span>
                  <span className="font-mono text-[12px] text-deep">
                    {counts.open_ambiguities}
                  </span>
                </div>
              )}
            </div>

            {lastChange && (
              <div className="mt-5">
                <p className="label-xs mb-2 text-ink">
                  What changed, as the editor described it
                </p>
                <p className="whitespace-pre-wrap text-[11.5px] leading-relaxed text-muted">
                  {lastChange}
                </p>
              </div>
            )}

            <p className="mt-4 text-[10.5px] leading-relaxed text-muted2">
              The “Approved Plan” pane shows the plan you signed off. It stays
              as it was on purpose — it is the record of what was agreed. The
              specification here is the current one.
            </p>
          </div>

          {error && (
            <div className="w-[280px] p-3 pt-0">
              <p className="border-l-[3px] border-accent bg-tint px-2 py-1.5
                            text-[11px] text-deep">
                {error}
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

function pageCount(doc) {
  const n = (v) => (Array.isArray(v) ? v.length : 0)
  return n(doc?.public_pages) + n(doc?.protected_pages)
}

function countOf(doc) {
  const n = (v) => (Array.isArray(v) ? v.length : 0)
  return {
    functional: n(doc?.functional_requirements),
    non_functional: n(doc?.non_functional_requirements),
    roles: n(doc?.roles),
    tables: n(doc?.database_design?.tables),
    modules: n(doc?.main_modules),
    use_cases: n(doc?.business_workflows),
    open_ambiguities: (doc?.ambiguities || []).filter(a => a?.needs_clarification).length,
  }
}

function Centered({ children, bad }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center p-8">
      <p className={cn('text-center text-[12.5px]', bad ? 'text-bad' : 'text-muted')}>
        {children}
      </p>
    </div>
  )
}
