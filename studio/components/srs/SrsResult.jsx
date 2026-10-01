'use client'

import { useEffect, useState } from 'react'
import { BookOpen, ClipboardCheck, Compass, Database, FileCode2, FileDown, FileText, LayoutList, Loader2, MessageSquare, RefreshCw, ShieldAlert, Users, Workflow } from 'lucide-react'
import { api } from '@/lib/api'
import { diagramRows } from '@/lib/srs-view'
import { useStore } from '@/lib/store'
import { Button, Empty, Tip } from '../ui'
import { cn } from '@/lib/utils'
import { VIEWS } from './views'
import SrsActivity from './SrsActivity'

const VIEW_ICONS = {
  overview: FileText,
  journey: Workflow,
  document: BookOpen,
  requirements: ClipboardCheck,
  diagrams: Compass,
  data: Database,
  roles: Users,
  plan: LayoutList,
  handoff: FileCode2,
  interview: MessageSquare,
  risks: ShieldAlert,
}

export default function SrsResult({ onApprove }) {
  const project = useStore(s => s.project)
  const busy = useStore(s => s.busy)
  const srsStamp = useStore(s => s.srsStamp[s.project])
  const sync = useStore(s => s.projectSync[s.project])
  const updatingSrs = sync?.status === 'running' && sync?.source === 'srs' && sync?.srs_status !== 'completed'
  const [srs, setSrs] = useState(null)
  const [sub, setSub] = useState('overview')
  const [state, setState] = useState('idle')
  const [error, setError] = useState('')
  const [downloadingPdf, setDownloadingPdf] = useState(false)
  const [redrawingDiagrams, setRedrawingDiagrams] = useState(false)

  async function downloadPdf() {
    setDownloadingPdf(true)
    try {
      await api.downloadProjectSrsPdf(project)
      useStore.getState().addLog('INFO', 'SRS PDF downloaded')
    } catch (e) {
      useStore.getState().addLog('WARN', `The SRS PDF could not be downloaded — ${e.message}`)
    } finally {
      setDownloadingPdf(false)
    }
  }

  async function redrawDiagrams() {
    if (!project) return
    setRedrawingDiagrams(true)
    setError('')
    try {
      const result = await api.srs(`/projects/${project}/diagrams/redraw`, {})
      useStore.getState().addLog('SUCCESS', `Diagram previews refreshed: ${result.rendered || 0}/${result.total || 0} SVG`)
      await load()
    } catch (e) {
      setError(e.message || 'Could not regenerate diagrams')
      useStore.getState().addLog('WARN', `Could not regenerate diagrams — ${e.message}`)
    } finally {
      setRedrawingDiagrams(false)
    }
  }

  async function load() {
    if (!project) return
    setState('loading')
    let last
    for (let i = 0; i < 4; i++) {
      try {
        const loaded = await api.srsResults(project)
        // Same normaliser the review screen uses, so both render identical rows.
        setSrs({ ...loaded, diagrams: diagramRows(loaded?.diagrams) })
        setState('ready')
        return
      } catch (e) {
        last = e
        await new Promise(r => setTimeout(r, 700))
      }
    }
    setError(last?.message || 'unknown error')
    setState('error')
  }

  useEffect(() => {
    // Keep the last readable document on screen (blurred) while the SRS branch
    // is actually rewriting it. As soon as that branch reports completed,
    // reload even if Prototype/Builder are still busy in parallel.
    if (updatingSrs) return
    if (!busy || sync?.source === 'srs' || !srs) load()
  }, [project, busy, srsStamp, sync?.status, sync?.source, sync?.srs_status, Boolean(srs)])

  if (!project) return <Empty>Open a project to see the SRS it was built from.</Empty>

  const have = srs?.have || {}
  const anything = Object.values(have).some(Boolean)
  const pages = srs?.wireframes || []
  const readyPages = pages.filter(page => page.has_html).length
  const drawingWireframes = sync?.source === 'wireframe' && sync?.status === 'running'
  const View = (VIEWS.find(v => v.id === sub) || VIEWS[0]).C

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[radial-gradient(circle_at_top_right,rgba(191, 185, 255,.07),transparent_30%)]">
      <div className={cn('transition-[filter,opacity] duration-200',
        updatingSrs && 'pointer-events-none select-none blur-[3px] opacity-55')}>
      <div className="flex shrink-0 items-center justify-end border-b border-line/70 bg-panel/80 px-3 py-2">
        <span className="flex shrink-0 items-center gap-2 px-3">
          {anything && !updatingSrs && (srs?.status !== 'approved' || readyPages < pages.length) && (
            <Button variant="solid" disabled={drawingWireframes || busy} onClick={onApprove}
                    title="Approve the SRS and draw HTML wireframes from its plan and handoff files">
              {drawingWireframes ? <><Loader2 className="size-3 animate-spin" /> Drawing wireframes…</>
                : srs?.status === 'approved' ? 'Draw wireframes again' : 'Approve SRS · Draw wireframes'}
            </Button>
          )}
          {srs?.status === 'approved' && pages.length > 0 && readyPages === pages.length && (
            <span className="text-[11px] font-semibold text-ok">Approved · {readyPages} wireframes ready</span>
          )}
          {have.pdf && (
            <button type="button" onClick={downloadPdf} disabled={downloadingPdf}
                    className="inline-flex h-[30px] items-center gap-1.5 border border-line2 px-3 font-display
                               text-[12px] font-extrabold text-ink transition-colors hover:bg-ink/[.07] disabled:opacity-50">
              {downloadingPdf ? <RefreshCw className="size-3 animate-spin" /> : <FileDown className="size-3" />} PDF
            </button>
          )}
          {have.diagrams && (
            <Button variant="outline" disabled={busy || redrawingDiagrams} onClick={redrawDiagrams}
                    title="Quickly redraw the saved diagrams with the current renderer and standards theme">
              {redrawingDiagrams
                ? <><Loader2 className="size-3 animate-spin" /> Refreshing diagrams…</>
                : <><Compass className="size-3" /> Refresh diagrams</>}
            </Button>
          )}
          <Button variant="outline" onClick={load}>
            <RefreshCw className="size-3" /> Refresh
          </Button>
        </span>
      </div>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside aria-label="SRS sections" className="flex w-[52px] shrink-0 flex-col items-center gap-1 border-r border-line bg-panel px-2 py-3">
          {VIEWS.filter(v => v.id !== 'wireframe').map(v => {
            const Icon = VIEW_ICONS[v.id] || FileText
            return (
              <Tip key={v.id} text={v.label} side="right">
                <button type="button" onClick={() => setSub(v.id)} aria-label={v.label}
                        aria-pressed={sub === v.id}
                        className={cn('relative grid size-9 place-items-center rounded-xl text-muted2 transition-colors hover:bg-raised hover:text-ink',
                          sub === v.id && 'text-deep')}>
                  <Icon className="size-4" />
                </button>
              </Tip>
            )
          })}
        </aside>

        <div className="relative min-w-0 flex-1 overflow-hidden">
        <div className={cn('h-full overflow-y-auto p-5 transition-[filter,opacity] duration-200',
          updatingSrs && 'pointer-events-none select-none blur-[3px] opacity-55')}>
          {state === 'loading' && !anything && <Empty>Reading the SRS…</Empty>}
          {state === 'error' && <Empty bad>Could not read it — {error}</Empty>}
          {state !== 'error' && !anything && state !== 'loading' && (
            <Empty>
              This project has no SRS. It was built straight from a prompt —
              start one with “Plan it first” on the home screen.
            </Empty>
          )}
          {anything && <View srs={srs} onSelectView={setSub} />}
        </div>
        {updatingSrs && (
          <div className="absolute inset-0 z-20 grid place-items-center overflow-y-auto bg-panel/30 px-5">
            <SrsActivity phase="generating" message="Every file is written in the chat stream as it happens." />
          </div>
        )}
      </div>
      </div>
    </div>
  )
}
