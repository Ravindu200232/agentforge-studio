'use client'

/**
 * The T tool: click any words on the page, type the new ones, press Enter.
 *
 * The words are swapped in the app's own source when they are written there in exactly one place, and the app is bundled again. When
 * they are put together in code, or written in several places, a plain swap could change the wrong one: the box says so and offers to
 * hand the change to the agent, which can follow it wherever it comes from.
 */
import { useEffect, useRef, useState } from 'react'
import { Loader2, Sparkles, Type, X } from 'lucide-react'

import { api, isJobCancelled } from '@/lib/api'
import { attachPicker, ownText } from '@/lib/picker'

const WHY = {
  'found in several places': 'These words are written in several places in the app, so a plain swap could change the wrong one.',
  'built in code': 'These words are put together in code, so they cannot be swapped directly.',
  'does not bundle': 'That change stopped the app from bundling, so it was put back.',
}

export default function AppTextEdit({ frameRef, active, loaded = 0, project, kind, onSaved, onAskAi }) {
  const [edit, setEdit] = useState(null)       // { old, value, left, top }
  const [state, setState] = useState({ busy: false, problem: '', reason: '' })
  const field = useRef(null)

  useEffect(() => {
    setEdit(null)
    setState({ busy: false, problem: '', reason: '' })
    const frame = frameRef.current
    if (!active || !frame) return undefined
    const detach = attachPicker(frame, (element) => {
      const text = ownText(element)
      if (!text) {
        setEdit(null)
        setState({ busy: false, problem: 'There is no text there — click on words.', reason: '' })
        return
      }
      const inside = element.getBoundingClientRect()
      const outside = frame.getBoundingClientRect()
      setState({ busy: false, problem: '', reason: '' })
      setEdit({ old: text, value: text, left: Math.max(8, outside.left + inside.left), top: outside.top + inside.bottom + 6 })
    })
    return () => { detach?.() }
  }, [active, loaded, frameRef])

  useEffect(() => { if (edit) field.current?.select() }, [edit?.old])

  if (!active || (!edit && !state.problem)) return null

  async function save() {
    if (!edit || state.busy) return
    if (edit.value.trim() === edit.old) { setEdit(null); return }
    setState({ busy: true, problem: '', reason: '' })
    try {
      const done = await api.editAppText(project, kind, edit.old, edit.value)
      if (done?.ok) {
        setEdit(null)
        setState({ busy: false, problem: '', reason: '' })
        onSaved?.(done)
        return
      }
      setState({ busy: false, reason: done?.reason || '',
        problem: WHY[done?.reason] || 'The text could not be changed.' })
    } catch (failure) {
      setState({ busy: false, reason: '', problem: isJobCancelled(failure) ? '' : (failure?.message || 'The text could not be changed.') })
    }
  }

  const rows = edit ? Math.min(6, Math.max(1, Math.ceil(edit.value.length / 38))) : 1
  return (
    <div
      role="dialog"
      aria-label="Edit text"
      className="fixed z-50 w-[min(380px,calc(100vw-1rem))] rounded-xl border border-line bg-panel p-2.5 shadow-2xl"
      style={edit ? { left: Math.min(edit.left, (typeof window !== 'undefined' ? window.innerWidth : 1200) - 396), top: edit.top }
        : { right: 16, bottom: 16 }}
    >
      {edit && (
        <form onSubmit={(event) => { event.preventDefault(); save() }} className="flex items-start gap-2">
          <Type className="mt-2 size-3.5 shrink-0 text-muted" />
          <textarea
            ref={field}
            rows={rows}
            value={edit.value}
            onChange={(event) => setEdit({ ...edit, value: event.target.value })}
            onKeyDown={(event) => {
              if (event.key === 'Escape') setEdit(null)
              if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); save() }
            }}
            className="min-w-0 flex-1 resize-none rounded-lg border border-line bg-white px-2.5 py-1.5 text-[12px] leading-snug text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
            aria-label="New text"
          />
          <button type="submit" disabled={state.busy}
            className="inline-flex h-8 items-center gap-1 rounded-lg bg-accent px-3 text-[11px] font-semibold text-ink disabled:opacity-50">
            {state.busy ? <Loader2 className="size-3 animate-spin" /> : 'Save'}
          </button>
          <button type="button" onClick={() => setEdit(null)} title="Cancel"
            className="grid size-8 place-items-center rounded-lg text-muted hover:bg-ink/[.06]"><X className="size-3.5" /></button>
        </form>
      )}
      {state.problem && (
        <div className="mt-2 text-[11px] leading-relaxed text-muted">
          <p>{state.problem}</p>
          {edit && onAskAi && state.reason !== 'does not bundle' && (
            <button type="button"
              onClick={() => { onAskAi({ old: edit.old, value: edit.value }); setEdit(null); setState({ busy: false, problem: '', reason: '' }) }}
              className="mt-1.5 inline-flex items-center gap-1 font-semibold text-accent hover:underline">
              <Sparkles className="size-3" /> Ask the AI to change it
            </button>
          )}
        </div>
      )}
    </div>
  )
}
