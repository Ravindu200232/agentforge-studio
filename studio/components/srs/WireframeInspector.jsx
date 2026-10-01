'use client'

import { useEffect, useState } from 'react'
import {
  RefreshCw,
  MousePointer2,
  Sparkles,
  Trash2,
  Type,
  Undo2,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const buttonClass = 'inline-flex items-center justify-center gap-1 rounded-lg border border-line bg-panel px-2 py-1.5 text-[11px] text-ink transition-colors hover:bg-black/[.04] disabled:cursor-not-allowed disabled:opacity-30'
const inputClass = 'w-full rounded-lg border border-line bg-white px-2 py-1.5 text-[11px] text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/15'

/**
 * A deliberately small low-fidelity wireframe rail. Layout, spacing, and
 * components move through the page-level AI request instead of CSS controls.
 */
export default function WireframeInspector({
  editor,
  selectionKey,
  onChange,
  onUndo,
  onRedraw,
  redrawing,
  onOpenAi,
  typing,
  onEditText,
  selectionMode,
  onSelectionMode,
}) {
  const [tool, setTool] = useState('')
  const [revision, setRevision] = useState(0)
  const element = editor?.selected?.()
  const tag = element?.tagName?.toLowerCase() || ''

  useEffect(() => setRevision(value => value + 1), [selectionKey])
  if (!editor) return null

  const run = operation => {
    operation?.()
    onChange?.()
    setRevision(value => value + 1)
  }
  const IconButton = ({ name, Icon, onClick, disabled = false, active = false }) => (
    <button
      type="button"
      title={name}
      aria-label={name}
      aria-pressed={tool === name || active}
      disabled={disabled}
      onClick={onClick || (() => setTool(tool === name ? '' : name))}
      className={cn(
        'grid size-9 place-items-center rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-30',
        tool === name || active ? 'bg-accent/15 text-deep' : 'text-ink hover:bg-black/[.05]',
      )}
    >
      <Icon size={15} />
    </button>
  )

  return (
    <aside aria-label="Wireframe tools" className="absolute left-3 top-3 z-40 flex items-start gap-2">
      <nav className="flex w-10 flex-col items-center gap-0.5 rounded-xl border border-line bg-panel p-1 shadow-xl">
        <IconButton
          name="text"
          Icon={Type}
          active={typing}
          onClick={() => {
            setTool('text')
            if (element?.textContent?.trim()) onEditText?.(!typing)
          }}
        />
        <IconButton
          name="Attach selected elements to AI prompt"
          Icon={MousePointer2}
          active={selectionMode}
          onClick={() => onSelectionMode?.(!selectionMode)}
        />
        <IconButton name="Redraw this page" Icon={RefreshCw} onClick={onRedraw} disabled={redrawing} />
        <IconButton name="Ask AI to update this page" Icon={Sparkles} onClick={onOpenAi} />
        <span className="my-0.5 h-px w-6 bg-line" />
        <button
          type="button"
          title="Undo last user step"
          aria-label="Undo last user step"
          disabled={!editor.hasHistory?.()}
          onClick={onUndo}
          className="grid size-9 place-items-center rounded-lg text-ink transition-colors hover:bg-black/[.05] disabled:cursor-not-allowed disabled:opacity-30"
        >
          <Undo2 size={15} />
        </button>
      </nav>

      {tool && (
        <section className="w-[min(360px,calc(100vw-7rem))] rounded-xl border border-line bg-panel p-3 shadow-2xl">
          <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
            <div>
              <p className="text-xs font-semibold text-ink">
                Text editor
              </p>
              <p className="text-[10px] text-muted">{tag ? `Selected <${tag}>` : 'Select an element when needed'}</p>
            </div>
            <button className="grid size-7 place-items-center rounded-lg border border-line text-muted hover:text-ink" onClick={() => setTool('')} title="Close controls">
              <X size={13} />
            </button>
          </div>

          {tool === 'text' && (
            element ? (
              <div className="space-y-3">
                <div className="rounded-lg border border-dashed border-line bg-white px-3 py-2 text-[11px] leading-relaxed text-muted">
                  {typing
                    ? 'Typing is live on the canvas. Click Done typing when you finish.'
                    : 'Click Type on canvas to edit this selected text directly, or use the field below.'}
                </div>
                <button
                  type="button"
                  disabled={!element.textContent?.trim()}
                  onClick={() => onEditText?.(!typing)}
                  className={`${buttonClass} w-full justify-center`}
                >
                  <Type size={12} /> {typing ? 'Done typing' : 'Type on canvas'}
                </button>
                {!typing && (
                <label className="flex flex-col gap-1 text-[10px] text-muted">
                  Text content
                  <textarea
                    key={`text-${revision}`}
                    className={inputClass}
                    aria-label="Text content"
                    rows={4}
                    defaultValue={element.textContent || ''}
                    onBlur={event => event.target.value !== event.target.defaultValue && run(() => editor.text(event.target.value))}
                  />
                </label>
                )}
                <button className={`${buttonClass} text-rose-600`} onClick={() => run(() => editor.remove())}>
                  <Trash2 size={12} /> Delete selected element
                </button>
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-line bg-white px-3 py-5 text-center text-xs leading-relaxed text-muted">Select a text block to edit or remove it. Use the AI tool for structure, spacing, layout, and larger redesigns.</p>
            )
          )}

        </section>
      )}
    </aside>
  )
}
