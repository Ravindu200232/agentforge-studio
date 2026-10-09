'use client'

/** The pieces of the select, pencil and text tools for a framed app: the buttons, the layer drawn on, a hint, and the chips. */
import { Eraser, MousePointerClick, Pencil, Type, X } from 'lucide-react'

import { Tip } from './ui'
import { cn } from '@/lib/utils'

const HINTS = {
  pick: 'Click anything on the page — it is sent with your next request',
  pencil: 'Draw around what you mean — it is sent with your next request',
  text: 'Click any words on the page, then type the new ones',
}

/** The three tools, and the eraser for what was drawn. */
export function ToolButtons({ mode, onTool, inked, onErase, small = false }) {
  const size = small ? 'size-7' : 'h-9 px-2'
  const cell = (id, tip, icon, disabled = false, onClick = () => onTool(id)) => {
    const Icon = icon
    return (
      <Tip key={id} text={tip}>
        <button type="button" disabled={disabled} onClick={onClick} aria-label={tip}
          aria-pressed={mode === id ? true : undefined}
          className={cn('grid place-items-center rounded-full text-ink transition-colors', size,
            mode === id ? 'bg-accent shadow-sm' : 'hover:bg-ink/[.06]', 'disabled:pointer-events-none disabled:text-faint')}>
          <Icon className="size-3.5" />
        </button>
      </Tip>
    )
  }
  return (
    <div className="flex items-center gap-0.5 rounded-full border border-line/80 bg-panel/80 p-0.5 shadow-sm" role="toolbar" aria-label="Page tools">
      {cell('pick', 'Select: click things on the page to ask about them', MousePointerClick)}
      {cell('pencil', 'Pencil: draw around what you mean', Pencil)}
      {cell('text', 'Text: click words on the page and retype them', Type)}
      {cell('erase', inked ? 'Erase the drawing' : 'Nothing drawn yet', Eraser, !inked, onErase)}
    </div>
  )
}

/** The layer the pencil draws on, over the page. */
export function DrawLayer({ canvasRef, active }) {
  return (
    <canvas ref={canvasRef}
      className={cn('absolute inset-0 z-[8] h-full w-full', active ? 'block' : 'hidden')}
      style={{ pointerEvents: active ? 'auto' : 'none', cursor: active ? 'crosshair' : 'default', touchAction: 'none' }} />
  )
}

export function ToolHint({ mode }) {
  if (!mode || !HINTS[mode]) return null
  return (
    <p className="pointer-events-none absolute inset-x-0 bottom-4 z-[9] mx-auto w-fit max-w-[90%] rounded-full bg-ink/85 px-3.5 py-1.5 text-[11px] font-medium text-bg shadow-lg">
      {HINTS[mode]}
    </p>
  )
}

/** What was pointed at or drawn around, waiting to go with the next request. */
export function Chips({ items, onRemove, className }) {
  if (!items.length) return null
  return (
    <ul className={cn('flex flex-wrap gap-1.5', className)} aria-label="Pointed at">
      {items.map(item => (
        <li key={item.key}
          className="inline-flex max-w-full items-center gap-1 rounded-full border border-line bg-panel py-0.5 pl-2.5 pr-1 text-[10.5px] text-ink">
          <span className="truncate">{item.label}</span>
          <button type="button" onClick={() => onRemove(item.key)} title="Remove" aria-label={`Remove ${item.label}`}
            className="grid size-4 shrink-0 place-items-center rounded-full text-muted hover:bg-ink/[.08]"><X className="size-2.5" /></button>
        </li>
      ))}
    </ul>
  )
}
