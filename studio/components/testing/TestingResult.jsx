'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Download, Loader2, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { Badge, Button, Empty } from '../ui'
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
import { e2eStageSummary } from '@/lib/e2e-rate'
import { unitTestStatus } from '@/lib/test-counts'
import { refreshQaReport } from '@/lib/qa-results'


const VIEWS = [
  { id: 'verification', label: 'Scaffold QA', C: Verification },
  { id: 'overview', label: 'Overview', C: Overview },
  { id: 'evidence', label: 'Evidence', C: Evidence },
  { id: 'unit', label: 'Unit Testing', C: UnitTests },
  { id: 'timeline', label: 'Test Timeline', C: Timeline },
  { id: 'e2e', label: 'Integration (E2E)', C: EndToEnd },
  { id: 'routes', label: 'API Contracts', C: Routes },
  { id: 'bugs', label: 'Bug Reports', C: BugReports },
  { id: 'security', label: 'Security', C: Security },
  { id: 'perf', label: 'Performance', C: Performance },
  { id: 'accessibility', label: 'Accessibility', C: Accessibility },
  { id: 'repair', label: 'Auto Repair', C: AutoRepair },
  { id: 'coder', label: 'Coder', C: Coder },
  { id: 'screenshots', label: 'UI Quality', C: Screenshots },
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

  const counts = useMemo(() => badges(qa), [qa])
  const View = (VIEWS.find(v => v.id === sub) || VIEWS[0]).C

  if (!project) return <Empty>Open a project to see its test results.</Empty>


  return (
    <div className="relative flex min-h-0 flex-1 flex-col text-ink" aria-busy={building || undefined}>
      <div className={cn('flex shrink-0 items-center gap-1.5 border-b border-line bg-panel px-4 py-2.5 backdrop-blur-md overflow-x-auto',
                         building && 'pointer-events-none select-none blur-sm')}>
        {VIEWS.map(v => (
          <button key={v.id} onClick={() => setSub(v.id)}
                  className={cn('flex shrink-0 items-center gap-1.5 rounded-none px-3 py-1.5',
                    'font-display text-[11.5px] transition-all cursor-pointer',
                    sub === v.id ? 'bg-[#BFB9FF] text-ink font-semibold shadow-[0_8px_16px_0_rgba(191, 185, 255,0.24)]'
                                 : 'text-muted hover:bg-ink/[.05] hover:text-ink')}>
            {v.label}
            {counts[v.id] != null && (
              <span className={cn('rounded-full px-1.5 py-0.2 font-mono text-[9.5px]',
                sub === v.id ? 'bg-black/20 text-ink'
                  : counts[v.id].bad ? 'bg-[#FF5630]/20 text-[#FF5630]' : 'bg-[#22C55E]/20 text-ink')}>
                {counts[v.id].n}
              </span>
            )}
          </button>
        ))}
        <span className="flex-1 min-w-4" />
        <Button variant="outline" size="sm" className="shrink-0 rounded-none border-line bg-panel2/60 text-ink hover:bg-raised"
                disabled={!project || state !== 'ready' || pdf}
                onClick={downloadPdf}
                title="Download the saved testing report as a PDF">
          {pdf ? <Loader2 className="size-3 animate-spin text-[#BFB9FF]" />
               : <Download className="size-3 text-[#BFB9FF]" />} PDF
        </Button>
        {live.running
          ? <span className="flex shrink-0 items-center gap-1.5 rounded-full border border-[#22C55E]/30 bg-[#22C55E]/10 px-2.5 py-1 font-mono text-[10.5px] font-semibold text-ink">
              <span className="size-1.5 animate-pulse rounded-full bg-[#22C55E]" /> running
            </span>
          : <Button variant="outline" size="sm" className="shrink-0 rounded-none border-line bg-panel2/60 text-ink hover:bg-raised" onClick={load}>
              <RefreshCw className="size-3" /> Refresh
            </Button>}
      </div>

      <div className={cn('min-h-0 flex-1 overflow-y-auto p-5',
                         building && 'pointer-events-none select-none blur-sm')}>
        {state === 'loading' && !qa && <Empty>Reading the results…</Empty>}
        {state === 'error' && <Empty bad>Could not read them — {error}</Empty>}
        {live.running && <p className="mb-3 text-[11px] text-accent">Testing is running. Completed results update here as each check finishes.</p>}
        {sub === 'e2e' && live.running && e2eLive?.active && <div className="mb-4"><E2ELiveLanes /></div>}
        {qa?.project === project && <View qa={qa} live={live} />}
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


function badges(qa) {
  const out = {}
  const r = qa?.report
  const v = qa?.vitest || qa?.savedVitest
  if (v) {
    const unit = unitTestStatus(v)
    out.unit = { n: `${unit.passed}/${unit.total}${unit.unit === 'files' ? ' files' : ''}${qa.unitEvidenceStatus === 'outdated' ? ' saved' : ''}`,
                 bad: unit.failed > 0 }
  }
  if (r) {
    const bugs = r.suite?.unresolved?.length || 0
    out.bugs = { n: qa?.resolvedBugs?.length ? `${bugs} open · ${qa.resolvedBugs.length} fixed` : bugs, bad: bugs > 0 }
  }
  if (r?.e2e) {
    const e = e2eStageSummary(r.e2e)
    if (e.total) out.e2e = { n: `${e.passed}/${e.total}`, bad: e.passed !== e.total }
    else if (r.e2e.recordedOutcomes?.length) out.e2e = { n: `${r.e2e.recordedOutcomes.length} saved`, bad: false }
  }
  if (r?.security) {
    const sec = (r.security.findings?.length || 0) + Object.values(r.security.audit || {}).reduce((sum, value) => sum + (Number(value) || 0), 0) + Object.values(r.security.headers?.checks || {}).filter(value => !value).length
    out.security = { n: r.security.audit_status !== 'completed' ? 'n/a' : sec, bad: sec > 0 || r.security.audit_status !== 'completed' }
  }
  if (qa?.load) out.perf = { n: qa.load.status === 'completed' ? `${qa.load.latencyMs?.p97_5 ?? '—'}ms p97.5` : qa.load.status, bad: qa.load.status !== 'completed' }
  if (qa?.accessibility) out.accessibility = { n: `${qa.accessibility.passed || 0}/${qa.accessibility.totalRoutes || 0}`, bad: qa.accessibility.status !== 'passed' }
  if (qa?.repairs?.rounds?.length) out.repair = { n: `${qa.repairs.rounds.length} round(s)`, bad: qa.repairs.status !== 'fixed' }
  const timeline = qa?.timeline?.length || qa?.history?.length
  if (timeline) out.timeline = { n: timeline, bad: false }
  if (qa?.screenshots?.length) out.screenshots = { n: qa.screenshots.length, bad: false }
  if (qa?.contracts?.length) out.routes = { n: qa.contracts.length, bad: false }
  return out
}


export const Summary = ({ children }) => (
  <div className="mb-5 flex flex-wrap items-center gap-6 rounded-none border border-black/10 bg-[#F2F0EF]/80 px-5 py-3.5 shadow-xl backdrop-blur-xl">{children}</div>
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
