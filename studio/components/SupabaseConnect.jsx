'use client'

import { useEffect, useRef, useState } from 'react'
import { ExternalLink, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { Button, Input } from './ui'

const Field = ({ label, hint, children }) => (
  <label className="block">
    <span className="label-2xs mb-1 block text-muted2 font-bold uppercase tracking-wider">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[10px] leading-snug text-muted2">{hint}</span>}
  </label>
)

/**
 * Supabase has no device-flow CLI sign-in the way GitHub/Vercel/Netlify/Azure do (see
 * cli_signin.py's own docstring on why it isn't there - tried live, `supabase login` refuses
 * outside a real terminal). So this drives the real OAuth thing instead: a one-time OAuth app
 * registered in the person's own Supabase organisation (Organization settings -> OAuth Apps ->
 * Publish OAuth app, with the callback URL below), then a genuine "click, approve in the browser"
 * sign-in for every project after that - the same shape as every other provider, just needing a
 * client secret as well as an id to get there, which only the person's own org can supply.
 */
export default function SupabaseConnect({ onDone }) {
  const [status, setStatus] = useState(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [flow, setFlow] = useState(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const stop = useRef(false)

  const look = () => api.supabaseOauthStatus().then(setStatus).catch(() => setStatus({ app_registered: false, connected: false }))

  useEffect(() => { stop.current = false; look(); return () => { stop.current = true } }, [])

  async function registerApp() {
    setBusy('register'); setErr('')
    try {
      await api.saveSettings({ supabase_client_id: clientId.trim(), supabase_client_secret: clientSecret.trim() })
      setClientSecret('')
      await look()
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }

  async function signIn() {
    setBusy('signin'); setErr(''); setFlow(null); stop.current = false
    let started
    try {
      started = await api.supabaseOauthStart()
      setFlow(started)
      window.open(started.verification_uri, '_blank', 'noopener')
      const deadline = Date.now() + 10 * 60 * 1000
      while (!stop.current && Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 2000))
        const answer = await api.supabaseOauthPoll(started.flow_id)
        if (answer.status === 'ready') {
          setFlow(null)
          await look()
          onDone?.(answer)
          setBusy('')
          return
        }
      }
      if (!stop.current) setErr('That sign-in did not finish in time. Start it again.')
    } catch (e) {
      if (!stop.current) setErr(e.message)
    }
    if (started?.flow_id) { try { await api.supabaseOauthCancel(started.flow_id) } catch { } }
    setFlow(null); setBusy('')
  }

  async function cancel() {
    stop.current = true
    if (flow?.flow_id) { try { await api.supabaseOauthCancel(flow.flow_id) } catch { } }
    setFlow(null); setBusy('')
  }

  if (!status) {
    return <p className="flex items-center gap-1.5 text-[10.5px] text-muted2"><Loader2 className="size-3 animate-spin" /> Checking Supabase…</p>
  }

  if (!status.app_registered) {
    return (
      <div className="space-y-2">
        <Field label="Supabase OAuth app"
               hint={<>One-time setup: in your Supabase organisation, go to Organization settings
                       {' '}&rarr; OAuth Apps &rarr; Publish OAuth app, and use{' '}
                       <code className="rounded bg-black/20 px-1">http://localhost:7824/__agentforge/api/supabase-oauth/callback</code>{' '}
                       as its exact callback URL — <b>localhost</b>, not 127.0.0.1: Supabase's
                       authorize endpoint only waives HTTPS for that literal hostname (this Studio's
                       own address either way — change the port only if AGENTFORGE_API_PORT is set
                       to something other than 7824). Then paste its Client ID and Secret here —
                       done once for this machine.{' '}
                       <a className="text-accent hover:underline" target="_blank" rel="noreferrer"
                          href="https://supabase.com/dashboard/org/_/apps">Manage OAuth apps</a></>}>
          <Input value={clientId} onChange={e => setClientId(e.target.value)} placeholder="Client ID" />
        </Field>
        <Input type="password" autoComplete="off" value={clientSecret}
               onChange={e => setClientSecret(e.target.value)} placeholder="Client Secret" />
        <Button size="sm" disabled={!clientId.trim() || !clientSecret.trim() || Boolean(busy)} onClick={registerApp}>
          {busy === 'register' && <Loader2 className="size-3 animate-spin" />} Save
        </Button>
        {err && <p className="text-[10.5px] text-bad">{err}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-muted">
        {status.connected
          ? <>Signed in{status.org ? <> as <b className="text-ink">{status.org}</b></> : ''}</>
          : 'App registered — sign in to connect your account.'}
      </p>
      {flow && (
        <div className="rounded-lg border border-line bg-panel2 p-3">
          <p className="text-[11px] text-muted">A browser tab opened — approve the sign-in there.</p>
          <a className="inline-flex items-center gap-1 break-all text-[11px] text-accent hover:underline"
             target="_blank" rel="noreferrer" href={flow.verification_uri}>
            Open the sign-in page <ExternalLink className="size-2.5 shrink-0" />
          </a>
          <p className="mt-2 flex items-center gap-1.5 text-[10.5px] text-muted2">
            <Loader2 className="size-3 animate-spin" /> Waiting for you to approve it…
          </p>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={Boolean(busy)} onClick={signIn}>
          {busy === 'signin' && <Loader2 className="size-3 animate-spin" />}
          {status.connected ? 'Sign in again' : 'Sign in with Supabase'}
        </Button>
        {flow && <Button size="sm" variant="outline" onClick={cancel}>Cancel</Button>}
      </div>
      {err && <p className="text-[10.5px] text-bad">{err}</p>}
    </div>
  )
}
