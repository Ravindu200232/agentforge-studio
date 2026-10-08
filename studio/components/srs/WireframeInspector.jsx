'use client'

import {
  RefreshCw,
  RotateCw,
  MousePointer2,
  Sparkles,
  Type,
} from 'lucide-react'

/**
 * A deliberately small rail for the wireframe app. It does not move or resize anything: a change is either a few words
 * retyped in place, or asked for in words (about the whole page, or about the element picked in the preview).
 */
export default function WireframeInspector({
  mode,
  onMode,
  onOpenAi,
  aiOpen,
  onReload,
  onRegenerate,
  regenerating,
}) {
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
          name="Pick an element to ask the AI about"
          Icon={MousePointer2}
          active={mode === 'pick'}
          onClick={() => onMode?.(mode === 'pick' ? '' : 'pick')}
        />
        <IconButton
          name="Edit text: click any words on the page and retype them"
          Icon={Type}
          active={mode === 'text'}
          onClick={() => onMode?.(mode === 'text' ? '' : 'text')}
        />
        <IconButton name="Ask AI to update the wireframe" Icon={Sparkles} active={aiOpen} onClick={onOpenAi} />
        <span className="my-0.5 h-px w-6 bg-line" />
        <IconButton name="Reload the preview" Icon={RotateCw} onClick={onReload} />
        <IconButton name="Build the whole wireframe again" Icon={RefreshCw} onClick={onRegenerate} disabled={regenerating} />
      </nav>
    </aside>
  )
}
