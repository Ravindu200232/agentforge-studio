'use client'

/** Conversation stream and control column alongside active preview, code, and tests. */

import { memo, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowDown, Check, CheckCircle2, ChevronDown, ChevronRight, CircleAlert, CircleCheck, Clock, Copy, ExternalLink, FileCode2, FlaskConical, ListChecks, Loader2,
  MessageCircleQuestion, MessageSquare, MousePointerClick, Palette, Paperclip, Pencil, Plug, Search,
  Send, SkipForward, Sparkles,
  Square, Terminal, Wrench, X,
} from 'lucide-react'

import { api } from '@/lib/api'
import { chatTurns } from '@/lib/chat'
import { chatDisplayBlocks, cleanChatProse } from '@/lib/chat-display'
import { consoleReport, forgetConsole } from '@/lib/console-log'
import { computeLineDiff } from '@/lib/diff'
import { modelLabel } from '@/lib/models'
import { useStore } from '@/lib/store'
import { useEditAttachments } from '@/lib/use-edit-attachments'
import { answerAsk, answerOption, answerQuestion, answerValue, declineAsk, reviseDrawing, send } from '@/lib/ws'
import { cn } from '@/lib/utils'
import ChangePlan from './ChangePlan'
import EditAttach from './EditAttach'
import PluginAccounts from './PluginAccounts'
import { Dropdown, Modal } from './ui'

const ICONS = {
  read: Search, plan: Search, write: FileCode2, build: FileCode2,
  test: FlaskConical, run: Terminal, fix: Wrench, design: Palette,
  verify: CircleCheck, done: CircleCheck, warn: CircleAlert,
  setup: Sparkles, note: Sparkles, effort: Sparkles,
}

// How much reasoning and tool lookup one model call used — Ollama has no
// native "effort" concept, so this is a rough four-level read, low to ultra.
const EFFORT_TONE = {
  low: 'bg-black/[.06] text-muted dark:bg-black/[.08]',
  medium: 'bg-accent/60 text-ink',
  high: 'bg-accent text-ink',
  ultra: 'bg-accent text-ink',
}

// Start at the current part of a long conversation. Earlier turns remain
// available from the top of the stream; they are never removed from history.
const TURN_PAGE_SIZE = 240

export default function AgentChat({ projectTitle = '', readOnly = false, className = '' }) {
  const logs = useStore(s => s.logs)
  const chat = useStore(s => s.chat)
  const busy = useStore(s => s.busy)
  const project = useStore(s => s.project)
  const projectSessions = useStore(s => s.projectSessions)
  const agentRole = useStore(s => s.agentRole)
  const question = useStore(s => s.question)
  const ask = useStore(s => s.ask)
  const drawing = useStore(s => s.drawing)
  const stats = useStore(s => {
    const candidates = [s.runStats, s.projectSessions[s.project]?.designer?.runStats,
      s.projectSessions[s.project]?.developer?.runStats].filter(Boolean)
    return candidates.sort((a, b) => (b.at || 0) - (a.at || 0))[0] || null
  })
  const agentState = useStore(s => s.agentState)
  const agentDetail = useStore(s => s.agentDetail)
  const reasoning = useStore(s => s.reasoning)
  const runStartedAt = useStore(s => s.runStartedAt)
  const pushChat = useStore(s => s.pushChat)
  const selection = useStore(s => s.selection)
  const removeSelection = useStore(s => s.removeSelection)
  const clearSelection = useStore(s => s.clearSelection)
  const planMode = useStore(s => s.planModeByProject[project] ?? true)
  const setPlanModeStore = useStore(s => s.setPlanMode)
  const [planModeBusy, setPlanModeBusy] = useState(false)
  const togglePlanMode = async () => {
    if (!project || planModeBusy) return
    const next = !planMode
    setPlanModeBusy(true)
    setPlanModeStore(project, next)   // optimistic — a typed change reads this immediately
    try {
      await api.setPlanMode(project, next)
    } catch (e) {
      setPlanModeStore(project, !next)
      useStore.getState().addLog('WARN', `Could not change plan mode — ${e.message}`)
    } finally {
      setPlanModeBusy(false)
    }
  }

  // Collapsing gives the whole width back to the work when someone wants it.
  const [open, setOpen] = useState(true)
  const text = useStore(s => s.draft || '')
  const setText = useStore(s => s.setDraft)
  const [reading, setReading] = useState(false)
  const [lifecycle, setLifecycle] = useState(null)
  const attach = useEditAttachments(project)
  const end = useRef(null)
  const box = useRef(null)
  const scrollRef = useRef(null)
  const userScrolledUp = useRef(false)
  const [showScrollBottom, setShowScrollBottom] = useState(false)
  const [visibleTurnCount, setVisibleTurnCount] = useState(TURN_PAGE_SIZE)

  // Designer and Developer are tool permissions, not separate conversations.
  // Merge their persisted UI projections while the backend shares the exact
  // model Memory through .agentforge/engine/conversation.json.
  const lifecycleStream = useMemo(() => {
    const own = projectSessions[project] || {}
    const sessions = ['designer', 'developer'].map(role => role === agentRole
      ? { logs, chat, busy, runStartedAt }
      : (own[role] || { logs: [], chat: [], busy: false, runStartedAt: 0 }))
    const unique = (rows, fields) => {
      const seen = new Set()
      return rows.filter(row => {
        const key = fields.map(field => String(row?.[field] ?? '')).join('\u0000')
        if (seen.has(key)) return false
        seen.add(key)
        return true
      }).sort((a, b) => (a.at || 0) - (b.at || 0))
    }
    return {
      logs: unique(sessions.flatMap(session => session.logs || []), ['at', 'level', 'text']),
      // Backend events are mirrored to both role projections so every tab sees
      // one conversation. Role is deliberately not part of this key: including
      // it rendered every persisted plan/message twice after a reload.
      chat: unique(sessions.flatMap(session => session.chat || []), ['at', 'text', 'title', 'kind']),
      busy: busy || ['designer', 'developer'].some(role => role !== agentRole && own[role]?.busy),
      startedAt: Math.max(0, ...sessions.map(session => Number(session.runStartedAt) || 0)),
    }
  }, [projectSessions, project, agentRole, logs, chat, busy, runStartedAt])
  const turns = useMemo(() => {
    const ordinary = chatTurns(lifecycleStream.logs, lifecycleStream.chat)
    // The "Checking this stage now…" cards are gone: the files and actions in
    // the stream already say what is happening.
    return [...ordinary, ...lifecycleTurns(lifecycle)]
      // Plans are internal execution input.  The stream shows the concrete
      // files, searches and decisions used to make them, not a large final
      // plan pasted into the conversation (including older persisted events).
      .filter(turn => turn.role !== 'stage' && turn.kind !== 'plan')
      .sort((a, b) => (a.at || 0) - (b.at || 0))
  }, [lifecycleStream, lifecycle])
  const firstVisibleTurn = Math.max(0, turns.length - visibleTurnCount)
  const visibleTurns = turns.slice(firstVisibleTurn)
  const hiddenTurnCount = firstVisibleTurn

  // Switching projects starts at that project's newest activity, with older
  // messages one click away rather than erased or mixed with another project.
  useEffect(() => {
    setVisibleTurnCount(TURN_PAGE_SIZE)
  }, [project])
  // A plan is on screen and waiting: whatever is typed now is about that plan.
  const planWaiting = turns.some(turn => turn.role === 'change' && turn.status === 'proposed')
  const waiting = useStore(s => s.queue)
  const queued = useMemo(() => waiting.filter(item => item.project === project),
                         [waiting, project])

  useEffect(() => {
    if (lifecycleStream.busy) setOpen(true)     // a run is the thing you watch
  }, [lifecycleStream.busy])

  // Stage plans and evidence are durable backend facts, so the same stream
  // remains truthful after reload and includes SRS, QA and Deploy even though
  // those stages use different tool adapters.
  useEffect(() => {
    let cancelled = false
    let timer = null
    if (!project) {
      setLifecycle(null)
      return undefined
    }
    const refresh = async () => {
      try {
        const result = await api.lifecycle(project)
        if (!cancelled) setLifecycle(result?.lifecycle || null)
      } catch {
        // The ordinary stream remains usable while an older backend restarts.
      } finally {
        if (!cancelled) timer = setTimeout(refresh, lifecycleStream.busy ? 1200 : 3500)
      }
    }
    refresh()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [project, lifecycleStream.busy])

  // Pointing at something in the preview is the start of a sentence, so the
  // box that finishes it comes to meet you.
  useEffect(() => {
    if (!selection.length) return
    setOpen(true)
    box.current?.focus()
  }, [selection.length])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const isBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    userScrolledUp.current = !isBottom
    setShowScrollBottom(!isBottom)
  }

  const scrollToBottom = () => {
    userScrolledUp.current = false
    setShowScrollBottom(false)
    end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }

  useEffect(() => {
    if (open && !userScrolledUp.current) {
      end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
    }
  }, [open, turns.length])

  // The moment a run ends, the next thing they typed goes. Firing sets the
  // agent working again, which brings this back for the one after it.
  useEffect(() => {
    if (lifecycleStream.busy || !project) return
    const next = useStore.getState().takeQueued(project, agentRole) // takeQueued(project)
    if (next) fire(next.payload, next.body)
  }, [lifecycleStream.busy, project])

  const stopRun = useStopRun(lifecycleStream.busy)

  async function submit() {
    const typed = text.trim()
    if (!typed || !project || reading) return

    // A question the agent stopped to ask is answered by the next thing they
    // type. It is first because it is the one the run is actually blocked on.
    if (ask?.variable) return         // a value is given in the question's own private box, not here
    if (ask && answerAsk(typed)) {
      pushChat({ role: 'user', text: typed, at: Date.now() })
      setText('')
      return
    }

    // A paused scope question is answered by the next thing they type.
    if (question && answerQuestion(typed)) {
      pushChat({ role: 'user', text: typed, at: Date.now() })
      setText('')
      return
    }

    // So is a drawing waiting in the preview: there is no dialog to type into,
    // so what they say here is what changes about it.
    if (drawing && reviseDrawing(typed)) {
      pushChat({ role: 'user', text: typed, at: Date.now() })
      setText('')
      return
    }

    let full = typed
    setReading(true)
    if (attach.items.length) {
      try {
        full = typed + await attach.collect()
      } catch (e) {
        useStore.getState().addLog('WARN', e.message)
        setReading(false)
        return
      }
    }

    if (useStore.getState().project !== project || useStore.getState().agentRole !== agentRole) {
      setReading(false)
      return
    }

    const route = agentRole === 'designer' ? '/prototype' : (selection[0]?.route || useStore.getState().previewRoute || '/')
    const payload = {
      type: selection.length ? 'element_edit' : 'agent_update',
      project, route, agent: agentRole,
      model: (agentRole === 'designer' ? useStore.getState().models.design : useStore.getState().models.builder) || useStore.getState().models.agent,
      think: useStore.getState().think,
      thinking_level: useStore.getState().thinkingLevel,
      qa_model: useStore.getState().models.qa || '',
      console: consoleReport(),
    }
    if (selection.length) {
      payload.elements = selection.filter(s => s.kind === 'element').map(s => s.info)
      payload.shots = selection.filter(s => s.shot)
        .map(s => ({ kind: s.kind, image: s.shot, label: s.label }))
    }

    const shots = selection.filter(s => s.shot).map(s => s.shot)
    if (lifecycleStream.busy) {
      queueUp(payload, full, typed, shots)
    } else {
      fire(payload, full)
    }
    setReading(false)
  }

  /** Hold it until the run in front of it is done. */
  function queueUp(payload, body, shown, shots) {
    useStore.getState().enqueue({ project, payload, body, shown, shots })
    // The console evidence in the payload has been taken; what arrives after
    // this belongs to whatever is said next.
    forgetConsole()
    attach.reset()
    clearSelection()
    setText('')
  }

  /** Say it, and it goes: sends typed prompts and attachments directly to the agent. */
  function fire(payload, body) {
    const s = useStore.getState()
    // The server journals and echoes the message, including queued requests.
    send({ ...payload, prompt: body })
    forgetConsole()
    s.setBusy(true)
    attach.reset()
    clearSelection()
    setText('')
  }

  if (!open) {
    return (
      <div className="flex w-[46px] shrink-0 flex-col items-center gap-3 border-r border-line/60 bg-panel/70 py-3">
        <button onClick={() => setOpen(true)} title="Show the agent"
                className="grid size-8 place-items-center rounded-xl text-ink transition-colors hover:bg-accent">
          <MessageSquare className="size-4" />
        </button>
        {lifecycleStream.busy && <Loader2 className="size-3.5 animate-spin text-accent" />}
      </div>
    )
  }

  return (
    <aside className={cn('flex w-[100%] lg:w-[var(--chat-w,500px)] max-w-full shrink-0 flex-col overflow-hidden border-r border-line/60 bg-panel', className)}>
      <header className="shrink-0 border-b border-line/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="min-w-0">
            <p className="truncate text-[12px] font-semibold leading-none text-ink">{projectTitle || 'Project chat'}</p>
            <p className="mt-1 text-[10px] text-muted2">
              {readOnly ? 'Interview conversation — it continues through every stage.'
                : lifecycleStream.busy ? 'Working on your request' : project ? 'Ready for the next request' : 'Open a project to begin'}
            </p>
          </div>
          <span className="flex-1" />
          {lifecycleStream.busy && (
            <span className="flex items-center gap-1 text-[10px] font-medium text-muted">
              <Loader2 className="size-3 animate-spin" /> working
            </span>
          )}
          <button onClick={() => setOpen(false)} title="Hide the agent"
                  className="grid size-7 place-items-center rounded-lg text-muted transition-colors hover:bg-black/[.05] hover:text-ink dark:hover:bg-black/[.06]">
            <ChevronDown className="size-3.5 -rotate-90" />
          </button>
        </div>
      </header>

      <div ref={scrollRef} onScroll={handleScroll} className="relative min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="space-y-2">
          {hiddenTurnCount > 0 && (
            <button
              onClick={() => setVisibleTurnCount(count => Math.min(turns.length, count + TURN_PAGE_SIZE))}
              className="w-full rounded-lg border border-line bg-panel px-3 py-2 text-[11px] font-medium text-muted transition-colors hover:border-accent hover:text-ink"
            >
              Show {Math.min(TURN_PAGE_SIZE, hiddenTurnCount)} older messages · {hiddenTurnCount} saved
            </button>
          )}
          {/* The last row is the one happening now, so it is the one that
              spins; the rows behind it have already happened. */}
          {visibleTurns.map(turn => (
            <Turn key={turn.id || `${turn.at}-${turn.role}-${turn.title || turn.text || ''}`} turn={turn}
                  live={lifecycleStream.busy && turn.id === turns.at(-1)?.id} />
          ))}
          {lifecycleStream.busy && (reasoning || Boolean(agentState)) && !ask &&
            <Thinking reasoning={reasoning} state={agentState} detail={agentDetail} />}
          {ask && <Asked ask={ask} onPick={said => { setText(said); box.current?.focus() }} />}
          {queued.map(item => (
            <Queued key={item.id} item={item}
                    onDrop={() => useStore.getState().dropQueued(item.id)} />
          ))}
          {!turns.length && !queued.length && (
            <p className="py-10 text-center text-[11.5px] text-muted">
              {project ? 'Continue this project with your next request.'
                       : 'Open a project to talk to the agent.'}
            </p>
          )}
          <div ref={end} />
        </div>
        {showScrollBottom && (
          <button onClick={scrollToBottom}
                  title="Scroll to latest messages"
                  className="sticky bottom-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5 rounded-full border border-line/90 bg-panel px-3.5 py-1.5 text-[11px] font-semibold text-ink shadow-xl backdrop-blur hover:bg-accent hover:text-ink transition-all">
            <ArrowDown className="size-3.5" /> Latest messages
          </button>
        )}
      </div>

      {lifecycleStream.busy && (
        <LiveTurnMeter stats={stats} startedAt={lifecycleStream.startedAt}
                       reasoning={reasoning} state={agentState} />
      )}

      {!readOnly && <footer className="shrink-0 border-t border-line bg-panel px-3 py-3">
        <Attached items={selection} onRemove={removeSelection} />
        <div className="rounded-xl border border-line bg-white p-2 shadow-sm transition-all focus-within:border-line2">
          <textarea
            ref={box}
            aria-label="Continue this project"
            value={text} rows={1}
            disabled={!project || reading}
            placeholder={ask
              ? 'Answer it here, or say it in your own words…'
              : question
              ? 'Answer the question above…'
              : drawing ? 'Say what to change about the drawing…'
              : planWaiting ? 'Say what to change about the plan — or approve it above'
              : lifecycleStream.busy ? 'Say what is next — it goes when this finishes'
              : selection.length
                ? 'Say what should change about it…'
              : project ? 'Plan, search, build anything…'
                        : 'Open a project first'}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
              if (e.key === 'Escape' && lifecycleStream.busy) { e.preventDefault(); stopRun.stop() }
            }}
            className="min-h-8 w-full resize-none bg-transparent px-1.5 py-1 text-[12.5px] leading-relaxed text-ink outline-none placeholder:text-muted2 disabled:opacity-45" />
          <div className="mt-1 flex items-center justify-between px-0.5">
            {project ? (
              <span className="flex min-w-0 items-center gap-1">
                <EditAttach attach={attach} project={project}
                        onSpoken={said => setText((text ? text.trimEnd() + ' ' : '') + said)} disabled={reading} />
                <PluginPicker project={project} />
                {selection.length ? (
                  <span
                    title="Element-specific edits are scoped to the selected artifact."
                    className="ml-1 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-semibold text-muted2">
                    <ListChecks className="size-3" />
                    Direct element edit
                  </span>
                ) : (
                  <button type="button" onClick={togglePlanMode} disabled={!project || planModeBusy}
                    title={planMode
                      ? 'Every request is planned first: you read the plan and approve it before anything changes. Click to apply changes directly instead.'
                      : 'Changes apply at once, with no plan to approve first. Click to plan first instead.'}
                    className={cn('ml-1 inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-[10px] font-medium transition-colors disabled:opacity-50',
                      planMode ? 'bg-panel2 text-ink hover:border-line2' : 'text-muted2 hover:bg-panel2 hover:text-ink')}>
                    <ListChecks className="size-3" />
                    {planMode ? 'Plan first' : 'Apply directly'}
                  </button>
                )}
              </span>
            ) : <span />}
            <div className="flex shrink-0 items-center gap-1">
              <ChatModelControls project={project} agentRole={agentRole} busy={lifecycleStream.busy} />
              <ContextUsage stats={stats} />
              {(!lifecycleStream.busy || text.trim()) && (
                <button onClick={submit}
                        disabled={!project || reading || !text.trim()}
                        title={lifecycleStream.busy ? 'Queue this (Enter)' : 'Send (Enter)'}
                        className="grid size-7 place-items-center rounded-full bg-raised text-muted shadow-sm transition-all hover:bg-accent hover:text-ink disabled:opacity-30">
                  {reading ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
                </button>
              )}
              {lifecycleStream.busy && (
                <button onClick={stopRun.stop} disabled={stopRun.stopping}
                        title={stopRun.stopping ? 'Stopping…' : 'Stop (Esc)'} aria-label="Stop"
                        className="grid size-7 place-items-center rounded-full bg-ink text-panel shadow-sm transition-all hover:opacity-85 disabled:opacity-60">
                  {stopRun.stopping ? <Loader2 className="size-3.5 animate-spin" /> : <Square className="size-2.5 fill-current" />}
                </button>
              )}
              <span role="status" aria-live="polite" className="sr-only">{stopRun.stopping ? 'Stop requested' : ''}</span>
            </div>
          </div>
        </div>
      </footer>}

    </aside>
  )
}

/**
 * The conversation owns its history; a model is only the engine used for the
 * next turn. Keeping this next to the stream makes that distinction visible
 * instead of burying it in global Settings.
 */
function ChatModelControls({ project, agentRole, busy }) {
  const models = useStore(s => s.models)
  const thinkingLevel = useStore(s => s.thinkingLevel)
  const setRoleModel = useStore(s => s.setRoleModel)
  const setThinkingLevel = useStore(s => s.setThinkingLevel)
  const addLog = useStore(s => s.addLog)
  const [catalog, setCatalog] = useState(null)
  const [saving, setSaving] = useState(false)
  const [open, setOpen] = useState(false)

  const role = agentRole === 'designer' ? 'design' : 'builder'
  const current = models[role] || models.agent || ''
  const groups = [
    ['On this machine', catalog?.local_models || []],
    ['Cloud', catalog?.cloud || []],
  ]
  const inCatalog = groups.some(([, rows]) => rows.some(row => (row.id || row) === current))
  const selected = groups.flatMap(([, rows]) => rows).find(row => (row.id || row) === current)
  const selectedLabel = modelLabel(selected || { id: current }) || current || 'Choose model'
  const effort = {
    low: 'Low', high: 'High', xhigh: 'Extra',
  }[thinkingLevel] || 'High'

  useEffect(() => {
    let alive = true
    api.models().then(result => { if (alive) setCatalog(result || {}) })
      .catch(() => { if (alive) setCatalog({}) })
    return () => { alive = false }
  }, [])

  async function save(nextModel, nextLevel) {
    setSaving(true)
    try {
      await api.saveSettings({ agent_model: nextModel, thinking_level: nextLevel })
    } catch (error) {
      addLog('WARN', `Could not save the chat model preference — ${error.message}`)
    } finally {
      setSaving(false)
    }
  }

  function chooseModel(next) {
    if (!next || next === current) return
    setRoleModel(role, next)
    save(next, thinkingLevel)
  }

  function chooseEffort(level) {
    if (level === thinkingLevel) return
    setThinkingLevel(level)
    save(current, level)
  }

  return (
    <div className="relative min-w-0">
      <button type="button" disabled={!project}
              onClick={() => setOpen(value => !value)}
              aria-haspopup="dialog" aria-expanded={open}
              title="Choose the model and reasoning effort for the next turn"
              className="flex max-w-[174px] items-center gap-1 rounded-md px-1.5 py-1 text-[10px] font-medium text-muted2 transition-colors hover:bg-panel2 hover:text-ink disabled:opacity-45">
        <span className="truncate text-ink">{selectedLabel}</span>
        <span className="shrink-0 text-muted2">{effort}</span>
        {saving || busy
          ? <Loader2 className="size-3 shrink-0 animate-spin text-deep" />
          : <ChevronDown className={cn('size-3 shrink-0 transition-transform', open && 'rotate-180')} />}
      </button>

      <Dropdown open={open} onClose={() => setOpen(false)}
                className="bottom-full right-0 mb-2 w-[296px] p-2">
        <div role="dialog" aria-label="Model and reasoning settings">
          <p className="px-2 pb-1 text-[10px] font-semibold text-muted2">Select model</p>
          <div className="max-h-52 space-y-1 overflow-y-auto pr-1">
            {current && !inCatalog && (
              <button type="button" onClick={() => chooseModel(current)}
                      className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[11px] text-ink hover:bg-panel2">
                <span className="truncate">{current}</span><span className="text-[9px] text-muted2">Current</span>
              </button>
            )}
            {groups.map(([name, rows]) => rows.length > 0 && (
              <section key={name} className="pb-1">
                <p className="px-2 py-1 text-[9px] font-semibold uppercase tracking-wide text-muted2">{name}</p>
                {rows.map(row => {
                  const id = row.id || row
                  const picked = id === current
                  return (
                    <button key={id} type="button" onClick={() => chooseModel(id)} disabled={saving}
                            aria-pressed={picked}
                            className={cn('flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition-colors disabled:opacity-45',
                              picked ? 'bg-accent/55 text-ink' : 'text-ink hover:bg-panel2')}>
                      <span className="min-w-0 flex-1 truncate">{modelLabel(row) || id}</span>
                      {picked && <Check className="size-3 shrink-0" />}
                    </button>
                  )
                })}
              </section>
            ))}
            {!catalog && <p className="px-2 py-3 text-[10px] text-muted2">Reading available models…</p>}
            {catalog && !groups.some(([, rows]) => rows.length) && <p className="px-2 py-3 text-[10px] text-muted2">No models are available yet.</p>}
          </div>

          <div className="mt-2 border-t border-line pt-2">
            <p className="px-2 pb-1 text-[10px] font-semibold text-muted2">Reasoning effort</p>
            <div aria-label="Reasoning effort" className="grid grid-cols-3 rounded-xl bg-panel2 p-1">
              {[
                ['low', 'Low'], ['high', 'High'], ['xhigh', 'Extra high'],
              ].map(([id, label]) => (
                <button key={id} type="button" disabled={saving} onClick={() => chooseEffort(id)}
                        title={id === 'xhigh'
                          ? 'Reasons and performs a separate final verification pass. Applies to the next turn.'
                          : `${label} effort. Applies to the next turn without clearing this project history.`}
                        aria-pressed={thinkingLevel === id}
                        className={cn('rounded-lg px-1 py-1.5 text-[10px] font-semibold transition-colors disabled:opacity-45',
                          thinkingLevel === id ? 'bg-panel text-ink shadow-sm' : 'text-muted2 hover:text-ink')}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <p aria-live="polite" className="px-2 pb-0.5 pt-2 text-[9.5px] text-muted2">
            {saving ? 'Saving preference…' : busy
              ? 'Applies to the next turn; this run keeps its current model.'
              : 'Changes keep this project’s conversation and memory.'}
          </p>
        </div>
      </Dropdown>
    </div>
  )
}

const STAGE_LABELS = {
  srs: 'SRS', design: 'Design system', prototype: 'Prototype',
  builder: 'Builder', qa: 'Quality audit', deployment: 'Deployment',
}

function evidenceDetail(item) {
  if (!item || typeof item !== 'object') return String(item || '')
  if (item.url) return item.url
  if (item.path) return item.path
  const facts = []
  if (item.pages != null) facts.push(`${item.pages} page(s)`)
  if (item.files != null) facts.push(`${Array.isArray(item.files) ? item.files.length : item.files} file(s)`)
  if (item.iterations != null) facts.push(`${item.iterations} iteration(s)`)
  if (item.tool_calls != null) facts.push(`${item.tool_calls} tool call(s)`)
  if (item.state) facts.push(String(item.state))
  return facts.join(' · ') || String(item.detail || '')
}

function lifecycleTurns(lifecycle) {
  if (!lifecycle?.stages) return []
  const turns = []
  for (const [name, stage] of Object.entries(lifecycle.stages)) {
    if (!stage || stage.status === 'pending') continue
    const at = Number(stage.updated_at || stage.started_at || 0) * 1000
    const active = ['planning', 'awaiting_approval', 'running'].includes(stage.status)
    turns.push({
      id: `lifecycle-${name}-${stage.updated_at}-${stage.status}`,
      role: 'stage', at, status: active ? 'active' : stage.status === 'passed' ? 'done' : 'error',
      title: `${STAGE_LABELS[name] || name} · ${String(stage.status).replaceAll('_', ' ')}`,
      detail: stage.summary || (stage.blockers || []).join(' · '),
    })
    ;(stage.evidence || []).forEach((item, index) => turns.push({
      id: `lifecycle-${name}-evidence-${index}-${stage.updated_at}`,
      role: 'test_result', at: at + index + 1,
      status: stage.status === 'passed' ? 'passed' : stage.status,
      title: item?.label || item?.kind || `${STAGE_LABELS[name] || name} evidence`,
      detail: evidenceDetail(item),
    }))
  }
  return turns
}

/** Visual chips showing picked elements and canvas pencil drawings attached to the message. */
function Attached({ items, onRemove }) {
  if (!items.length) return null
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {items.map(item => {
        const Icon = item.kind === 'drawing' ? Pencil : MousePointerClick
        return (
          <span key={item.key} title={item.label}
                aria-label={`Attached ${item.kind === 'drawing' ? 'drawing' : 'element'}: ${item.label}`}
                className="group relative grid size-8 place-items-center rounded-lg border border-line/80 bg-panel2/70">
            <span className="grid size-8 shrink-0 place-items-center overflow-hidden rounded-md bg-white ring-1 ring-line/70 dark:bg-black/10">
              {item.state === 'shooting'
                ? <Loader2 className="size-3 animate-spin text-accent" />
                : item.shot
                  ? <img src={item.shot} alt="" className="size-full object-cover object-top" />
                  : <Icon className="size-3 text-muted2" />}
            </span>
            <button onClick={() => onRemove(item.key)}
                    aria-label="Remove this from the message"
                    title="Remove this from the message"
                    className="absolute -right-1 -top-1 hidden size-3.5 place-items-center rounded-full border border-line bg-panel text-muted2 transition-colors hover:text-bad group-hover:grid focus:grid">
              <X className="size-2" />
            </button>
          </span>
        )
      })}
    </div>
  )
}

/** Stop, as in Claude: the send button's place while the agent works, one press (or Esc) and it stops - no
 * confirmation. The run ends at once on the server; the button spins until the studio sees it has. */
function useStopRun(busy) {
  const [stopping, setStopping] = useState(false)
  const addLog = useStore(s => s.addLog)

  useEffect(() => { if (!busy) setStopping(false) }, [busy])

  async function stop() {
    if (stopping) return
    setStopping(true)
    try {
      const current = useStore.getState()
      const result = await api.cancelBuild(current.project, current.agentRole)
      if (result?.status === 'stopping') {
        addLog('INFO', 'Stop requested — ending the current step now.')
      } else {
        setStopping(false)
        addLog('INFO', result?.detail || 'No active run to stop.')
      }
    } catch (e) {
      setStopping(false)
      addLog('WARN', `could not cancel — ${e.message}`)
    }
  }

  return { stop, stopping }
}

/** The tiny ring beside the model opens the detailed context meter without
 * taking a permanent footer row away from the conversation. */
function ContextUsage({ stats }) {
  const [open, setOpen] = useState(false)
  if (!stats) return null
  const focused = stats.context_scope === 'focused'
  const percent = Math.max(0, Math.min(100, Number(stats.percent) || 0))
  const spent = (Number(stats.sent) || 0) + (Number(stats.received) || 0)
  const remaining = Math.max(0, (Number(stats.limit) || 0) - (Number(stats.tokens) || 0))
  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen(value => !value)} aria-label={`Context usage ${Math.round(percent)}%`}
              aria-haspopup="dialog" aria-expanded={open} title={`Context usage: ${Math.round(percent)}%`}
              className="grid size-6 place-items-center rounded-full text-deep transition-colors hover:bg-panel2">
        <svg viewBox="0 0 20 20" className="size-4 -rotate-90" aria-hidden="true">
          <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeOpacity=".18" strokeWidth="2" />
          <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                  pathLength="100" strokeDasharray={`${Math.max(4, percent)} 100`} />
        </svg>
      </button>
      <Dropdown open={open} onClose={() => setOpen(false)} className="bottom-full right-0 mb-2 w-[344px] p-3 context-window-card">
        <div role="dialog" aria-label="Context-window usage">
          <div className="flex items-center justify-between gap-3 text-[12px]">
            <span className="context-window-title font-medium">{focused ? 'Largest model context so far' : 'Context window'}</span>
            <span className="context-window-value font-mono tabular-nums">
              {stats.limit ? `${compact(stats.tokens)} / ${compact(stats.limit)} (${Math.round(percent)}%)`
                : `${compact(stats.tokens)} tokens`}
            </span>
          </div>
          {stats.limit ? <>
            <div className="context-window-track mt-2 h-1 overflow-hidden rounded-full">
              <span className="context-window-progress block h-full rounded-full transition-[width] duration-500"
                    style={{ width: `${percent}%` }} />
            </div>
            <p className="mt-2 text-[11px] text-muted">{focused
              ? 'The biggest single request this project’s interview, SRS and wireframes have sent so far. Each of those steps rebuilds its context from the saved project files, so nothing is lost between them.'
              : `${compact(remaining)} remains before older detail is compacted automatically.`}</p>
          </> : <p className="mt-2 text-[11px] text-muted">The provider reported usage but not its context-window capacity.</p>}
          <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 border-t border-line pt-3 font-mono text-[10px] text-muted2">
            {stats.requests > 0 && <span>{stats.requests} requests</span>}
            {spent > 0 && <span>{compact(stats.sent)}↑ {compact(stats.received)}↓</span>}
            {stats.iterations > 0 && <span>{stats.iterations} steps</span>}
            {stats.tools > 0 && <span>{stats.tools} tools</span>}
            {stats.files > 0 && <span>{stats.files} files</span>}
          </div>
        </div>
      </Dropdown>
    </div>
  )
}

function compact(n) {
  const value = Number(n) || 0
  return value >= 1000 ? `${Math.round(value / 100) / 10}k` : String(value)
}

/**
 * A request-level status line. Time ticks locally, while the token total comes
 * only from the provider's completed-response accounting in the event stream.
 * That means a slow model never gets a fabricated "typing" token animation.
 */
function LiveTurnMeter({ stats, startedAt = 0, reasoning = false, state = '' }) {
  const [now, setNow] = useState(() => Date.now())
  const started = Number(stats?.turn_started_at) || Number(startedAt) || now
  useEffect(() => {
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [started])

  const elapsed = Math.max(0, Math.floor((now - started) / 1000))
  const generated = Math.max(0, Number(stats?.turn_tokens) || 0)
  const thinking = reasoning || state === 'thinking' || /plan|draft|revis/i.test(state)
  return (
    <div aria-live="polite" aria-label={`${thinking ? 'Thinking' : 'Working'} for ${elapsed} seconds; ${generated} generated tokens`}
         className="flex shrink-0 items-center gap-1.5 border-t border-line/60 bg-panel px-4 py-2 font-mono text-[10px] tabular-nums text-muted2">
      <Loader2 className="size-3 animate-spin text-accent" />
      <span className="font-sans font-medium text-muted">{thinking ? 'Thinking' : 'Working'}</span>
      <span aria-hidden="true">·</span>
      <span>{formatRunTime(elapsed)}</span>
      <span aria-hidden="true">·</span>
      <span title="Exact generated-token total reported by the model for this request.">
        {compact(generated)} {generated === 1 ? 'token' : 'tokens'}
      </span>
    </div>
  )
}

function formatRunTime(seconds) {
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`
}

/** The design the customiser chose, as the swatches it actually picked. */
function DesignCard({ design }) {
  const tokens = design?.tokens || {}
  const swatches = ['primary', 'accent', 'background', 'surface', 'text']
    .filter(role => tokens[role])
  return (
    <div className="mt-1.5 rounded-xl border border-line/70 bg-panel2/60 p-3">
      <p className="text-[12px] font-semibold text-ink">{design.palette}</p>
      <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{design.mood}</p>
      {swatches.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {swatches.map(role => (
            <span key={role} title={`${role} ${tokens[role]}`}
                  className="flex items-center gap-1.5 rounded-lg border border-line/70 bg-panel px-1.5 py-1">
              <span className="size-3 rounded-[4px] ring-1 ring-black/[.08]"
                    style={{ background: tokens[role] }} />
              <span className="font-mono text-[9.5px] text-muted2">{tokens[role]}</span>
            </span>
          ))}
        </div>
      )}
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[10.5px] text-muted">
        <Row label="Theme" value={design.theme} />
        <Row label="Type" value={design.font} />
        <Row label="Corners" value={design.radius} />
        <Row label="Spacing" value={design.density} />
      </dl>
      <p className="mt-2 font-mono text-[9.5px] text-muted2">{design.path}</p>
    </div>
  )
}

const Row = ({ label, value }) => (
  <div className="flex gap-1.5">
    <dt className="text-muted2">{label}</dt>
    <dd className="truncate text-ink">{value}</dd>
  </div>
)

/** Animated indicator showing when the agent is reasoning or working between tool calls. */
function Thinking({ reasoning = false, state = '', detail = '' }) {
  const labels = {
    compacting: 'Compacting earlier work into memory',
    thinking: 'Thinking',
    planning: 'Reviewing requirements and choosing what to inspect',
    'drafting the plan': 'Drafting the product scope',
    'revising the plan': 'Revising the product scope',
    building: 'Writing the next files',
    read_file: 'Reading a project file',
    list_files: 'Reviewing the project structure',
    search_text: 'Searching the project context',
    web_search: 'Researching supporting context',
    web_fetch: 'Reading a supporting source',
    write_file: 'Writing the next file',
    replace_text: 'Editing a file',
    run_command: 'Running a command',
    browser_inspect: 'Checking the page in a browser',
  }
  const label = labels[state] || (reasoning ? 'Analysing project context' : 'Working')
  // A model writing a whole page sends nothing until the page is done. A clock
  // that keeps counting is what tells a long write apart from a stuck one.
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    setSeconds(0)
    const timer = setInterval(() => setSeconds(value => value + 1), 1000)
    return () => clearInterval(timer)
  }, [state])
  // Compacting says how far along it is: `12/35` parts summarized, then `merging 35`.
  const part = state === 'compacting' ? String(detail).match(/^(\d+)\/(\d+)$/) : null
  const merging = state === 'compacting' && /^merging/.test(String(detail))
  const done = part ? Number(part[1]) : 0
  const total = part ? Number(part[2]) : 0
  const step = part ? ` · ${done} of ${total} parts done` : merging ? ' · merging the parts' : ''
  return (
    <div className="py-1 text-muted">
      <div className="flex items-center gap-2">
        <Loader2 className="size-3 shrink-0 animate-spin" />
        <span className="text-[12px]">
          {label}{step}{seconds >= 3 ? ` · ${seconds}s` : ''}
        </span>
        <span className="flex gap-1" aria-hidden="true">
          {[0, 1, 2].map(i => (
            <span key={i}
                  className="size-1 animate-bounce rounded-full bg-accent"
                  style={{ animationDelay: `${i * 140}ms`, animationDuration: '900ms' }} />
          ))}
        </span>
      </div>
      {(part || merging) && (
        <div className="ml-5 mt-1.5 flex max-w-[320px] items-center gap-2" title="The conversation grew past the model's window: older work is being summarized so the run can carry on">
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-black/[.07]">
            <span className="block h-full rounded-full bg-accent transition-[width] duration-500"
                  style={{ width: `${merging ? 100 : total ? Math.round((done / total) * 100) : 0}%` }} />
          </span>
          <span className="font-mono text-[10.5px] text-muted2">{merging ? 'merging' : `${done}/${total}`}</span>
        </div>
      )}
    </div>
  )
}

/** Modal picker to configure and toggle third-party plugins for the current project. */
function PluginPicker({ project }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)} title="Plugins this app uses"
              className="grid size-8 shrink-0 place-items-center rounded-xl text-muted transition-colors hover:bg-accent hover:text-ink">
        <Plug className="size-3.5" />
      </button>
      {open && (
        <Modal onClose={() => setOpen(false)} className="max-w-[620px]">
          <header className="mb-4 flex items-center gap-2.5">
            <span className="grid size-8 place-items-center rounded-xl bg-accent text-ink">
              <Plug className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-[14px] font-bold tracking-tight text-ink">Plugins</h2>
              <p className="mt-0.5 text-[11px] text-muted">
                Set providers up once, then select every plugin this app needs.
              </p>
            </div>
          </header>
          <div className="max-h-[62vh] overflow-y-auto pr-1">
            <PluginAccounts project={project} />
          </div>
        </Modal>
      )}
    </>
  )
}

/** In-stream interactive question prompt allowing the user to select or customize an option. */
function Asked({ ask, onPick }) {
  const options = ask.options || []
  const asksValue = Boolean(ask.variable)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState('')

  // A value is tried and saved on the server; a value that is not accepted says why and the question stays.
  async function give() {
    if (!value.trim() || busy) return
    setBusy(true)
    setProblem('')
    try {
      const result = await answerValue(value)
      if (result.ok) setValue('')
      else setProblem(result.detail || 'That value was not accepted.')
    } catch (e) {
      setProblem(e.message || 'Could not send that.')
    }
    setBusy(false)
  }

  return (
    <div className="flex gap-2.5 my-1">
      <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-accent text-ink">
        <MessageCircleQuestion className="size-3" />
      </span>
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm border border-line bg-white px-3.5 py-3 shadow-sm">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-[.12em] text-muted2">
          Waiting for you
        </p>
        <p className="whitespace-pre-wrap break-words text-[13px] font-medium leading-relaxed text-ink">
          {ask.question}
        </p>
        {ask.why && (
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">{ask.why}</p>
        )}
        {options.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {options.map(option => (
              <button key={option.id} onClick={() => (asksValue ? answerOption(option.label) : onPick(option.label))}
                      title={option.hint || (asksValue ? 'Answer with this instead of a value' : 'Put this in the box below')}
                      className="rounded-xl border border-line2 bg-panel px-2.5 py-1.5 text-left
                                 text-[11.5px] font-semibold text-ink transition-colors
                                 hover:border-accent hover:text-accent">
                {option.label}
              </button>
            ))}
          </div>
        )}
        {asksValue && (
          <form className="mt-3 space-y-1.5" onSubmit={e => { e.preventDefault(); give() }}>
            <label className="block text-[10px] font-semibold uppercase tracking-[.12em] text-muted2">
              {ask.variable}
              <span className="ml-1.5 font-normal normal-case tracking-normal">kept on this computer, never shown in the chat or sent to the model</span>
            </label>
            <div className="flex items-center gap-2">
              <input type={ask.secret === false ? 'text' : 'password'} value={value} autoComplete="off" spellCheck={false}
                     onChange={e => setValue(e.target.value)} disabled={busy}
                     placeholder={ask.check === 'mongodb' ? 'mongodb+srv://…  (it is tried before it is accepted)' : 'Type it here'}
                     className="h-9 min-w-0 flex-1 rounded-xl border border-line bg-panel px-3 text-[12.5px] text-ink outline-none placeholder:text-muted2 focus:border-accent/60" />
              <button type="submit" disabled={!value.trim() || busy}
                      className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl bg-accent px-3.5 text-[12px] font-semibold text-ink transition-colors hover:bg-press disabled:opacity-40">
                {busy && <Loader2 className="size-3 animate-spin" />}{busy && ask.check ? 'Trying…' : 'Save'}
              </button>
            </div>
            {problem && <p className="text-[11.5px] leading-relaxed text-bad">{problem}</p>}
          </form>
        )}
        <div className="mt-2.5 flex items-center gap-2 border-t border-accent/15 pt-2">
          <span className="min-w-0 flex-1 truncate text-[10.5px] leading-relaxed text-muted2">
            {ask.assumption ? `No answer: it will ${ask.assumption}`
                            : 'No answer: it decides and says what it assumed.'}
          </span>
          <button onClick={declineAsk} title="Let the agent decide this one"
                  className="inline-flex shrink-0 items-center gap-1 text-[10.5px] font-semibold
                             text-muted transition-colors hover:text-ink">
            <SkipForward className="size-3" /> You decide
          </button>
        </div>
      </div>
    </div>
  )
}

/** Something said while the agent was busy, waiting its turn. */
function Queued({ item, onDrop }) {
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="max-w-[88%] rounded-2xl rounded-br-md border border-dashed border-accent/45 bg-accent px-3 py-2 text-[12.5px] leading-relaxed text-ink">
        {item.shown}
      </div>
      <span className="flex items-center gap-2 pr-1 text-[10px] text-muted2">
        <Clock className="size-2.5" /> waiting for the current run
        <button onClick={onDrop} className="text-muted2 underline-offset-2 hover:text-ink hover:underline">
          don’t send
        </button>
      </span>
    </div>
  )
}

function parseFileInfo(title) {
  const clean = String(title || '').replace(/^(written|created|patched|edited|writing|editing|removed|reading|read)\s+/i, '').trim()
  const pathOnly = clean.replace(/\s*\(\d+\s*lines\)/i, '').trim()
  const parts = pathOnly.split('/')
  const fileName = parts[parts.length - 1] || pathOnly
  return { fileName, filePath: pathOnly }
}

function FileActionCard({ turn, live }) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const [fetchedContent, setFetchedContent] = useState(null)
  const [fetching, setFetching] = useState(false)

  const { fileName, filePath } = parseFileInfo(turn.file || turn.title)
  const files = useStore(s => s.files)
  const fileHistory = useStore(s => s.fileHistory || {})
  const readFiles = useStore(s => s.readFiles || {})
  const project = useStore(s => s.project)
  const agentRole = useStore(s => s.agentRole)

  const isPatch = turn.action === 'patched' || turn.action === 'edited' || turn.action === 'editing' || /patched|edited|editing/i.test(turn.title || '')
  const isRead = turn.kind === 'read'

  // History & contents
  const history = fileHistory[filePath] || fileHistory[fileName] || {}
  const oldText = history.oldContent || ''
  const currentText = files[filePath] || files[fileName] || history.newContent || fetchedContent || ''
  const readContent = readFiles[filePath] || readFiles[fileName] || currentText || ''

  const diff = useMemo(() => {
    if (!isPatch) return null
    return computeLineDiff(oldText, currentText)
  }, [isPatch, oldText, currentText])

  // Lazy fetch if expanded and not in memory
  useEffect(() => {
    if (expanded && !currentText && !readContent && !fetching && project) {
      setFetching(true)
      api.files(project, agentRole)
        .then(res => {
          if (res?.files?.[filePath]) setFetchedContent(res.files[filePath])
        })
        .catch(() => {})
        .finally(() => setFetching(false))
    }
  }, [expanded, currentText, readContent, fetching, project, agentRole, filePath])

  const copyCode = (e) => {
    e.stopPropagation()
    const textToCopy = isRead ? readContent : currentText
    if (!textToCopy) return
    navigator.clipboard.writeText(textToCopy).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const openInEditor = (e) => {
    e.stopPropagation()
    useStore.getState().setView('code')
    if (filePath) useStore.getState().setActiveFile(filePath)
  }

  const badgeText = isRead
    ? 'read'
    : isPatch
      ? (diff && (diff.additions > 0 || diff.deletions > 0) ? `+${diff.additions} -${diff.deletions}` : (turn.inProgress ? 'editing' : 'patched'))
      : (turn.inProgress ? (turn.action || 'writing') : (turn.action || 'created'))

  const badgeStyle = isRead
    ? 'bg-transparent text-warn border-warn/30'
    : isPatch
      ? 'bg-transparent text-info border-info/30'
      : 'bg-transparent text-deep border-accent/30'

  return (
    <div className="my-2 overflow-hidden rounded-xl border border-line bg-panel shadow-sm transition-all hover:border-line2">
      <div onClick={() => setExpanded(prev => !prev)}
           title={expanded ? 'Click to collapse' : 'Click to inspect code'}
           className="flex items-center justify-between gap-3 px-3 py-2 cursor-pointer select-none hover:bg-panel2/50 transition-colors">
        <div className="flex items-center gap-2 min-w-0">
          <FileCode2 className="size-3.5 shrink-0 text-muted2" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="truncate font-mono font-medium text-ink text-[11.5px]">{filePath || fileName}</p>
              <span className={cn('rounded px-1 py-px text-[9px] font-mono border', badgeStyle)}>
                {badgeText}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {live || turn.inProgress ? (
            <Loader2 className="size-4 animate-spin text-accent" />
          ) : (
            <Check className="size-3.5 text-ok" />
          )}
          <ChevronRight className={cn('size-4 text-muted2 transition-transform duration-200', expanded && 'rotate-90 text-ink')} />
        </div>
      </div>

      {expanded && (
        <div className="border-t border-line/60 bg-panel p-3 text-ink">
          <div className="flex items-center justify-between gap-2 pb-2 mb-2 border-b border-black/10 text-xs">
            <span className="font-mono text-[11px] text-muted truncate max-w-[220px]" title={filePath}>
              {filePath}
            </span>
            <div className="flex items-center gap-1.5 shrink-0">
              <button onClick={copyCode}
                      title="Copy code"
                      className="flex items-center gap-1 rounded-md border border-black/10 bg-black/5 px-2 py-1 text-[11px] font-medium text-ink hover:bg-black/10 hover:text-ink transition-colors">
                {copied ? <Check className="size-3 text-ink" /> : <Copy className="size-3" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
              <button onClick={openInEditor}
                      title="Open in editor"
                      className="flex items-center gap-1 rounded-md border border-black/10 bg-black/5 px-2 py-1 text-[11px] font-medium text-ink hover:bg-black/10 hover:text-ink transition-colors">
                <ExternalLink className="size-3" /> Editor
              </button>
            </div>
          </div>

          <div className="max-h-[320px] overflow-auto rounded-lg border border-black/10 bg-panel p-2 font-mono text-[11px] leading-relaxed select-text">
            {fetching ? (
              <div className="py-6 flex items-center justify-center gap-2 text-muted text-xs">
                <Loader2 className="size-3.5 animate-spin text-accent" /> Loading file content…
              </div>
            ) : isPatch && diff ? (
              <div className="space-y-0.5">
                {diff.lines.map((line, idx) => (
                  <div key={idx}
                       className={cn('flex items-start px-2 py-0.5 rounded-[3px]',
                         line.type === 'del' && 'bg-rose-500/15 text-rose-700 border-l-2 border-rose-500 font-medium',
                         line.type === 'add' && 'bg-emerald-500/15 text-ink border-l-2 border-emerald-500 font-medium',
                         line.type === 'same' && 'text-muted hover:bg-black/[0.03]')}>
                    <span className="w-8 shrink-0 select-none text-right pr-2 opacity-40 tabular-nums">
                      {line.type === 'del' ? line.oldNo : line.type === 'add' ? line.newNo : line.newNo || line.oldNo}
                    </span>
                    <span className="w-4 shrink-0 select-none text-center font-bold">
                      {line.type === 'del' ? '-' : line.type === 'add' ? '+' : ' '}
                    </span>
                    <span className="flex-1 whitespace-pre-wrap break-all">{line.text || ' '}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-0.5">
                {((isRead ? readContent : currentText) || '// File content empty or loaded from environment').split(/\r?\n/).map((line, idx) => (
                  <div key={idx} className="flex items-start px-2 py-0.5 text-ink hover:bg-black/[0.03] rounded-[3px]">
                    <span className="w-8 shrink-0 select-none text-right pr-2 opacity-40 tabular-nums">
                      {idx + 1}
                    </span>
                    <span className="flex-1 whitespace-pre-wrap break-all">{line || ' '}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/** Memoized conversation turn row rendering messages, tool events, and plans. */
const Turn = memo(function Turn({ turn, live }) {
  if (turn.role === 'stage') {
    const active = turn.status === 'active'
    const passed = turn.status === 'done'
    const Icon = active ? Loader2 : passed ? CheckCircle2 : CircleAlert
    return (
      <div className={cn('my-2 rounded-xl border px-3.5 py-3 shadow-sm',
        active ? 'border-accent/35 bg-accent' : passed
          ? 'border-ok/30 bg-ok-tint/60' : 'border-warn/35 bg-warn-tint/50')}>
        <div className="flex items-start gap-2.5">
          <span className={cn('mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg',
            active ? 'bg-accent text-ink' : passed ? 'bg-ok/15 text-ok' : 'bg-warn/15 text-warn')}>
            <Icon className={cn('size-4', active && 'animate-spin')} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center justify-between gap-1.5">
              <p className="text-[12.5px] font-semibold text-ink">{turn.title}</p>
              <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                active ? 'bg-accent text-ink' : passed ? 'bg-ok/15 text-ok' : 'bg-warn/15 text-warn')}>
                {active ? 'Running' : passed ? 'Completed' : 'Needs attention'}
              </span>
            </div>
            <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
              {turn.detail || (active ? 'Checking this stage now…' : passed
                ? 'Stage finished; moving to the next check.' : 'See the test evidence for details.')}
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (turn.role === 'change') return <ChangePlan turn={turn} />

  if (turn.role === 'test_result') {
    const passed = ['pass', 'passed'].includes(turn.status)
    const Icon = passed ? CircleCheck : CircleAlert
    return (
      <div className="my-1 flex items-start gap-2.5 rounded-lg border border-line/70 bg-panel2/50 px-3 py-2">
        <Icon className={cn('mt-0.5 size-3.5 shrink-0', passed ? 'text-ok' : 'text-warn')} />
        <div className="min-w-0 flex-1">
          <p className="text-[11.5px] font-medium text-ink">{turn.title}</p>
          {turn.detail && <p className="mt-0.5 text-[11px] text-muted">{turn.detail}</p>}
        </div>
        <span className={cn('text-[10px] font-semibold uppercase', passed ? 'text-ok' : 'text-warn')}>
          {passed ? 'Pass' : turn.status || 'Check'}
        </span>
      </div>
    )
  }

  if (turn.role === 'user') {
    return (
      <div className="my-2 flex flex-col items-start gap-1.5">
        {(turn.shots || []).length > 0 && (
          <div className="flex w-full flex-wrap gap-1.5">
            {turn.shots.map((shot, i) => (
              <img key={i} src={shot} alt="What they pointed at"
                   className="max-h-[104px] rounded-xl border border-line/70 object-cover object-top shadow-sm" />
            ))}
          </div>
        )}
        <p className="w-full rounded-xl border border-line bg-panel px-3 py-2 text-[12.5px] leading-relaxed text-ink">
          {turn.text}
        </p>
      </div>
    )
  }

  if (turn.role === 'assistant') {
    if (turn.kind === 'attachment') return (
      <div className="my-1 ml-8 flex min-w-0 items-center gap-2 rounded-lg border border-line/70 bg-panel2/50 px-2.5 py-1.5 text-[11px]">
        <Paperclip className="size-3 shrink-0 text-accent" />
        <span className="min-w-0 truncate font-semibold text-ink">{turn.title}</span>
        <span className="min-w-0 truncate font-mono text-muted2" title={turn.text}>{turn.text}</span>
      </div>
    )
    if (['command', 'command_output'].includes(turn.kind)) return <CommandTurn turn={turn} live={live} />
    return (
      <div className="my-3 min-w-0 pl-1">
        <div className="min-w-0 flex-1">
          {turn.title && !/^agent update$/i.test(cleanChatProse(turn.title).trim()) && (
            <p className="text-[12.5px] font-semibold text-ink">{cleanChatProse(turn.title)}</p>
          )}
          {turn.kind === 'design' && turn.design
            ? <DesignCard design={turn.design} />
            : turn.kind === 'plan'
              ? (
                <div className="mt-1 rounded-xl border border-line bg-panel2/60 p-3">
                  <div className="flex items-center gap-2 text-accent font-semibold text-[12px] mb-2">
                    <ListChecks className="size-3.5" /> Plan
                  </div>
                  <pre className="max-h-[280px] overflow-auto whitespace-pre-wrap font-sans font-body text-[12px] leading-relaxed text-ink">{turn.text}</pre>
                </div>
              )
              : <ReadableAgentText text={turn.text} />}
        </div>
      </div>
    )
  }

  // Bolt File Action Card (Image 1)
  // Interactive File Action Card for write, patch and read (Image 1)
  if (turn.file && (turn.kind === 'write' || turn.kind === 'read')) {
    return <FileActionCard turn={turn} live={live} />
  }

  const Icon = ICONS[turn.kind] || Sparkles
  return (
    <div className="my-1.5 flex gap-2 pl-1 text-muted">
      <span className={cn('mt-0.5 grid size-4 shrink-0 place-items-center',
        turn.kind === 'warn' && 'text-bad')}>
        {/* The step actually happening spins; the ones behind it do not. */}
        {live ? <Loader2 className="size-3 animate-spin" /> : <Icon className="size-3" />}
      </span>
      <div className="min-w-0 flex-1">
        <p className={cn('break-words text-[11.5px]',
          turn.kind === 'warn' ? 'text-bad' : 'text-muted')}>
          {turn.kind === 'effort' && turn.level && (
            <span className={cn('mr-1.5 rounded-full px-1.5 py-px align-middle font-mono text-[9.5px] font-bold uppercase tracking-wide',
              EFFORT_TONE[turn.level] || EFFORT_TONE.low)}>
              {turn.level}
            </span>
          )}
          {turn.title}
        </p>
        {turn.detail && (
          <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{turn.detail}</p>
        )}
      </div>
    </div>
  )
})

/** Terminal output remains available without overwhelming a long chat. */
function CommandTurn({ turn, live }) {
  const [expanded, setExpanded] = useState(false)
  const output = String(turn.text || '')
  const lines = output ? output.split(/\r?\n/).filter(Boolean).length : 0
  const isOutput = turn.kind === 'command_output'
  return (
    <div className="my-2 min-w-0 pl-1">
      <button type="button" onClick={() => setExpanded(value => !value)} aria-expanded={expanded}
              className="flex w-full items-center gap-2 rounded-xl border border-line bg-panel2/50 px-3 py-2 text-left transition-colors hover:bg-raised">
        <Terminal className={cn('size-3.5 shrink-0', live ? 'text-deep' : 'text-muted2')} />
        <span className="min-w-0 flex-1 truncate text-[11.5px] font-semibold text-ink">
          {turn.title || (isOutput ? 'Command output' : 'Command')}
        </span>
        <span className="shrink-0 text-[10px] text-muted2">{lines ? `${lines} lines` : 'empty'}</span>
        <ChevronRight className={cn('size-3.5 shrink-0 text-muted2 transition-transform', expanded && 'rotate-90')} />
      </button>
      {expanded && (
        <pre className="mt-1 max-h-[280px] overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-panel2/70 p-3 font-mono text-[10.5px] leading-relaxed text-ink">
          {output || '(No output was recorded.)'}
        </pre>
      )}
    </div>
  )
}

/** Readable natural-language stream; raw commands and outputs bypass this component. */
function ReadableAgentText({ text }) {
  const blocks = chatDisplayBlocks(text)
  return (
    <div className="space-y-2 text-[13px] font-normal leading-relaxed text-ink/90">
      {blocks.map((block, index) => block.kind === 'code' ? (
        <pre key={index}
             className="max-h-[280px] overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-panel2/70 p-3 font-mono text-[10.5px] leading-relaxed text-ink">
          {block.text}
        </pre>
      ) : block.kind === 'list' ? (
        <ul key={index} className="space-y-1 pl-4">
          {block.items.map((item, itemIndex) => (
            <li key={itemIndex} className="relative pl-2 before:absolute before:-left-2 before:text-accent before:content-['•']">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p key={index} className="whitespace-pre-wrap break-words">{block.text}</p>
      ))}
    </div>
  )
}
