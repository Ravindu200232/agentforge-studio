'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft, ArrowRight, FileText, Loader2, SkipForward, Sparkles,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { TYPE_ANOTHER } from '@/lib/srs-constants'
import { useAttachments } from '@/lib/use-attachments'
import { AttachButtons, AttachList } from './Attachments'
import AgentChat from '../AgentChat'
import { Button, TextArea } from '../ui'
import { cn } from '@/lib/utils'

export default function Interview({ projectId, onDone, onCancel }) {
  const addLog = useStore(s => s.addLog)
  const [state, setState] = useState({ question: null, transcript: [], answers: [], done: false })
  const [phase, setPhase] = useState('loading')
  const [typing, setTyping] = useState(false)
  const [text, setText] = useState('')
  const [picked, setPicked] = useState([])
  const [error, setError] = useState('')
  const [pending, setPending] = useState(null)
  const composer = useRef(null)
  const tail = useRef(null)
  const attach = useAttachments()

  async function refresh() {
    try {
      const next = await api.srs(`/projects/${projectId}/interview`)
      setState(next)
      setPending(null)
      setTyping(false)
      setText('')
      if (next.done || !next.question) {
        return onDone?.(next)
      }
      setPhase('asking')
    } catch (e) {
      if (/404|not found/i.test(e.message || '')) return onCancel?.()
      setError(e.message)
      setPending(null)
      setPhase('error')
    }
  }

  useEffect(() => { refresh() }, [projectId])
  useEffect(() => {
    tail.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [state.question?.id, state.answers?.length, pending])
  useEffect(() => { if (typing) composer.current?.focus() }, [typing])

  const q = state.question
  const options = q?.options?.length ? q.options
                                     : (q?.suggested_options || []).map(o => ({ label: o, value: o }))
  const multi = /multi/.test(q?.answer_type || '')
  const prefill = q?.prefill || []
  const recommended = q?.recommended

  useEffect(() => {
    const initPicked = (prefill || []).map(String)
    setPicked(initPicked)
    setText(!options.length && prefill?.length ? String(prefill[0]) : '')
  }, [q?.id])

  function draftPlanNow() {
    onDone?.(state)
  }

  async function answer(payload) {
    setPhase('sending')
    setError('')
    try {
      let attachments = []
      if (attach.items.length) {
        const uploaded = await attach.upload(projectId)
        attachments = uploaded.ids || []
        const said = payload.value != null || (payload.selected || []).length || String(payload.text || '').trim()
        if (!attachments.length && !said) {
          setError('That attachment could not be read. Try it again, or answer in text.')
          setPending(null)
          setPhase('asking')
          return
        }
      }
      await api.srs(`/projects/${projectId}/interview/answer`, attachments.length ? { ...payload, attachments } : payload)
      attach.reset()

      await refresh()
    } catch (e) {
      setError(e.message)
      setPending(null)
      addLog('WARN', `The SRS could not record that answer — ${e.message}`)
      setPhase('asking')
    }
  }

  function submitAnswer() {
    if (phase === 'sending' || !q) return

    // Extract human-readable labels for all selected options
    const selectedLabels = picked.map(val => {
      const opt = options.find(o =>
        String(o.value ?? o.label) === String(val) ||
        String(o.label) === String(val) ||
        String(o.value) === String(val)
      )
      return opt?.label ?? String(val)
    }).filter(Boolean)

    const selectedText = selectedLabels.join(', ')
    const customText = text.trim()

    // Must have at least one chosen option, custom typed text, or attachment
    if (!selectedText && !customText && !attach.items.length) {
      composer.current?.focus()
      return
    }

    // Combine both: option label(s) + custom typed text
    const parts = []
    if (selectedText) parts.push(selectedText)
    if (customText) parts.push(customText)
    const combined = parts.join(' — ')

    const val = combined || (multi && picked.length ? picked : (picked[0] ?? null))

    const payload = {
      key: q.id,
      value: val,
      text: combined || customText || selectedText,
      selected: picked.map(String),
      custom: customText,
    }

    // Instantly show in the chat stream UI optimistically
    setPending({
      question: q.question,
      answer: combined || customText || selectedText,
    })

    setText('')
    setPicked([])
    answer(payload)
  }

  const history = useMemo(() => {
    const byId = Object.fromEntries((state.answers || []).map(a => [a.question_id, a]))
    return (state.transcript || []).filter(row => byId[row.id]).map(row => ({ row, answer: byId[row.id] }))
  }, [state.transcript, state.answers])
  const answered = (state.answers || []).length
  const total = Math.max((state.transcript || []).length, answered + 1, 8)

  if (phase === 'loading') return <div className="grid min-h-0 flex-1 place-items-center"><Waiting>Preparing your interview…</Waiting></div>
  if (phase === 'error' && !q) return (
    <div className="grid min-h-0 flex-1 place-items-center p-8">
      <div className="max-w-[460px] rounded-none bg-black/75 p-6 shadow-xl ring-1 ring-line dark:bg-black/[.04]">
        <p className="text-[13px] text-ink">The interview could not start.</p>
        <p className="mt-2 text-[12px] text-muted">{error}</p>
        <Button variant="outline" className="mt-4" onClick={onCancel}>Back</Button>
      </div>
    </div>
  )

  return (
    <div className="srs-messenger flex min-h-0 flex-1 flex-col bg-panel text-ink">
      <header className="flex shrink-0 items-center gap-3 border-b border-black/10 px-7 py-4 backdrop-blur-md">
        <button onClick={onCancel} className="grid size-9 place-items-center rounded-none border border-black/10 bg-black/[.04] text-muted transition hover:bg-black/[.08] hover:text-ink">
          <ArrowLeft className="size-4" />
        </button>
        <div>
          <p className="font-display text-[14.5px] font-bold tracking-tight text-ink">Plan conversation</p>
          <p className="text-[11px] text-muted2">
            {`Question ${answered + 1} of about ${total}`}
          </p>
        </div>
        <span className="flex-1" />
        <div className="hidden items-center gap-1.5 sm:flex">
          {Array.from({ length: Math.min(total, 10) }).map((_, i) => (
            <span key={i} className={cn('h-1.5 rounded-full transition-all',
              i < answered
                ? 'w-5 bg-emerald-400'
                : i === answered
                  ? 'w-8 bg-accent'
                  : 'w-3 bg-black/15'
            )} />
          ))}
        </div>
        <button onClick={draftPlanNow} className="ml-2 inline-flex h-9 items-center gap-2 rounded-none border border-black/10 bg-black/[.05] px-3.5 text-[11.5px] font-semibold text-ink transition hover:bg-black/[.1] hover:text-ink">
          <SkipForward className="size-3.5 text-accent" /> Draft plan now
        </button>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* The same durable stream used by SRS, wireframe, prototype, build,
            QA and deploy. Interview controls stay in the work pane. */}
        <AgentChat projectTitle="Plan conversation" readOnly className="hidden lg:flex lg:w-[360px]" />

      <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">
        <div className="mx-auto max-w-[820px] py-4">
          <div className="mb-7 flex justify-center">
            <span className="rounded-full border border-black/10 bg-black/[.04] px-4 py-1 text-[11px] font-medium text-muted shadow-sm backdrop-blur-md">
              AgentForge asks only what it needs to build the app correctly.
            </span>
          </div>

          <div className="lg:hidden">
            {history.map(({ row, answer: a }, i) => (
              <div key={row.id || i} className="mb-7">
                <Message side="left" label="AgentForge">{row.question}</Message>
                <Message side="right" label="You">{said(a)}</Message>
              </div>
            ))}

            {pending && (
              <div className="mb-7 animate-in fade-in duration-200">
                <Message side="left" label="AgentForge">{pending.question}</Message>
                <Message side="right" label="You">{pending.answer}</Message>
              </div>
            )}
          </div>

          {phase === 'sending' && (
            <div role="status" className="mb-5 flex items-center gap-2.5 py-2 text-[12px] text-muted">
              <Loader2 className="size-3.5 animate-spin text-accent" />
              <span>AgentForge is reviewing your answer and preparing the next step…</span>
            </div>
          )}

          {q && phase !== 'sending' && (
            <div className="mb-5">
              <Message side="left" label="AgentForge" current>
                <span className="block text-[16px] font-bold leading-[1.45] text-ink">{q.question}</span>
                {q.why_needed && <span className="mt-2.5 block text-[12px] leading-relaxed text-muted">{q.why_needed}</span>}
                {q.hint && !q.why_needed?.includes(q.hint) && <span className="mt-2 block text-[11.5px] font-medium text-amber-300/85">{q.hint}</span>}
                {q.prefill_note && <span className="mt-2 block text-[11.5px] font-medium text-accent">You previously said “{q.prefill_note}”.</span>}
              </Message>
            </div>
          )}

          {phase !== 'sending' && options.length > 0 && (
            <div className="ml-11 mb-4 max-w-[680px]">
              <div className="flex flex-wrap gap-2.5">
                {options.map((o, i) => {
                  const valStr = String(o.value ?? o.label)
                  const known = prefill.map(String).includes(valStr)
                  const chosen = picked.map(String).includes(valStr) ||
                    (o.value != null && picked.map(String).includes(String(o.value))) ||
                    (o.label != null && picked.map(String).includes(String(o.label)))
                  const suggested = o.suggested || o.value === recommended || o.label === recommended
                  return (
                    <button
                      key={`${valStr}-${i}`}
                      disabled={phase === 'sending'}
                      onClick={() => {
                        if (valStr === TYPE_ANOTHER) {
                          composer.current?.focus()
                          return
                        }
                        if (multi) {
                          return setPicked(p => p.map(String).includes(valStr) ? p.filter(x => String(x) !== valStr) : [...p, valStr])
                        }
                        // Single-select: toggle pick so the user can unpick or pick a different one
                        setPicked(p => p.map(String).includes(valStr) ? [] : [valStr])
                      }}
                      className={cn('rounded-full px-4 py-2 text-[12px] font-medium transition-all shadow-sm disabled:opacity-45 text-left',
                        chosen
                          ? 'bg-accent text-ink border border-accent shadow-[0_4px_12px_0_rgba(191, 185, 255,0.24)]'
                          : 'border border-black/10 bg-black/[.05] text-ink hover:bg-black/[.1] hover:text-ink hover:border-black/20'
                      )}
                    >
                      <span>{o.label ?? valStr}</span>
                      {o.hint && <span className="mt-0.5 block text-[10.5px] font-normal text-muted2">{o.hint}</span>}
                      {(suggested || known) && (
                        <span className={cn('ml-2 text-[9px] font-semibold uppercase tracking-wider', chosen ? 'text-ink' : 'text-muted2')}>
                          {known ? 'from brief' : 'suggested'}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
              {multi && (
                <div className="mt-3 flex items-center gap-3">
                  <Button variant="solid" disabled={!picked.length || phase === 'sending'} onClick={submitAnswer}>
                    Continue with {picked.length} selected
                  </Button>
                </div>
              )}
            </div>
          )}

          {phase !== 'sending' && (
            <div className="ml-auto mt-2 max-w-[690px] rounded-none border border-line bg-panel p-4 shadow-2xl backdrop-blur-2xl transition-all focus-within:border-accent/50 focus-within:shadow-[0_15px_40px_rgba(191, 185, 255,.15)]">
              {options.length > 0 && (
                <div className="mb-2 px-1 text-[11px] font-medium text-muted2">
                  Or type your own answer / extra details:
                </div>
              )}
              <TextArea
                ref={composer}
                value={text}
                rows={options.length > 0 ? 2 : 3}
                placeholder={options.length > 0 ? "Type custom details or a different answer…" : "Type your answer…"}
                onChange={e => setText(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    submitAnswer()
                  }
                }}
                className="w-full resize-none bg-transparent px-1 py-1 text-[13.5px] leading-relaxed text-ink outline-none placeholder:text-muted2 caret-accent"
              />
              <AttachList attach={attach} className="mx-1 mb-2" />
              <div className="flex items-center gap-2 border-t border-black/10 px-1 pt-3">
                <AttachButtons attach={attach} disabled={phase === 'sending'} />
                <span className="flex-1" />
                <button
                  disabled={phase === 'sending' || (!text.trim() && !attach.items.length && !picked.length)}
                  onClick={submitAnswer}
                  className="inline-flex h-9 items-center gap-2 rounded-none bg-accent px-4 text-[12px] font-semibold text-ink shadow-[0_8px_16px_0_rgba(191, 185, 255,0.24)] transition hover:bg-press disabled:opacity-40 cursor-pointer"
                >
                  <ArrowRight className="size-3.5" /> Send
                </button>
              </div>
            </div>
          )}

          {error && <p className="ml-auto mt-3 max-w-[690px] rounded-none border border-red-500/30 bg-red-500/10 px-4 py-3 text-[11.5px] text-red-300">{error}</p>}
          <div ref={tail} />
        </div>
      </div>
      </div>

      <footer className="shrink-0 border-t border-line bg-panel/90 px-6 py-3 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[820px] items-center gap-2 text-[11px] text-muted">
          <Sparkles className="size-3.5 text-accent" /> Your answers become the implementation contract. You can review the full plan before anything is built.
          <span className="flex-1" />
          <button disabled={answered === 0} onClick={draftPlanNow} className="inline-flex items-center gap-1.5 rounded-none border border-line bg-panel2/80 px-3.5 py-1.5 font-medium text-ink transition hover:bg-raised disabled:opacity-40 cursor-pointer">
            <FileText className="size-3 text-warn" /> Review plan
          </button>
        </div>
      </footer>
    </div>
  )
}

function Message({ side, label, current, children }) {
  const right = side === 'right'
  return (
    <div className={cn('flex items-end gap-3', right && 'justify-end')}>
      {!right && (
        <span className="grid size-8 shrink-0 place-items-center rounded-none bg-accent border border-accent/30 text-[11px] font-bold text-ink shadow-sm">
          AF
        </span>
      )}
      <div className={cn('max-w-[75%]', right && 'text-right')}>
        <div className="mb-1.5 px-1 text-[9.5px] font-bold uppercase tracking-[.14em] text-muted2">{label}</div>
        <div className={cn('inline-block rounded-none px-4 py-3.5 text-left text-[13px] leading-relaxed shadow-sm',
          right
            ? 'rounded-none bg-accent border border-accent/35 text-ink font-medium'
            : current
              ? 'rounded-none bg-panel border border-accent/40 ring-1 ring-accent/20 text-ink'
              : 'rounded-none bg-panel/90 border border-black/10 text-ink'
        )}>
          {children}
        </div>
      </div>
    </div>
  )
}

function said(a) {
  if (!a) return ''
  const custom = a.custom || a.custom_text || a.raw_text
  if (typeof a.value === 'string' && a.value.trim()) {
    if (custom && custom !== a.value && !a.value.includes(custom)) {
      return `${a.value} — ${custom}`
    }
    return a.value
  }
  if (Array.isArray(a.value)) {
    const sel = a.value.map(String).join(', ')
    if (custom && custom !== sel && !sel.includes(custom)) {
      return `${sel} — ${custom}`
    }
    return sel || custom || 'Answered'
  }
  return custom || (a.value != null ? String(a.value) : 'Answered')
}

export function Waiting({ children, sub }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col items-center px-6 py-10 text-center">
      <Loader2 className="size-7 animate-spin text-accent" />
      <p className="mt-4 font-display text-[18px] font-bold text-ink">{children}</p>
      {sub && <p className="mt-1.5 text-[12px] text-muted">{sub}</p>}
    </div>
  )
}


