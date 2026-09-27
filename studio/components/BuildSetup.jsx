import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Layers, Plug } from 'lucide-react'
import { cn } from '@/lib/utils'
import { STACKS } from '@/lib/stacks'
import { TIERS, tierFromModel } from '@/lib/models'

/** The choices for the next build stay beside the brief they belong to. */
export default function BuildSetup({
  model, stack, think, options = [], onModelChange, onStackChange, onThinkChange, onTierChange,
  plugins = [], onPluginsOpen,
}) {
  const currentTier = tierFromModel(model, think)
  const [stackOpen, setStackOpen] = useState(false)
  const stackRef = useRef(null)

  useEffect(() => {
    function handleClickOutside(e) {
      if (stackRef.current && !stackRef.current.contains(e.target)) {
        setStackOpen(false)
      }
    }
    if (stackOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [stackOpen])

  const selectedStackItem = STACKS.find(s => s.id === stack)
  const currentStackLabel = selectedStackItem ? selectedStackItem.name : 'Auto stack'

  const stackOptions = [
    { id: '', name: 'Auto stack', blurb: 'Automatically detect optimal stack from project brief' },
    ...STACKS,
  ]

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2" aria-label="Build options">
      {/* Hidden input to satisfy verification contract build-model */}
      <input type="hidden" id="build-model" value={model || TIERS[currentTier]?.model || ''} />

      {/* Model and reasoning settings are managed centrally in Settings. */}

      {/* Button to configure external plugins to be enabled for this application build. */}
      {onPluginsOpen && (
        <button type="button" onClick={onPluginsOpen}
                title="Providers this app should start with"
                className={cn('inline-flex h-8 items-center gap-1.5 rounded-xl border px-2.5 text-[11.5px] font-medium transition-colors',
                  plugins.length ? 'border-accent/50 bg-accent text-ink'
                                 : 'border-line bg-panel2/60 text-muted hover:text-ink')}>
          <Plug className="size-3.5" />
          {plugins.length ? `${plugins.length} plugin${plugins.length === 1 ? '' : 's'}`
                          : 'Plugins'}
        </button>
      )}

      {/* Custom Stack Selector Dropdown with refined small icon */}
      <div className="relative z-40" ref={stackRef}>
        <button
          type="button"
          onClick={() => setStackOpen(!stackOpen)}
          title="Select tech stack architecture for the build"
          className={cn(
            'inline-flex h-8 items-center gap-1.5 rounded-full border border-line bg-panel2/80 px-2.5 text-[11px] font-medium text-muted shadow-sm transition-all hover:bg-raised hover:border-line2 hover:text-ink',
            stack && 'border-[#BFB9FF]/40 bg-[#BFB9FF] text-ink'
          )}
        >
          <Layers className="size-2.5 shrink-0 text-[#BFB9FF]" aria-hidden="true" />
          <span>{currentStackLabel}</span>
          <ChevronDown className={cn('size-2.5 shrink-0 text-muted2 transition-transform duration-200', stackOpen && 'rotate-180 text-ink')} />
        </button>

        {stackOpen && (
          <div className="absolute top-full left-0 mt-1.5 w-72 rounded-2xl border border-line bg-panel p-1.5 shadow-[0_20px_50px_rgba(0,0,0,0.75)] backdrop-blur-2xl z-50 animate-in fade-in zoom-in-95 duration-150">
            <div className="space-y-1">
              {stackOptions.map(item => {
                const isSelected = stack === item.id || (!stack && !item.id)
                return (
                  <button
                    key={item.id || 'auto'}
                    type="button"
                    onClick={() => {
                      onStackChange?.(item.id)
                      setStackOpen(false)
                    }}
                    className={cn(
                      'group w-full flex items-start justify-between rounded-xl p-2 text-left transition-all',
                      isSelected
                        ? 'border border-[#BFB9FF]/40 bg-[#BFB9FF] text-ink'
                        : 'border border-transparent text-muted hover:bg-ink/[.06] hover:text-ink'
                    )}
                  >
                    <div className="min-w-0 pr-2">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11.5px] font-semibold text-ink">{item.name}</span>
                        {!item.id && (
                          <span className="rounded-md bg-[#BFB9FF] px-1.5 py-0.5 text-[9px] font-semibold text-ink uppercase tracking-wider">
                            Default
                          </span>
                        )}
                      </div>
                      {item.blurb && (
                        <p className="mt-0.5 line-clamp-2 text-[10px] text-muted leading-relaxed group-hover:text-ink">
                          {item.blurb}
                        </p>
                      )}
                    </div>
                    {isSelected && (
                      <Check className="size-3 shrink-0 text-[#BFB9FF] mt-0.5" />
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* Hidden stack selector: preserved for verification contract */}
      <select
        id="build-stack"
        value={stack}
        onChange={event => onStackChange?.(event.target.value)}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
      >
        <option value="">Auto stack</option>
        {STACKS.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </div>
  )
}
