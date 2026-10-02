'use client'

import { useEffect, useRef, useState } from 'react'
import { Activity, Accessibility as AccessibilityIcon, Bug, Code2, Download, FileCheck2, FileSearch, Gauge, History, Loader2, Network, RefreshCw, Route, ShieldCheck, Sparkles, Wrench } from 'lucide-react'
import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { Button, Empty, Tip } from '../ui'
import { cn } from '@/lib/utils'
import Overview from './Overview'
import Evidence from './Evidence'
import UnitTests from './UnitTests'
import Timeline from './Timeline'
import EndToEnd from './EndToEnd'
import Routes from './Routes'
import BugReports from './BugReports'
import Security from './Security'
import Performance from './Performance'
import Accessibility from './Accessibility'
import AutoRepair from './AutoRepair'
import Coder from './Coder'
import Screenshots from './Screenshots'
import E2ELiveLanes from './E2ELiveLanes'
import Verification from './Verification'
import { refreshQaReport } from '@/lib/qa-results'


const VIEWS = [
  { id: 'verification', label: 'Scaffold QA', Icon: FileCheck2, C: Verification },
  { id: 'overview', label: 'Overview', Icon: Activity, C: Overview },
  { id: 'evidence', label: 'Evidence', Icon: FileSearch, C: Evidence },
  { id: 'unit', label: 'Unit Testing', Icon: Code2, C: UnitTests },
  { id: 'timeline', label: 'Test Timeline', Icon: History, C: Timeline },
  { id: 'e2e', label: 'Integration (E2E)', Icon: Network, C: EndToEnd },
  { id: 'routes', label: 'API Contracts', Icon: Route, C: Routes },
  { id: 'bugs', label: 'Bug Reports', Icon: Bug, C: BugReports },
  { id: 'security', label: 'Security', Icon: ShieldCheck, C: Security },
  { id: 'perf', label: 'Performance', Icon: Gauge, C: Performance },
  { id: 'accessibility', label: 'Accessibility', Icon: AccessibilityIcon, C: Accessibility },
  { id: 'repair', label: 'Auto Repair', Icon: Wrench, C: AutoRepair },
  { id: 'coder', label: 'Coder', Icon: Code2, C: Coder },
  { id: 'screenshots', label: 'UI Quality', Icon: Sparkles, C: Screenshots },
]

export default function TestingResult() {
  const project = useStore(s => s.project)
  const live = useStore(s => s.tests)
  const e2eLive = useStore(s => s.e2eParallel)
  const qa = useStore(s => s.qaReport)
  const addLog = useStore(s => s.addLog)
  // While this project's build runs, what is here is half a run. It is shown
  // blurred, the way the preview is, and read afresh when the build ends.
  const busy = useStore(s => s.busy)
  const busyProject = useStore(s => s.busyProject)
  const building = busy && (!busyProject || busyProject === project)
  const [sub, setSub] = useState('verification')
  const [state, setState] = useState('idle')
  const [error, setError] = useState('')
  const [pdf, setPdf] = useState(false)

  async function downloadPdf() {
    setPdf(true)
    try {
      await api.downloadQaPdf(project)
      addLog('INFO', '📄 Test report downloaded')
    } catch (e) {
      addLog('WARN', `⚠ The test report could not be built — ${e.message}`)
    }
    setPdf(false)
  }

  async function load() {
    if (!project) return
    setState('loading')
    let last
    for (let i = 0; i < 4; i++) {
      try {
        await refreshQaReport(project)
        if (useStore.getState().project !== project) return
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

  useEffect(() => { load()  }, [project])
  useEffect(() => {
    if (!live.running || !project) return
    const timer = setInterval(() => { refreshQaReport(project).catch(() => {}) }, 2500)
    return () => clearInterval(timer)
  }, [live.running, project])
  useEffect(() => {
    if (!live.running && project) load()

  }, [live.running])
  const wasBuilding = useRef(building)
  useEffect(() => {
    if (wasBuilding.current && !building) load()
    wasBuilding.current = building
  }, [building])

  const View = (VIEWS.find(v => v.id === sub) || VIEWS[0]).C

  if (!project) return <Empty>Open a project to see its test results.</Empty>


  return (
    <div className="testing-workspace relative flex min-h-0 flex-1 flex-col text-ink" aria-busy={building || undefined}>
      <div className={cn('flex shrink-0 items-center gap-1.5 border-b border-line bg-panel px-4 py-2.5 backdrop-blur-md',
                         building && 'pointer-events-none select-none blur-sm')}>
        <span className="flex-1 min-w-4" />
        <Button variant="outline" size="sm" className="shrink-0 rounded-none border-line bg-panel2/60 text-ink hover:bg-raised"
                disabled={!project || state !== 'ready' || pdf}
                onClick={downloadPdf}
                title="Download the saved testing report as a PDF">
          {pdf ? <Loader2 className="size-3 animate-spin text-accent" />
               : <Download className="size-3 text-accent" />} PDF
        </Button>
        {live.running
          ? <span className="flex shrink-0 items-center gap-1.5 rounded-full border border-ok/30 bg-transparent px-2.5 py-1 font-mono text-[10.5px] font-semibold text-ok">
              <span className="size-1.5 animate-pulse rounded-full bg-ok" /> running
            </span>
          : <Button variant="outline" size="sm" className="shrink-0 rounded-none border-line bg-panel2/60 text-ink hover:bg-raised" onClick={load}>
              <RefreshCw className="size-3" /> Refresh
            </Button>}
      </div>

      <div className={cn('flex min-h-0 flex-1 overflow-hidden',
                         building && 'pointer-events-none select-none blur-sm')}>
        <aside aria-label="Testing sections" className="flex w-[52px] shrink-0 flex-col items-center gap-1 overflow-y-auto border-r border-line bg-panel px-2 py-3 no-scrollbar">
          {VIEWS.map(({ id, label, Icon }) => (
              <Tip key={id} text={label} side="right">
                <button type="button" onClick={() => setSub(id)} aria-label={label} aria-pressed={sub === id}
                        className={cn('relative grid size-9 shrink-0 place-items-center rounded-xl text-muted2 transition-colors hover:bg-raised hover:text-ink',
                          sub === id && 'text-deep')}>
                  <Icon className="size-4" />
                </button>
              </Tip>
          ))}
        </aside>
      <div className="min-w-0 flex-1 overflow-y-auto p-5">
        {state === 'loading' && !qa && <Empty>Reading the results…</Empty>}
        {state === 'error' && <Empty bad>Could not read them — {error}</Empty>}
        {live.running && <p className="mb-3 text-[11px] text-accent">Testing is running. Completed results update here as each check finishes.</p>}
        {sub === 'e2e' && live.running && e2eLive?.active && <div className="mb-4"><E2ELiveLanes /></div>}
        {qa?.project === project && <View qa={qa} live={live} />}
      </div>
      </div>

      {building && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 p-8 text-center" role="status">
          <p className="font-semibold text-ink">Build in progress</p>
          <p className="max-w-lg text-sm text-muted">The test results will show when the build is ready.</p>
        </div>
      )}
    </div>
  )
}


export const Summary = ({ children }) => (
  <div className="mb-5 flex flex-wrap items-center gap-6 rounded-none border border-black/10 bg-panel/80 px-5 py-3.5 shadow-xl backdrop-blur-xl">{children}</div>
)

export function Stat({ n, label, tone }) {
  return (
    <span className="inline-flex items-baseline text-[12px] text-muted">
      <b className={cn('mr-2 font-display text-[22px] font-extrabold tracking-tight',
                       tone || 'text-ink')}>{n ?? '—'}</b>
      {label}
    </span>
  )
}
