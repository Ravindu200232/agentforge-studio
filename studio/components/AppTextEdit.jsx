'use client'

/**
 * Retype a word on the page: click any text in the preview, type the new words, press Enter. The text is swapped in
 * the app's source when it is written there exactly once; when it is built in code or appears in several places the
 * edit is handed to the AI instead, which can follow it wherever it comes from.
 */
import { useEffect, useRef, useState } from 'react'
import { Loader2, Sparkles, Type } from 'lucide-react'

import { api, isJobCancelled } from '@/lib/api'
import { attachPicker } from '@/lib/picker'

/** The words an element carries itself: a leaf's whole text, or the first text node of a mixed element. */
export function ownText(element) {
  if (!element) return ''
  if (!element.children || element.children.length === 0) return String(element.textContent || '').trim()
  for (const node of element.childNodes || []) {
    if (node.nodeType === 3 && String(node.textContent || '').trim()) return String(node.textContent).trim()
  }
  return ''
}

export default function AppTextEdit({ frameRef, active, loaded = 0, project, kind, onSaved, onAskAi }) {
  const [edit, setEdit] = useState(null)       // { old, value, left, top }
  const [state, setState] = useState({ busy: false, problem: '' })
  const input = useRef(null)

  useEffect(() => {
    setEdit(null)
    const frame = frameRef.current
    if (!active || !frame) return undefined
    const detach = attachPicker(frame, (element) => {
      const text = ownText(element)
      if (!text) { setState({ busy: false, problem: 'There is no text there — click on words.' }); return }
      const inside = element.getBoundingClientRect()
      const outside = frame.getBoundingClientRect()
      setState({ busy: false, problem: '' })
      setEdit({ old: text, value: text,
        left: Math.max(8, outside.left + inside.left), top: outside.top + inside.bottom + 6 })
    })
    return () => { detach?.() }
  }, [active, loaded, frameRef])

  useEffect(() => { if (edit) input.current?.select() }, [edit?.old])

  if (!active || (!edit && !state.problem)) return null

  async function save() {
    if (!edit || state.busy || edit.value === edit.old) { setEdit(null); return }
    setState({ busy: true, problem: '' })
    try {
      const done = await api.editAppText(project, kind, edit.old, edit.value)
      if (done?.ok) { setEdit(null); setState({ busy: false, problem: '' }); onSaved?.(done); return }
      setState({ busy: false, problem: done?.reason === 'found in several places'
        ? 'These words appear in several places in the app, so a plain swap could change the wrong one.'
        : 'These words are built in code, so they cannot be swapped directly.' })
    } catch (failure) {
      setState({ busy: false, problem: isJobCancelled(failure) ? '' : (failure?.message || 'The text could not be changed.') })
    }
  }

  return (
    <div
      role="dialog"
      aria-label="Edit text"
      className="fixed z-50 w-[min(360px,calc(100vw-1rem))] rounded-xl border border-line bg-panel p-2.5 shadow-2xl"
      style={edit ? { left: Math.min(edit.left, (typeof window !== 'undefined' ? window.innerWidth : 1200) - 376), top: edit.top }
        : { right: 16, bottom: 16 }}
    >
      {edit && (
        <form onSubmit={(event) => { event.preventDefault(); save() }} className="flex items-center gap-2">
          <Type className="size-3.5 shrink-0 text-muted" />
          <input
            ref={input}
            value={edit.value}
            onChange={(event) => setEdit({ ...edit, value: event.target.value })}
            onKeyDown={(event) => { if (event.key === 'Escape') setEdit(null) }}
            className="min-w-0 flex-1 rounded-lg border border-line bg-white px-2.5 py-1.5 text-[12px] text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
            aria-label="New text"
          />
          <button type="submit" disabled={state.busy}
            className="inline-flex h-8 items-center gap-1 rounded-lg bg-accent px-3 text-[11px] font-semibold text-ink disabled:opacity-50">
            {state.busy ? <Loader2 className="size-3 animate-spin" /> : 'Save'}
          </button>
        </form>
      )}
      {state.problem && (
        <div className="mt-2 text-[11px] leading-relaxed text-muted">
          <p>{state.problem}</p>
          {edit && onAskAi && (
            <button type="button"
              onClick={() => { onAskAi({ old: edit.old, value: edit.value }); setEdit(null); setState({ busy: false, problem: '' }) }}
              className="mt-1.5 inline-flex items-center gap-1 font-semibold text-accent hover:underline">
              <Sparkles className="size-3" /> Ask the AI to change it
            </button>
          )}
        </div>
      )}
    </div>
  )
}
