'use client'

import { Fragment, useEffect, useRef, useState } from 'react'
import {
  Check, Database, Keyboard,
  LayoutGrid, Loader2, Network, Palette, Plug, SlidersHorizontal, X,
  Download, ExternalLink, FolderUp, LogOut,
} from 'lucide-react'
import { api } from '@/lib/api'
import { Modal } from './ui'
import { cn } from '@/lib/utils'
import { useStore } from '@/lib/store'
import { useAuthStore } from '@/lib/auth'
import BrandIcon, { BRANDS, BRAND_ORDER } from './BrandIcon'
import DeployAccount from './deploy/DeployAccounts'
import PluginAccounts from './PluginAccounts'
import McpServers from './McpServers'

// Each service the studio connects to has a page of its own in this list, behind its own logo.
const PROVIDER_ABOUT = {
  github:   'Sign in so a deployment can create a private repository under your account and push its workflows.',
  aws:      'Deploy to your own AWS account. Sign in with the AWS command line tool or IAM Identity Center; no access keys are stored.',
  vercel:   'Deploy to your own Vercel account.',
  netlify:  'Deploy to your own Netlify account.',
  azure:    'Deploy to your own Azure subscription.',
  supabase: 'Every Supabase-stack project gets its own real Supabase project, in the account you sign in with.',
  mongodb:  'A real production database for MongoDB-stack deployments: sign in to Atlas, or paste a connection string.',
}

export default function SettingsModal({ onClose, onSaved, onImport, onZip, onOpenInNewTab, onLogout, initialTab }) {
  const user = useAuthStore(s => s.user)
  // The open project, so the Plugins tab can offer to tick them for it rather
  // than only hold the credentials.
  const project = useStore(s => s.project)

  // The old single "Integrations" page is now one page per service: land on the first of them.
  const [activeTab, setActiveTab] = useState(initialTab === 'integrations' ? 'github' : initialTab || 'general')
  const folderRef = useRef(null)

  // Real server settings, including the model engine on this computer.
  const [mongo, setMongo] = useState('')
  const [engineChoice, setEngineChoice] = useState('built-in')
  const [ollamaHost, setOllamaHost] = useState('http://localhost:11434')
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
        setEngineChoice(d.engine === 'local' ? 'local' : 'built-in')
        setOllamaHost(d.ollama_host || 'http://localhost:11434')
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
    body.engine = engineChoice === 'local' ? 'local' : 'built-in'
    if (engineChoice === 'local') body.ollama_host = ollamaHost.trim() || 'http://localhost:11434'
    try {
      const d = await api.saveSettings(body)
      setMeta(d)
      if (engineChoice === 'local') {
        const catalog = await api.models()
        const picked = (catalog.local_models || [])[0]?.id || catalog.local?.[0]
        if (picked) {
          useStore.setState(state => ({ models: { ...state.models, planner: picked, design: picked,
            builder: picked, agent: picked, qa: picked, srs: picked, deploy: picked } }))
          await api.saveSettings({ model: picked })
          setNote(`Local Ollama connected · ${picked}`)
        } else {
          setNote('Local mode saved. Start Ollama and pull a model to connect.')
        }
      } else {
        const catalog = await api.models()
        const cloud = catalog.cloud || []
        const current = useStore.getState().models.builder
        const picked = cloud.find(row => row.id === current)?.id
          || cloud.find(row => row.id === 'deepseek-v4.1-flash:cloud')?.id || cloud[0]?.id
        if (picked) {
          useStore.setState(state => ({ models: { ...state.models, planner: picked, design: picked,
            builder: picked, agent: picked, qa: picked, srs: picked, deploy: picked } }))
          await api.saveSettings({ model: picked })
        }
        setNote(picked ? `Cloud connected · ${picked}` : 'Cloud mode saved. Models will appear when the engine is available.')
      }
      setMongo('')
      setTone('ok')
      await useAuthStore.getState().init()
      onSaved?.()
    } catch (e) {
      setNote('save failed — ' + e.message)
      setTone('bad')
    }
    setSaving(false)
  }

  const cloudOn = tone === 'ok'
  // AgentForge's own database is the whole machine's, so it is its admin's.
  // Everyone's deployment accounts are their own — one Settings page per service.
  const isAdmin = Boolean(meta?.admin)

  const displayName = user?.name || user?.username || 'User'
  const displayEmail = user?.email || ''
  const initial = (user?.name || user?.username || 'U')[0]?.toUpperCase() || 'U'

  const settingsNav = [
    { id: 'general',      label: 'General',      Icon: SlidersHorizontal },
    { id: 'application',  label: 'Application',  Icon: LayoutGrid },
    { id: 'appearance',   label: 'Appearance',   Icon: Palette },
    ...BRAND_ORDER.map(id => ({ id, label: BRANDS[id].title, brand: true })),
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
              {settingsNav.map((item, index) => {
                const active = activeTab === item.id
                const first = item.brand && !settingsNav[index - 1]?.brand
                const last = item.brand && !settingsNav[index + 1]?.brand
                return (
                  <Fragment key={item.id}>
                  {first && <div className="my-1.5 hidden h-px bg-ink/[.07] sm:block" />}
                  <button
                    type="button"
                    onClick={() => setActiveTab(item.id)}
                    className={cn(
                      'shrink-0 sm:w-full flex items-center gap-2 sm:gap-2.5 px-2.5 py-1.5 rounded-xl text-left text-[12px] whitespace-nowrap transition-all',
                      active
                        ? 'bg-accent text-ink font-semibold shadow-sm'
                        : 'text-muted hover:text-ink hover:bg-ink/[.06] font-medium'
                    )}
                  >
                    {item.brand
                      ? <BrandIcon name={item.id} className={cn('size-4 shrink-0', active ? 'text-ink' : 'text-muted')} />
                      : <item.Icon className={cn('size-3.5 shrink-0', active ? 'text-accent' : 'text-muted2')} />}
                    <span>{item.label}</span>
                  </button>
                  {last && <div className="my-1.5 hidden h-px bg-ink/[.07] sm:block" />}
                  </Fragment>
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
               : BRANDS[activeTab]            ? BRANDS[activeTab].title
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
                  : PROVIDER_ABOUT[activeTab]
                  ? PROVIDER_ABOUT[activeTab]
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
                <AccountRequests />
                <EngineChoice value={engineChoice} onChange={setEngineChoice} host={ollamaHost} onHost={setOllamaHost} />
                <button type="button" disabled={saving} onClick={save}
                  className="rounded-xl bg-accent px-4 py-2 text-[12px] font-semibold text-ink disabled:opacity-50">
                  {saving ? 'Connecting…' : 'Save AI connection'}
                </button>
                <p className="text-[11px] text-muted">{note}</p>
                <p className="rounded-2xl border border-line bg-panel px-4 py-3 text-[12px] text-muted">
                  AgentForge's own database is shared by everyone on this
                  machine, so only its admin changes it. Your GitHub, AWS, Vercel
                  and production database are yours alone — each has its own page
                  in the Settings list.
                </p>
                <MongoState mongo={meta?.mongo} />
                <WorkspaceActions project={project} folderRef={folderRef} onImport={onImport}
                                  onZip={onZip} onOpenInNewTab={onOpenInNewTab} onLogout={onLogout} />
              </div>
            )}

            {activeTab === 'general' && isAdmin && (
              <div className="space-y-5 max-w-[700px]">
                <AccountRequests />
                <EngineChoice value={engineChoice} onChange={setEngineChoice} host={ollamaHost} onHost={setOllamaHost} />
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

            {/* ── SERVICES: GitHub, AWS, Vercel, Netlify, Azure, Supabase, MongoDB — one page each ── */}
            {BRANDS[activeTab] && (
              <div className="max-w-[700px]">
                <DeployAccount key={activeTab} provider={activeTab} deploy={meta?.deploy} onSaved={() => {
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

/** The signed-in AgentForge account's requests (one per AI call): the limit the admin gave, what is used and what is left,
 * going down live as the AI works (`account_usage` events). Nothing is shown when AgentForge accounts are off. */
function EngineChoice({ value, onChange, host, onHost }) {
  return <div className="rounded-2xl border border-line bg-panel px-4 py-4 space-y-3">
    <h3 className="text-[13px] font-semibold text-ink">AI connection</h3>
    <label className="flex gap-2 text-[12px]"><input type="radio" name="ai-engine" checked={value === 'built-in'} onChange={() => onChange('built-in')} /> AgentForge Cloud · uses account credit</label>
    <label className="flex gap-2 text-[12px]"><input type="radio" name="ai-engine" checked={value === 'local'} onChange={() => onChange('local')} /> Local Ollama · uses your computer, no cloud credit</label>
    {value === 'local' && <label className="block text-[11px] text-muted">Ollama address
      <input value={host} onChange={e => onHost(e.target.value)} placeholder="http://localhost:11434"
        className="mt-1 block w-full rounded-xl border border-line bg-panel2 px-3 py-2 text-[12px] text-ink" />
    </label>}
  </div>
}

function AccountRequests() {
  const [account, setAccount] = useState(null)
  const [purchaseError, setPurchaseError] = useState('')
  const live = useStore(s => s.accountUsage)

  useEffect(() => {
    let alive = true
    api.account().then(a => { if (alive) setAccount(a) }).catch(() => {})
    return () => { alive = false }
  }, [])

  if (!account?.enabled || !account?.signed_in) return null
  const shown = live && live.status !== 'signed_out' ? { ...account, ...live } : account
  if (shown.unlimited) return <AdminRequests shown={shown} />
  const limit = Number(shown.limitUsd) || 0
  const used = Number(shown.usedUsd) || 0
  const left = Math.max(0, Number(shown.remainingUsd) || 0)
  const share = limit ? Math.min(100, Math.round((used / limit) * 100)) : 100
  const low = !limit || left / limit < 0.1
  return (
    <div className="rounded-2xl border border-line bg-panel px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-ink">Cloud credit · {shown.plan === 'paid' ? 'Paid weekly' : 'Free once'}</h3>
        <span className="text-[11px] text-muted2">{shown.email}</span>
      </div>
      <p className={`mt-2 font-display text-[22px] font-black tabular-nums ${low ? 'text-bad' : 'text-ink'}`}>
        ${left.toFixed(2)} <span className="text-[12px] font-semibold text-muted">left of ${limit.toFixed(2)}</span>
      </p>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-panel2">
        <div className={`h-full rounded-full transition-all duration-500 ${low ? 'bg-bad' : 'bg-accent'}`} style={{ width: `${share}%` }} />
      </div>
      <p className="mt-1.5 text-[11px] text-muted">
        ${used.toFixed(2)} used · local Ollama does not spend this credit
      </p>
      {shown.weekResetsAt && <p className="text-[11px] text-muted">Resets {new Date(shown.weekResetsAt).toLocaleString()}</p>}
      {shown.plan !== 'paid' && <button type="button" disabled={!shown.checkoutAvailable}
        className="mt-3 rounded-xl bg-accent px-3 py-2 text-[12px] font-semibold text-ink disabled:opacity-50"
        onClick={async () => {
          setPurchaseError('')
          try {
            const result = await api.accountCheckout()
            if (!result.ok || !result.url) throw new Error(result.error || 'Checkout unavailable')
            window.open(result.url, '_blank', 'noopener,noreferrer')
          } catch (error) { setPurchaseError(error.message) }
        }}>
        Buy ${Number(shown.weeklyPriceUsd || 21).toFixed(2)}/week · weekly cloud credit
      </button>}
      {!shown.checkoutAvailable && shown.plan !== 'paid' && <p className="mt-1 text-[11px] text-muted">Checkout is being set up by the admin.</p>}
      {purchaseError && <p className="mt-1 text-[11px] text-bad">{purchaseError}</p>}
    </div>
  )
}

/** The admin's own AgentForge: never limited; the Ollama account's balance as ollama.com reports it, and the requests made here. */
function AdminRequests({ shown }) {
  const included = shown.ollama?.included
  const usedShare = included?.allowance ? Math.min(100, Math.round(((included.allowance - included.balance) / included.allowance) * 100)) : 0
  return (
    <div className="rounded-2xl border border-line bg-panel px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-ink">Cloud account</h3>
        <span className="text-[11px] text-muted2">{shown.email} · admin</span>
      </div>
      <p className="mt-2 font-display text-[22px] font-black text-ink">Unlimited</p>
      {included ? (
        <>
          <p className="mt-1 text-[12px] text-muted">
            AgentForge account: ${Number(included.balance).toFixed(2)} left of ${Number(included.allowance).toFixed(2)} this period
          </p>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-panel2">
            <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${usedShare}%` }} />
          </div>
        </>
      ) : shown.ollama?.error ? (
        <p className="mt-1 text-[11.5px] text-muted">AgentForge account: {shown.ollama.error}</p>
      ) : null}
      <p className="mt-1.5 text-[11px] text-muted">Admin access is unlimited</p>
    </div>
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
