'use client'

/** The pieces of the select, pencil and text tools for a framed app: the buttons, the layer drawn on, a hint, and the chips. */
import { Circle, Eraser, Image, Loader2, MousePointerClick, Pencil, Square, Type, X } from 'lucide-react'

import { Button, Tip } from './ui'
import { cn } from '@/lib/utils'

const HINTS = {
  pick: 'Click a box to show its resize handles. Drag the box to move it.',
  pencil: 'Draw around what you mean — it is sent with your next request',
  text: 'Click any words on the page, then type the new ones',
  rectangle: 'Drag to draw a rectangle. Hold Space while drawing to move it.',
  ellipse: 'Drag to draw an ellipse. Hold Space while drawing to move it.',
  textbox: 'Drag to draw a text box. Hold Space while drawing to move it.',
  picture: 'Drag to draw a picture placeholder. Hold Space while drawing to move it.',
}

/** The three tools, and the eraser for what was drawn. */
export function ToolButtons({ mode, onTool, inked, onErase, small = false, shapes = false, picture = false }) {
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
      {cell('pick', 'Select, move or resize elements', MousePointerClick)}
      {cell('pencil', 'Pencil: draw around what you mean', Pencil)}
      {cell('text', 'Text: click words on the page and retype them', Type)}
      {cell('erase', inked ? 'Erase the drawing' : 'Nothing drawn yet', Eraser, !inked, onErase)}
      {shapes && <>
        <span aria-hidden="true" className="mx-0.5 h-4 border-l border-line" />
        {cell('rectangle', 'Add rectangle', Square)}
        {cell('ellipse', 'Add ellipse', Circle)}
        {cell('textbox', 'Add text box', Type)}
        {picture && cell('picture', 'Add picture placeholder', Image)}
      </>}
    </div>
  )
}

const editLabels = { move: 'Position change', resize: 'Size change', layout: 'Position and size changes',
  insert: 'New element', picture: 'Picture placeholder' }

export function LayoutControls({ draft, operation, onSave, onCancel, disabled = false }) {
  if (!draft && !operation) return null
  return (
    <div role="group" aria-label="Layout preview"
      className="absolute inset-x-2 top-3 z-20 mx-auto flex w-fit max-w-[calc(100%-1rem)] flex-wrap items-center gap-2 rounded-xl border border-line bg-panel px-3 py-1.5 text-xs text-ink shadow-lg">
      <span role="status" className="flex items-center gap-1.5">
        {operation ? <><Loader2 className="size-3.5 animate-spin" /> Saving preview…</> : `${editLabels[draft.operation]} · Unsaved`}
      </span>
      {!operation && <>
        {['insert', 'picture'].includes(draft.operation) && <span className="text-muted">Drag the preview to move it</span>}
        {draft.setShape && (
          <select aria-label="Picture shape" value={draft.details.shape}
            onChange={event => draft.setShape(event.target.value)}
            className="rounded-md border border-line bg-panel px-2 py-1">
            <option value="rectangle">Rectangle</option>
            <option value="square">Square</option>
            <option value="circle">Round</option>
            <option value="triangle">Triangle</option>
          </select>
        )}
        {draft.setText && (
          <input aria-label="Text box content" value={draft.details.text} onChange={event => draft.setText(event.target.value)}
            maxLength={300} className="w-32 rounded-md border border-line bg-transparent px-2 py-1 outline-none focus:border-accent" />
        )}
        <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
        <Button type="button" variant="solid" disabled={disabled || draft.setText && !draft.details.text.trim()} onClick={onSave}>Save</Button>
      </>}
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
