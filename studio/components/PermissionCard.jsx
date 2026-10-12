'use client'

/**
 * The agent asks before an edit or a command (the mode decides which): a card in the chat stream, the way Claude Code asks —
 * what it wants to do, and numbered answers. The run holds still until one is given.
 */
import { useRef, useState } from 'react'
import { ShieldAlert, ShieldQuestion } from 'lucide-react'

import { answerPermission } from '@/lib/ws'
import { cn } from '@/lib/utils'

export default function PermissionCard({ card }) {
  const edit = card.action === 'edit'
  const [telling, setTelling] = useState(false)
  const [note, setNote] = useState('')
  const [sent, setSent] = useState(false)
  const noteBox = useRef(null)
  const again = card.always_label || ''
  const denyNumber = again ? 3 : 2

  const give = (verdict, text = '') => {
    if (sent) return
    setSent(true)
    answerPermission(card, verdict, text)
  }
  const tell = () => {
    setTelling(true)
    requestAnimationFrame(() => noteBox.current?.focus())
  }
  const onKeyDown = event => {
    if (event.target instanceof HTMLInputElement) return
    if (event.key === '1') { event.preventDefault(); give('allow') }
    else if (event.key === '2' && again) { event.preventDefault(); give('always') }
    else if (event.key === String(denyNumber)) { event.preventDefault(); tell() }
    else if (event.key === 'Escape') { event.preventDefault(); give('deny') }
  }

  return (
    <div className="my-1 flex gap-2.5" role="group" aria-label="Permission request" tabIndex={0} onKeyDown={onKeyDown}>
      <span className={cn('mt-0.5 grid size-6 shrink-0 place-items-center rounded-full',
        card.danger ? 'bg-bad/10 text-bad' : 'bg-accent text-ink')}>
        {card.danger ? <ShieldAlert className="size-3" /> : <ShieldQuestion className="size-3" />}
      </span>
      <div className={cn('min-w-0 flex-1 rounded-2xl rounded-tl-sm border bg-white px-3.5 py-3 shadow-sm',
        card.danger ? 'border-bad/40' : 'border-line')}>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-[.12em] text-muted2">
          {card.danger ? 'Risky: needs your permission' : 'Needs your permission'}
        </p>
        <p className="text-[13px] font-medium leading-relaxed text-ink">{card.question || (edit ? 'Edit this file?' : 'Run this command?')}</p>
        <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-panel2 px-3 py-2 font-mono text-[12px] leading-relaxed text-ink">
          {card.detail}
        </pre>
        {card.extra_detail && <p className="mt-1 text-[11px] text-muted2">{card.extra_detail}</p>}
        {card.reason && <p className={cn('mt-1.5 text-[11.5px] leading-relaxed', card.danger ? 'text-bad' : 'text-muted')}>{card.reason}</p>}

        <div className="mt-3 space-y-1">
          <Choice number={1} disabled={sent} onClick={() => give('allow')}>Yes</Choice>
          {again && <Choice number={2} disabled={sent} onClick={() => give('always')}>{again}</Choice>}
          {telling ? (
            <form className="flex items-center gap-2 rounded-lg bg-panel2 px-2.5 py-1.5"
              onSubmit={event => { event.preventDefault(); give('deny', note) }}>
              <span className="w-4 text-[11.5px] font-semibold text-muted2">{denyNumber}</span>
              <input ref={noteBox} value={note} onChange={event => setNote(event.target.value)} disabled={sent}
                placeholder="Tell the agent what to do differently (Enter to send)"
                onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); setTelling(false) } }}
                className="min-w-0 flex-1 bg-transparent text-[12px] text-ink outline-none placeholder:text-muted2" />
              <button type="submit" disabled={sent} className="text-[11.5px] font-semibold text-ink hover:underline">Send</button>
            </form>
          ) : (
            <Choice number={denyNumber} disabled={sent} onClick={tell}>No, and tell the agent what to do differently</Choice>
          )}
        </div>
        <p className="mt-2 text-[10.5px] text-muted2">Press 1{again ? ', 2' : ''} or {denyNumber}, or Esc to say no.</p>
      </div>
    </div>
  )
}

function Choice({ number, children, onClick, disabled }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[12px] text-ink transition-colors hover:bg-panel2 disabled:opacity-50">
      <span className="w-4 text-[11.5px] font-semibold text-muted2">{number}</span>
      <span className="min-w-0 flex-1">{children}</span>
    </button>
  )
}
