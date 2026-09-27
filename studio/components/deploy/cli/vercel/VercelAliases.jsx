'use client'

import { Link2 } from 'lucide-react'
import { View, Table, Flow } from '../parts'

/** The addresses that point at deployments, and which deployment each points at. */
export default function VercelAliases({ project, item }) {
  return (
    <View project={project} item={item} icon={Link2} title="Aliases" about="Addresses that resolve to a deployment. Moving an alias is how a release goes live or rolls back.">
      {({ json }) => {
        if (!json) return null
        const rows = json.aliases || []
        const first = rows[0]
        return (<>
          {first && (
            <Flow title="The newest alias" steps={[
              { label: 'Visitor', sub: 'browser', tone: 'mute' },
              { label: first.alias, sub: 'alias', tone: 'run' },
              { label: 'Deployment', sub: (first.url || '').replace(/^https?:\/\//, ''), tone: 'ok' },
            ]} />
          )}
          <Table rows={rows} empty="No aliases." columns={[
            { label: 'Alias', key: 'alias', kind: 'link' }, { label: 'Points at', key: 'url', kind: 'link' }, { label: 'Created', key: 'createdAt', kind: 'date' },
          ]} />
        </>)
      }}
    </View>
  )
}
