'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, ExternalLink, Loader2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { Button, Input, SectionLabel } from '../ui'
import { cn } from '@/lib/utils'


const SSO_REGIONS = ['us-east-1', 'us-east-2', 'us-west-2', 'eu-west-1',
                     'eu-central-1', 'ap-south-1', 'ap-southeast-1',
                     'ap-southeast-2', 'ap-northeast-1']
const AWS_REGIONS = ['ap-south-1', 'us-east-1', 'us-east-2', 'us-west-2',
                     'eu-west-1', 'eu-west-2', 'eu-central-1',
                     'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1']
const AWS_CONSOLE_PROFILE = 'agentforge-console'

export default function DeployAccounts({ deploy, onSaved }) {
  const [open, setOpen] = useState(false)
  const [probe, setProbe] = useState(null)
  const [note, setNote] = useState('')

  useEffect(() => {
    if (!open || probe) return
    api.deployRead('/onboarding/status')
      .then(setProbe)
      .catch(e => setNote(`could not read the deployment agent — ${e.message}`))
  }, [open, probe])

  const save = async (patch) => {
    await api.saveSettings(patch)
    onSaved?.()
  }

  return (
    <section className="mt-5 border-t-2 border-line2 pt-3">
      <button onClick={() => setOpen(o => !o)} className="w-full text-left">
        <SectionLabel className="border-b-2 border-line2 pb-1.5" right={<span className="text-[10px] text-muted2">
                               {open ? 'hide' : 'show'}
                             </span>}>
          Deployment accounts
        </SectionLabel>
      </button>
      {!open && (
        <p className="mt-1.5 text-[10.5px] text-muted2">
          {summarise(deploy)}
        </p>
      )}

      {open && (
        <div className="mt-3 space-y-4">
          {note && (
            <p className="border-l-[3px] border-accent bg-tint px-2.5 py-1.5
                          text-[11px] text-deep">
              {note}
            </p>
          )}
          <Github deploy={deploy} onSave={save} probe={probe}
                  onRecheck={() => setProbe(null)} />
          <Aws deploy={deploy} onSave={save} probe={probe}
               onRecheck={() => setProbe(null)} />
          <Vercel deploy={deploy} onSave={save} />
          <HostedCredential title="Netlify" provider="netlify" setting="netlify_token" saved={deploy?.netlify_token_set} onSave={save}
            label="Personal access token" href="https://app.netlify.com/user/applications#personal-access-tokens"
            hint="Create a token in your Netlify account. The deployment uses it to provision your site and as an encrypted GitHub Actions secret." />
          <HostedCredential title="Azure" provider="azure" setting="azure_credentials" saved={Boolean(deploy?.azure_credentials_set || deploy?.azure_account)} onSave={save}
            label="Service principal credentials (JSON)" href="https://learn.microsoft.com/en-us/azure/app-service/deploy-github-actions"
            hint="Enter JSON containing clientId, clientSecret, tenantId and subscriptionId for your deployment service principal. Give it access to the selected resource group." />
          <Mongo deploy={deploy} onSave={save} />
        </div>
      )}
    </section>
  )
}

function summarise(d) {
  if (!d) return 'GitHub, AWS, Vercel, Netlify, Azure and the production database.'
  const bits = []
  bits.push(d.github_token_set
    ? `GitHub ${d.github_login || 'connected'}` : 'GitHub not connected')
  bits.push(d.aws_profile ? `AWS ${d.aws_profile}` : 'AWS not connected')
  bits.push(d.vercel_token_set ? 'Vercel connected' : 'Vercel not connected')
  bits.push(d.netlify_token_set ? 'Netlify connected' : 'Netlify not connected')
  bits.push(d.azure_credentials_set || d.azure_account ? 'Azure connected' : 'Azure not connected')
  bits.push(d.mongodb_uri_set ? 'database set' : 'no database')
  return bits.join(' · ')
}


function Github({ deploy, onSave, probe, onRecheck }) {
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const ok = Boolean(deploy?.github_token_set)
  const login = deploy?.github_login || probe?.github_account || ''

  // Sign in to GitHub via OAuth device flow directly to user settings.
  const [clientId, setClientId] = useState(deploy?.github_client_id || '')
  const [flow, setFlow] = useState(null)
  const [signing, setSigning] = useState(false)
  const stop = useRef(false)

  useEffect(() => () => { stop.current = true }, [])

  async function signIn() {
    setSigning(true); setErr(''); setFlow(null)
    try {
      if (clientId.trim() && clientId.trim() !== (deploy?.github_client_id || '')) {
        await onSave({ github_client_id: clientId.trim() })
      }
      const started = await api.githubDeviceStart(clientId.trim())
      setFlow(started)
      window.open(started.verification_uri, '_blank', 'noopener')
      stop.current = false
      const deadline = Date.now() + (started.expires_in || 900) * 1000
      let wait = (started.interval || 5) * 1000
      while (!stop.current && Date.now() < deadline) {
        await new Promise(r => setTimeout(r, wait))
        const answer = await api.githubDevicePoll(started.flow_id)
        if (answer.status === 'ready') {
          setFlow(null)
          onRecheck?.()
          return
        }
        wait = (answer.interval || 5) * 1000
      }
      setErr('That sign-in expired before it was approved.')
      setFlow(null)
    } catch (e) {
      setErr(e.message); setFlow(null)
    } finally {
      setSigning(false)
    }
  }

  async function save() {
    setBusy(true)
    setErr('')
    try {
      await onSave({ github_token: token.trim() })
      setToken('')
      onRecheck?.()
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  return (
    <Row title="GitHub" ok={ok} unknown={false}
         detail={ok ? `connected as ${login || 'your account'}`
                    : 'the deployment creates a private repository under your '
                      + 'account and pushes the workflows that build it'}>
      <div className="mt-2 w-full space-y-3">
        <CliSignIn provider="github" onDone={() => { onSave({}); onRecheck?.() }} />
        <details className="group rounded-lg border border-line px-3 py-2">
          <summary className="cursor-pointer text-[11px] font-semibold text-muted transition-colors hover:text-ink">Other ways to sign in</summary>
          <div className="mt-3 space-y-3">
        <Field label="Sign in with an OAuth app"
               hint={<>Approved in your browser, the way the AWS console sign-in
                       is. Needs the <b>Client ID</b> of an OAuth app with
                       Device Flow enabled — make one at{' '}
                       <a className="text-accent hover:underline" target="_blank"
                          rel="noreferrer" href="https://github.com/settings/developers">
                         github.com/settings/developers
                       </a>. The Client ID is public; there is no secret to keep.</>}>
          <Input value={clientId} onChange={e => setClientId(e.target.value)}
                 placeholder="Iv1.0123456789abcdef" />
        </Field>
        {flow ? (
          <div className="rounded-lg border border-line bg-panel2 p-3">
            <p className="text-[11px] text-muted">
              Enter this code on GitHub, then leave this open — it finishes on its own.
            </p>
            <p className="my-2 font-mono text-[18px] font-bold tracking-[0.3em] text-ink">
              {flow.user_code}
            </p>
            <a className="text-[11px] text-accent hover:underline" target="_blank"
               rel="noreferrer" href={flow.verification_uri}>
              {flow.verification_uri}
            </a>
            <p className="mt-2 text-[10.5px] text-muted2">
              Granting: {flow.scopes}
            </p>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={signing} onClick={signIn}>
            {signing && <Loader2 className="size-3 animate-spin" />}
            {ok ? 'Sign in again' : 'Sign in with GitHub'}
          </Button>
          {signing && (
            <Button size="sm" variant="outline"
                    onClick={() => { stop.current = true; setSigning(false); setFlow(null) }}>
              Cancel
            </Button>
          )}
        </div>

        <Field label="Or paste a personal access token"
               hint={<>Your own GitHub account, not this machine's — deployments
                       push as you. Create a token with the <b>repo</b> and{' '}
                       <b>workflow</b> scopes at{' '}
                       <a className="text-accent hover:underline" target="_blank"
                          rel="noreferrer"
                          href="https://github.com/settings/tokens/new?scopes=repo,workflow&description=AgentForge">
                         github.com/settings/tokens
                       </a>. Type a single - to clear it.</>}>
          <Input type="password" value={token} onChange={e => setToken(e.target.value)}
                 placeholder={ok ? `connected as ${login}` : 'ghp_…'} />
        </Field>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={!token.trim() || busy}
                  onClick={save}>
            {busy && <Loader2 className="size-3 animate-spin" />} Save token
          </Button>
          <Button size="sm" onClick={onRecheck}>Recheck</Button>
        </div>
          </div>
        </details>
        {err && <p className="text-[10.5px] text-deep">{err}</p>}
      </div>
    </Row>
  )
}


function Aws({ deploy, onSave, probe, onRecheck }) {
  const [profile, setProfile] = useState(deploy?.aws_profile || '')
  const [startUrl, setStartUrl] = useState(deploy?.aws_start_url || '')
  const [ssoRegion, setSsoRegion] = useState(deploy?.aws_sso_region || 'us-east-1')
  const [region, setRegion] = useState(deploy?.aws_region || 'ap-south-1')
  const [flow, setFlow] = useState(null)
  const [accounts, setAccounts] = useState(null)
  const [account, setAccount] = useState('')
  const [roles, setRoles] = useState([])
  const [role, setRole] = useState('')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState('')

  const identity = probe?.aws_identities?.[deploy?.aws_profile]
  const connected = Boolean(identity) || Boolean(deploy?.aws_profile)

  async function begin() {
    setErr('')
    setBusy('starting')
    try {
      const f = await api.deploy('/aws/sso/start',
                                 { start_url: startUrl.trim(), region: ssoRegion })
      setFlow(f)

      const link = f.verification_uri_complete || f.verification_uri
      if (link) window.open(link, '_blank', 'noopener,noreferrer')
      poll(f)
    } catch (e) {
      setErr(e.message)
      setBusy('')
    }
  }

  async function poll(f) {
    setBusy('waiting')
    const every = Math.max(2, Number(f.interval || 5)) * 1000
    const deadline = Date.now() + Math.max(60, Number(f.expires_in || 600)) * 1000
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, every))
      try {
        const d = await api.deploy('/aws/sso/poll', { flow_id: f.flow_id })
        if (d.status === 'complete') {
          setAccounts(d.accounts || [])
          setBusy('')
          return
        }
      } catch (e) {
        setErr(e.message)
        setBusy('')
        return
      }
    }
    setErr('the AWS sign-in expired — start it again')
    setBusy('')
  }

  async function waitForProfile(name) {
    const deadline = Date.now() + 10 * 60 * 1000
    while (Date.now() < deadline) {
      const status = await api.deploy('/aws/profile/status', {
        profile: name,
        region,
      }).catch(() => null)
      if (status?.authenticated) {
        await onSave({ aws_profile: name, aws_region: region })
        setProfile(name)
        setNotice(`AWS sign-in completed — profile ${name} is selected.`)
        onRecheck?.()
        return true
      }
      await new Promise(resolve => setTimeout(resolve, 3000))
    }
    setErr('AWS sign-in was not completed in time. Start it again.')
    return false
  }

  async function pickAccount(id) {
    setAccount(id)
    setRole('')
    setRoles([])
    if (!id) return
    try {
      const d = await api.deploy('/aws/sso/roles',
                                 { flow_id: flow.flow_id, account_id: id })
      setRoles(d.roles || [])
      if ((d.roles || []).length === 1) setRole(d.roles[0])
    } catch (e) { setErr(e.message) }
  }

  async function use() {
    setBusy('selecting')
    setErr('')
    try {

      const d = await api.deploy('/aws/sso/select', {
        flow_id: flow.flow_id, account_id: account, role_name: role,
        persist_profile: true, profile: 'deployment-agent',
        deployment_region: region,
      })
      await onSave({
        aws_profile: d.profile || 'deployment-agent',
        aws_region: region,
        aws_start_url: startUrl.trim(),
        aws_sso_region: ssoRegion,
      })
      onRecheck?.()
      setFlow(null)
      setAccounts(null)
    } catch (e) {
      setErr(e.message)
    }
    setBusy('')
  }

  return (
    <Row title="AWS" ok={connected} unknown={!probe}
         detail={connected
           ? `profile ${deploy.aws_profile} · ${identity?.role_name || 'signed in'} · ${deploy.aws_region || 'ap-south-1'}`
           : deploy?.aws_profile
             ? `profile ${deploy.aws_profile} needs sign-in or has expired`
             : 'sign in through IAM Identity Center — no access keys are stored'}>
      <div className="mt-2 w-full space-y-2">
        <Field label="Deploy into">
          <Select value={region} onChange={setRegion} options={AWS_REGIONS} />
        </Field>
        <CliSignIn provider="aws" region={region} label="AWS command line tool"
                   onDone={() => { setProfile(AWS_CONSOLE_PROFILE); onSave({ aws_profile: AWS_CONSOLE_PROFILE, aws_region: region }); onRecheck?.() }} />

        <details className="group rounded-lg border border-line px-3 py-2">
          <summary className="cursor-pointer text-[11px] font-semibold text-muted transition-colors hover:text-ink">IAM Identity Center (advanced)</summary>
          <div className="mt-3 space-y-2">
        <Field label="Identity Center start URL">
          <Input value={startUrl} onChange={e => setStartUrl(e.target.value)}
                 placeholder="https://d-xxxxxxxxxx.awsapps.com/start" />
        </Field>
        <Field label="Sign-in region">
          <Select value={ssoRegion} onChange={setSsoRegion} options={SSO_REGIONS} />
        </Field>

        {!flow && (
          <Button size="sm" variant="outline"
                  disabled={!startUrl.trim() || Boolean(busy)} onClick={begin}>
            {busy === 'starting' && <Loader2 className="size-3 animate-spin" />}
            {connected ? 'Connect a different account' : 'Sign in to AWS'}
          </Button>
        )}

        {flow && !accounts && (
          <div className=" border border-line bg-bg px-2.5 py-2">
            <p className="text-[11px] text-muted">
              Approve this in the browser tab that opened, then come back.
            </p>
            <p className="mt-1 flex items-center gap-2">
              <code className=" bg-panel2 px-1.5 py-0.5 font-mono
                               text-[13px] tracking-[2px] text-ink">
                {flow.user_code}
              </code>
              <a href={flow.verification_uri_complete || flow.verification_uri}
                 target="_blank" rel="noreferrer"
                 className="inline-flex items-center gap-1 text-[10.5px] text-accent
                            hover:underline">
                open again <ExternalLink className="size-2.5" />
              </a>
              {busy === 'waiting' && (
                <Loader2 className="size-3 animate-spin text-muted2" />
              )}
            </p>
          </div>
        )}

        {accounts && (
          <div className="space-y-2">
            <Field label="Account">
              <Select value={account} onChange={pickAccount} placeholder="choose an account"
                      options={accounts.map(a => ({
                        value: a.account_id,
                        label: `${a.account_name || a.account_id} (${a.account_id})`,
                      }))} />
            </Field>
            {roles.length > 0 && (
              <Field label="Role">
                <Select value={role} onChange={setRole} placeholder="choose a role"
                        options={roles} />
              </Field>
            )}
            <Button size="sm" variant="solid"
                    disabled={!account || !role || Boolean(busy)} onClick={use}>
              {busy === 'selecting' && <Loader2 className="size-3 animate-spin" />}
              Use this account
            </Button>
          </div>
        )}

          </div>
        </details>

        <div className="border-t border-line pt-2">
          <Field label="Or use an AWS CLI profile you already have"
                 hint="Made by `aws configure sso`, or any profile that works.
                       Nothing secret is copied — only the name.">
            {(probe?.aws_profiles || []).length > 0 ? (
              <Select value={profile} onChange={setProfile}
                      placeholder="choose a profile"
                      options={Array.from(new Set([
                        ...probe.aws_profiles.map(p =>
                          typeof p === 'string' ? p : p.name),
                        profile,
                      ].filter(Boolean))).map(name => ({ value: name, label: name }))} />
            ) : (
              <Input value={profile} onChange={e => setProfile(e.target.value)}
                     placeholder="deployment-agent" />
            )}
          </Field>
          <Button size="sm" variant="outline" className="mt-2"
                  disabled={!profile.trim() || Boolean(busy)}
                  onClick={async () => {
                    setBusy('profile'); setErr('')
                    try {
                      await onSave({ aws_profile: profile.trim(),
                                     aws_region: region })
                      onRecheck?.()
                    } catch (e) { setErr(e.message) }
                    setBusy('')
                  }}>
            {busy === 'profile' && <Loader2 className="size-3 animate-spin" />}
            Use this profile
          </Button>
        </div>

        {notice && <p className="text-[10.5px] text-muted">{notice}</p>}
        {String(identity?.arn || '').endsWith(':root') && (
          <p className="text-[10.5px] text-deep">
            Root identity detected. Use an IAM Identity Center deployment role
            for routine releases instead of the AWS account root user.
          </p>
        )}
        {err && <p className="text-[10.5px] text-deep">{err}</p>}
      </div>
    </Row>
  )
}


/**
 * Signing in through the provider's own command line tool.
 *
 * Says whether the tool is installed (and how to install it if not), who it is already signed in as
 * (which can be used as it is, with no browser), and otherwise runs its login: the code to type and
 * the link to open appear here, and the sign-in finishes on its own once approved in the browser.
 */
function CliSignIn({ provider, onDone, region = '', label = '' }) {
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


function Vercel({ deploy, onSave }) {
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState('')
  const [status, setStatus] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let ok = true
    api.deploy('/aws/vercel/status', { token: '' })
      .then(d => { if (ok) setStatus(d) })
      .catch(() => { })
    return () => { ok = false }
  }, [deploy?.vercel_token_set])

  async function check() {
    setBusy('check')
    setErr('')
    try {
      setStatus(await api.deploy('/aws/vercel/status', { token: token.trim() }))
    } catch (e) { setErr(e.message) }
    setBusy('')
  }

  async function saveToken() {
    setBusy('save')
    setErr('')
    try {
      await onSave({ vercel_token: token.trim() })
      setToken('')
    } catch (e) { setErr(e.message) }
    setBusy('')
  }

  const who = status?.username || status?.email || status?.name || ''
  const connected = Boolean(status?.connected) || Boolean(deploy?.vercel_token_set)
  const detail = status?.connected
    ? `connected as ${who}`
    : deploy?.vercel_token_set
      ? `token saved (${deploy.vercel_token_hint})`
      : 'paste a token from your own Vercel account'

  return (
    <Row title="Vercel" ok={connected}
         unknown={!status && !deploy?.vercel_token_set}
         detail={detail}>
      <div className="mt-2 w-full space-y-3">
        <CliSignIn provider="vercel" onDone={() => onSave({})} />
        <Field label="Or paste an access token"
               hint="Your own Vercel account. Kept with your account here, encrypted,
                     and set as a GitHub Actions secret on the repository the
                     deployment creates — Vercel has no OIDC equivalent. Type a
                     single - to clear it.">
          <Input type="password" value={token} onChange={e => setToken(e.target.value)}
                 placeholder={deploy?.vercel_token_set
                   ? `saved (${deploy.vercel_token_hint})`
                   : 'paste a Vercel token'} />
        </Field>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={!token.trim() || Boolean(busy)}
                  onClick={saveToken}>
            {busy === 'save' && <Loader2 className="size-3 animate-spin" />} Save token
          </Button>
          <Button size="sm" disabled={Boolean(busy)} onClick={check}>
            {busy === 'check' && <Loader2 className="size-3 animate-spin" />} Check
          </Button>
        </div>
        {status && !status.connected && (
          <p className="text-[10.5px] text-muted">
            {status.message || 'not connected yet'}
          </p>
        )}
        {err && <p className="text-[10.5px] text-deep">{err}</p>}
      </div>
    </Row>
  )
}


/** Validates and saves API credentials directly against hosted deployment providers. */
function HostedCredential({ title, provider, setting, saved, label, hint, href, onSave }) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState('')
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')

  // What is already saved, checked once, so the row opens telling the truth.
  useEffect(() => {
    let live = true
    if (!saved) { setStatus(null); return undefined }
    api.deploy(`/aws/${provider}/status`, { token: '' })
      .then(answer => { if (live) setStatus(answer) })
      .catch(() => {})
    return () => { live = false }
  }, [provider, saved])

  async function check(token) {
    setBusy('check'); setError(''); setStatus(null)
    try { setStatus(await api.deploy(`/aws/${provider}/status`, { token })) }
    catch (failure) { setError(failure.message) }
    finally { setBusy('') }
  }

  async function save() {
    setBusy('save'); setError('')
    try {
      await onSave({ [setting]: value.trim() })
      const token = value.trim()
      setValue('')
      if (token !== '-') await check(token)
    } catch (failure) { setError(failure.message) } finally { setBusy('') }
  }

  const connected = Boolean(status?.connected)
  const detail = status
    ? (connected
        ? `${status.account || 'connected'}${status.verified === false ? ' · signs in on the runner' : ''}`
        : status.message || status.error || 'credentials rejected')
    : saved ? 'credentials saved' : 'connect your account'

  return <Row title={title} ok={saved ? connected : false} unknown={Boolean(saved) && !status}
              detail={detail}>
    {(provider === 'netlify' || provider === 'azure') && (
      <div className="mt-2 w-full">
        <CliSignIn provider={provider} onDone={() => onSave({})} />
      </div>
    )}
    <div className="mt-2 w-full space-y-2">
      <Field label={label} hint={<>{hint} Stored encrypted with your account. Type a single - to clear it. <a href={href} target="_blank" rel="noreferrer" className="text-accent hover:underline">Setup guide</a></>}>
        <Input type="password" autoComplete="off" value={value} onChange={e => setValue(e.target.value)} placeholder={saved ? 'saved — enter a replacement' : label} />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={Boolean(busy) || !value.trim()} onClick={save}>
          {busy === 'save' && <Loader2 className="size-3 animate-spin" />}Save and sign in
        </Button>
        <Button size="sm" variant="ghost" disabled={Boolean(busy) || (!saved && !value.trim())}
                onClick={() => check(value.trim())}>
          {busy === 'check' && <Loader2 className="size-3 animate-spin" />}Test connection
        </Button>
      </div>
      {status && !connected && (
        <p className="text-[10.5px] text-bad">{status.message || status.error}</p>
      )}
      {status?.connected && status.verified === false && (
        <p className="text-[10.5px] text-muted">{status.message}</p>
      )}
      {error && <p className="text-[10.5px] text-bad">{error}</p>}
    </div>
  </Row>
}

function Mongo({ deploy, onSave }) {
  const [uri, setUri] = useState('')
  const [busy, setBusy] = useState('')
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')

  // Tries the string typed in the box, or the saved one when the box is empty: it connects, signs in and pings.
  async function test(typed = uri.trim()) {
    setBusy('test')
    setErr('')
    setResult(null)
    try {
      setResult(await api.deploy('/mongodb/check', { uri: typed }))
    } catch (e) { setErr(e.message) }
    setBusy('')
  }

  async function save() {
    setBusy('save')
    setErr('')
    try {
      await onSave({ deploy_mongodb_uri: uri.trim() })
      setUri('')
    } catch (e) { setErr(e.message); setBusy(''); return }
    setBusy('')
    await test('')                                   // what is saved is what gets tried
  }

  return (
    <Row title="Production database" ok={Boolean(deploy?.mongodb_uri_set)} unknown={false}
         detail={deploy?.mongodb_uri_set ? `saved (${deploy.mongodb_uri_hint})`
                                         : 'the deployed app needs one it can reach'}>
      <div className="mt-2 w-full space-y-2">
        <Field label="MongoDB URI"
               hint="Kept separate from the MongoDB URI above, which is AgentForge's own
                     and is usually a local one. A loopback address is refused here —
                     deployed, it would point at a database that does not exist.">
          <Input type="password" value={uri} onChange={e => setUri(e.target.value)}
                 placeholder={deploy?.mongodb_uri_set
                   ? `saved (${deploy.mongodb_uri_hint})`
                   : 'mongodb+srv://user:password@cluster.mongodb.net/database'} />
        </Field>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={!uri.trim() || Boolean(busy)}
                  onClick={save}>
            {busy === 'save' && <Loader2 className="size-3 animate-spin" />} Save
          </Button>
          <Button size="sm" disabled={(!uri.trim() && !deploy?.mongodb_uri_set) || Boolean(busy)} onClick={() => test()}
                  title={uri.trim() ? 'Try what is typed above' : 'Try the saved connection string'}>
            {busy === 'test' && <Loader2 className="size-3 animate-spin" />} Test
          </Button>
        </div>
        {result && (
          <div className="space-y-1">
            <p className={cn('text-[10.5px]', result.ok ? (result.verified === false ? 'text-[#FFAB00]' : 'text-ink') : 'text-[#FF5630]')}>
              {result.message}
              {result.server_version ? ` · MongoDB ${result.server_version}` : ''}
              {result.database ? ` · database ${result.database}` : ''}
            </p>
            {(result.warnings || []).map((warning, i) => (
              <p key={i} className="text-[10.5px] text-[#FFAB00]">{warning}</p>
            ))}
          </div>
        )}
        {err && <p className="text-[10.5px] text-deep">{err}</p>}
      </div>
    </Row>
  )
}


function Row({ title, ok, unknown, detail, actions, children }) {
  return (
    <div className={cn('rounded-xl border border-[rgba(145,158,171,0.16)] border-l-[3px] bg-[#F2F0EF] p-3 shadow-sm transition-all',
      unknown ? 'border-l-white/20' : ok ? 'border-l-[#22C55E]' : 'border-l-[#FF5630]')}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="grid size-3.5 shrink-0 place-items-center">
          {unknown ? <Loader2 className="size-3 animate-spin text-[#6B7280]" />
                   : ok ? <Check className="size-3.5 text-ink" />
                        : <X className="size-3.5 text-[#FF5630]" />}
        </span>
        <span className="text-[12.5px] font-bold text-ink">{title}</span>
        <span className="min-w-0 flex-1 truncate text-[11px] text-[#6B7280]">{detail}</span>
        {actions}
      </div>
      {children}
    </div>
  )
}

const Field = ({ label, hint, children }) => (
  <label className="block">
    <span className="label-2xs mb-1 block text-muted2 font-bold uppercase tracking-wider">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[10px] leading-snug text-muted2">
               {hint}
             </span>}
  </label>
)

const Select = ({ value, onChange, options, placeholder }) => (
  <select value={value} onChange={e => onChange(e.target.value)}
          className="h-[32px] w-full rounded-xl border border-[rgba(145,158,171,0.2)] bg-[#F2F0EF] px-2.5
                     text-[12px] text-ink outline-none focus:border-[#BFB9FF]/60 transition-colors">
    {placeholder && <option value="" className="bg-[#F2F0EF] text-ink">{placeholder}</option>}
    {options.map(o => {
      const v = typeof o === 'string' ? o : o.value
      const l = typeof o === 'string' ? o : o.label
      return <option key={v} value={v} className="bg-[#F2F0EF] text-ink">{l}</option>
    })}
  </select>
)
