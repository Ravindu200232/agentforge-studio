'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, ExternalLink, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from './ui'

/**
 * Signs in to a provider through its own command line tool (`cli_signin.py`: `gh`, `vercel`,
 * `netlify`, `az`, `aws`), the same shape for every one of them. Supabase is not one of these -
 * its CLI has no browser sign-in at all; see `SupabaseConnect.jsx` for its own OAuth flow instead.
 *
 * Says whether the tool is installed (and how to install it if not), who it is already signed in as
 * (which can be used as it is, with no browser), and otherwise runs its login: the code to type and
 * the link to open appear here, and the sign-in finishes on its own once approved in the browser.
 */
export default function CliSignIn({ provider, onDone, region = '', label = '' }) {
  const [tool, setTool] = useState(undefined)        // undefined: asking; null: could not ask
  const [state, setState] = useState(null)           // the running sign-in: { flow_id, title }
  const [seen, setSeen] = useState(null)             // { code, uri } printed while it waits
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const [notice, setNotice] = useState('')         // what the server says about what it kept
  const stop = useRef(false)
  const opened = useRef('')

  const look = useCallback((fresh = false) => api.cliSigninAvailable(provider, fresh)
    .then(d => setTool(d?.providers?.[provider] || null))
    .catch(() => setTool(null)), [provider])

  useEffect(() => { stop.current = false; look(); return () => { stop.current = true } }, [look])

  async function finished(answer) {
    setState(null); setSeen(null); setBusy(''); setNotice(answer?.note || '')
    await look(true)
    onDone?.(answer)
  }

  async function signIn() {
    setBusy('login'); setErr(''); setSeen(null); stop.current = false; opened.current = ''
    let started
    try {
      started = await api.cliSigninStart(provider, region)
      setState(started)
      if (started.verification_uri) setSeen({ code: '', uri: started.verification_uri })
      const deadline = Date.now() + 10 * 60 * 1000
      while (!stop.current && Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 2000))
        const answer = await api.cliSigninPoll(started.flow_id)
        if (answer.status === 'ready') return finished(answer)
        if (answer.user_code || answer.verification_uri) {
          setSeen({ code: answer.user_code || '', uri: answer.verification_uri || '' })
          // The tool opens its own browser tab for some providers; for the others it is opened here, once.
          if (answer.verification_uri && !answer.opens_browser && opened.current !== answer.verification_uri) {
            opened.current = answer.verification_uri
            window.open(answer.verification_uri, '_blank', 'noopener,noreferrer')
          }
        }
      }
      if (!stop.current) setErr('That sign-in did not finish in time. Start it again.')
    } catch (e) {
      if (!stop.current) setErr(e.message)
    }
    if (started?.flow_id) { try { await api.cliSigninCancel(started.flow_id) } catch { } }
    setState(null); setSeen(null); setBusy('')
  }

  async function useExisting() {
    setBusy('existing'); setErr('')
    try {
      await finished(await api.cliSigninUseExisting(provider, region))
    } catch (e) { setErr(e.message); setBusy('') }
  }

  async function cancel() {
    stop.current = true
    if (state?.flow_id) { try { await api.cliSigninCancel(state.flow_id) } catch { } }
    setBusy(''); setState(null); setSeen(null)
  }

  async function copyInstall() {
    try {
      await navigator.clipboard.writeText(String(tool.install).split('  (')[0])
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { }
  }

  if (tool === undefined) {
    return <p className="flex items-center gap-1.5 text-[10.5px] text-muted2"><Loader2 className="size-3 animate-spin" /> Looking for the command line tool…</p>
  }
  if (tool === null) {
    return <p className="text-[10.5px] text-muted2">Could not ask the server about the command line tool.</p>
  }

  const title = tool.title
  if (!tool.installed) {
    return (
      <div className="rounded-lg border border-line bg-panel2 p-3">
        <p className="text-[11px] text-muted">
          The {title} command line tool is not installed on this PC. Install it, then check again — signing in
          then takes one click.
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <code className="rounded-md bg-black/20 px-2 py-1 font-mono text-[11px] text-ink">{tool.install}</code>
          <Button size="sm" variant="outline" onClick={copyInstall}>{copied ? <Check className="size-3" /> : null}{copied ? 'Copied' : 'Copy'}</Button>
          <Button size="sm" onClick={() => { setTool(undefined); look(true) }}>Check again</Button>
        </div>
      </div>
    )
  }

  const who = tool.identity?.account
  const missing = tool.identity?.missing_scopes || []
  const running = busy === 'login'
  const usable = tool.signed_in && missing.length === 0
  return (
    <div className="space-y-2">
      <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
        <Check className="size-3 text-ok" />
        {label || `${title} command line tool`} found
        {tool.signed_in && <> · signed in as <b className="text-ink">{who}</b></>}
        {tool.identity?.subscription && <> · {tool.identity.subscription}</>}
      </p>
      {missing.length > 0 && (
        <p className="border-l-[3px] border-warn bg-warn-tint px-2.5 py-1.5 text-[10.5px] text-ink">
          This sign-in lacks the <b>{missing.join(', ')}</b> permission the deployment needs to push its workflows.
          Add it below; the browser asks you to approve it once.
        </p>
      )}
      {seen && (
        <div className="rounded-lg border border-line bg-panel2 p-3">
          {seen.code ? (
            <>
              <p className="text-[11px] text-muted">Enter this code in the browser, then leave this open — it finishes on its own.</p>
              <p className="my-1.5 font-mono text-[18px] font-bold tracking-[0.3em] text-ink">{seen.code}</p>
            </>
          ) : (
            <p className="text-[11px] text-muted">
              {tool.opens_browser ? 'A browser tab opened — approve the sign-in there.' : 'Open the link and approve the sign-in.'}
            </p>
          )}
          {seen.uri && (
            <a className="inline-flex items-center gap-1 break-all text-[11px] text-accent hover:underline" target="_blank"
               rel="noreferrer" href={seen.uri}>
              {seen.code ? seen.uri : 'Open the sign-in page'} <ExternalLink className="size-2.5 shrink-0" />
            </a>
          )}
          <p className="mt-2 flex items-center gap-1.5 text-[10.5px] text-muted2"><Loader2 className="size-3 animate-spin" /> Waiting for you to approve it…</p>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {usable && !running && (
          <Button size="sm" variant="solid" disabled={Boolean(busy)} onClick={useExisting}>
            {busy === 'existing' && <Loader2 className="size-3 animate-spin" />} Use this account
          </Button>
        )}
        <Button size="sm" variant={usable ? 'outline' : 'solid'} disabled={Boolean(busy)} onClick={signIn}>
          {running && <Loader2 className="size-3 animate-spin" />}
          {missing.length > 0 ? 'Add the permission' : tool.signed_in ? 'Sign in again' : `Sign in with ${title} CLI`}
        </Button>
        {running && <Button size="sm" variant="outline" onClick={cancel}>Cancel</Button>}
        {!running && <Button size="sm" variant="ghost" onClick={() => { setTool(undefined); look(true) }}>Recheck</Button>}
      </div>
      {notice && <p className="border-l-[3px] border-accent bg-tint px-2.5 py-1.5 text-[10.5px] leading-relaxed text-deep">{notice}</p>}
      {err && <p className="text-[10.5px] text-deep">{err}</p>}
    </div>
  )
}
