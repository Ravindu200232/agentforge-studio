'use client'

import { FolderKanban } from 'lucide-react'
import { View, Card, Facts, Flow } from '../parts'

/** The Vercel project: what it builds, with what, and where its functions run. */
export default function VercelProject({ project, item }) {
  return (
    <View project={project} item={item} icon={FolderKanban} title="Project" about="The Vercel project this deployment belongs to: its framework, how it is built, and where its code runs.">
      {({ json }) => json && (<>
        <Flow title="How it gets built and served" steps={[
          { label: 'Source', sub: json.rootDirectory || 'project root', tone: 'mute' },
          { label: 'Build', sub: `${json.framework || 'detected framework'} · ${json.buildCommand || 'default command'}`, tone: 'run' },
          { label: 'Output', sub: json.outputDirectory || 'framework default', tone: 'run' },
          { label: 'Runs on', sub: `Node ${json.nodeVersion || '—'} · ${json.sandbox?.region || 'default region'}`, tone: 'ok' },
        ]} />
        <Card title="Details">
          <Facts items={[
            ['Name', json.name], ['Owner', json.owner?.name], ['Framework', json.framework, 'chips'], ['Node version', json.nodeVersion],
            ['Install command', json.installCommand || 'default'], ['Build command', json.buildCommand || 'default'],
            ['Output directory', json.outputDirectory || 'default'], ['Root directory', json.rootDirectory || '.'],
            ['Function region', json.sandbox?.region], ['Failover regions', json.sandbox?.failoverRegions?.length ? json.sandbox.failoverRegions : 'none'],
            ['Created', json.createdAt, 'datetime'], ['Project id', json.id, 'mono'],
          ]} />
        </Card>
      </>)}
    </View>
  )
}
