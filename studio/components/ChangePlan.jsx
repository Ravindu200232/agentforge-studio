'use client'

/**
 * The plan for a request typed in the chat, as a card in the conversation.
 *
 * It says what will change and in which stage, in what order and in which files, and what was
 * assumed. Until it is approved nothing has been touched: approve it, or say what to change
 * (here, or just type in the box below) and it is planned again. Every word on it comes from the
 * plan the model wrote; the card only lays it out.
 */

import { useState } from 'react'
import {
  Ban, Check, CheckCircle2, ChevronDown, CircleAlert, ListChecks, Loader2, MessageSquarePlus,
  Play, RotateCcw, Send, ShieldQuestion, X,
} from 'lucide-react'

import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { cn } from '@/lib/utils'

const STATUS = {
  proposed: { label: 'Needs your approval', tone: 'text-ink bg-accent' },
  approved: { label: 'Approved', tone: 'text-ink bg-accent' },
  running: { label: 'Being carried out', tone: 'text-ink bg-accent' },
  asking: { label: 'Waiting for your answer', tone: 'text-ink bg-accent' },
  done: { label: 'Done', tone: 'text-ok bg-ok-tint' },
  failed: { label: 'Not finished', tone: 'text-bad bg-bad/12' },
  cancelled: { label: 'Cancelled', tone: 'text-muted bg-black/[.05] dark:bg-black/[.07]' },
  superseded: { label: 'Replaced by a newer plan', tone: 'text-muted bg-black/[.05] dark:bg-black/[.07]' },
}

export default function ChangePlan({ turn }) {
  const project = useStore(s => s.project)
  const plan = turn.plan || {}
  const status = STATUS[turn.status] ? turn.status : 'proposed'
  const waiting = status === 'proposed'
  const live = status === 'approved' || status === 'running'
  const deploying = turn.flow === 'deploy'
  const [revising, setRevising] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [sending, setSending] = useState('')
  const [error, setError] = useState('')
  const [open, setOpen] = useState(waiting)
  const [why, setWhy] = useState(-1)          // which stage's reason is showing
  const [opened, setOpened] = useState(() => new Set())   // which steps show their detail
  const [excluded, setExcluded] = useState(() => new Set())   // affected stages unticked for this run

  const impact = Array.isArray(plan.impact) ? plan.impact : []
  const steps = Array.isArray(plan.steps) ? plan.steps : []
  const notes = [['What it needs', plan.requirements], ['Assumptions', plan.assumptions], ['Risks', plan.risks],
    ['How it will be checked', plan.verification], ['If it goes wrong', plan.rollback], ['Cost', plan.cost],
    ['Guides it followed', plan.skills]]
    .filter(([, rows]) => Array.isArray(rows) && rows.length)

  async function decide(decision, extra = {}) {
    setSending(decision)
    setError('')
    try {
      const state = useStore.getState()
      const result = await api.changeDecide(project, turn.changeId, {
        decision, model: state.models.builder || state.models.agent, ...extra,
      })
      if (result && result.ok === false) setError(result.detail || 'That plan is no longer waiting.')
      else { setRevising(false); setFeedback('') }
    } catch (e) {
      setError(e.message || 'Could not send that.')
    } finally {
      setSending('')
    }
  }

  const toggleStep = i => setOpened(current => {
    const next = new Set(current)
    if (next.has(i)) next.delete(i); else next.add(i)
    return next
  })
  const allOpen = steps.length > 0 && opened.size === steps.length
  const toggleExcluded = stage => setExcluded(current => {
    const next = new Set(current)
    if (next.has(stage)) next.delete(stage); else next.add(stage)
    return next
  })

  const Icon = live ? Loader2 : status === 'done' ? CheckCircle2 : status === 'failed' ? CircleAlert
    : status === 'cancelled' || status === 'superseded' ? Ban : ListChecks

  return (
    <div className={cn('my-1 rounded-2xl border bg-panel shadow-sm',
      waiting ? 'border-accent/40' : 'border-line')}>
      <button type="button" onClick={() => setOpen(v => !v)} aria-expanded={open}
              className="flex w-full items-start gap-2.5 px-3.5 py-3 text-left">
        <span className={cn('mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg',
          waiting || live ? 'bg-accent text-ink' : status === 'done' ? 'bg-ok-tint text-ok'
            : status === 'failed' ? 'bg-bad/12 text-bad' : 'bg-black/[.05] text-muted dark:bg-black/[.07]')}>
          <Icon className={cn('size-3.5', live && 'animate-spin')} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-[.14em] text-muted2">{deploying ? 'Deployment plan' : 'Plan'}</span>
            {turn.revision > 1 && (
              <span className="rounded-full bg-black/[.05] px-1.5 py-px font-mono text-[9.5px] font-semibold text-muted dark:bg-black/[.07]">v{turn.revision}</span>
            )}
            <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', STATUS[status].tone)}>
              {STATUS[status].label}
            </span>
            {turn.version && (
              <span role="link" tabIndex={0} title="Open the versions list"
                    onClick={e => { e.stopPropagation(); useStore.getState().setView('versions') }}
                    onKeyDown={e => { if (e.key === 'Enter') { e.stopPropagation(); useStore.getState().setView('versions') } }}
                    className="cursor-pointer rounded-full bg-accent px-2 py-0.5 font-mono text-[10px] font-bold text-ink hover:bg-accent">
                Saved as v{turn.version}
              </span>
            )}
          </span>
          <span className="mt-1 block text-[13.5px] font-semibold leading-snug text-ink">{plan.title}</span>
          {plan.summary && <span className="mt-0.5 block text-[12px] leading-relaxed text-muted">{plan.summary}</span>}
        </span>
        <ChevronDown className={cn('mt-1 size-3.5 shrink-0 text-muted2 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="space-y-3.5 border-t border-line/70 px-3.5 py-3">
          {impact.length > 0 && (
            <section>
              <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-[.14em] text-muted2">What it touches</h4>
              <div className="flex flex-wrap gap-1.5">
                {impact.map((row, i) => {
                  // Deploy plans reuse this same card but `_execute_flow` does not
                  // consult `excluded_stages` — only the chat-typed change path does.
                  const excludable = row.affected && waiting && !deploying
                  const isExcluded = row.affected && excluded.has(row.stage)
                  return (
                    <span key={i}
                          className={cn('inline-flex items-center gap-1 rounded-full border pl-1 pr-2.5 py-1 text-[11px] font-semibold transition-colors',
                            isExcluded ? 'border-line bg-black/[.03] text-muted2 line-through decoration-muted2/70'
                              : row.affected ? 'border-accent/40 bg-accent text-ink'
                                : 'border-line bg-black/[.03] text-muted2',
                            why === i && 'ring-1 ring-accent/50')}>
                      {excludable && (
                        <button type="button" onClick={() => toggleExcluded(row.stage)}
                                title={isExcluded ? 'Include this stage in this run' : 'Exclude this stage from this run'}
                                className={cn('grid size-3.5 shrink-0 place-items-center rounded-full border transition-colors',
                                  isExcluded ? 'border-muted2/50' : 'border-ink/40 bg-ink/10')}>
                          {!isExcluded && <Check className="size-2.5" />}
                        </button>
                      )}
                      <button type="button" onClick={() => setWhy(why === i ? -1 : i)} aria-pressed={why === i}
                              title={row.why || ''} className="inline-flex items-center gap-1">
                        {!row.affected && <X className="size-2.5" />}
                        {row.stage}
                      </button>
                    </span>
                  )
                })}
              </div>
              {excluded.size > 0 && (
                <p className="mt-1.5 text-[10.5px] leading-relaxed text-muted2">
                  Excluded from this run: {Array.from(excluded).join(', ')} — their steps will not be carried out.
                </p>
              )}
              {why >= 0 && impact[why] && (
                <p className="mt-2 rounded-xl bg-black/[.03] px-3 py-2 text-[11.5px] leading-relaxed text-muted dark:bg-black/[.04]">
                  <span className="font-semibold text-ink">{impact[why].stage}: </span>
                  {impact[why].why || (impact[why].affected ? 'Changes' : 'Left as it is')}
                </p>
              )}
            </section>
          )}

          {steps.length > 0 && (
            <section>
              <div className="mb-1.5 flex items-center justify-between">
                <h4 className="text-[10px] font-semibold uppercase tracking-[.14em] text-muted2">Steps, in order</h4>
                <button type="button" onClick={() => setOpened(allOpen ? new Set() : new Set(steps.map((_, i) => i)))}
                        className="text-[10.5px] font-semibold text-muted transition-colors hover:text-accent">
                  {allOpen ? 'Hide details' : 'Show details'}
                </button>
              </div>
              <ol className="space-y-1">
                {steps.map((step, i) => {
                  const shown = opened.has(i)
                  const commands = Array.isArray(step.commands) ? step.commands : []
                  const hasMore = Boolean(step.detail) || commands.length > 0 || (Array.isArray(step.files) && step.files.length > 0)
                  const stepExcluded = excluded.has(step.stage)
                  return (
                    <li key={i} className={cn('rounded-xl border border-transparent transition-colors hover:border-line/70',
                      stepExcluded && 'opacity-50')}>
                      <button type="button" disabled={!hasMore} onClick={() => toggleStep(i)} aria-expanded={shown}
                              className="flex w-full items-start gap-2.5 rounded-xl px-1.5 py-1.5 text-left">
                        <span className="mt-px grid size-5 shrink-0 place-items-center rounded-full bg-accent font-mono text-[10px] font-bold text-ink">{i + 1}</span>
                        <span className="min-w-0 flex-1">
                          <span className={cn('block text-[12.5px] font-medium leading-snug text-ink', stepExcluded && 'line-through')}>{step.title}</span>
                          <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10.5px] text-muted2">
                            {step.stage && <span className="font-semibold">{step.stage}</span>}
                            {stepExcluded && <span className="font-semibold text-muted2">excluded from this run</span>}
                            {Array.isArray(step.files) && step.files.length > 0 && (
                              <span>{step.files.length} file{step.files.length === 1 ? '' : 's'}</span>
                            )}
                          </span>
                        </span>
                        {hasMore && <ChevronDown className={cn('mt-1 size-3 shrink-0 text-muted2 transition-transform', shown && 'rotate-180')} />}
                      </button>
                      {shown && (
                        <div className="ml-[34px] space-y-1.5 pb-2 pr-1.5">
                          {step.detail && <p className="text-[11.5px] leading-relaxed text-muted">{step.detail}</p>}
                          {commands.length > 0 && (
                            <span className="flex flex-col gap-1">
                              {commands.map(command => (
                                <code key={command} title={command}
                                      className="block max-w-full overflow-x-auto whitespace-pre rounded-md bg-black/[.06] px-2 py-1 font-mono text-[10px] text-ink dark:bg-black/[.08]">{command}</code>
                              ))}
                            </span>
                          )}
                          {Array.isArray(step.files) && step.files.length > 0 && (
                            <span className="flex flex-wrap gap-1">
                              {step.files.map(file => (
                                <code key={file} title={file}
                                      className="max-w-full truncate rounded-md bg-black/[.05] px-1.5 py-0.5 font-mono text-[10px] text-muted dark:bg-black/[.07]">{file}</code>
                              ))}
                            </span>
                          )}
                        </div>
                      )}
                    </li>
                  )
                })}
              </ol>
            </section>
          )}

          {notes.map(([heading, rows]) => (
            <details key={heading} className="group rounded-xl border border-line/70 px-3 py-2">
              <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[11.5px] font-semibold text-ink">
                <ChevronDown className="size-3 -rotate-90 text-muted2 transition-transform group-open:rotate-0" />
                {heading === 'Assumptions' && <ShieldQuestion className="size-3 text-muted2" />}
                {heading}
                <span className="rounded-full bg-black/[.05] px-1.5 py-px font-mono text-[9.5px] text-muted dark:bg-black/[.07]">{rows.length}</span>
              </summary>
              <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[11.5px] leading-relaxed text-muted marker:text-muted2">
                {rows.map((row, i) => <li key={i}>{row}</li>)}
              </ul>
            </details>
          ))}

          {turn.summary && status === 'done' && (
            <p className="whitespace-pre-wrap rounded-xl bg-ok-tint px-3 py-2 text-[11.5px] leading-relaxed text-ink">{turn.summary}</p>
          )}
          {turn.error && status === 'failed' && (
            <p className="whitespace-pre-wrap rounded-xl bg-bad/10 px-3 py-2 text-[11.5px] leading-relaxed text-bad">{turn.error}</p>
          )}
        </div>
      )}

      {waiting && (
        <div className="border-t border-line/70 px-3.5 py-3">
          {revising ? (
            <div>
              <textarea autoFocus value={feedback} rows={3} placeholder="What should be different about this plan?"
                        onChange={e => setFeedback(e.target.value)}
                        className="w-full resize-none rounded-xl border border-line bg-panel2/70 px-3 py-2 text-[12.5px] leading-relaxed text-ink outline-none placeholder:text-muted2 focus:border-accent/50" />
              <div className="mt-2 flex items-center gap-2">
                <button type="button" disabled={!feedback.trim() || Boolean(sending)}
                        onClick={() => decide('revise', { feedback: feedback.trim() })}
                        className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-accent px-3 text-[12px] font-semibold text-ink transition-colors hover:bg-press disabled:opacity-40">
                  {sending === 'revise' ? <Loader2 className="size-3 animate-spin" /> : <Send className="size-3" />} Plan again
                </button>
                <button type="button" onClick={() => { setRevising(false); setFeedback('') }}
                        className="h-8 rounded-xl px-2.5 text-[12px] font-semibold text-muted transition-colors hover:text-ink">Back</button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" disabled={Boolean(sending)}
                      onClick={() => decide('approve', { excluded_stages: Array.from(excluded) })}
                      className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-accent px-3.5 text-[12px] font-semibold text-ink shadow-sm transition-colors hover:bg-press disabled:opacity-50">
                {sending === 'approve' ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />} {deploying ? 'Approve and deploy' : 'Approve and carry it out'}
              </button>
              <button type="button" disabled={Boolean(sending)} onClick={() => setRevising(true)}
                      className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-line2 px-3 text-[12px] font-semibold text-ink transition-colors hover:border-accent hover:text-accent disabled:opacity-50">
                <RotateCcw className="size-3" /> Revise
              </button>
              <button type="button" disabled={Boolean(sending)} onClick={() => decide('cancel')}
                      className="ml-auto inline-flex h-8 items-center gap-1 rounded-xl px-2.5 text-[12px] font-semibold text-muted transition-colors hover:text-bad disabled:opacity-50">
                <Ban className="size-3" /> Cancel
              </button>
            </div>
          )}
          <p className="mt-2 flex items-center gap-1.5 text-[10.5px] leading-relaxed text-muted2">
            <MessageSquarePlus className="size-3 shrink-0" />
            {deploying ? 'Nothing has been deployed yet.' : 'Nothing has been changed yet.'} You can also just type what to change in the box below.
          </p>
          {error && <p className="mt-1.5 text-[11px] text-bad">{error}</p>}
        </div>
      )}
    </div>
  )
}
