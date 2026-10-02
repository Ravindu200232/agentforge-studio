'use client'

/**
 * Database: what the project's databases hold, read live by their own tools: the Supabase command line tool for the
 * project's Supabase project, and the project's own MongoDB driver for a MongoDB stack. The rail lists every look the
 * catalogue (`prompts/database/monitors.json`) offers for the connections this project has; Home says what is connected
 * and where. A table or collection opens its first rows beside the page.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, ArchiveRestore, Check, Cloud, Database, FolderArchive, GitBranch, HardDrive, KeyRound, Layers,
  ListTree, Loader2, Lock, LockKeyhole, Network, Puzzle, Server, ShieldCheck, SlidersHorizontal, SquareFunction, Table2,
  Timer, Users, Zap,
} from 'lucide-react'

import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { stackNeeds } from '@/lib/stacks'
import { cn } from '@/lib/utils'
import { Tip } from '../ui'
import { Card, Facts, Note, Stats } from '../deploy/cli/parts'
import { Db } from './context'
import DatabasePage from './pages'
import RowsDrawer from './RowsDrawer'

const ICONS = {
  project: Cloud, 'api-keys': KeyRound, tables: Table2, storage: HardDrive, 'auth-users': Users, policies: ShieldCheck,
  'db-functions': SquareFunction, extensions: Puzzle, 'edge-functions': Zap, secrets: Lock, migrations: GitBranch,
  backups: ArchiveRestore, 'database-stats': Activity, 'index-stats': ListTree, outliers: Timer,
  'postgres-config': SlidersHorizontal, ssl: LockKeyhole, network: Network,
  'mongo-overview': Server, 'mongo-collections': Layers, 'mongo-indexes': ListTree, 'mongo-gridfs': FolderArchive,
}

export default function DatabasePanel({ stack = '', onSettings, connectionsVersion = 0 }) {
  const project = useStore(s => s.project)
  const [listing, setListing] = useState({ loaded: false, items: [], context: {}, error: '' })
  const [view, setView] = useState('home')
  const [rows, setRows] = useState(null)
  const [accounts, setAccounts] = useState({ supabase: null, mongodb: null })
  const needs = stackNeeds(stack)

  const load = useCallback(() => {
    if (!project) return () => {}
    let ok = true
    api.cliMonitorList(project, 'database')
      .then(r => { if (ok) setListing({ loaded: true, items: r?.items || [], context: r?.context || {}, error: '' }) })
      .catch(e => { if (ok) setListing({ loaded: true, items: [], context: {}, error: e.message }) })
    return () => { ok = false }
  }, [project])
  useEffect(() => load(), [load, connectionsVersion])

  // Whether the accounts themselves are connected: a project with no database yet still says why.
  useEffect(() => {
    let ok = true
    api.supabaseOauthStatus().then(r => { if (ok) setAccounts(a => ({ ...a, supabase: r || {} })) })
      .catch(() => { if (ok) setAccounts(a => ({ ...a, supabase: {} })) })
    api.settings().then(r => { if (ok) setAccounts(a => ({ ...a, mongodb: { saved: Boolean(r?.deploy?.deploy_mongodb_uri_set) } })) })
      .catch(() => { if (ok) setAccounts(a => ({ ...a, mongodb: { saved: false } })) })
    return () => { ok = false }
  }, [connectionsVersion])

  useEffect(() => { setView('home'); setRows(null) }, [project])
  const current = listing.items.find(item => item.id === view)
  useEffect(() => { if (view !== 'home' && listing.loaded && !current) setView('home') }, [view, listing.loaded, current])

  const shared = useMemo(() => ({ context: listing.context, openRows: setRows, go: setView }), [listing.context])

  if (!project) return <div className="min-h-0 flex-1 overflow-auto p-5 text-[12px] text-muted">Open a project first.</div>

  return (
    <Db.Provider value={shared}>
      <div className="relative flex min-h-0 flex-1 overflow-hidden bg-[radial-gradient(circle_at_top_right,rgba(191,185,255,.08),transparent_30%)]">
        <DatabaseNav view={view} setView={setView} items={listing.items} />
        <div className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1180px] space-y-4 p-5">
            {view !== 'home' && current
              ? <DatabasePage key={`${project}:${current.set}/${current.id}`} project={project} item={current} />
              : <Home listing={listing} accounts={accounts} needs={needs} onSettings={onSettings} go={setView} />}
          </div>
        </div>
        {rows && <RowsDrawer key={JSON.stringify(rows)} project={project} target={rows} onClose={() => setRows(null)} />}
      </div>
    </Db.Provider>
  )
}

function DatabaseNav({ view, setView, items }) {
  return (
    <aside aria-label="Database sections" className="flex w-[52px] shrink-0 flex-col items-center gap-1 overflow-y-auto border-r border-line bg-panel px-2 py-3 no-scrollbar">
      <Tip text="Databases home" side="right">
        <button type="button" onClick={() => setView('home')} aria-label="Databases" aria-pressed={view === 'home'}
                className={cn('grid size-9 place-items-center rounded-xl text-muted2 transition-colors hover:bg-raised hover:text-ink',
                  view === 'home' && 'text-deep')}>
          <Database className="size-4" />
        </button>
      </Tip>
      {items.map((item, index) => {
        const Icon = ICONS[item.id] || Database
        const newSet = index === 0 || item.cli !== items[index - 1]?.cli
        const newGroup = !newSet && item.group !== items[index - 1]?.group
        return (
          <div key={item.id} className="flex flex-col items-center">
            {newSet && <span className="mb-1 mt-2 text-[8.5px] font-bold uppercase tracking-[.08em] text-muted2">{item.cli === 'MongoDB' ? 'Mongo' : item.cli}</span>}
            {newGroup && <span className="my-1 block h-px w-5 bg-line" />}
            <Tip text={`${item.label} · ${item.group}`} side="right">
              <button type="button" onClick={() => setView(item.id)} aria-label={item.label} aria-pressed={view === item.id}
                      className={cn('grid size-9 place-items-center rounded-xl text-muted2 transition-colors hover:bg-raised hover:text-ink',
                        view === item.id && 'bg-accent/15 text-deep')}>
                <Icon className="size-4" />
              </button>
            </Tip>
          </div>
        )
      })}
    </aside>
  )
}

// ---- home ------------------------------------------------------------------------------------------------------

function Home({ listing, accounts, needs, onSettings, go }) {
  const { context } = listing
  const supabase = context?.supabase
  const mongodb = context?.mongodb
  const showMongo = Boolean(mongodb) || needs.includes('mongodb')
  // A MongoDB-only stack has no Supabase: its card appears only when a Supabase database actually exists.
  const showSupabase = Boolean(supabase) || needs.includes('supabase')

  return (
    <section className="space-y-4">
      <header className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-ink"><Database className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <h1 className="text-[17px] font-semibold text-ink">Databases</h1>
          <p className="mt-0.5 max-w-[720px] text-[12px] leading-relaxed text-muted">
            What this project's databases hold, read live by their own tools whenever a page is opened. Pick a page on the left —
            tables and collections open their first rows when clicked. Nothing here changes any data.
          </p>
        </div>
      </header>

      {listing.error && <Note tone="bad">{listing.error}</Note>}
      {!listing.loaded && <p className="flex items-center gap-2 text-[12px] text-muted"><Loader2 className="size-3.5 animate-spin" /> Reading this project's connections…</p>}

      <div className={cn('grid gap-4', showMongo && showSupabase && 'lg:grid-cols-2')}>
        {showSupabase && <SupabaseCard supabase={supabase} account={accounts.supabase} onSettings={onSettings} go={go} loaded={listing.loaded} />}
        {showMongo && <MongoCard mongodb={mongodb} account={accounts.mongodb} onSettings={onSettings} go={go} loaded={listing.loaded} />}
      </div>
    </section>
  )
}

function Connect({ name, onSettings }) {
  return (
    <button type="button" onClick={() => onSettings?.('integrations')} title={`Connect ${name} in Settings › Integrations`}
            className="inline-flex h-7 items-center gap-1 rounded-lg border border-bad/35 px-2.5 text-[11px] font-medium text-bad transition-colors hover:bg-bad/10">
      {name} not connected · <span className="underline">Connect</span>
    </button>
  )
}

const Connected = ({ children }) => (
  <span className="inline-flex h-7 items-center gap-1 rounded-lg border border-ok/35 px-2.5 text-[11px] font-medium text-ok">
    <Check className="size-3" /> {children}
  </span>
)

function Jumps({ items, go }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map(([id, label]) => {
        const Icon = ICONS[id] || Database
        return (
          <button key={id} type="button" onClick={() => go(id)}
                  className="inline-flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-[11px] font-semibold text-ink ring-1 ring-inset ring-black/10 hover:bg-black/5">
            <Icon className="size-3 text-muted" /> {label}
          </button>
        )
      })}
    </div>
  )
}

function SupabaseCard({ supabase, account, onSettings, go, loaded }) {
  const signedIn = Boolean(account?.connected)
  return (
    <Card title="Supabase" right={supabase ? <Connected>Connected{account?.org ? ` · ${account.org}` : ''}</Connected>
      : account && !signedIn ? <Connect name="Supabase" onSettings={onSettings} /> : null}>
      {supabase ? (
        <div className="space-y-4">
          <Facts items={[
            ['Project', supabase.name], ['Reference', supabase.ref, 'mono'],
            ['API address', supabase.url, 'link'],
            ['Dashboard', `https://supabase.com/dashboard/project/${supabase.ref}`, 'link'],
          ]} />
          <Jumps go={go} items={[['tables', 'Tables'], ['storage', 'Storage buckets'], ['auth-users', 'Auth users'],
                                  ['policies', 'Security'], ['database-stats', 'Health'], ['project', 'Project']]} />
        </div>
      ) : !loaded || account === null ? (
        <p className="text-[12px] text-muted">Checking…</p>
      ) : signedIn ? (
        <Empty>This project's own Supabase project is created the first time it is built. Its tables, storage and users
          show here after that.</Empty>
      ) : (
        <Empty>Connect a Supabase account in Settings › Integrations. Every build gets a Supabase project of its own there.</Empty>
      )}
    </Card>
  )
}

function MongoCard({ mongodb, account, onSettings, go, loaded }) {
  const [atlas, setAtlas] = useState(null)
  useEffect(() => {
    if (!mongodb) return
    let ok = true
    api.databaseAtlas().then(r => { if (ok) setAtlas(r) }).catch(() => { if (ok) setAtlas({}) })
    return () => { ok = false }
  }, [mongodb])
  const cluster = atlas?.cluster
  return (
    <Card title="MongoDB" right={mongodb ? <Connected>Connected</Connected>
      : account && !account.saved ? <Connect name="MongoDB" onSettings={onSettings} /> : null}>
      {mongodb ? (
        <div className="space-y-4">
          {cluster ? (
            <Stats items={[
              { label: 'Cluster', value: cluster.name, sub: cluster.host },
              { label: 'Tier', value: cluster.tier || '—', sub: [cluster.provider, cluster.region].filter(Boolean).join(' · ') },
              { label: 'State', value: cluster.paused ? 'Paused' : cluster.state || '—', tone: cluster.paused ? 'warn' : /idle/i.test(cluster.state) ? 'ok' : 'run' },
              { label: 'MongoDB', value: cluster.version || '—', sub: cluster.backup ? 'backups on' : 'no backups' },
            ]} />
          ) : null}
          <Facts items={[
            ['Database this app uses', mongodb.database, 'mono'],
            ['Atlas organisation', atlas?.org],
            ['Network access', atlas?.access?.length ? atlas.access.map(row => row.entry).join(', ') : ''],
            ['Database users', atlas?.users?.length ? atlas.users.map(row => row.name).join(', ') : ''],
          ]} />
          {atlas?.access?.some(row => row.entry === '0.0.0.0/0') && (
            <Note tone="warn">The cluster accepts connections from any address (0.0.0.0/0). That is what a hosted app on a
              changing address needs, and it makes the database user's password the only lock.</Note>
          )}
          {atlas?.error && <Note tone="bad">Atlas did not answer: {atlas.error}</Note>}
          <Jumps go={go} items={[['mongo-collections', 'Collections'], ['mongo-overview', 'Overview'],
                                  ['mongo-indexes', 'Indexes'], ['mongo-gridfs', 'GridFS buckets']]} />
        </div>
      ) : !loaded || account === null ? (
        <p className="text-[12px] text-muted">Checking…</p>
      ) : account?.saved ? (
        <Empty>This project does not use MongoDB yet, or it has not been built: its collections show here once it is.</Empty>
      ) : (
        <Empty>Save a MongoDB connection string (or connect an Atlas account) in Settings › Integrations.</Empty>
      )}
    </Card>
  )
}

const Empty = ({ children }) => <p className="rounded-xl border border-dashed border-black/10 px-4 py-5 text-[12px] leading-relaxed text-muted">{children}</p>
