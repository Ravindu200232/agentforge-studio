'use client'

import { useEffect, useRef, useState } from 'react'
import {
  Check, Database, Keyboard,
  LayoutGrid, Loader2, Network, Palette, Plug, SlidersHorizontal, X, Link2,
  Download, ExternalLink, FolderUp, LogOut,
} from 'lucide-react'
import { api } from '@/lib/api'
import { Modal } from './ui'
import { cn } from '@/lib/utils'
import { useStore } from '@/lib/store'
import { useAuthStore } from '@/lib/auth'
import DeployAccounts from './deploy/DeployAccounts'
import PluginAccounts from './PluginAccounts'
import McpServers from './McpServers'

export default function SettingsModal({ onClose, onSaved, onImport, onZip, onOpenInNewTab, onLogout, initialTab }) {
  const user = useAuthStore(s => s.user)
  // The open project, so the Plugins tab can offer to tick them for it rather
  // than only hold the credentials.
  const project = useStore(s => s.project)

  const [activeTab, setActiveTab] = useState(initialTab || 'general')
  const folderRef = useRef(null)

  // Real server settings — loaded via api.settings(). The AI engine is built into AgentForge: nothing to set here.
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
        setMeta(d)
        setNote('ready')
        setTone('ok')
      })
      .catch(() => { if (alive) { setNote('server offline'); setTone('bad') } })
    return () => { alive = false }
  }, [])

  async function save() {
    setSaving(true)
    setNote('saving…')
    setTone('muted')
    const body = {}
    if (mongo.trim()) body.mongodb_uri = mongo.trim() === '-' ? '' : mongo.trim()
    try {
      const d = await api.saveSettings(body)
      setMeta(d)
      setMongo('')
      setNote('saved')
      setTone('ok')
      onSaved?.()
    } catch (e) {
      setNote('save failed — ' + e.message)
      setTone('bad')
    }
    setSaving(false)
  }

  const cloudOn = tone === 'ok'
  // AgentForge's own database is the whole machine's, so it is its admin's.
  // Everyone's deployment accounts are their own — Integrations.
  const isAdmin = Boolean(meta?.admin)

  const displayName = user?.name || user?.username || 'User'
  const displayEmail = user?.email || ''
  const initial = (user?.name || user?.username || 'U')[0]?.toUpperCase() || 'U'

  const settingsNav = [
    { id: 'general',      label: 'General',      Icon: SlidersHorizontal },
    { id: 'application',  label: 'Application',  Icon: LayoutGrid },
    { id: 'appearance',   label: 'Appearance',   Icon: Palette },
    { id: 'integrations', label: 'Integrations', Icon: Link2 },
    { id: 'plugins',      label: 'Plugins',      Icon: Plug },
    { id: 'mcp',          label: 'MCP Servers',  Icon: Network },
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
                        ? 'bg-accent text-ink font-semibold shadow-sm'
                        : 'text-muted hover:text-ink hover:bg-ink/[.06] font-medium'
                    )}
                  >
                    <item.Icon className={cn('size-3.5 shrink-0', active ? 'text-accent' : 'text-muted2')} />
                    <span>{item.label}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* User profile footer */}
          <div className="hidden sm:block pt-2 border-t border-line">
            <div className="flex items-center gap-2.5 px-2 py-2 rounded-xl bg-ink/[.04] border border-line">
              <div className="size-7 rounded-full bg-accent flex items-center justify-center text-[12px] font-bold text-ink shrink-0 shadow-md shadow-[var(--accent)]/25">
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
               : activeTab === 'appearance'   ? 'Appearance'
               : activeTab === 'integrations' ? 'Integrations'
               : activeTab === 'plugins'      ? 'Plugins'
               : activeTab === 'mcp'          ? 'MCP Servers'
               : 'Keyboard Shortcuts'}
              </h2>
              <p className="text-[10.5px] sm:text-[11px] text-muted mt-0.5 truncate">
                {activeTab === 'general'
                  ? isAdmin ? 'AgentForge database connection and this workspace.'
                            : 'What this machine runs, and what is yours.'
                  : activeTab === 'application'
                  ? 'Running services and database status.'
                  : activeTab === 'appearance'
                  ? 'Studio visual theme.'
                  : activeTab === 'integrations'
                  ? 'Connect GitHub, AWS, Vercel, Netlify, Azure and your production database.'
                  : activeTab === 'plugins'
                  ? 'Stripe, Resend, Supabase, Google and the rest — set up once, used by any app you tick.'
                  : activeTab === 'mcp'
                  ? 'External MCP servers whose tools the agent can also call.'
                  : 'Key bindings active in AgentForge Studio.'}
              </p>
            </div>
            <button
              onClick={onClose}
              title="Close"
              className="rounded-xl p-1.5 text-muted hover:bg-raised hover:text-ink transition-all shrink-0"
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
                  AgentForge's own database is shared by everyone on this
                  machine, so only its admin changes it. Your GitHub, AWS, Vercel
                  and production database are yours alone — they are under{' '}
                  <b className="text-ink">Integrations</b>.
                </p>
                <MongoState mongo={meta?.mongo} />
                <WorkspaceActions project={project} folderRef={folderRef} onImport={onImport}
                                  onZip={onZip} onOpenInNewTab={onOpenInNewTab} onLogout={onLogout} />
              </div>
            )}

            {activeTab === 'general' && isAdmin && (
              <div className="space-y-5 max-w-[700px]">
                <div className="grid gap-4 sm:grid-cols-2">
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
                      cloudOn ? 'bg-ok shadow-[0_0_6px_rgba(34,197,94,0.6)]'
                      : tone === 'bad' ? 'bg-bad'
                      : 'bg-warn'
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
                <WorkspaceActions project={project} folderRef={folderRef} onImport={onImport}
                                  onZip={onZip} onOpenInNewTab={onOpenInNewTab} onLogout={onLogout} />
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
                      <span className="rounded-lg bg-ok/15 border border-ok/20 px-2.5 py-0.5 text-[11px] font-semibold text-ink">
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

            {/* ── APPEARANCE ── */}
            {activeTab === 'appearance' && (
              <div className="space-y-4 max-w-[700px]">
                <div className="rounded-2xl border border-line bg-panel p-5 shadow-sm">
                  <div className="text-[13px] font-semibold text-ink mb-1">Color Theme</div>
                  <p className="text-[11.5px] text-muted mb-4">Material Kit Dark is the default design system for AgentForge Studio.</p>
                  <div className="max-w-[340px]">
                    <div
                      className="relative rounded-xl border-2 border-accent bg-panel p-4 text-left shadow-[0_0_20px_rgba(191, 185, 255,0.18)] ring-1 ring-accent/40"
                    >
                      <div className="flex gap-1.5 mb-3">
                        <span className="size-2.5 rounded-full bg-accent" />
                        <span className="size-2.5 rounded-full bg-accent" />
                        <span className="size-2.5 rounded-full bg-ok" />
                      </div>
                      <div className="text-[12.5px] font-semibold text-ink">Material Kit Dark</div>
                      <div className="text-[11px] text-muted mt-0.5">
                        Active theme (Default)
                      </div>
                      <div className="absolute top-3 right-3 size-5 rounded-full bg-accent flex items-center justify-center text-ink shadow-sm">
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

            {/* ── MCP SERVERS ── */}
            {activeTab === 'mcp' && (
              isAdmin
                ? <McpServers meta={meta} onSaved={d => { setMeta(d); onSaved?.() }} />
                : <p className="max-w-[700px] rounded-2xl border border-line bg-panel px-4 py-3 text-[12px] text-muted">
                    MCP servers run as local commands on this machine, so only
                    its admin registers them.
                  </p>
            )}

            {/* ── SHORTCUTS ── */}
            {activeTab === 'shortcuts' && (
              <div className="max-w-[700px]">
                <div className="rounded-2xl border border-line bg-panel divide-y divide-[rgba(145,158,171,0.12)]">
                  {[
                    { key: 'Ctrl + Enter', action: 'Submit prompt and start build' },
                    { key: 'Escape',       action: 'Close modal or dropdown' },
                    { key: 'Ctrl + /',     action: 'Focus prompt input' },
                  ].map((s, i) => (
                    <div key={i} className="flex items-center justify-between px-4 py-3.5">
                      <span className="text-[12.5px] text-ink">{s.action}</span>
                      <kbd className="rounded-lg border border-line bg-panel px-2.5 py-1 font-mono text-[11px] text-ink font-medium">
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

function WorkspaceActions({ project, folderRef, onImport, onZip, onOpenInNewTab, onLogout }) {
  return (
    <section className="rounded-2xl border border-line bg-panel p-4 shadow-sm">
      <input ref={folderRef} type="file" hidden webkitdirectory="" directory="" multiple
             onChange={event => {
               const files = event.target.files
               event.target.value = ''
               if (files?.length) onImport?.(files)
             }} />
      <h3 className="text-[13px] font-semibold text-ink">Workspace actions</h3>
      <p className="mt-1 text-[11.5px] text-muted">Import a project or manage the open workspace.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button type="button" onClick={() => folderRef.current?.click()}
                className="inline-flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-left text-[11.5px] font-medium text-ink hover:bg-raised">
          <FolderUp className="size-3.5 text-muted2" /> Import project folder
        </button>
        <button type="button" disabled={!project} onClick={onZip}
                className="inline-flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-left text-[11.5px] font-medium text-ink hover:bg-raised disabled:cursor-not-allowed disabled:opacity-40">
          <Download className="size-3.5 text-muted2" /> Download project ZIP
        </button>
        <button type="button" disabled={!project} onClick={onOpenInNewTab}
                className="inline-flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-left text-[11.5px] font-medium text-ink hover:bg-raised disabled:cursor-not-allowed disabled:opacity-40">
          <ExternalLink className="size-3.5 text-muted2" /> Open in new tab
        </button>
      </div>
      {onLogout && (
        <div className="mt-3 border-t border-line pt-3">
          <button type="button" onClick={onLogout}
                  className="inline-flex items-center gap-2 rounded-xl border border-bad/35 px-3 py-2 text-[11.5px] font-medium text-bad hover:bg-raised">
            <LogOut className="size-3.5" /> Sign out
          </button>
        </div>
      )}
    </section>
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
    tone = 'text-warn'
  } else {
    text = mongo.reason || 'mongod not downloaded yet'
    tone = mongo.reason ? 'text-bad' : 'text-muted'
  }
  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-line bg-panel px-3.5 py-2.5 font-mono text-[11px]">
      <Database className="size-3.5 shrink-0 text-accent" />
      <span className={tone}>{text}</span>
    </div>
  )
}
