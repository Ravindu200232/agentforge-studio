'use client'

import { useEffect, useRef, useState } from 'react'
import { Check, ExternalLink, Loader2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { Button, Input } from '../ui'
import CliSignIn from '../CliSignIn'
import SupabaseConnect from '../SupabaseConnect'
import { cn } from '@/lib/utils'


const SSO_REGIONS = ['us-east-1', 'us-east-2', 'us-west-2', 'eu-west-1',
                     'eu-central-1', 'ap-south-1', 'ap-southeast-1',
                     'ap-southeast-2', 'ap-northeast-1']
const AWS_REGIONS = ['ap-south-1', 'us-east-1', 'us-east-2', 'us-west-2',
                     'eu-west-1', 'eu-west-2', 'eu-central-1',
                     'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1']
const AWS_CONSOLE_PROFILE = 'agentforge-console'

export default function DeployAccounts({ deploy, onSaved }) {
  const [probe, setProbe] = useState(null)
  const [note, setNote] = useState('')

  useEffect(() => {
    if (probe) return
    api.deployRead('/onboarding/status')
      .then(setProbe)
      .catch(e => setNote(`could not read the deployment agent — ${e.message}`))
  }, [probe])

  const save = async (patch) => {
    await api.saveSettings(patch)
    onSaved?.()
  }

  return (
    <section className="space-y-4">
      {note && (
        <p className="border-l-[3px] border-accent bg-tint px-2.5 py-1.5 text-[11px] text-deep">
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
      <Row title="Supabase" ok={Boolean(deploy?.supabase_org)} unknown={false}
           detail={deploy?.supabase_org ? `signed in as ${deploy.supabase_org}` : 'every Supabase-stack project gets its own real project'}>
        <div className="mt-2 w-full">
          <SupabaseConnect onDone={onSaved} />
        </div>
      </Row>
      <Mongodb deploy={deploy} onSave={save} />
    </section>
  )
}

function Mongodb({ deploy, onSave }) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState('')
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const saved = Boolean(deploy?.deploy_mongodb_uri_set)

  const [account, setAccount] = useState(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [accountBusy, setAccountBusy] = useState('')
  const [accountError, setAccountError] = useState('')

  const loadAccount = () => api.deploy('/mongodb/account/status').then(setAccount).catch(() => {})
  useEffect(() => { loadAccount() }, [])

  useEffect(() => {
    let live = true
    if (!saved) { setStatus(null); return undefined }
    api.deploy('/mongodb/status', { uri: '' }).then(a => { if (live) setStatus(a) }).catch(() => {})
    return () => { live = false }
  }, [saved])

  async function test(uri) {
    setBusy('check'); setError(''); setStatus(null)
    try { setStatus(await api.deploy('/mongodb/status', { uri })) }
    catch (failure) { setError(failure.message) } finally { setBusy('') }
  }

  async function save() {
    setBusy('save'); setError('')
    try {
      const uri = value.trim()
      await onSave({ deploy_mongodb_uri: uri })
      setValue('')
      if (uri && uri !== '-') await test('')
    } catch (failure) { setError(failure.message) } finally { setBusy('') }
  }

  async function connectAccount() {
    setAccountBusy('connect'); setAccountError('')
    try {
      await api.deploy('/mongodb/account/save', { client_id: clientId.trim(), client_secret: clientSecret.trim() })
      setClientId(''); setClientSecret('')
      await loadAccount()
    } catch (failure) { setAccountError(failure.message) } finally { setAccountBusy('') }
  }

  async function disconnectAccount() {
    setAccountBusy('disconnect'); setAccountError('')
    try { await api.deploy('/mongodb/account/forget', {}); await loadAccount() }
    catch (failure) { setAccountError(failure.message) } finally { setAccountBusy('') }
  }

  async function provision() {
    setAccountBusy('provision'); setAccountError('')
    try {
      await api.deploy('/mongodb/provision', {})
      await loadAccount()
      await onSave({})   // the server already wrote deploy_mongodb_uri; this just refreshes the saved/hint props
      await test('')
    } catch (failure) { setAccountError(failure.message) } finally { setAccountBusy('') }
  }

  const connected = Boolean(status?.connected)
  const detail = status
    ? (connected ? 'connected — ready for a MongoDB-stack deployment' : status.message || 'connection refused')
    : saved ? 'connection string saved' : 'every MongoDB-stack deployment uses this, never a local database'

  return (
    <Row title="MongoDB" ok={saved ? connected : false} unknown={Boolean(saved) && !status} detail={detail}>
      <div className="mt-2 w-full space-y-3">
        <div className="space-y-2 border-b border-line pb-3">
          <p className="text-[11px] text-muted">
            {!account ? 'Checking MongoDB Atlas…'
              : account.connected
                ? <>Atlas account connected{account.org ? <> — <b className="text-ink">{account.org}</b></> : ''}</>
                : 'Connect a MongoDB Atlas Service Account to auto-provision a real cluster, instead of pasting one below.'}
          </p>
          {account && !account.connected && (
            <div className="space-y-2">
              <Field label="Atlas Service Account"
                     hint={<>One-time setup: in Atlas, go to Organization Access Manager &rarr; Service Accounts &rarr;
                             Create, give it a role that can manage projects and clusters, then paste its Client ID
                             and Secret here. (Atlas has no one-click browser sign-in yet for third-party apps like
                             this one — MongoDB requires a partner approval for that — so this is the closest
                             self-service equivalent.){' '}
                             <a className="text-accent hover:underline" target="_blank" rel="noreferrer"
                                href="https://cloud.mongodb.com/v2#/access/serviceAccounts">Open Atlas</a></>}>
                <Input value={clientId} onChange={e => setClientId(e.target.value)} placeholder="Client ID" />
              </Field>
              <Input type="password" autoComplete="off" value={clientSecret}
                     onChange={e => setClientSecret(e.target.value)} placeholder="Client Secret" />
              <Button size="sm" disabled={!clientId.trim() || !clientSecret.trim() || Boolean(accountBusy)} onClick={connectAccount}>
                {accountBusy === 'connect' && <Loader2 className="size-3 animate-spin" />}Connect account
              </Button>
            </div>
          )}
          {account?.connected && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" disabled={Boolean(accountBusy) || account.cluster_ready} onClick={provision}>
                {accountBusy === 'provision' && <Loader2 className="size-3 animate-spin" />}
                {account.cluster_ready ? 'Cluster ready' : 'Create / use a cluster'}
              </Button>
              <Button size="sm" variant="ghost" disabled={Boolean(accountBusy)} onClick={disconnectAccount}>
                {accountBusy === 'disconnect' && <Loader2 className="size-3 animate-spin" />}Disconnect
              </Button>
              {accountBusy === 'provision' && <span className="text-[10.5px] text-muted2">this can take a few minutes…</span>}
            </div>
          )}
          {accountError && <p className="text-[10.5px] text-bad">{accountError}</p>}
        </div>
        <Field label="Or paste a production connection string directly"
               hint="A real, internet-reachable cluster — MongoDB Atlas or any host you run. A loopback address (localhost, 127.0.0.1) is refused: a deployed application cannot reach this computer. Stored encrypted with your account. Type a single - to clear it.">
          <Input type="password" autoComplete="off" value={value} onChange={e => setValue(e.target.value)}
                 placeholder={saved ? `saved (…${deploy?.deploy_mongodb_uri_hint || ''})` : 'mongodb+srv://user:pass@cluster.mongodb.net/app'} />
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={Boolean(busy) || !value.trim()} onClick={save}>
            {busy === 'save' && <Loader2 className="size-3 animate-spin" />}Save
          </Button>
          <Button size="sm" variant="ghost" disabled={Boolean(busy) || (!saved && !value.trim())}
                  onClick={() => test(value.trim())}>
            {busy === 'check' && <Loader2 className="size-3 animate-spin" />}Test connection
          </Button>
        </div>
        {status && !connected && <p className="text-[10.5px] text-bad">{status.message}</p>}
        {status?.warnings?.map(w => <p key={w} className="text-[10.5px] text-muted">{w}</p>)}
        {error && <p className="text-[10.5px] text-bad">{error}</p>}
      </div>
    </Row>
  )
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

function Row({ title, ok, unknown, detail, actions, children }) {
  return (
    <div className={cn('rounded-xl border border-line border-l-[3px] bg-panel p-3 shadow-sm transition-all',
      unknown ? 'border-l-white/20' : ok ? 'border-l-[var(--green)]' : 'border-l-[var(--red)]')}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="grid size-3.5 shrink-0 place-items-center">
          {unknown ? <Loader2 className="size-3 animate-spin text-muted" />
                   : ok ? <Check className="size-3.5 text-ink" />
                        : <X className="size-3.5 text-bad" />}
        </span>
        <span className="text-[12.5px] font-bold text-ink">{title}</span>
        <span className="min-w-0 flex-1 truncate text-[11px] text-muted">{detail}</span>
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
          className="h-[32px] w-full rounded-xl border border-line bg-panel px-2.5
                     text-[12px] text-ink outline-none focus:border-accent/60 transition-colors">
    {placeholder && <option value="" className="bg-panel text-ink">{placeholder}</option>}
    {options.map(o => {
      const v = typeof o === 'string' ? o : o.value
      const l = typeof o === 'string' ? o : o.label
      return <option key={v} value={v} className="bg-panel text-ink">{l}</option>
    })}
  </select>
)
