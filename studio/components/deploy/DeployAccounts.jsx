'use client'

import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ExternalLink, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { Button, Input as BaseInput } from '../ui'
import AccountList from '../AccountList'
import BrandIcon from '../BrandIcon'
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

/**
 * One service's page in Settings: its logo, whether it is connected, and its own form. Each service is listed
 * on its own in the Settings sidebar (`provider` is its id there), so a person sees one account at a time.
 */
export default function DeployAccount({ provider, deploy, onSaved }) {
  const [probe, setProbe] = useState(null)
  const [note, setNote] = useState('')
  const needsProbe = provider === 'github' || provider === 'aws'

  useEffect(() => {
    if (probe || !needsProbe) return
    api.deployRead('/onboarding/status')
      .then(setProbe)
      .catch(e => setNote(`could not read the deployment agent — ${e.message}`))
  }, [probe, needsProbe])

  const save = async (patch) => {
    await api.saveSettings(patch)
    onSaved?.()
  }

  return (
    <section className="space-y-4">
      {note && <p className="rounded-2xl bg-tint px-4 py-2.5 text-[11px] text-deep">{note}</p>}
      {provider === 'github' && <Github deploy={deploy} onSave={save} probe={probe} onRecheck={() => setProbe(null)} />}
      {provider === 'aws' && <Aws deploy={deploy} onSave={save} probe={probe} onRecheck={() => setProbe(null)} />}
      {provider === 'vercel' && <Vercel deploy={deploy} onSave={save} />}
      {provider === 'netlify' && (
        <HostedCredential title="Netlify" provider="netlify" setting="netlify_token" saved={deploy?.netlify_token_set} onSave={save}
          label="Personal access token" href="https://app.netlify.com/user/applications#personal-access-tokens"
          hint="Create a token in your Netlify account. The deployment uses it to provision your site and as an encrypted GitHub Actions secret." />
      )}
      {provider === 'azure' && (
        <HostedCredential title="Azure" provider="azure" setting="azure_credentials" saved={Boolean(deploy?.azure_credentials_set || deploy?.azure_account)} onSave={save}
          label="Service principal credentials (JSON)" href="https://learn.microsoft.com/en-us/azure/app-service/deploy-github-actions"
          hint="Enter JSON containing clientId, clientSecret, tenantId and subscriptionId for your deployment service principal. Give it access to the selected resource group." />
      )}
      {provider === 'supabase' && (
        <Row title="Supabase" ok={Boolean(deploy?.supabase_org)} unknown={false}
             detail={deploy?.supabase_org ? `signed in as ${deploy.supabase_org}` : 'every Supabase-stack project gets its own real project'}>
          <Soft><SupabaseConnect onDone={onSaved} /></Soft>
        </Row>
      )}
      {provider === 'mongodb' && <Mongodb deploy={deploy} onSave={save} />}
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
  const [picker, setPicker] = useState(null)   // the list of the account's clusters while it is open

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

  // Use, or sign out of, one of the accounts signed in through the Atlas CLI. Each has the cluster made for it, so
  // the connection string the deployments read changes with the account in use.
  async function changeAccount(kind, id) {
    setAccountBusy(`${kind}:${id}`); setAccountError('')
    try {
      setPicker(null)   // the list belongs to the account that was in use
      setAccount(await api.deploy(`/mongodb/account/${kind}`, { id }))
      await onSave({})
      setStatus(null)
    } catch (failure) { setAccountError(failure.message) } finally { setAccountBusy('') }
  }

  // Make a new free cluster. Only when asked: the ones the account already has are chosen from the list.
  async function provision() {
    setAccountBusy('provision'); setAccountError('')
    try {
      await api.deploy('/mongodb/provision', { create: true })
      setPicker(null)
      await loadAccount()
      await onSave({})   // the server already wrote deploy_mongodb_uri; this just refreshes the saved/hint props
      await test('')
    } catch (failure) { setAccountError(failure.message) } finally { setAccountBusy('') }
  }

  // The clusters the account already has, to choose one from.
  async function openPicker() {
    setPicker({ loading: true, rows: [], missing: false, error: '' })
    try {
      const found = await api.deploy('/mongodb/clusters')
      setPicker({ loading: false, rows: found.clusters || [], missing: Boolean(found.missing), error: '' })
    } catch (failure) { setPicker({ loading: false, rows: [], missing: false, error: failure.message }) }
  }

  async function useCluster(row) {
    setAccountBusy(`use:${row.group_id}:${row.name}`); setAccountError('')
    try {
      await api.deploy('/mongodb/cluster/use', { group_id: row.group_id, name: row.name })
      setPicker(null)
      await loadAccount()
      await onSave({})
      await test('')
    } catch (failure) { setAccountError(failure.message) } finally { setAccountBusy('') }
  }

  const connected = Boolean(status?.connected)
  const detail = status
    ? (connected ? 'connected — ready for a MongoDB-stack deployment' : status.message || 'connection refused')
    : saved ? 'connection string saved' : 'every MongoDB-stack deployment uses this, never a local database'

  return (
    <Row title="MongoDB" ok={saved ? connected : false} unknown={Boolean(saved) && !status} detail={detail}>
      <div className="space-y-4">
        <Soft className="space-y-3">
          <p className="text-[11.5px] text-muted">
            {!account ? 'Checking MongoDB Atlas…'
              : account.connected
                ? <>Atlas account connected{(account.account || account.org) ? <> — <b className="text-ink">{account.account || account.org}</b></> : ''}</>
                : 'Sign in to MongoDB Atlas and AgentForge creates a real cluster for your deployments. A browser tab opens, you approve it there, and that is all.'}
          </p>
          {account && account.via !== 'service_account' && (
            <CliSignIn provider="atlas" label="MongoDB Atlas command line tool" onDone={loadAccount} />
          )}
          {account?.via === 'cli' && account.accounts?.length > 1 && (
            <AccountList accounts={account.accounts} busy={accountBusy}
                         onSwitch={id => changeAccount('switch', id)} onRemove={id => changeAccount('remove', id)} />
          )}
          {account?.via === 'cli' && (
            <div className="space-y-1">
              <CliSignIn provider="atlas" add onDone={loadAccount} />
              {account.accounts?.length === 1 && (
                <p className="text-[10.5px] leading-snug text-muted2">
                  Have another Atlas account? Add it, then switch between them here. Each account gets its own
                  cluster.
                </p>
              )}
            </div>
          )}
          {account?.connected && (
            <div className="space-y-2.5">
              <div className="flex flex-wrap items-center gap-2">
                {account.cluster_ready && (
                  <span className="text-[11.5px] text-muted">Cluster in use — <b className="text-ink">{account.cluster}</b></span>
                )}
                <Button size="sm" variant={account.cluster_ready ? 'soft' : 'primary'}
                        disabled={Boolean(accountBusy) || picker?.loading}
                        onClick={() => (picker ? setPicker(null) : openPicker())}>
                  {picker?.loading && <Loader2 className="size-3 animate-spin" />}
                  {picker ? 'Close' : account.cluster_ready ? 'Change cluster' : 'Choose a cluster'}
                </Button>
                {account.via === 'service_account' && (
                  <Button size="sm" variant="ghost" disabled={Boolean(accountBusy)} onClick={disconnectAccount}>
                    {accountBusy === 'disconnect' && <Loader2 className="size-3 animate-spin" />}Disconnect
                  </Button>
                )}
              </div>
              {picker && <ClusterPicker picker={picker} busy={accountBusy} onUse={useCluster} onCreate={provision} onRefresh={openPicker} />}
            </div>
          )}
          {account && account.via !== 'service_account' && (
            <Advanced title="Advanced: use an Atlas Service Account instead">
                <Field label="Atlas Service Account"
                       hint={<>For automation, or if you already have one: in Atlas, go to Organization Access Manager
                               &rarr; Service Accounts &rarr; Create, give it a role that can manage projects and
                               clusters, then paste its Client ID and Secret here.{' '}
                               <a className="text-accent hover:underline" target="_blank" rel="noreferrer"
                                  href="https://cloud.mongodb.com/v2#/access/serviceAccounts">Open Atlas</a></>}>
                  <Input value={clientId} onChange={e => setClientId(e.target.value)} placeholder="Client ID" />
                </Field>
                <Input type="password" autoComplete="off" value={clientSecret}
                       onChange={e => setClientSecret(e.target.value)} placeholder="Client Secret" />
                <Button size="sm" disabled={!clientId.trim() || !clientSecret.trim() || Boolean(accountBusy)} onClick={connectAccount}>
                  {accountBusy === 'connect' && <Loader2 className="size-3 animate-spin" />}Connect account
                </Button>
            </Advanced>
          )}
          {accountError && <p className="text-[10.5px] text-bad">{accountError}</p>}
        </Soft>
        <Soft className="space-y-3">
        <Field label="Or paste a production connection string directly"
               hint="A real, internet-reachable cluster — MongoDB Atlas or any host you run. A loopback address (localhost, 127.0.0.1) is refused: a deployed application cannot reach this computer. Stored encrypted with your account. Type a single - to clear it.">
          <Input type="password" autoComplete="off" value={value} onChange={e => setValue(e.target.value)}
                 placeholder={saved ? `saved (…${deploy?.deploy_mongodb_uri_hint || ''})` : 'mongodb+srv://user:pass@cluster.mongodb.net/app'} />
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="soft" disabled={Boolean(busy) || !value.trim()} onClick={save}>
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
        </Soft>
      </div>
    </Row>
  )
}


/** The clusters an Atlas account already has, with a button to use one, and (only if wanted) a button to make another. */
function ClusterPicker({ picker, busy, onUse, onCreate, onRefresh }) {
  const creating = busy === 'provision'
  return (
    <div className="space-y-2">
      {picker.loading ? (
        <p className="flex items-center gap-2 text-[11.5px] text-muted"><Loader2 className="size-3 animate-spin" /> Looking for your clusters…</p>
      ) : picker.error ? (
        <p className="text-[10.5px] text-bad">{picker.error}</p>
      ) : (
        <>
          {picker.missing && (
            <p className="text-[10.5px] leading-snug text-bad">
              The cluster this studio was using is no longer in this account. Choose another one, or create a new one.
            </p>
          )}
          {picker.rows.length === 0 ? (
            <p className="text-[11.5px] text-muted">This account has no clusters yet. Create a free one below.</p>
          ) : (
            <ul className="space-y-1.5">
              {picker.rows.map(row => {
                const key = `use:${row.group_id}:${row.name}`
                const paused = row.state === 'PAUSED'
                return (
                  <li key={key} className="flex items-center gap-3 rounded-xl bg-panel px-3 py-2 shadow-sm">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12px] font-semibold text-ink">{row.name}</p>
                      <p className="truncate text-[10.5px] text-muted">
                        {[row.project, row.tier, row.region, row.state && row.state.toLowerCase()].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                    {row.selected ? (
                      <span className="text-[10.5px] font-semibold tracking-wide text-ok">IN USE</span>
                    ) : paused ? (
                      // A paused cluster has no address, and Atlas resumes a free one only in its own web console.
                      <Button size="sm" variant="ghost"
                              onClick={() => window.open(`https://cloud.mongodb.com/v2/${row.group_id}#/overview`, '_blank', 'noopener,noreferrer')}>
                        <ExternalLink className="size-3" />Resume in Atlas
                      </Button>
                    ) : (
                      <Button size="sm" variant="soft" disabled={Boolean(busy)} onClick={() => onUse(row)}>
                        {busy === key && <Loader2 className="size-3 animate-spin" />}Use this cluster
                      </Button>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          {picker.rows.some(row => row.state === 'PAUSED') && (
            <p className="text-[10.5px] leading-snug text-muted2">
              A paused cluster has no address, so nothing can connect to it (that is the &ldquo;address could not be found&rdquo;
              error). Atlas pauses a free cluster nobody has used for a while. Resume it in Atlas, then press Refresh.
            </p>
          )}
          <p className="text-[10.5px] leading-snug text-muted2">
            Choosing a cluster adds a database user (agentforge_app) to its project and lets any address reach it, with that
            user&apos;s password as the lock. The connection string saved below is replaced by the one for this cluster.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" disabled={Boolean(busy)} onClick={onCreate}>
              {creating && <Loader2 className="size-3 animate-spin" />}Create a new free cluster
            </Button>
            <Button size="sm" variant="ghost" disabled={Boolean(busy)} onClick={onRefresh}>Refresh</Button>
            {creating && <span className="text-[10.5px] text-muted2">this can take a few minutes…</span>}
          </div>
        </>
      )}
    </div>
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
      <div className="space-y-4">
        <Soft><CliSignIn provider="github" onDone={() => { onSave({}); onRecheck?.() }} /></Soft>
        <Advanced title="Other ways to sign in">
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
          <div className="rounded-2xl bg-bg/60 p-4">
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
            <Button size="sm" variant="soft"
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
          <Button size="sm" variant="soft" disabled={!token.trim() || busy}
                  onClick={save}>
            {busy && <Loader2 className="size-3 animate-spin" />} Save token
          </Button>
          <Button size="sm" onClick={onRecheck}>Recheck</Button>
        </div>
        </Advanced>
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
      <div className="space-y-4">
        <Soft className="space-y-3">
          <Field label="Deploy into">
            <Select value={region} onChange={setRegion} options={AWS_REGIONS} />
          </Field>
          <CliSignIn provider="aws" region={region} label="AWS command line tool"
                     onDone={() => { setProfile(AWS_CONSOLE_PROFILE); onSave({ aws_profile: AWS_CONSOLE_PROFILE, aws_region: region }); onRecheck?.() }} />
        </Soft>

        <Advanced title="IAM Identity Center (advanced)">
        <Field label="Identity Center start URL">
          <Input value={startUrl} onChange={e => setStartUrl(e.target.value)}
                 placeholder="https://d-xxxxxxxxxx.awsapps.com/start" />
        </Field>
        <Field label="Sign-in region">
          <Select value={ssoRegion} onChange={setSsoRegion} options={SSO_REGIONS} />
        </Field>

        {!flow && (
          <Button size="sm" variant="soft"
                  disabled={!startUrl.trim() || Boolean(busy)} onClick={begin}>
            {busy === 'starting' && <Loader2 className="size-3 animate-spin" />}
            {connected ? 'Connect a different account' : 'Sign in to AWS'}
          </Button>
        )}

        {flow && !accounts && (
          <div className="rounded-2xl bg-bg/60 p-4">
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
            <Button size="sm" variant="primary"
                    disabled={!account || !role || Boolean(busy)} onClick={use}>
              {busy === 'selecting' && <Loader2 className="size-3 animate-spin" />}
              Use this account
            </Button>
          </div>
        )}

        </Advanced>

        <Soft>
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
          <Button size="sm" variant="soft" className="mt-2"
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
        </Soft>

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
      <div className="space-y-4">
        <Soft><CliSignIn provider="vercel" onDone={() => onSave({})} /></Soft>
        <Soft className="space-y-3">
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
          <Button size="sm" variant="soft" disabled={!token.trim() || Boolean(busy)}
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
        </Soft>
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
    <div className="space-y-4">
    {(provider === 'netlify' || provider === 'azure') && (
      <Soft><CliSignIn provider={provider} onDone={() => onSave({})} /></Soft>
    )}
    <Soft className="space-y-3">
      <Field label={label} hint={<>{hint} Stored encrypted with your account. Type a single - to clear it. <a href={href} target="_blank" rel="noreferrer" className="text-accent hover:underline">Setup guide</a></>}>
        <Input type="password" autoComplete="off" value={value} onChange={e => setValue(e.target.value)} placeholder={saved ? 'saved — enter a replacement' : label} />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="soft" disabled={Boolean(busy) || !value.trim()} onClick={save}>
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
    </Soft>
    </div>
  </Row>
}

/** A service's header (logo, name, whether it is connected) and then its form. No borders: soft fills only. */
function Row({ title, ok, unknown, detail, actions, children }) {
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center gap-3.5">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-panel shadow-sm">
          <BrandIcon name={title.toLowerCase()} className="size-6" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-display text-[15px] font-bold text-ink">{title}</h3>
            <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10.5px] font-semibold',
              // Tints made with the colour variables: a `bg-ok` class would be redrawn as an outlined box by globals.css.
              unknown ? 'bg-ink/[.07] text-muted'
                : ok ? 'bg-[color-mix(in_srgb,var(--green)_14%,transparent)] text-ok'
                     : 'bg-[color-mix(in_srgb,var(--red)_12%,transparent)] text-bad')}>
              {unknown ? <Loader2 className="size-2.5 animate-spin" />
                       : <span className={cn('size-1.5 rounded-full', ok ? 'bg-ok' : 'bg-bad')} />}
              {unknown ? 'Checking' : ok ? 'Connected' : 'Not connected'}
            </span>
          </div>
          <p className="mt-0.5 text-[11.5px] leading-snug text-muted">{detail}</p>
        </div>
        {actions}
      </header>
      {children}
    </div>
  )
}

/** The fields here are filled, not outlined. */
const Input = ({ className, ...rest }) => <BaseInput className={cn('border-transparent bg-bg/60 shadow-none', className)} {...rest} />

/** A collapsed section for the less usual ways in. */
const Advanced = ({ title, children }) => (
  <details className="group rounded-2xl bg-panel px-4 py-3 shadow-sm">
    <summary className="flex cursor-pointer select-none list-none items-center justify-between text-[11.5px] font-semibold text-muted transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
      {title}
      <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
    </summary>
    <div className="mt-3 space-y-3">{children}</div>
  </details>
)

/** A quiet section inside a form (a flow in progress, the advanced options). */
const Soft = ({ className, children }) => <div className={cn('rounded-2xl bg-panel p-4 shadow-sm', className)}>{children}</div>

const Field = ({ label, hint, children }) => (
  <label className="block">
    <span className="mb-1.5 block text-[11.5px] font-semibold text-ink/85">{label}</span>
    {children}
    {hint && <span className="mt-1.5 block text-[10.5px] leading-snug text-muted2">
               {hint}
             </span>}
  </label>
)

const Select = ({ value, onChange, options, placeholder }) => (
  <select value={value} onChange={e => onChange(e.target.value)}
          className="h-10 w-full rounded-xl border border-transparent bg-bg/60 px-3
                     text-[12.5px] text-ink outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent">
    {placeholder && <option value="" className="bg-panel text-ink">{placeholder}</option>}
    {options.map(o => {
      const v = typeof o === 'string' ? o : o.value
      const l = typeof o === 'string' ? o : o.label
      return <option key={v} value={v} className="bg-panel text-ink">{l}</option>
    })}
  </select>
)
