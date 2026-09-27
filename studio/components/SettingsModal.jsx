'use client'

import { useEffect, useState } from 'react'
import {
  Check, Cpu, Database, Keyboard,
  LayoutGrid, Loader2, Palette, Plug, SlidersHorizontal, X, Link2,
} from 'lucide-react'
import { api } from '@/lib/api'
import { Modal } from './ui'
import { cn } from '@/lib/utils'
import { useStore } from '@/lib/store'
import { useAuthStore } from '@/lib/auth'
import { modelLabel } from '@/lib/models'
import DeployAccounts from './deploy/DeployAccounts'
import PluginAccounts from './PluginAccounts'

/** Model picker interface for selecting and configuring LLM models across all agent roles. */
function ModelPicker({ meta, onSaved }) {
  const [catalog, setCatalog] = useState(null)
  const [chosen, setChosen] = useState('')
  const [think, setThink] = useState(true)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  // Server-synced state to track whether chosen model settings have been saved.
  const [saved, setSaved] = useState({ model: '', think: true })

  useEffect(() => {
    if (!meta) return
    setChosen(meta.agent_model || '')
    setThink(meta.agent_think !== false)
    setSaved({ model: meta.agent_model || '', think: meta.agent_think !== false })
  }, [meta])

  useEffect(() => {
    let alive = true
    api.models().then(d => { if (alive) setCatalog(d) }).catch(() => { if (alive) setCatalog({}) })
    return () => { alive = false }
  }, [])

  async function save() {
    setBusy(true); setNote('')
    try {
      await api.saveSettings({ agent_model: chosen, agent_think: think })
      // The server's `agent_model` is only a fallback: the studio keeps a
      // model per role and sends it on every run, so without this the saved
      // choice would lose to whatever those roles already held.
      const roles = useStore.getState().applyModel(chosen)
      setSaved({ model: chosen, think })
      setNote(`saved — ${roles.length} agents now use it`)
      onSaved?.()
    } catch (failure) { setNote(failure.message) } finally { setBusy(false) }
  }

  const dirty = chosen !== saved.model || think !== saved.think

  const groups = [
    ['On this machine', catalog?.local_models || []],
    ['Cloud', catalog?.cloud || []],
  ]
  const anything = groups.some(([, rows]) => rows.length)

  return (
    <div className="max-w-[700px] space-y-4">
      <div className="flex items-center justify-between rounded-2xl border border-line bg-panel px-4 py-3.5 shadow-sm">
        <div>
          <p className="text-[12.5px] font-medium text-ink">Thinking</p>
          <p className="mt-0.5 text-[11px] text-muted">
            Reasoning before answering. Slower, and better on hard changes. The
            specification agent never uses it.
          </p>
        </div>
        <button type="button" disabled={busy} onClick={() => { setThink(!think); setNote('') }}
          aria-pressed={think}
          className={cn('h-6 w-11 shrink-0 rounded-full border transition-colors',
            think ? 'border-accent bg-accent' : 'border-line bg-panel2')}>
          <span className={cn('block size-4 rounded-full bg-white transition-transform',
            think ? 'translate-x-6' : 'translate-x-1')} />
        </button>
      </div>

      <div className="rounded-2xl border border-line bg-panel shadow-sm">
        {!catalog && <p className="px-4 py-3.5 text-[11.5px] text-muted">Reading the model list…</p>}
        {catalog && !anything && (
          <p className="px-4 py-3.5 text-[11.5px] text-muted">
            Ollama reported no models. Start it, or pull one, and reopen this tab.
          </p>
        )}
        {groups.map(([label, rows]) => rows.length > 0 && (
          <div key={label}>
            <p className="border-b border-line px-4 pb-1.5 pt-3 text-[10px] uppercase tracking-wider text-muted2">
              {label}
            </p>
            <div className="divide-y divide-line">
              {rows.map(row => {
                const id = row.id || row
                const picked = id === chosen
                return (
                  <button key={id} type="button" disabled={busy}
                    onClick={() => { setChosen(id); setNote('') }}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-panel2">
                    <span className={cn('grid size-4 shrink-0 place-items-center rounded-full border',
                      picked ? 'border-accent bg-accent' : 'border-line')}>
                      {picked && <Check className="size-2.5 text-ink" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] text-ink">
                        {modelLabel ? modelLabel(id) : id}
                      </span>
                      <span className="block truncate font-mono text-[10px] text-muted2">{id}</span>
                    </span>
                    {row.installed === false && (
                      <span className="shrink-0 text-[10px] text-muted2">not pulled</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <p className="min-w-0 flex-1 text-[11px] text-muted">
          {busy ? 'Saving…'
                : note
                || (dirty ? 'Not saved yet — nothing uses this until you save it.'
                          : 'Every build, prototype, specification, test and deployment '
                            + 'uses this model.')}
        </p>
        <button type="button" disabled={busy || !chosen || !dirty} onClick={save}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-accent px-4 py-2 text-[11.5px] font-semibold text-ink transition-colors hover:bg-press disabled:opacity-40">
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
          Save
        </button>
      </div>
    </div>
  )
}

export default function SettingsModal({ onClose, onSaved }) {
  const theme = useStore(s => s.theme)
  const setTheme = useStore(s => s.setTheme)
  const user = useAuthStore(s => s.user)
  // The open project, so the Plugins tab can offer to tick them for it rather
  // than only hold the credentials.
  const project = useStore(s => s.project)

  const [activeTab, setActiveTab] = useState('general')

  // Real server settings — loaded via api.settings()
  const [host, setHost] = useState('')
  const [ctx, setCtx] = useState('')
  const [key, setKey] = useState('')
  const [mongo, setMongo] = useState('')
  const [meta, setMeta] = useState(null)
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState('loading…')
  const [tone, setTone] = useState('muted')

  useEffect(() => {
    let alive = true
    api.settings()
      .then(d => {
        if (!alive) return
        setHost(d.ollama_host || '')
        setCtx(d.local_num_ctx || '')
        setMeta(d)
        setNote(d.cloud_enabled ? 'cloud enabled' : 'cloud off — local only')
        setTone(d.cloud_enabled ? 'ok' : 'muted')
      })
      .catch(() => { if (alive) { setNote('server offline'); setTone('bad') } })
    return () => { alive = false }
  }, [])

  async function save() {
    setSaving(true)
    setNote('saving…')
    setTone('muted')
    const body = { ollama_host: host.trim(), local_num_ctx: String(ctx).trim() }
    if (key.trim()) body.ollama_api_key = key.trim()
    if (mongo.trim()) body.mongodb_uri = mongo.trim() === '-' ? '' : mongo.trim()
    try {
      const d = await api.saveSettings(body)
      setNote(!d.cloud_enabled ? 'cloud off — local only'
        : d.cloud_reachable ? 'cloud key verified' : 'key saved but not accepted')
      setTone(!d.cloud_enabled ? 'muted' : d.cloud_reachable ? 'ok' : 'bad')
      onSaved?.()
      if (d.cloud_reachable) setTimeout(onClose, 800)
    } catch (e) {
      setNote('save failed — ' + e.message)
      setTone('bad')
    }
    setSaving(false)
  }

  const cloudOn = tone === 'ok'
  // AgentForge's own engine and database are the whole machine's, so they are
  // its admin's. Everyone's deployment accounts are their own — Integrations.
  const isAdmin = Boolean(meta?.admin)

  const displayName = user?.name || user?.username || 'User'
  const displayEmail = user?.email || ''
  const initial = (user?.name || user?.username || 'U')[0]?.toUpperCase() || 'U'

  const settingsNav = [
    { id: 'general',      label: 'General',      Icon: SlidersHorizontal },
    { id: 'application',  label: 'Application',  Icon: LayoutGrid },
    { id: 'models',       label: 'Models',       Icon: Cpu },
    { id: 'appearance',   label: 'Appearance',   Icon: Palette },
    { id: 'integrations', label: 'Integrations', Icon: Link2 },
    { id: 'plugins',      label: 'Plugins',      Icon: Plug },
    { id: 'shortcuts',    label: 'Shortcuts',    Icon: Keyboard },
  ]

  return (
    <Modal onClose={onClose} className="max-w-none w-[min(1040px,95vw)] h-[min(650px,90vh)] p-0 overflow-hidden flex flex-col rounded-3xl border border-line bg-panel shadow-2xl">
      <div className="flex flex-col sm:flex-row flex-1 min-h-0 overflow-hidden">

        {/* ── Left Sidebar / Mobile Top Nav ── */}
        <aside className="w-full sm:w-56 shrink-0 border-b sm:border-b-0 sm:border-r border-line bg-panel2/50 flex sm:flex-col justify-between p-2 sm:p-3 select-none">
          <div className="flex-1 overflow-x-auto sm:overflow-y-auto no-scrollbar sm:pr-1">
            <div className="hidden sm:block px-2.5 pb-2 pt-1 text-[11px] font-semibold uppercase tracking-wider text-muted2">
              Settings
            </div>
            <div className="flex sm:flex-col gap-1 sm:gap-0.5">
              {settingsNav.map(item => {
                const active = activeTab === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setActiveTab(item.id)}
                    className={cn(
                      'shrink-0 sm:w-full flex items-center gap-2 sm:gap-2.5 px-2.5 py-1.5 rounded-xl text-left text-[12px] whitespace-nowrap transition-all',
                      active
                        ? 'bg-[#BFB9FF] text-ink font-semibold shadow-sm'
                        : 'text-muted hover:text-ink hover:bg-ink/[.06] font-medium'
                    )}
                  >
                    <item.Icon className={cn('size-3.5 shrink-0', active ? 'text-[#BFB9FF]' : 'text-muted2')} />
                    <span>{item.label}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* User profile footer */}
          <div className="hidden sm:block pt-2 border-t border-line">
            <div className="flex items-center gap-2.5 px-2 py-2 rounded-xl bg-ink/[.04] border border-line">
              <div className="size-7 rounded-full bg-[#BFB9FF] flex items-center justify-center text-[12px] font-bold text-ink shrink-0 shadow-md shadow-[#BFB9FF]/25">
                {initial}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[11.5px] font-semibold text-ink">{displayName}</div>
                {displayEmail && (
                  <div className="truncate text-[10px] text-muted font-mono">{displayEmail}</div>
                )}
              </div>
            </div>
          </div>
        </aside>

        {/* ── Right Content ── */}
        <main className="flex-1 flex flex-col min-w-0 bg-bg overflow-hidden">
          {/* Header */}
          <header className="h-[52px] sm:h-[58px] shrink-0 border-b border-line px-4 sm:px-6 flex items-center justify-between">
            <div className="min-w-0 flex-1 pr-2">
              <h2 className="font-display text-[15px] sm:text-[16px] font-bold tracking-tight text-ink truncate">
                {activeTab === 'general'      ? 'General'
               : activeTab === 'application'  ? 'Application'
               : activeTab === 'models'       ? 'AI Models'
               : activeTab === 'appearance'   ? 'Appearance'
               : activeTab === 'integrations' ? 'Integrations'
               : activeTab === 'plugins'      ? 'Plugins'
               : 'Keyboard Shortcuts'}
              </h2>
              <p className="text-[10.5px] sm:text-[11px] text-muted mt-0.5 truncate">
                {activeTab === 'general'
                  ? isAdmin ? 'Ollama engine, API key and MongoDB connection.'
                            : 'What this machine runs, and what is yours.'
                  : activeTab === 'application'
                  ? 'Running services and database status.'
                  : activeTab === 'models'
                  ? isAdmin ? 'One model, used by every agent. Choose it, then save.'
                            : 'The model every agent uses on this machine.'
                  : activeTab === 'appearance'
                  ? 'Studio visual theme.'
                  : activeTab === 'integrations'
                  ? 'Connect GitHub, AWS, Vercel, Netlify, Azure and your production database.'
                  : activeTab === 'plugins'
                  ? 'Stripe, Resend, Supabase, Google and the rest — set up once, used by any app you tick.'
                  : 'Key bindings active in AgentForge Studio.'}
              </p>
            </div>
            <button
              onClick={onClose}
              title="Close"
              className="rounded-xl p-1.5 text-[#6B7280] hover:bg-[rgba(145,158,171,0.08)] hover:text-ink transition-all shrink-0"
            >
              <X className="size-4" />
            </button>
          </header>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5 text-ink" style={{ scrollbarWidth: 'thin' }}>

            {/* ── GENERAL ── */}
            {activeTab === 'general' && !isAdmin && (
              <div className="space-y-4 max-w-[700px]">
                <p className="rounded-2xl border border-line bg-panel px-4 py-3 text-[12px] text-muted">
                  The Ollama engine, its key and AgentForge's own database are
                  shared by everyone on this machine, so only its admin changes
                  them. Your GitHub, AWS, Vercel and production database are
                  yours alone — they are under <b className="text-ink">Integrations</b>.
                </p>
                <MongoState mongo={meta?.mongo} />
              </div>
            )}

            {activeTab === 'general' && isAdmin && (
              <div className="space-y-5 max-w-[700px]">
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="block">
                    <span className="mb-1.5 block text-[11.5px] font-semibold text-muted">Ollama Host</span>
                    <input
                      value={host}
                      onChange={e => setHost(e.target.value)}
                      placeholder="http://127.0.0.1:11434"
                      className="w-full rounded-xl border border-line bg-panel2/60 px-3 py-2 text-[12.5px] text-ink outline-none placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent transition-colors"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-1.5 block text-[11.5px] font-semibold text-muted">ollama.com API Key</span>
                    <input
                      type="password"
                      value={key}
                      onChange={e => setKey(e.target.value)}
                      placeholder={meta?.api_key_hint ? `saved (${meta.api_key_hint})` : 'Paste your key'}
                      className="w-full rounded-xl border border-line bg-panel2/60 px-3 py-2 text-[12.5px] text-ink outline-none placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent transition-colors"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-1.5 block text-[11.5px] font-semibold text-muted">Local Context Window</span>
                    <input
                      value={ctx}
                      onChange={e => setCtx(e.target.value)}
                      placeholder="e.g. 32768"
                      className="w-full rounded-xl border border-line bg-panel2/60 px-3 py-2 text-[12.5px] text-ink outline-none placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent transition-colors"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-1.5 block text-[11.5px] font-semibold text-muted">MongoDB URI</span>
                    <input
                      value={mongo}
                      onChange={e => setMongo(e.target.value)}
                      placeholder={meta?.mongodb_uri_set ? `saved (${meta.mongodb_uri_hint})` : 'mongodb+srv://…'}
                      className="w-full rounded-xl border border-line bg-panel2/60 px-3 py-2 text-[12.5px] text-ink outline-none placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent transition-colors"
                    />
                  </label>
                </div>

                <MongoState mongo={meta?.mongo} />

                <div className="flex items-center justify-between pt-4 border-t border-line">
                  <div className="flex items-center gap-2 text-[11.5px]">
                    <span className={cn(
                      'size-2 rounded-full',
                      cloudOn ? 'bg-[#22C55E] shadow-[0_0_6px_rgba(34,197,94,0.6)]'
                      : tone === 'bad' ? 'bg-[#FF5630]'
                      : 'bg-[#FFAB00]'
                    )} />
                    <span className="text-muted font-mono">{note}</span>
                  </div>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={save}
                    className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-[12px] font-semibold text-ink shadow-sm hover:bg-press disabled:opacity-50 transition-all active:scale-95 cursor-pointer"
                  >
                    {saving && <Loader2 className="size-3.5 animate-spin" />}
                    Save Settings
                  </button>
                </div>
              </div>
            )}

            {/* ── APPLICATION ── */}
            {activeTab === 'application' && (
              <div className="space-y-4 max-w-[700px]">
                <div className="rounded-2xl border border-line bg-panel divide-y divide-line shadow-sm">
                  {[
                    { name: 'HTTP Gateway',     desc: 'API server on port 7824',              status: 'Running' },
                    { name: 'WebSocket Bridge', desc: 'Live stream on ws://127.0.0.1:7825',   status: 'Connected' },
                    { name: 'SRS Agent',        desc: 'Specification planner on port 7826',   status: 'Running' },
                  ].map(svc => (
                    <div key={svc.name} className="flex items-center justify-between p-4">
                      <div>
                        <div className="text-[13px] font-medium text-ink">{svc.name}</div>
                        <div className="text-[11.5px] text-muted mt-0.5">{svc.desc}</div>
                      </div>
                      <span className="rounded-lg bg-[#22C55E]/15 border border-[#22C55E]/20 px-2.5 py-0.5 text-[11px] font-semibold text-ink">
                        {svc.status}
                      </span>
                    </div>
                  ))}
                </div>

                <MongoState mongo={meta?.mongo} />

                {isAdmin && meta?.mongo && !meta.mongo.downloaded && !meta.mongo.override && (
                  <button
                    type="button"
                    onClick={() => api.mongoPrefetch().catch(() => {})}
                    className="rounded-xl border border-line bg-panel2/60 px-4 py-2 text-[12px] font-medium text-ink hover:bg-raised transition-colors"
                  >
                    Download mongod binary
                  </button>
                )}
              </div>
            )}

            {/* ── MODELS ── */}
            {activeTab === 'models' && (
              isAdmin
                ? <ModelPicker meta={meta} onSaved={onSaved} />
                : <div className="max-w-[700px] space-y-4">
                    <p className="rounded-2xl border border-line bg-panel px-4 py-3 text-[12px] text-muted">
                      The model every agent uses is shared by everyone on this
                      machine, so only its admin changes it. It is currently{' '}
                      <b className="text-ink">
                        {meta?.agent_model ? (modelLabel ? modelLabel(meta.agent_model)
                                                         : meta.agent_model)
                                           : 'whatever Ollama reports as largest'}
                      </b>
                      {meta?.agent_think === false ? ', with thinking off.' : '.'}
                    </p>
                  </div>
            )}

            {/* ── APPEARANCE ── */}
            {activeTab === 'appearance' && (
              <div className="space-y-4 max-w-[700px]">
                <div className="rounded-2xl border border-line bg-panel p-5 shadow-sm">
                  <div className="text-[13px] font-semibold text-ink mb-1">Color Theme</div>
                  <p className="text-[11.5px] text-muted mb-4">Material Kit Dark is the default design system for AgentForge Studio.</p>
                  <div className="max-w-[340px]">
                    <div
                      className="relative rounded-xl border-2 border-[#BFB9FF] bg-[#F2F0EF] p-4 text-left shadow-[0_0_20px_rgba(191, 185, 255,0.18)] ring-1 ring-[#BFB9FF]/40"
                    >
                      <div className="flex gap-1.5 mb-3">
                        <span className="size-2.5 rounded-full bg-[#BFB9FF]" />
                        <span className="size-2.5 rounded-full bg-[#BFB9FF]" />
                        <span className="size-2.5 rounded-full bg-[#22C55E]" />
                      </div>
                      <div className="text-[12.5px] font-semibold text-ink">Material Kit Dark</div>
                      <div className="text-[11px] text-[#6B7280] mt-0.5">
                        Active theme (Default)
                      </div>
                      <div className="absolute top-3 right-3 size-5 rounded-full bg-[#BFB9FF] flex items-center justify-center text-ink shadow-sm">
                        <Check className="size-3" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* ── INTEGRATIONS ── */}
            {activeTab === 'integrations' && (
              <div className="space-y-4 max-w-[700px]">
                <DeployAccounts deploy={meta?.deploy} onSaved={() => {
                  api.settings().then(setMeta).catch(() => {})
                  onSaved?.()
                }} />
              </div>
            )}

            {/* ── PLUGINS ── */}
            {/* Global plugin account configuration and per-project plugin activation. */}
            {activeTab === 'plugins' && (
              <div className="max-w-[700px]">
                <PluginAccounts project={project} />
              </div>
            )}

            {/* ── SHORTCUTS ── */}
            {activeTab === 'shortcuts' && (
              <div className="max-w-[700px]">
                <div className="rounded-2xl border border-[rgba(145,158,171,0.16)] bg-[#F2F0EF] divide-y divide-[rgba(145,158,171,0.12)]">
                  {[
                    { key: 'Ctrl + Enter', action: 'Submit prompt and start build' },
                    { key: 'Escape',       action: 'Close modal or dropdown' },
                    { key: 'Ctrl + /',     action: 'Focus prompt input' },
                  ].map((s, i) => (
                    <div key={i} className="flex items-center justify-between px-4 py-3.5">
                      <span className="text-[12.5px] text-ink">{s.action}</span>
                      <kbd className="rounded-lg border border-[rgba(145,158,171,0.2)] bg-[#F2F0EF] px-2.5 py-1 font-mono text-[11px] text-ink font-medium">
                        {s.key}
                      </kbd>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        </main>
      </div>
    </Modal>
  )
}

function MongoState({ mongo }) {
  if (!mongo) return null
  let text, tone
  if (mongo.override) {
    text = 'using your MONGODB_URI'
    tone = 'text-ink'
  } else if (mongo.running) {
    text = mongo.external
      ? `adopted the MongoDB already on :${mongo.port}`
      : `MongoDB running on :${mongo.port}`
    tone = 'text-ink'
  } else if (mongo.downloaded) {
    text = 'mongod downloaded, not running'
    tone = 'text-[#FFAB00]'
  } else {
    text = mongo.reason || 'mongod not downloaded yet'
    tone = mongo.reason ? 'text-[#FF5630]' : 'text-[#6B7280]'
  }
  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-[rgba(145,158,171,0.16)] bg-[#F2F0EF] px-3.5 py-2.5 font-mono text-[11px]">
      <Database className="size-3.5 shrink-0 text-[#BFB9FF]" />
      <span className={tone}>{text}</span>
    </div>
  )
}
