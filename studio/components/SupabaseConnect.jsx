'use client'

import { useEffect, useRef, useState } from 'react'
import { ExternalLink, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import AccountList from './AccountList'
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
 * outside a real terminal). So this drives the real OAuth thing instead: a genuine "click, approve
 * in the browser" sign-in, like "Sign in with Google". The OAuth app behind it is the publisher's,
 * one for everyone, kept by the engine server (`status.broker`; supabase_connect.py), so the person
 * registers nothing and types no client id or callback URL. Only a copy with no engine server (a
 * development checkout) still asks for an OAuth app of the person's own, below.
 */
export default function SupabaseConnect({ onDone }) {
  const [status, setStatus] = useState(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [flow, setFlow] = useState(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
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

  // Switch to, or sign out of, one of the accounts signed in here.
  async function change(kind, id) {
    setBusy(`${kind}:${id}`); setErr('')
    try {
      setStatus(kind === 'switch' ? await api.supabaseOauthSwitch(id) : await api.supabaseOauthRemove(id))
      onDone?.({ status: 'ready' })
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(flow.verification_uri)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { }
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
          <Input className="border-transparent bg-bg/60 shadow-none" value={clientId} onChange={e => setClientId(e.target.value)} placeholder="Client ID" />
        </Field>
        <Input className="border-transparent bg-bg/60 shadow-none" type="password" autoComplete="off" value={clientSecret}
               onChange={e => setClientSecret(e.target.value)} placeholder="Client Secret" />
        <Button size="sm" variant="primary" disabled={!clientId.trim() || !clientSecret.trim() || Boolean(busy)} onClick={registerApp}>
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
          : status.accounts?.length
            ? 'Signed out. Pick one of your accounts below, or sign in again.'
            : status.broker
              ? 'Connect your Supabase account: a browser tab opens, you approve it there, and you are back here.'
              : 'App registered — sign in to connect your account.'}
      </p>
      {(status.accounts?.length > 1 || (status.accounts?.length === 1 && !status.connected)) && (
        <AccountList accounts={status.accounts} busy={busy}
                     onSwitch={id => change('switch', id)} onRemove={id => change('remove', id)} />
      )}
      {flow && (
        <div className="rounded-2xl bg-bg/60 p-4">
          <p className="text-[11px] text-muted">A browser tab opened — approve the sign-in there.</p>
          <a className="inline-flex items-center gap-1 break-all text-[11px] text-accent hover:underline"
             target="_blank" rel="noreferrer" href={flow.verification_uri}>
            Open the sign-in page <ExternalLink className="size-2.5 shrink-0" />
          </a>
          {status.connected && (
            <p className="mt-1.5 text-[10.5px] leading-snug text-muted2">
              Your browser may already be signed in to another Supabase account. To add a different one, sign in to it
              there first, or{' '}
              <button type="button" className="text-accent hover:underline" onClick={copyLink}>
                {copied ? 'link copied' : 'copy the sign-in link'}
              </button>{' '}
              and open it in a private window.
            </p>
          )}
          <p className="mt-2 flex items-center gap-1.5 text-[10.5px] text-muted2">
            <Loader2 className="size-3 animate-spin" /> Waiting for you to approve it…
          </p>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={status.connected ? 'soft' : 'primary'} disabled={Boolean(busy)} onClick={signIn}>
          {busy === 'signin' && <Loader2 className="size-3 animate-spin" />}
          {status.connected ? 'Add another account' : 'Sign in with Supabase'}
        </Button>
        {flow && <Button size="sm" variant="soft" onClick={cancel}>Cancel</Button>}
      </div>
      {status.connected && status.accounts?.length === 1 && (
        <p className="text-[10.5px] leading-snug text-muted2">
          Have another Supabase account or organisation? Add it, then switch between them here. New projects are made in
          the one marked in use.
        </p>
      )}
      {err && <p className="text-[10.5px] text-bad">{err}</p>}
    </div>
  )
}
