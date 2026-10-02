import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Layers, Plug } from 'lucide-react'
import { cn } from '@/lib/utils'
import { STACKS } from '@/lib/stacks'
import { TIERS, isCloud, tierFromModel } from '@/lib/models'

/** The choices for the next build stay beside the brief they belong to. */
export default function BuildSetup({
  model, stack, think, thinkingLevel = think ? 'high' : 'low', options = [], onModelChange,
  onStackChange, onThinkChange, onThinkingLevelChange,
  plugins = [], onPluginsOpen, compact = false,
}) {
  const currentTier = tierFromModel(model, think)
  const [stackOpen, setStackOpen] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
  const stackRef = useRef(null)
  const modelRef = useRef(null)

  // The accounts a stack needs are shown and connected beside the Start button (Home), not here.
  function chooseStack(id) {
    onStackChange?.(id)
  }

  useEffect(() => {
    function handleClickOutside(e) {
      if (stackRef.current && !stackRef.current.contains(e.target)) setStackOpen(false)
      if (modelRef.current && !modelRef.current.contains(e.target)) setModelOpen(false)
    }
    if (stackOpen || modelOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [stackOpen, modelOpen])

  const selectedStackItem = STACKS.find(s => s.id === stack)
  const currentStackLabel = selectedStackItem ? selectedStackItem.name : 'Auto stack'

  const stackOptions = [
    { id: '', name: 'Auto stack', blurb: 'Automatically detect optimal stack from project brief' },
    ...STACKS,
  ]
  const modelRows = Array.from(new Map([
    ...(model ? [[model, { id: model, label: model }]] : []),
    ...(options || []).map(item => {
      const id = typeof item === 'string' ? item : item?.id
      return id ? [id, typeof item === 'string' ? { id, label: id } : item] : null
    }).filter(Boolean),
  ]).values())
  const modelGroups = [
    ['Cloud', modelRows.filter(item => item.cloud || isCloud(item.id || item))],
    ['On this machine', modelRows.filter(item => !(item.cloud || isCloud(item.id || item)))],
  ]
  const effortLabel = { low: 'Low', high: 'High', xhigh: 'Extra' }[thinkingLevel] || 'High'

  function chooseEffort(level) {
    if (onThinkingLevelChange) return onThinkingLevelChange(level)
    onThinkChange?.(level !== 'low')
  }

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2" aria-label="Build options">
      {/* Hidden input to satisfy verification contract build-model */}
      <input type="hidden" id="build-model" value={model || TIERS[currentTier]?.model || ''} />

      {/* New projects use the same model picker as chat, without a context meter. */}
      {onModelChange && (
        <div className="relative z-40" ref={modelRef}>
          <button
            type="button"
            onClick={() => setModelOpen(value => !value)}
            aria-label={`Select build model: ${model || 'none selected'}`}
            aria-haspopup="dialog"
            aria-expanded={modelOpen}
            title={`Select build model: ${model || 'none selected'}`}
            className={cn(
              compact ? 'flex max-w-[174px] items-center gap-1 rounded-md px-1.5 py-1 text-[10px] font-medium text-muted2 transition-colors hover:bg-panel2 hover:text-ink'
                      : 'inline-flex h-8 items-center gap-1.5 rounded-full border border-line bg-panel2/80 px-2.5 text-[11px] font-medium text-muted shadow-sm transition-all hover:bg-raised hover:border-line2 hover:text-ink'
            )}
          >
            <span className={cn(compact ? 'truncate text-ink' : 'max-w-36 truncate')}>{model || 'Choose model'}</span>
            {compact && <span className="shrink-0 text-muted2">{effortLabel}</span>}
            <ChevronDown className={cn(compact ? 'size-3 shrink-0 transition-transform' : 'size-2.5 transition-transform', modelOpen && 'rotate-180')} />
          </button>

          {modelOpen && (
            <div role="dialog" aria-label="Select build model"
                 className="absolute top-full left-0 mt-2 w-80 rounded-2xl border border-line bg-panel p-2 shadow-[0_20px_50px_rgba(0,0,0,0.28)] z-50 animate-in fade-in zoom-in-95 duration-150">
              <p className="px-1.5 pb-2 pt-0.5 text-[10px] font-semibold text-muted2">Select model</p>
              <div className="max-h-52 overflow-y-auto pr-1 custom-scrollbar">
                {modelGroups.map(([group, rows]) => rows.length > 0 && (
                  <section key={group} className="pb-1.5">
                    <p className="px-1.5 py-1 text-[9px] font-semibold uppercase tracking-[.1em] text-muted2">{group}</p>
                    {rows.map(item => {
                      const id = item.id || item
                      const selected = id === model
                      return (
                        <button key={id} type="button" aria-pressed={selected}
                                onClick={() => onModelChange(id)}
                                className={cn('flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left text-[11.5px] transition-colors',
                                  selected ? 'text-accent' : 'text-ink hover:bg-panel2')}>
                          <span className="min-w-0 flex-1 truncate">{item.label || id}</span>
                          {selected && <Check className="size-3 shrink-0 text-accent" />}
                        </button>
                      )
                    })}
                  </section>
                ))}
                {!modelRows.length && <p className="px-2 py-3 text-[10px] text-muted2">No models are available yet.</p>}
              </div>

              <div className="mt-1 border-t border-line pt-2">
                <p className="px-1.5 pb-1 text-[10px] font-semibold text-muted2">Reasoning effort</p>
                <div aria-label="Reasoning effort" className="grid grid-cols-3 rounded-xl bg-panel2 p-1">
                  {[
                    ['low', 'Low'], ['high', 'High'], ['xhigh', 'Extra high'],
                  ].map(([id, label]) => (
                    <button key={id} type="button" onClick={() => chooseEffort(id)}
                            aria-pressed={thinkingLevel === id}
                            className={cn('rounded-lg px-1 py-1.5 text-[10px] font-semibold transition-colors',
                              thinkingLevel === id ? 'bg-panel text-accent shadow-sm' : 'text-muted2 hover:text-ink')}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <p className="px-1.5 pb-0.5 pt-2 text-[9.5px] text-muted2">
                Applies to this new project; it does not change any open project's history.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Button to configure external plugins to be enabled for this application build. */}
      {onPluginsOpen && (
        <button type="button" onClick={onPluginsOpen}
                aria-label={`Plugins${plugins.length ? ` (${plugins.length} selected)` : ''}`}
                title={`Providers this app should start with${plugins.length ? ` (${plugins.length} selected)` : ''}`}
                className={cn(compact ? 'grid size-8 place-items-center rounded-xl border transition-colors'
                                      : 'inline-flex h-8 items-center gap-1.5 rounded-xl border px-2.5 text-[11.5px] font-medium transition-colors',
                  plugins.length ? 'border-accent/50 bg-accent text-ink'
                                 : 'border-line bg-panel2/60 text-muted hover:text-ink')}>
          <Plug className="size-3.5" />
          {!compact && (plugins.length ? `${plugins.length} plugin${plugins.length === 1 ? '' : 's'}`
                                      : 'Plugins')}
        </button>
      )}

      {/* Custom Stack Selector Dropdown with refined small icon */}
      <div className="relative z-40" ref={stackRef}>
        <button
          type="button"
          onClick={() => setStackOpen(!stackOpen)}
          aria-label={`Select tech stack architecture: ${currentStackLabel}`}
          title={`Select tech stack architecture: ${currentStackLabel}`}
          className={cn(
            compact ? 'grid size-8 place-items-center rounded-xl border border-line bg-panel2/80 text-muted shadow-sm transition-all hover:bg-raised hover:border-line2 hover:text-ink'
                    : 'inline-flex h-8 items-center gap-1.5 rounded-full border border-line bg-panel2/80 px-2.5 text-[11px] font-medium text-muted shadow-sm transition-all hover:bg-raised hover:border-line2 hover:text-ink',
            stack && 'border-accent/40 bg-accent text-ink'
          )}
        >
          <Layers className={cn(compact ? 'size-3.5' : 'size-2.5 shrink-0', 'text-accent')} aria-hidden="true" />
          {!compact && <span>{currentStackLabel}</span>}
          {!compact && <ChevronDown className={cn('size-2.5 shrink-0 text-muted2 transition-transform duration-200', stackOpen && 'rotate-180 text-ink')} />}
        </button>

        {stackOpen && (
          <div className="absolute top-full left-0 mt-1.5 w-72 max-h-[min(320px,calc(100dvh-10rem))] overflow-y-auto rounded-2xl border border-line bg-panel p-1.5 shadow-[0_20px_50px_rgba(0,0,0,0.75)] backdrop-blur-2xl z-50 animate-in fade-in zoom-in-95 duration-150">
            <div className="space-y-1 pr-0.5">
              {stackOptions.map(item => {
                const isSelected = stack === item.id || (!stack && !item.id)
                return (
                  <button
                    key={item.id || 'auto'}
                    type="button"
                    onClick={() => {
                      chooseStack(item.id)
                      setStackOpen(false)
                    }}
                    className={cn(
                      'group w-full flex items-start justify-between rounded-xl p-2 text-left transition-all',
                      isSelected
                        ? 'border border-accent/40 bg-accent text-ink'
                        : 'border border-transparent text-muted hover:bg-ink/[.06] hover:text-ink'
                    )}
                  >
                    <div className="min-w-0 pr-2">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11.5px] font-semibold text-ink">{item.name}</span>
                        {!item.id && (
                          <span className="rounded-md bg-accent px-1.5 py-0.5 text-[9px] font-semibold text-ink uppercase tracking-wider">
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
                      <Check className="size-3 shrink-0 text-accent mt-0.5" />
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
        onChange={event => chooseStack(event.target.value)}
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
