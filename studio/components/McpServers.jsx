'use client'

/** Registering external MCP (Model Context Protocol) servers: additive tool
 * sources the agent can call alongside its built-in read/write/run tools,
 * never a replacement for them. */

import { useState } from 'react'
import { Check, Loader2, Plug, Plus, Trash2 } from 'lucide-react'

import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

function parseArgs(text) {
  return (text || '').trim().split(/\s+/).filter(Boolean)
}

function parseEnv(text) {
  const env = {}
  for (const line of (text || '').split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || !trimmed.includes('=')) continue
    const [key, ...rest] = trimmed.split('=')
    if (key.trim()) env[key.trim()] = rest.join('=').trim()
  }
  return env
}

export default function McpServers({ meta, onSaved }) {
  const servers = meta?.mcp_servers || []
  const [adding, setAdding] = useState(false)
  const [id, setId] = useState('')
  const [command, setCommand] = useState('')
  const [args, setArgs] = useState('')
  const [env, setEnv] = useState('')
  const [testing, setTesting] = useState(false)
  const [tested, setTested] = useState(null) // { ok, tools } | { ok: false, error }
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  function reset() {
    setId(''); setCommand(''); setArgs(''); setEnv('')
    setTested(null); setError(''); setAdding(false)
  }

  async function test() {
    setTesting(true); setError(''); setTested(null)
    try {
      const answer = await api.mcpProbe({ id: id.trim(), command: command.trim(),
                                          args: parseArgs(args), env: parseEnv(env) })
      setTested(answer)
    } catch (e) {
      setError(e.message)
    }
    setTesting(false)
  }

  async function save() {
    setSaving(true); setError('')
    try {
      const next = [...servers, { id: id.trim(), command: command.trim(),
                                  args: parseArgs(args), env: parseEnv(env), enabled: true }]
      const d = await api.saveSettings({ mcp_servers: next })
      onSaved?.(d)
      reset()
    } catch (e) {
      setError(e.message)
    }
    setSaving(false)
  }

  async function remove(serverId) {
    try {
      const next = servers.filter(s => s.id !== serverId)
      const d = await api.saveSettings({ mcp_servers: next })
      onSaved?.(d)
    } catch (e) {
      setError(e.message)
    }
  }

  async function toggle(server) {
    try {
      const next = servers.map(s => s.id === server.id ? { ...s, enabled: !s.enabled } : s)
      const d = await api.saveSettings({ mcp_servers: next })
      onSaved?.(d)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="max-w-[700px] space-y-4">
      <p className="rounded-2xl border border-line bg-panel px-4 py-3 text-[12px] text-muted">
        Each server is a local command the agent's tool-calling loop talks to
        over stdio — its tools show up alongside <code className="text-ink">read_file</code>,{' '}
        <code className="text-ink">web_search</code> and the rest, prefixed
        with the server's id so two servers can never collide.
      </p>

      {servers.length > 0 && (
        <div className="rounded-2xl border border-line bg-panel divide-y divide-line shadow-sm">
          {servers.map(server => (
            <div key={server.id} className="flex items-center gap-3 p-3.5">
              <Plug className="size-4 shrink-0 text-muted2" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12.5px] font-medium text-ink">{server.id}</div>
                <div className="truncate font-mono text-[10.5px] text-muted2">
                  {server.command} {(server.args || []).join(' ')}
                </div>
              </div>
              <button type="button" onClick={() => toggle(server)}
                aria-pressed={server.enabled !== false}
                className={cn('h-5 w-9 shrink-0 rounded-full border transition-colors',
                  server.enabled !== false ? 'border-accent bg-accent' : 'border-line bg-panel2')}>
                <span className={cn('block size-3.5 rounded-full bg-white transition-transform',
                  server.enabled !== false ? 'translate-x-4' : 'translate-x-0.5')} />
              </button>
              <button type="button" onClick={() => remove(server.id)}
                className="shrink-0 rounded-lg p-1.5 text-muted2 hover:bg-panel2 hover:text-ink transition-colors">
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {!adding ? (
        <button type="button" onClick={() => setAdding(true)}
          className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-panel2/60 px-3.5 py-2 text-[11.5px] font-medium text-ink hover:bg-raised transition-colors">
          <Plus className="size-3.5" /> Add MCP server
        </button>
      ) : (
        <div className="space-y-3 rounded-2xl border border-line bg-panel p-4 shadow-sm">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-[11.5px] font-semibold text-muted">Server id</span>
              <input value={id} onChange={e => { setId(e.target.value); setTested(null) }}
                placeholder="e.g. filesystem"
                className="w-full rounded-xl border border-line bg-panel2/60 px-3 py-2 text-[12.5px] text-ink outline-none placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent transition-colors" />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11.5px] font-semibold text-muted">Command</span>
              <input value={command} onChange={e => { setCommand(e.target.value); setTested(null) }}
                placeholder="npx"
                className="w-full rounded-xl border border-line bg-panel2/60 px-3 py-2 text-[12.5px] text-ink outline-none placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent transition-colors" />
            </label>
          </div>
          <label className="block">
            <span className="mb-1.5 block text-[11.5px] font-semibold text-muted">Arguments (space-separated)</span>
            <input value={args} onChange={e => { setArgs(e.target.value); setTested(null) }}
              placeholder="-y @modelcontextprotocol/server-filesystem /path/to/allow"
              className="w-full rounded-xl border border-line bg-panel2/60 px-3 py-2 font-mono text-[11.5px] text-ink outline-none placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent transition-colors" />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[11.5px] font-semibold text-muted">Environment (one NAME=value per line, optional)</span>
            <textarea value={env} onChange={e => { setEnv(e.target.value); setTested(null) }} rows={2}
              placeholder="API_KEY=..."
              className="w-full rounded-xl border border-line bg-panel2/60 px-3 py-2 font-mono text-[11.5px] text-ink outline-none placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent transition-colors" />
          </label>

          {tested?.ok && (
            <div className="rounded-xl border border-ok/25 bg-ok/10 px-3 py-2 text-[11.5px] text-ink">
              Connected — {tested.tools.length} tool{tested.tools.length === 1 ? '' : 's'}:{' '}
              {tested.tools.map(t => t.name).join(', ') || 'none'}
            </div>
          )}
          {error && (
            <div className="rounded-xl border border-bad/25 bg-bad/10 px-3 py-2 text-[11.5px] text-ink">
              {error}
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <button type="button" onClick={reset}
              className="rounded-xl px-3.5 py-2 text-[11.5px] font-medium text-muted hover:text-ink transition-colors">
              Cancel
            </button>
            <button type="button" disabled={testing || !id.trim() || !command.trim()} onClick={test}
              className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-panel2/60 px-3.5 py-2 text-[11.5px] font-medium text-ink hover:bg-raised disabled:opacity-40 transition-colors">
              {testing ? <Loader2 className="size-3.5 animate-spin" /> : <Plug className="size-3.5" />}
              Test connection
            </button>
            <button type="button" disabled={saving || !tested?.ok} onClick={save}
              className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-3.5 py-2 text-[11.5px] font-semibold text-ink hover:bg-press disabled:opacity-40 transition-colors">
              {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
              Add server
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
