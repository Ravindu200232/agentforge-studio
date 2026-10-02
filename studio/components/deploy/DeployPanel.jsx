'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Boxes, Check, Cloud, Database, FileCode2, GitBranch, Globe2, HardDrive, KeyRound, Layers, Link2, Loader2, Lock, Network, Package, Plug, Rocket, Server, Settings2, Shield, ShieldCheck, Upload, Users, Workflow, X } from 'lucide-react'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { PLAN_STATES, STATE_TEXT, TARGETS, TERMINAL } from '@/lib/deploy-constants'
import { Button, Empty, SectionLabel, Tip } from '../ui'
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
  const current = monitors.items.find(item => item.id === view)
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
    <div className="flex min-h-0 flex-1 overflow-hidden bg-[radial-gradient(circle_at_top_right,rgba(191,185,255,.08),transparent_30%)]">
      <DeployNav view={view} setView={setView} items={monitors.items}
                 last={live || last} running={running} runId={runId} onDone={refresh} />

      <div className="min-w-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1180px] space-y-4 p-5">
        {view !== 'deploy' && current ? (
          <CommandPage key={`${project}:${current.set}/${current.id}`} project={project} item={current} />
        ) : (<>
          {live && PLAN_STATES.has(live.state) && <DeployPlanStage live={live} plan={mine?.plan} card={planCard} />}
          {live && !PLAN_STATES.has(live.state) && <DeployProgress run={live} />}

          {!running && (
            <div className="rounded-2xl border border-line bg-panel p-6 shadow-[0_0_2px_0_rgba(145,158,171,0.2),0_12px_24px_-4px_rgba(0,0,0,0.16)] backdrop-blur-xl">
              <SectionLabel>Where should it go?</SectionLabel>
              <p className="mt-1 text-[11.5px] text-muted">
                Choose the cloud destination for this reviewed build.
                {hidden > 0 && ` ${mine?.stack_name || 'This stack'} ${mine?.refusal || 'is not supported everywhere'}, so only these are offered.`}
              </p>
              <div className="mt-3.5 grid gap-3 sm:grid-cols-2">
                {targets.map(t => (
                  <button key={t.id} onClick={() => setTarget(t.id)}
                          className={cn('rounded-xl border p-4 text-left shadow-sm transition-all',
                            target === t.id
                              ? 'border-accent bg-accent ring-1 ring-accent/30'
                              : 'border-line bg-panel/50 hover:-translate-y-0.5 hover:border-[rgba(145,158,171,0.28)] hover:bg-raised/50')}>
                    <span className="flex items-center gap-2.5 text-[13px] font-bold text-ink">
                      <span className={cn('grid size-4 place-items-center rounded-full border',
                        target === t.id ? 'border-accent bg-accent' : 'border-[rgba(145,158,171,0.32)] bg-panel')}>
                        {target === t.id && <Check className="size-2.5 text-ink" />}
                      </span>
                      {t.label}
                    </span>
                    <span className="mt-1.5 block text-[11px] leading-relaxed text-muted">{t.blurb}</span>
                  </button>
                ))}
              </div>

              <SectionLabel className="mt-6"
                            right={onSettings && (
                              <Button variant="outline" size="sm" className="rounded-xl border-line bg-panel/60 text-ink hover:bg-raised" onClick={onSettings}>
                                <Settings2 className="size-3" /> Settings
                              </Button>
                            )}>
                Accounts
              </SectionLabel>
              <ul className="mt-3 grid gap-2.5 sm:grid-cols-2">
                {needs.map(n => (
                  <li key={n.id} className={cn('flex items-start gap-2.5 rounded-xl border px-3.5 py-3',
                    n.unknown || (!n.ok && n.optional) ? 'border-line bg-panel/30'
                      : n.ok ? 'border-ok/20 bg-ok/10' : 'border-bad/20 bg-bad/10')}>
                    <span className="mt-[2px] grid size-3.5 shrink-0 place-items-center">
                      {n.unknown
                        ? <Loader2 className="size-3 animate-spin text-muted" />
                        : n.ok ? <Check className="size-3.5 text-ink" />
                               : <X className={cn('size-3.5', n.optional ? 'text-muted' : 'text-bad')} />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="text-[12px] font-semibold text-ink">{n.label}</span>
                      <span className={cn('ml-2 text-[11px]', n.unknown || n.ok || n.optional ? 'text-muted' : 'text-bad')}>
                        {n.hint}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>

              {!green && (
                <label className={cn('mt-4 flex cursor-pointer items-start gap-2.5 rounded-xl border px-3.5 py-3 text-[12px]',
                  override ? 'border-accent/30 bg-accent text-ink'
                           : 'border-line bg-panel/30 text-muted')}>
                  <input type="checkbox" checked={override} className="mt-0.5 accent-[var(--accent)]"
                         onChange={e => setOverride(e.target.checked)} />
                  <span>
                    {!tested
                      ? 'This project has not been tested in this session. Deploy anyway.'
                      : `${failures} unit test${failures === 1 ? '' : 's'} failing. Deploy anyway.`}
                  </span>
                </label>
              )}
              {green && (
                <p className="mt-4 flex items-center gap-2.5 rounded-xl border border-ok/20 bg-ok/10 px-3.5 py-3 text-[12px] text-ink">
                  <Check className="size-3.5 text-ink" />
                  Every unit test passes.
                </p>
              )}

              <p className="mt-4 text-[11px] text-muted">Pressing Deploy starts a plan, not a deployment: the agent reads your project and this target's guide, asks you everything it needs (names, README, domain, scale, database, passwords), and shows the plan for you to approve.</p>

              <footer className="mt-6 flex items-center gap-3 border-t border-line pt-4">
                <Button variant="solid" size="lg" className="h-11 rounded-xl bg-accent px-6 font-display text-[13px] font-bold text-ink shadow-[0_8px_16px_0_rgba(191, 185, 255,0.24)] hover:bg-press" disabled={!ready || starting}
                        onClick={deploy}>
                  {starting ? <Loader2 className="size-3.5 animate-spin" />
                            : <Rocket className="size-3.5" />}
                  {redeploy ? 'Redeploy' : 'Deploy'} to {where}
                </Button>
                {!ready && !starting && (
                  <span className="text-[11.5px] text-muted">
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

          <DeployResult data={mine} onResumed={refresh} />
        </>)}
      </div>
      </div>
    </div>
  )
}

/** Command monitors can be numerous, so this keeps the shared rail language
 * while exposing each command's name and CLI group for quick recognition. */
function DeployNav({ view, setView, items, last, running, runId, onDone }) {
  const [, tone] = last ? (STATE_TEXT[last.state] || [last.state, 'mute']) : ['', 'mute']
  const statusDot = tone === 'pass' ? 'bg-ok' : tone === 'fail' ? 'bg-bad' : running ? 'bg-ok' : 'bg-muted2'
  const usedIcons = new Set()
  return (
    <aside aria-label="Deployment sections" className="flex w-[52px] shrink-0 flex-col items-center gap-1 overflow-y-auto border-r border-line bg-panel px-2 py-3 no-scrollbar">
      <Tip text="Deployment home" side="right">
        <button type="button" onClick={() => setView('deploy')} aria-label="Deploy" aria-pressed={view === 'deploy'}
                className={cn('grid size-9 place-items-center rounded-xl text-muted2 transition-colors hover:bg-raised hover:text-ink',
                  view === 'deploy' && 'text-deep')}>
          <Rocket className="size-4" />
        </button>
      </Tip>
      {last && <span className={cn('my-1 size-2 shrink-0 rounded-full', statusDot)} title={last.state} />}
      {items.length > 0 && <span className="my-1 h-px w-full bg-line" />}
      {items.map((item, index) => {
        const label = item.label || item.display || item.id
        const Icon = monitorIcon(item, index, usedIcons)
        const newGroup = index === 0 || item.cli !== items[index - 1]?.cli
        return (
          <div key={item.id}>
            {newGroup && index > 0 && <span className="my-1 block h-px w-7 bg-line" />}
            <Tip text={item.display || label} side="right">
              <button type="button" onClick={() => setView(item.id)} aria-label={label} aria-pressed={view === item.id}
                      className={cn('grid size-9 place-items-center rounded-xl text-muted2 transition-colors hover:bg-raised hover:text-ink',
                        view === item.id && 'text-deep')}>
                <Icon className={cn('size-4', view === item.id && 'text-deep')} />
              </button>
            </Tip>
          </div>
        )
      })}
      <span className="flex-1" />
      <div className="flex justify-end"><DeployDanger compact runId={runId} state={last?.state || ''} running={running} onDone={onDone} /></div>
    </aside>
  )
}

function monitorIcon(item, index, used) {
  const text = `${item?.cli || ''} ${item?.label || ''} ${item?.display || ''} ${item?.id || ''}`.toLowerCase()
  const preferred = /git|repo|branch|commit|pull request/.test(text) ? GitBranch
    : /domain|dns|url|route|alias|redirect/.test(text) ? Globe2
    : /secret|token|key|environment|variable|credential/.test(text) ? KeyRound
    : /security|protect|firewall|access|permission/.test(text) ? ShieldCheck
    : /database|storage|cache|blob|bucket/.test(text) ? Database
    : /team|account|member|user|owner/.test(text) ? Users
    : /network|function|runtime|edge|log/.test(text) ? Network
    : /deploy|build|release|project/.test(text) ? Cloud : null
  const choices = [preferred, Boxes, FileCode2, HardDrive, Layers, Link2, Lock, Package, Plug, Server, Shield, Upload, Workflow].filter(Boolean)
  const Icon = choices.find(candidate => !used.has(candidate)) || choices[index % choices.length]
  used.add(Icon)
  return Icon
}
