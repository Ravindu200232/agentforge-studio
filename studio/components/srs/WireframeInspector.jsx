'use client'

import {
  RefreshCw,
  MousePointer2,
  Sparkles,
  Trash2,
  Undo2,
} from 'lucide-react'

/**
 * A deliberately small low-fidelity wireframe rail. Text is typed straight into the canvas where it is clicked;
 * layout, spacing, and components move through the page-level AI request instead of drag, swap or resize tools.
 */
export default function WireframeInspector({
  editor,
  onChange,
  onUndo,
  onRedraw,
  redrawing,
  onOpenAi,
  selectionMode,
  onSelectionMode,
}) {
  if (!editor) return null
  const element = editor.selected?.()

  const IconButton = ({ name, Icon, onClick, disabled = false, active = false }) => (
    <button
      type="button"
      title={name}
      aria-label={name}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={`grid size-9 place-items-center rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-30 ${
        active ? 'bg-accent/15 text-deep' : 'text-ink hover:bg-black/[.05]'}`}
    >
      <Icon size={15} />
    </button>
  )

  return (
    <aside aria-label="Wireframe tools" className="absolute left-3 top-3 z-40 flex items-start gap-2">
      <nav className="flex w-10 flex-col items-center gap-0.5 rounded-xl border border-line bg-panel p-1 shadow-xl">
        <IconButton
          name="Delete selected element"
          Icon={Trash2}
          disabled={!element}
          onClick={() => { editor.remove(); onChange?.() }}
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
        <IconButton name="Undo last user step" Icon={Undo2} disabled={!editor.hasHistory?.()} onClick={onUndo} />
      </nav>
    </aside>
  )
}
