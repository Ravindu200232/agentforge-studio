'use client'

/**
 * One page per database look in `prompts/database/monitors.json`, keyed `<set>/<id>`; a look without a page of its own
 * is laid out automatically. Every page is a `View` (it runs the command when opened and shows its live status), and
 * lays the answer out with the same pieces the deployment pages use.
 */

import { useState } from 'react'
import {
  Activity, ArchiveRestore, Cloud, FolderArchive, GitBranch, HardDrive, KeyRound, Layers, ListTree, Lock, Puzzle,
  Server, ShieldCheck, SquareFunction, Table2, Timer, Users, Zap,
} from 'lucide-react'

import { Auto, Bars, Card, Facts, Note, StackedBar, Stats, Table, View, bytes, parseTable } from '../deploy/cli/parts'
import { useDatabase } from './context'

/** The rows of a `supabase db query -o json` answer. */
const sqlRows = json => (Array.isArray(json?.rows) ? json.rows : null)
const number = value => (value == null || value === '' ? '—' : Number(value).toLocaleString())
const percent = value => (value == null || value === '' ? '—' : `${Number(value).toFixed(1)}%`)

/** A text table the tool printed (`a | b` with a rule under the header), as rows. */
function TextTable({ text, empty }) {
  const { columns, rows } = parseTable(text)
  if (!columns.length) return null
  return <Table rows={rows} empty={empty} columns={columns.map(name => ({ label: name, key: name, mono: /query|statement/i.test(name) }))} />
}

/** What a MongoDB look answered, or why it could not. */
function mongo(json, render) {
  if (!json) return null
  if (json.ok === false) return <Note tone="bad">{json.message || 'MongoDB could not be read.'}</Note>
  return render(json)
}

// ---- Supabase --------------------------------------------------------------------------------------------------

function SupabaseProject({ project, item }) {
  const { context } = useDatabase()
  const ref = context?.supabase?.ref
  return (
    <View project={project} item={item} icon={Cloud} title="Project" about="This project's own Supabase project: where it runs, its Postgres version and whether it is healthy.">
      {({ json }) => {
        if (!Array.isArray(json)) return null
        const mine = json.find(row => row.ref === ref || row.id === ref)
        if (!mine) return <Note tone="warn">The signed-in Supabase account does not list this project ({ref}).</Note>
        const others = json.filter(row => row !== mine)
        return (<>
          <Stats items={[
            { label: 'Status', value: mine.status || '—', tone: /healthy/i.test(mine.status) ? 'ok' : /inactive|paused/i.test(mine.status) ? 'warn' : 'run' },
            { label: 'Region', value: mine.region || '—' },
            { label: 'Postgres', value: mine.database?.postgres_engine || '—', sub: mine.database?.version },
            { label: 'Created', value: mine.created_at ? new Date(mine.created_at).toLocaleDateString() : '—' },
          ]} />
          <Card><Facts items={[
            ['Name', mine.name], ['Reference', mine.ref || mine.id, 'mono'], ['Database host', mine.database?.host, 'mono'],
            ['Release channel', mine.database?.release_channel], ['Organisation', mine.organization_slug || mine.organization_id, 'mono'],
            ['Dashboard', `https://supabase.com/dashboard/project/${mine.ref || mine.id}`, 'link'],
          ]} /></Card>
          {others.length > 0 && (
            <Table rows={others} empty="" columns={[
              { label: 'Other projects in the account', key: 'name' }, { label: 'Status', key: 'status', kind: 'status' },
              { label: 'Region', key: 'region' }, { label: 'Created', key: 'created_at', kind: 'date' },
            ]} />
          )}
        </>)
      }}
    </View>
  )
}

function SupabaseKeys({ project, item }) {
  return (
    <View project={project} item={item} icon={KeyRound} title="API keys" about="The keys apps use to reach this project. Secret keys are never shown here: only their names, kinds and prefixes.">
      {({ json }) => Array.isArray(json) ? (
        <Table rows={json} empty="No API keys." columns={[
          { label: 'Name', key: 'name' }, { label: 'Kind', key: 'type' }, { label: 'Prefix', key: 'prefix', mono: true },
          { label: 'Description', key: 'description' }, { label: 'Key', key: 'api_key', mono: true },
        ]} />
      ) : null}
    </View>
  )
}

function SupabaseTables({ project, item }) {
  const { openRows } = useDatabase()
  const [system, setSystem] = useState(false)
  return (
    <View project={project} item={item} icon={Table2} wide title="Tables" about="Every table, how many rows and how much space it has, and whether row level security protects it. Click a table to see its first rows.">
      {({ json }) => {
        const all = sqlRows(json)
        if (!all) return null
        const rows = all.filter(row => system || !row.system)
        const appTables = all.filter(row => !row.system)
        const open = appTables.filter(row => row.schema === 'public' && !row.rls_enabled)
        return (<>
          <Stats items={[
            { label: 'Tables', value: appTables.length, sub: `${all.length - appTables.length} more in Supabase's own schemas` },
            { label: 'Rows', value: number(appTables.reduce((sum, row) => sum + Number(row.live_rows || row.estimated_rows || 0), 0)) },
            { label: 'Size', value: bytes(appTables.reduce((sum, row) => sum + Number(row.total_bytes || 0), 0)) },
            { label: 'Without RLS', value: open.length, tone: open.length ? 'bad' : 'ok', sub: open.length ? 'public tables anyone with the anon key can read' : 'every public table is protected' },
          ]} />
          {open.length > 0 && <Note tone="warn">Row level security is off on {open.map(row => row.name).join(', ')}: with the public anon key, anyone can read and change these tables directly.</Note>}
          {rows.filter(row => Number(row.total_bytes) > 0).length > 1 && (
            <Bars title="Largest tables" format={bytes}
                  items={[...rows].sort((a, b) => b.total_bytes - a.total_bytes).slice(0, 10)
                    .map(row => ({ label: `${row.schema}.${row.name}`, value: Number(row.total_bytes), tone: row.system ? 'mute' : 'run' }))} />
          )}
          <label className="flex w-fit cursor-pointer items-center gap-1.5 px-1 text-[11.5px] text-muted">
            <input type="checkbox" checked={system} onChange={e => setSystem(e.target.checked)} className="accent-[var(--accent)]" />
            Show Supabase's own schemas (auth, storage, realtime…)
          </label>
          <Table rows={rows} empty={system ? 'No tables.' : 'This project has no tables of its own yet.'}
                 onRow={row => openRows({ source: 'supabase', schema: row.schema, table: row.name })} rowTitle="Show the first rows"
                 columns={[
                   { label: 'Table', get: row => `${row.schema}.${row.name}`, mono: true },
                   { label: 'Rows', get: row => number(row.live_rows || row.estimated_rows) },
                   { label: 'Size', key: 'total_bytes', kind: 'bytes' }, { label: 'Indexes', key: 'index_bytes', kind: 'bytes' },
                   { label: 'Columns', key: 'columns' }, { label: 'RLS', key: 'rls_enabled', kind: 'yesno' },
                   { label: 'Policies', key: 'policies' }, { label: 'About', key: 'comment' },
                 ]} />
        </>)
      }}
    </View>
  )
}

function SupabaseStorage({ project, item }) {
  return (
    <View project={project} item={item} icon={HardDrive} title="Storage buckets" about="Where the app keeps uploaded files: each bucket, whether it is public, and how many files and bytes it holds.">
      {({ json }) => {
        const rows = sqlRows(json)
        if (!rows) return null
        return (<>
          <Stats items={[
            { label: 'Buckets', value: rows.length },
            { label: 'Files', value: number(rows.reduce((sum, row) => sum + Number(row.objects || 0), 0)) },
            { label: 'Size', value: bytes(rows.reduce((sum, row) => sum + Number(row.bytes || 0), 0)) },
            { label: 'Public', value: rows.filter(row => row.public).length, sub: 'readable by anyone with the link' },
          ]} />
          {rows.length > 1 && rows.some(row => Number(row.bytes) > 0) && (
            <StackedBar title="Space by bucket" format={bytes} items={rows.map(row => ({ label: row.name, value: Number(row.bytes || 0) }))} />
          )}
          <Table rows={rows} empty="No storage buckets yet: the app has not stored any files." columns={[
            { label: 'Bucket', key: 'name', mono: true }, { label: 'Public', key: 'public', kind: 'yesno' },
            { label: 'Files', key: 'objects' }, { label: 'Size', key: 'bytes', kind: 'bytes' },
            { label: 'File limit', key: 'file_size_limit', kind: 'bytes' }, { label: 'Allowed types', key: 'allowed_mime_types', kind: 'chips' },
            { label: 'Last upload', key: 'last_upload', kind: 'date' }, { label: 'Created', key: 'created_at', kind: 'date' },
          ]} />
        </>)
      }}
    </View>
  )
}

function SupabaseUsers({ project, item }) {
  return (
    <View project={project} item={item} icon={Users} wide title="Auth users" about="Who can sign in to the app: how many accounts there are, how they sign in, and the newest ones.">
      {({ json }) => {
        const users = sqlRows(json)?.[0]?.users
        if (!users) return null
        const providers = Object.entries(users.providers || {}).map(([label, value]) => ({ label, value }))
        return (<>
          <Stats items={[
            { label: 'Accounts', value: number(users.total) },
            { label: 'Confirmed', value: number(users.confirmed), tone: users.total && users.confirmed < users.total ? 'warn' : undefined },
            { label: 'Signed in · 7 days', value: number(users.signed_in_last_7_days) },
            { label: 'New · 7 days', value: number(users.created_last_7_days), sub: users.anonymous ? `${users.anonymous} anonymous` : undefined },
          ]} />
          {providers.length > 0 && <StackedBar title="How they sign in" items={providers} format={number} />}
          <Table rows={users.recent || []} empty="Nobody has signed up yet." columns={[
            { label: 'Email', get: row => row.email || row.phone }, { label: 'Provider', key: 'provider' },
            { label: 'Confirmed', key: 'confirmed', kind: 'yesno' }, { label: 'Created', key: 'created_at', kind: 'date' },
            { label: 'Last sign-in', key: 'last_sign_in_at', kind: 'date' }, { label: 'Role', key: 'role' },
          ]} />
        </>)
      }}
    </View>
  )
}

function SupabasePolicies({ project, item }) {
  return (
    <View project={project} item={item} icon={ShieldCheck} wide title="Row level security" about="The rules that decide which rows each user may read or change, table by table.">
      {({ json }) => {
        const rows = sqlRows(json)
        if (!rows) return null
        return (<>
          <Stats items={[
            { label: 'Policies', value: rows.length },
            { label: 'Tables covered', value: new Set(rows.map(row => `${row.schema}.${row.table}`)).size },
            { label: 'Restrictive', value: rows.filter(row => row.permissive === 'RESTRICTIVE').length },
            { label: 'For everyone', value: rows.filter(row => String(row.roles).includes('public')).length, sub: 'apply to the public role' },
          ]} />
          <Table rows={rows} empty="No policies: tables with row level security on refuse every request from the app's users." columns={[
            { label: 'Table', get: row => `${row.schema}.${row.table}`, mono: true }, { label: 'Policy', key: 'name' },
            { label: 'Command', key: 'command' }, { label: 'Roles', key: 'roles', kind: 'chips' },
            { label: 'Using', key: 'using_expression', mono: true }, { label: 'Check', key: 'check_expression', mono: true },
          ]} />
        </>)
      }}
    </View>
  )
}

const sqlTable = (icon, title, about, columns, empty) => function SqlTable({ project, item }) {
  return (
    <View project={project} item={item} icon={icon} title={title} about={about}>
      {({ json }) => { const rows = sqlRows(json); return rows ? <Table rows={rows} empty={empty} columns={columns} /> : null }}
    </View>
  )
}

const SupabaseFunctions = sqlTable(SquareFunction, 'Database functions', 'Functions and procedures the app defined in Postgres, and the triggers that run them.', [
  { label: 'Function', get: row => `${row.schema}.${row.name}(${row.arguments})`, mono: true }, { label: 'Returns', key: 'returns', mono: true },
  { label: 'Language', key: 'language' }, { label: 'Runs as', key: 'security' }, { label: 'Triggers', key: 'triggers' },
], 'The app has defined no database functions.')

const SupabaseExtensions = sqlTable(Puzzle, 'Extensions', 'Postgres extensions installed in this database, and whether a newer version is available.', [
  { label: 'Extension', key: 'name', mono: true }, { label: 'Version', key: 'version' }, { label: 'Latest', key: 'latest_version' },
  { label: 'Schema', key: 'schema' }, { label: 'About', key: 'comment' },
], 'No extensions.')

function SupabaseEdge({ project, item }) {
  return (
    <View project={project} item={item} icon={Zap} title="Edge functions" about="Server functions deployed to this project, their state and version.">
      {({ json }) => Array.isArray(json) ? (
        <Table rows={json} empty="No edge functions are deployed." columns={[
          { label: 'Function', get: row => row.name || row.slug, mono: true }, { label: 'Status', key: 'status', kind: 'status' },
          { label: 'Version', key: 'version' }, { label: 'JWT check', key: 'verify_jwt', kind: 'yesno' },
          { label: 'Updated', get: row => row.updated_at, kind: 'date' },
        ]} />
      ) : null}
    </View>
  )
}

function SupabaseSecrets({ project, item }) {
  return (
    <View project={project} item={item} icon={Lock} title="Secrets" about="Variables the edge functions are given. Only names and fingerprints are shown, never values.">
      {({ json }) => Array.isArray(json) ? (
        <Table rows={json} empty="No secrets are set." columns={[{ label: 'Name', key: 'name', mono: true }, { label: 'Fingerprint', key: 'value', mono: true }]} />
      ) : null}
    </View>
  )
}

function SupabaseMigrations({ project, item }) {
  return (
    <View project={project} item={item} icon={GitBranch} title="Migrations" about="Schema migrations in this project's folder and on the database, side by side: a line with only one side is not applied, or not in the folder.">
      {({ text }) => <TextTable text={text} empty="No migrations, here or on the database." />}
    </View>
  )
}

function SupabaseBackups({ project, item }) {
  return (
    <View project={project} item={item} icon={ArchiveRestore} title="Backups" about="The database's backups and whether it can be restored to a moment in time.">
      {({ json }) => json && typeof json === 'object' ? (<>
        <Stats items={[
          { label: 'Backups', value: (json.backups || []).length },
          { label: 'Point in time', value: json.pitr_enabled ? 'On' : 'Off', tone: json.pitr_enabled ? 'ok' : 'mute' },
          { label: 'WAL archiving', value: json.walg_enabled ? 'On' : 'Off', tone: json.walg_enabled ? 'ok' : 'mute' },
          { label: 'Region', value: json.region || '—' },
        ]} />
        <Table rows={json.backups || []} empty="No backups yet. The free plan keeps none you can restore from here." columns={[
          { label: 'Taken', key: 'inserted_at', kind: 'datetime' }, { label: 'Status', key: 'status', kind: 'status' },
          { label: 'Kind', get: row => (row.is_physical_backup ? 'physical' : 'logical') },
        ]} />
      </>) : null}
    </View>
  )
}

function SupabaseHealth({ project, item }) {
  return (
    <View project={project} item={item} icon={Activity} title="Database health" about="The database as a whole: its size, connections, and how often reads are answered from memory.">
      {({ json }) => {
        const row = sqlRows(json)?.[0]
        if (!row) return null
        const hit = Number(row.cache_hit_percent)
        return (<>
          <Stats items={[
            { label: 'Size', value: bytes(row.database_bytes) },
            { label: 'Connections', value: `${row.connections} / ${row.max_connections}`, tone: row.connections > row.max_connections * 0.8 ? 'warn' : undefined },
            { label: 'Cache hits', value: percent(row.cache_hit_percent), tone: !Number.isFinite(hit) ? undefined : hit >= 99 ? 'ok' : hit >= 95 ? 'warn' : 'bad' },
            { label: 'Index hits', value: percent(row.index_hit_percent) },
          ]} />
          <Card><Facts items={[
            ['Postgres', row.version], ['Database', row.name, 'mono'], ['Public tables', row.public_tables],
            ['Schemas', row.schemas], ['Committed transactions', number(row.commits)], ['Rolled back', number(row.rollbacks)],
            ['Counting since', row.stats_reset, 'datetime'],
          ]} /></Card>
        </>)
      }}
    </View>
  )
}

const textPage = (icon, title, about, empty) => function TextPage({ project, item }) {
  return (
    <View project={project} item={item} icon={icon} wide title={title} about={about}>
      {({ text }) => <TextTable text={text} empty={empty} />}
    </View>
  )
}

const SupabaseIndexes = textPage(ListTree, 'Index use', 'How often each index is used and how big it is: an unused index only slows writes down.', 'No indexes have statistics yet.')
const SupabaseOutliers = textPage(Timer, 'Slowest queries', 'The queries that took the most total time since the statistics were reset.', 'No query statistics yet.')

// ---- MongoDB ---------------------------------------------------------------------------------------------------

function MongoOverview({ project, item }) {
  return (
    <View project={project} item={item} icon={Server} title="Overview" about="The MongoDB server, the database this app uses, and every database on the same cluster.">
      {({ json }) => mongo(json, data => (<>
        <Stats items={[
          { label: 'MongoDB', value: data.server_version || '—' },
          { label: 'Collections', value: number(data.database?.collections) },
          { label: 'Documents', value: number(data.database?.documents) },
          { label: 'Data', value: bytes(data.database?.data_bytes), sub: `${bytes(data.database?.storage_bytes)} on disk` },
        ]} />
        <Card><Facts items={[
          ['Cluster address', data.host, 'mono'], ['Database this app uses', data.app_database, 'mono'],
          ['Replica set', data.replica_set, 'mono'], ['Members', data.members], ['Accepts writes', data.writable, 'yesno'],
          ['Indexes', `${number(data.database?.indexes)} · ${bytes(data.database?.index_bytes)}`],
        ]} /></Card>
        <Table rows={data.databases || []} empty="No databases." columns={[
          { label: 'Database', get: row => row.name, mono: true },
          { label: 'Used by this app', key: 'app', kind: 'yesno' },
          { label: 'Size on disk', key: 'bytes', kind: 'bytes' }, { label: 'Empty', key: 'empty', kind: 'yesno' },
        ]} />
      </>))}
    </View>
  )
}

function MongoCollections({ project, item }) {
  const { openRows } = useDatabase()
  return (
    <View project={project} item={item} icon={Layers} wide title="Collections" about="Every collection in the app's database: how many documents, how much space, and its indexes. Click one to see its newest documents.">
      {({ json }) => mongo(json, data => {
        const rows = data.collections || []
        return (<>
          <Stats items={[
            { label: 'Collections', value: rows.length, sub: data.database },
            { label: 'Documents', value: number(rows.reduce((sum, row) => sum + Number(row.count || 0), 0)) },
            { label: 'Data', value: bytes(rows.reduce((sum, row) => sum + Number(row.bytes || 0), 0)) },
            { label: 'Indexes', value: number(rows.reduce((sum, row) => sum + Number(row.indexes || 0), 0)) },
          ]} />
          {rows.length > 1 && (
            <Bars title="Documents per collection" format={number}
                  items={[...rows].sort((a, b) => (b.count || 0) - (a.count || 0)).slice(0, 12).map(row => ({ label: row.name, value: Number(row.count || 0) }))} />
          )}
          <Table rows={rows} empty="This database has no collections yet."
                 onRow={row => openRows({ source: 'mongodb', database: data.database, collection: row.name })} rowTitle="Show the newest documents"
                 columns={[
                   { label: 'Collection', key: 'name', mono: true }, { label: 'Kind', key: 'type' },
                   { label: 'Documents', get: row => number(row.count) }, { label: 'Data', key: 'bytes', kind: 'bytes' },
                   { label: 'On disk', key: 'storage_bytes', kind: 'bytes' }, { label: 'Avg document', key: 'average_document_bytes', kind: 'bytes' },
                   { label: 'Indexes', key: 'indexes' }, { label: 'Validation', key: 'validator', kind: 'yesno' },
                 ]} />
        </>)
      })}
    </View>
  )
}

function MongoIndexes({ project, item }) {
  return (
    <View project={project} item={item} icon={ListTree} wide title="Indexes" about="Every index, the fields it covers, and how often it has been used since the server started.">
      {({ json }) => mongo(json, data => (
        <Table rows={data.indexes || []} empty="No indexes." columns={[
          { label: 'Collection', key: 'collection', mono: true }, { label: 'Index', key: 'name', mono: true },
          { label: 'Fields', key: 'keys', mono: true }, { label: 'Unique', key: 'unique', kind: 'yesno' },
          { label: 'Expires after', get: row => (row.ttl_seconds != null ? `${row.ttl_seconds}s` : null) },
          { label: 'Partial', key: 'partial', kind: 'yesno' }, { label: 'Uses', get: row => (row.uses == null ? null : number(row.uses)) },
        ]} />
      ))}
    </View>
  )
}

function MongoGridfs({ project, item }) {
  return (
    <View project={project} item={item} icon={FolderArchive} title="GridFS buckets" about="Files stored inside MongoDB itself: each bucket, how many files and how much space.">
      {({ json }) => mongo(json, data => (
        <Table rows={data.buckets || []} empty="No GridFS buckets: the app does not keep files in MongoDB." columns={[
          { label: 'Bucket', key: 'name', mono: true }, { label: 'Files', key: 'files' }, { label: 'Size', key: 'bytes', kind: 'bytes' },
          { label: 'Chunks', key: 'chunks' }, { label: 'Last upload', key: 'last_upload', kind: 'date' },
        ]} />
      ))}
    </View>
  )
}

const PAGES = {
  'supabase/project': SupabaseProject,
  'supabase/api-keys': SupabaseKeys,
  'supabase/tables': SupabaseTables,
  'supabase/storage': SupabaseStorage,
  'supabase/auth-users': SupabaseUsers,
  'supabase/policies': SupabasePolicies,
  'supabase/db-functions': SupabaseFunctions,
  'supabase/extensions': SupabaseExtensions,
  'supabase/edge-functions': SupabaseEdge,
  'supabase/secrets': SupabaseSecrets,
  'supabase/migrations': SupabaseMigrations,
  'supabase/backups': SupabaseBackups,
  'supabase/database-stats': SupabaseHealth,
  'supabase/index-stats': SupabaseIndexes,
  'supabase/outliers': SupabaseOutliers,
  'mongodb/mongo-overview': MongoOverview,
  'mongodb/mongo-collections': MongoCollections,
  'mongodb/mongo-indexes': MongoIndexes,
  'mongodb/mongo-gridfs': MongoGridfs,
}

/** The page for one database look: its own, or its answer laid out automatically. */
export default function DatabasePage({ project, item }) {
  const Page = PAGES[`${item.set}/${item.id}`]
  if (Page) return <Page project={project} item={item} />
  return (
    <View project={project} item={item} icon={ShieldCheck} title={item.label} about={`What \`${item.display}\` reports.`}>
      {({ json, text }) => (json ? <Auto json={json} /> : <TextTable text={text} empty="Nothing to show." />)}
    </View>
  )
}
