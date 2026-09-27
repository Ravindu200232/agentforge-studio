'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Check, ExternalLink, Loader2, Rocket, Settings2, Terminal, X } from 'lucide-react'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { groupMonitors } from '@/lib/deploy-nav'
import { PLAN_STATES, STATE_TEXT, TARGETS, TERMINAL } from '@/lib/deploy-constants'
import { Button, Empty, SectionLabel, Tag } from '../ui'
import { cn } from '@/lib/utils'
import CommandPage from './cli/CommandPage'
import DeployProgress from './DeployProgress'
import DeployPlanStage from './DeployPlanStage'
import DeployResult from './DeployResult'
import { DeployDanger } from './DeployDanger'
import { projectUnitTestStatus } from '@/lib/test-counts'

/**
 * Deploy: choose where it goes, and the plan is made, asked about, approved and carried out (the plan card is in the chat).
 * Once there is a deployment, the navigation above is what its own command line tools can show, each one run live when opened.
 */
export default function DeployPanel({ onSettings, accountsRevision = 0 }) {
  const project = useStore(s => s.project)
  const qa = useStore(s => s.qaReport)
  const setQa = useStore(s => s.setQaReport)

  const [data, setData] = useState(null)
  const [cli, setCli] = useState(null)
  const [target, setTarget] = useState('vercel')
  const [override, setOverride] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const [view, setView] = useState('deploy')
  const [monitors, setMonitors] = useState({ loaded: false, items: [] })
  const alive = useRef(true)
  const currentProject = useRef(project)
  currentProject.current = project
  const currentAccountsRevision = useRef(accountsRevision)
  currentAccountsRevision.current = accountsRevision

  const mine = data?.project === project ? data : null
  // The plan card in the chat, shown here too so the plan can be read and approved from either place.
  const chat = useStore(s => s.chat)
  const planCard = useMemo(() => {
    const id = mine?.change?.id
    return id ? [...chat].reverse().find(row => row.role === 'change' && row.changeId === id) || null : null
  }, [chat, mine?.change?.id])
  const live = mine?.live
  const last = mine?.last
  const running = Boolean(live && !TERMINAL.has(live.state) && !live.error)

  // Publish it so the chat beside this panel can show the same run.
  const runId = live?.run_id || last?.run_id || ''
  const setDeployRunId = useStore(s => s.setDeployRunId)
  useEffect(() => { setDeployRunId(runId) }, [runId, setDeployRunId])

  const refresh = useCallback(async () => {
    if (!project) return
    try {
      const d = await api.deployResults(project)
      if (alive.current && currentProject.current === project && currentAccountsRevision.current === accountsRevision) setData(d)
    } catch (e) {
      if (alive.current && currentProject.current === project && currentAccountsRevision.current === accountsRevision) setError(e.message)
    }
  }, [project, accountsRevision])

  useEffect(() => {
    alive.current = true
    refresh()
    return () => { alive.current = false }
  }, [refresh])

  useEffect(() => {
    setData(null); setError(''); setOverride(false); setView('deploy'); setMonitors({ loaded: false, items: [] })
  }, [project])
  useEffect(() => {
    if (mine) setTarget(mine.last?.target || mine.live?.target || 'vercel')
  }, [mine?.project])

  useEffect(() => {
    if (!project || qa?.project === project) return
    let ok = true
    api.qa(project).then(d => { if (ok) setQa(d) }).catch(() => { })
    return () => { ok = false }
  }, [project, qa, setQa])

  useEffect(() => {
    if (!running) return
    const t = setInterval(refresh, 1400)
    return () => clearInterval(t)
  }, [running, refresh])

  // What this deployment's own command line tools can show, offered from what its record holds (it grows as the run records more).
  const monitorsKey = `${project}|${last?.run_id || ''}|${last?.state || ''}|${last?.host ? 1 : 0}`
  useEffect(() => {
    if (!project || !last?.target) { setMonitors({ loaded: true, items: [] }); return }
    let ok = true
    api.cliMonitorList(project)
      .then(r => { if (ok) setMonitors({ loaded: true, items: r?.items || [] }) })
      .catch(() => { if (ok) setMonitors({ loaded: true, items: [] }) })
    return () => { ok = false }
  }, [monitorsKey])            // eslint-disable-line react-hooks/exhaustive-deps
  const clis = useMemo(() => [...new Set(monitors.items.map(item => item.cli))], [monitors.items])
  const [cliTab, setCliTab] = useState('')
  const current = monitors.items.find(item => item.id === view)
  useEffect(() => { if (!clis.includes(cliTab)) setCliTab(clis[0] || '') }, [clis, cliTab])
  useEffect(() => { if (current && current.cli !== cliTab) setCliTab(current.cli) }, [current])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (view !== 'deploy' && monitors.loaded && !current) setView('deploy')
  }, [view, monitors.loaded, current])

  // Which command line tools are installed and who each is signed in as: every deployment goes through the target's own tool.
  useEffect(() => {
    let ok = true
    setCli(null)
    api.cliSigninAvailable().then(r => { if (ok) setCli(r?.providers || {}) }).catch(() => { if (ok) setCli({}) })
    return () => { ok = false }
  }, [accountsRevision])

  // A stack that only some targets can host offers only those; which is the deployment pack's own data.
  const allowed = mine?.allowed_targets
  const targets = Array.isArray(allowed) ? TARGETS.filter(t => allowed.includes(t.id)) : TARGETS
  const hidden = TARGETS.length - targets.length
  useEffect(() => {
    if (Array.isArray(allowed) && allowed.length && !allowed.includes(target)) setTarget(allowed[0])
  }, [allowed, target])
  const where = TARGETS.find(t => t.id === target)?.label || target

  const unit = projectUnitTestStatus(qa, project)
  const failures = unit?.failed ?? null
  const tested = Boolean(unit?.tested)
  const green = tested && failures === 0

  // What the deployment needs from this computer: the target's own command line tool, signed in. GitHub is listed for
  // the repository step but does not block: the plan asks about it when it is missing.
  const providerOf = mine?.targets?.find(t => t.id === target)?.provider || target
  const toolNeed = (key, optional) => {
    const row = cli?.[key]
    const who = row?.identity || {}
    return {
      id: key, label: row?.title || key, optional,
      ok: Boolean(row?.signed_in), unknown: !cli,
      hint: !row ? '' : !row.installed ? `not installed — install it with: ${row.install}`
        : !row.signed_in ? (who.expired ? 'its session has expired — sign in again from Settings → Integrations'
                                        : 'not signed in — sign in from Settings → Integrations')
        : `signed in as ${who.account || 'this computer’s account'}`
          + (who.missing_scopes?.length ? ` · missing permission: ${who.missing_scopes.join(', ')}` : ''),
    }
  }
  const needs = [toolNeed(providerOf, false), ...(providerOf === 'github' ? [] : [toolNeed('github', true)])]
  const ready = needs.every(n => n.ok || n.optional) && (green || override) && !starting
  const redeploy = Boolean(last?.run_id && last.target === target)

  async function deploy() {
    setStarting(true)
    setError('')
    try {
      const state = useStore.getState()
      await api.deployStart({ project, target, model: state.models.builder || state.models.agent })
      await refresh()
    } catch (e) {
      setError(e.message)
    }
    setStarting(false)
  }

  if (!project) {
    return <div className="min-h-0 flex-1 overflow-auto p-5">
             <Empty>Open a project first.</Empty>
           </div>
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto bg-[radial-gradient(circle_at_top_right,rgba(191, 185, 255,.08),transparent_30%)]">
      <DeployNav view={view} setView={setView} items={monitors.items} clis={clis} cliTab={cliTab} setCliTab={setCliTab}
                 last={live || last} running={running} runId={runId} onDone={refresh} />

      <div className="mx-auto max-w-[1180px] space-y-4 p-5">
        {view !== 'deploy' && current ? (
          <CommandPage key={`${project}:${current.set}/${current.id}`} project={project} item={current} />
        ) : (<>
          {live && PLAN_STATES.has(live.state) && <DeployPlanStage live={live} plan={mine?.plan} card={planCard} />}
          {live && !PLAN_STATES.has(live.state) && <DeployProgress run={live} />}

          {!running && (
            <div className="rounded-2xl border border-[rgba(145,158,171,0.16)] bg-[#F2F0EF] p-6 shadow-[0_0_2px_0_rgba(145,158,171,0.2),0_12px_24px_-4px_rgba(0,0,0,0.16)] backdrop-blur-xl">
              <SectionLabel>Where should it go?</SectionLabel>
              <p className="mt-1 text-[11.5px] text-[#6B7280]">
                Choose the cloud destination for this reviewed build.
                {hidden > 0 && ` ${mine?.stack_name || 'This stack'} ${mine?.refusal || 'is not supported everywhere'}, so only these are offered.`}
              </p>
              <div className="mt-3.5 grid gap-3 sm:grid-cols-2">
                {targets.map(t => (
                  <button key={t.id} onClick={() => setTarget(t.id)}
                          className={cn('rounded-xl border p-4 text-left shadow-sm transition-all',
                            target === t.id
                              ? 'border-[#BFB9FF] bg-[#BFB9FF] ring-1 ring-[#BFB9FF]/30'
                              : 'border-[rgba(145,158,171,0.16)] bg-[#F2F0EF]/50 hover:-translate-y-0.5 hover:border-[rgba(145,158,171,0.28)] hover:bg-[#E3E1E0]/50')}>
                    <span className="flex items-center gap-2.5 text-[13px] font-bold text-ink">
                      <span className={cn('grid size-4 place-items-center rounded-full border',
                        target === t.id ? 'border-[#BFB9FF] bg-[#BFB9FF]' : 'border-[rgba(145,158,171,0.32)] bg-[#F2F0EF]')}>
                        {target === t.id && <Check className="size-2.5 text-ink" />}
                      </span>
                      {t.label}
                    </span>
                    <span className="mt-1.5 block text-[11px] leading-relaxed text-[#6B7280]">{t.blurb}</span>
                  </button>
                ))}
              </div>

              <SectionLabel className="mt-6"
                            right={onSettings && (
                              <Button variant="outline" size="sm" className="rounded-xl border-[rgba(145,158,171,0.2)] bg-[#F2F0EF]/60 text-ink hover:bg-[#E3E1E0]" onClick={onSettings}>
                                <Settings2 className="size-3" /> Settings
                              </Button>
                            )}>
                Accounts
              </SectionLabel>
              <ul className="mt-3 grid gap-2.5 sm:grid-cols-2">
                {needs.map(n => (
                  <li key={n.id} className={cn('flex items-start gap-2.5 rounded-xl border px-3.5 py-3',
                    n.unknown || (!n.ok && n.optional) ? 'border-[rgba(145,158,171,0.16)] bg-[#F2F0EF]/30'
                      : n.ok ? 'border-[#22C55E]/20 bg-[#22C55E]/10' : 'border-[#FF5630]/20 bg-[#FF5630]/10')}>
                    <span className="mt-[2px] grid size-3.5 shrink-0 place-items-center">
                      {n.unknown
                        ? <Loader2 className="size-3 animate-spin text-[#6B7280]" />
                        : n.ok ? <Check className="size-3.5 text-ink" />
                               : <X className={cn('size-3.5', n.optional ? 'text-[#6B7280]' : 'text-[#FF5630]')} />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="text-[12px] font-semibold text-ink">{n.label}</span>
                      <span className={cn('ml-2 text-[11px]', n.unknown || n.ok || n.optional ? 'text-[#6B7280]' : 'text-[#FF5630]')}>
                        {n.hint}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>

              {!green && (
                <label className={cn('mt-4 flex cursor-pointer items-start gap-2.5 rounded-xl border px-3.5 py-3 text-[12px]',
                  override ? 'border-accent/30 bg-accent text-ink'
                           : 'border-[rgba(145,158,171,0.16)] bg-[#F2F0EF]/30 text-[#6B7280]')}>
                  <input type="checkbox" checked={override} className="mt-0.5 accent-[#BFB9FF]"
                         onChange={e => setOverride(e.target.checked)} />
                  <span>
                    {!tested
                      ? 'This project has not been tested in this session. Deploy anyway.'
                      : `${failures} unit test${failures === 1 ? '' : 's'} failing. Deploy anyway.`}
                  </span>
                </label>
              )}
              {green && (
                <p className="mt-4 flex items-center gap-2.5 rounded-xl border border-[#22C55E]/20 bg-[#22C55E]/10 px-3.5 py-3 text-[12px] text-ink">
                  <Check className="size-3.5 text-ink" />
                  Every unit test passes.
                </p>
              )}

              <p className="mt-4 text-[11px] text-[#6B7280]">Pressing Deploy starts a plan, not a deployment: the agent reads your project and this target's guide, asks you everything it needs (names, README, domain, scale, database, passwords), and shows the plan for you to approve.</p>

              <footer className="mt-6 flex items-center gap-3 border-t border-[rgba(145,158,171,0.16)] pt-4">
                <Button variant="solid" size="lg" className="h-11 rounded-xl bg-[#BFB9FF] px-6 font-display text-[13px] font-bold text-ink shadow-[0_8px_16px_0_rgba(191, 185, 255,0.24)] hover:bg-[#9B94E8]" disabled={!ready || starting}
                        onClick={deploy}>
                  {starting ? <Loader2 className="size-3.5 animate-spin" />
                            : <Rocket className="size-3.5" />}
                  {redeploy ? 'Redeploy' : 'Deploy'} to {where}
                </Button>
                {!ready && !starting && (
                  <span className="text-[11.5px] text-[#6B7280]">
                    {needs.find(n => !n.ok && !n.optional)
                      ? `${needs.find(n => !n.ok && !n.optional).label} is not connected yet`
                      : 'confirm you want to deploy a failing build'}
                  </span>
                )}
              </footer>

              {error && (
                <p className="mt-3 flex items-start gap-2.5 rounded-2xl border border-bad/20 bg-bad/[.045] px-3 py-3 text-[11.5px] text-bad">
                  <AlertTriangle className="mt-px size-3.5 shrink-0 text-accent" /> {error}
                </p>
              )}
            </div>
          )}

          <DeployResult data={mine} />
        </>)}
      </div>
    </div>
  )
}

/**
 * The navigation: Deploy, then the pages of the deployment's own command line tools. One strip of tabs per tool (Vercel CLI,
 * GitHub CLI), each command its own tab, grouped; opening a tab runs its command and shows the answer live.
 */
function DeployNav({ view, setView, items, clis, cliTab, setCliTab, last, running, runId, onDone }) {
  const [label, tone] = last ? (STATE_TEXT[last.state] || [last.state, 'mute']) : ['', 'mute']
  const mine = items.filter(item => item.cli === cliTab)
  const groups = groupMonitors(mine)
  return (
    <div className="sticky top-0 z-10 border-b border-[rgba(145,158,171,0.16)] bg-[#F2F0EF]/95 backdrop-blur-xl">
      <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
        <Chip on={view === 'deploy'} onClick={() => setView('deploy')}><Rocket className="size-3" /> Deploy</Chip>
        {last && <Tag tone={{ pass: 'ok', fail: 'bad', run: 'accent' }[tone] || 'mute'}>{label}</Tag>}
        {last?.url && (
          <a href={last.url} target="_blank" rel="noreferrer"
             className="inline-flex min-w-0 items-center gap-1 truncate font-mono text-[11px] text-[#BFB9FF] hover:underline">
            {last.url.replace(/^https:\/\//, '')} <ExternalLink className="size-2.5 shrink-0" />
          </a>
        )}
        <span className="flex-1" />
        <DeployDanger runId={runId} state={last?.state || ''} running={running} onDone={onDone} />
      </div>

      {clis.length > 0 && (
        <div className="mt-2.5 flex items-center gap-1 px-4">
          <Terminal className="mr-1 size-3 shrink-0 text-[#6B7280]" />
          {clis.map(name => (
            <button key={name} type="button" onClick={() => { setCliTab(name); const first = items.find(item => item.cli === name); if (first) setView(first.id) }}
                    className={cn('rounded-t-lg border-b-2 px-3 py-1.5 text-[11.5px] font-semibold transition-colors',
                      cliTab === name ? 'border-[#BFB9FF] text-ink' : 'border-transparent text-[#6B7280] hover:text-ink')}>
              {name}
              <span className="ml-1.5 font-mono text-[10px] text-[#637381]">{items.filter(item => item.cli === name).length}</span>
            </button>
          ))}
        </div>
      )}

      {groups.length > 0 && (
        <div className="flex items-center gap-1 overflow-x-auto border-t border-[rgba(145,158,171,0.1)] px-3 py-2">
          {groups.map((group, index) => (
            <div key={group.name} className={cn('flex shrink-0 items-center gap-1', index > 0 && 'ml-2 border-l border-[rgba(145,158,171,0.16)] pl-3')}>
              <span className="mr-1 text-[9.5px] font-semibold uppercase tracking-[.12em] text-[#637381]">{group.name}</span>
              {group.items.map(item => (
                <Chip key={item.id} on={view === item.id} onClick={() => setView(item.id)} title={item.display}>{item.label}</Chip>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Chip({ on, onClick, title, children }) {
  return (
    <button type="button" onClick={onClick} title={title} aria-pressed={on}
            className={cn('inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11.5px] font-semibold transition-colors',
              on ? 'border-[#BFB9FF] bg-[#BFB9FF] text-ink'
                 : 'border-[rgba(145,158,171,0.2)] text-ink hover:bg-black/5 hover:text-ink')}>
      {children}
    </button>
  )
}
