'use client'

/**
 * The mode menu, the way Claude Code has it: what the agent may do without asking. Beside the chat input (for the open
 * project) and beside the first input of a new project (the mode it starts in).
 */
import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, ShieldAlert } from 'lucide-react'

import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { cn } from '@/lib/utils'

export const MODES = [
  { id: 'auto', label: 'Auto', hint: 'The agent edits and runs its commands on its own, and asks only before something risky' },
  { id: 'manual', label: 'Manual', hint: 'Always ask before making changes' },
  { id: 'accept_edits', label: 'Accept edits', hint: 'File edits and the usual web commands (npm, node, git…) go ahead; other commands are asked' },
]
const BYPASS = { id: 'bypass', label: 'Bypass permissions', hint: 'Nothing is asked and nothing is refused' }

export function modeLabel(id) {
  return [...MODES, BYPASS].find(mode => mode.id === id)?.label || 'Auto'
}

/** The current mode of a project, or the one a new project starts in. */
export function useMode(project) {
  return useStore(s => (project ? s.permissionModeByProject[project] : undefined) ?? s.defaultPermissionMode)
}

export default function PermissionMode({ project = null, className = '' }) {
  const mode = useMode(project)
  const bypassEnabled = useStore(s => s.bypassEnabled)
  const loaded = useStore(s => s.permissionsLoaded)
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const root = useRef(null)

  useEffect(() => {
    if (loaded) return
    api.permissions().then(status => useStore.getState().setPermissionSettings({
      defaultPermissionMode: status.default || 'auto', bypassEnabled: Boolean(status.bypass_enabled), permissionsLoaded: true,
    })).catch(() => {})
  }, [loaded])

  async function choose(id) {
    setOpen(false)
    setConfirming(false)
    if (id === mode) return
    const store = useStore.getState()
    const before = mode
    try {
      if (project) {
        store.setPermissionMode(project, id)                    // a typed change reads this at once
        await api.setPermissionMode(project, id)
      } else {
        store.setPermissionSettings({ defaultPermissionMode: id })
        await api.setPermissions({ default: id })
      }
    } catch (error) {
      if (project) store.setPermissionMode(project, before)
      else store.setPermissionSettings({ defaultPermissionMode: before })
      store.addLog('WARN', `Could not change the mode — ${error.message}`)
    }
  }

  async function setBypass(on) {
    setBusy(true)
    try {
      const status = await api.setPermissions({ bypass: on })
      const store = useStore.getState()
      store.setPermissionSettings({ bypassEnabled: Boolean(status.bypass_enabled), defaultPermissionMode: status.default || 'auto' })
      if (!on && project && mode === 'bypass') store.setPermissionMode(project, 'auto')
      setConfirming(false)
    } catch (error) {
      useStore.getState().addLog('WARN', `Could not change that — ${error.message}`)
    }
    setBusy(false)
  }

  useEffect(() => {
    if (!open) return undefined
    const onDown = event => { if (root.current && !root.current.contains(event.target)) { setOpen(false); setConfirming(false) } }
    const onKey = event => {
      if (event.key === 'Escape') { setOpen(false); setConfirming(false); return }
      const index = Number(event.key) - 1
      const rows = bypassEnabled ? [...MODES, BYPASS] : MODES
      if (index >= 0 && index < rows.length && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault()
        choose(rows[index].id)
      }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  })

  const risky = mode === 'bypass'
  return (
    <div ref={root} className={cn('relative', className)}>
      <button type="button" onClick={() => setOpen(value => !value)} aria-haspopup="menu" aria-expanded={open}
        title={`Mode: ${modeLabel(mode)}. ${[...MODES, BYPASS].find(m => m.id === mode)?.hint || ''}`}
        className={cn('inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors',
          risky ? 'bg-bad/10 text-bad hover:bg-bad/15' : 'bg-panel2 text-ink hover:bg-raised')}>
        {risky && <ShieldAlert className="size-3" />}
        {modeLabel(mode)}
        <ChevronDown className="size-3 text-muted2" />
      </button>

      {open && (
        <div role="menu" aria-label="Mode"
          className="absolute bottom-full left-0 z-50 mb-2 w-[330px] overflow-hidden rounded-2xl border border-line bg-white py-2 shadow-xl">
          <p className="px-4 pb-1 pt-1 text-[12.5px] font-medium text-muted2">Mode</p>
          {MODES.map((item, index) => (
            <button key={item.id} type="button" role="menuitemradio" aria-checked={mode === item.id} onClick={() => choose(item.id)}
              className="flex w-full items-start gap-3 px-4 py-2 text-left transition-colors hover:bg-panel2">
              <span className="min-w-0 flex-1">
                <span className="block text-[14px] font-medium leading-snug text-ink">{item.label}</span>
                <span className="mt-0.5 block text-[12px] leading-snug text-muted">{item.hint}</span>
              </span>
              <span className="flex shrink-0 items-center gap-3 pt-0.5 text-[12.5px] text-muted2">
                {mode === item.id && <Check className="size-4 text-accent" />}
                <span className="w-2 text-right">{index + 1}</span>
              </span>
            </button>
          ))}
          <div className="mt-1 border-t border-line/70 pt-1">
            {bypassEnabled ? (
              <div className="flex items-center gap-3 px-4 py-2">
                <button type="button" role="menuitemradio" aria-checked={mode === 'bypass'} onClick={() => choose('bypass')}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left">
                  <span className="text-[14px] font-medium text-ink">{BYPASS.label}</span>
                  {mode === 'bypass' && <Check className="size-4 text-accent" />}
                </button>
                <button type="button" onClick={() => setBypass(false)} disabled={busy}
                  className="text-[12.5px] font-medium text-muted2 hover:text-ink disabled:opacity-50">Disable</button>
                <span className="w-2 text-right text-[12.5px] text-muted2">{MODES.length + 1}</span>
              </div>
            ) : confirming ? (
              <div className="px-4 py-2">
                <p className="text-[12.5px] leading-snug text-ink">
                  Bypass permissions lets the agent run any command and change any file without asking you, and nothing is refused.
                  Only use it in a project you can afford to lose.
                </p>
                <div className="mt-2 flex justify-end gap-2">
                  <button type="button" onClick={() => setConfirming(false)}
                    className="rounded-lg px-2.5 py-1 text-[12px] font-medium text-muted hover:bg-panel2">Cancel</button>
                  <button type="button" onClick={() => setBypass(true)} disabled={busy}
                    className="rounded-lg bg-ink px-2.5 py-1 text-[12px] font-semibold text-panel hover:opacity-85 disabled:opacity-50">Enable</button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between px-4 py-2">
                <span className="text-[14px] font-medium text-ink">{BYPASS.label}</span>
                <button type="button" onClick={() => setConfirming(true)}
                  className="text-[12.5px] font-semibold text-muted hover:text-ink">Enable</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
