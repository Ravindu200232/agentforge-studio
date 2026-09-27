'use client'

import { Folders } from 'lucide-react'
import { View, Table, Stats } from '../parts'

/** Every project on the team. */
export default function VercelProjects({ project, item }) {
  return (
    <View project={project} item={item} icon={Folders} title="All projects" about="Every project on the current team, with its production address.">
      {({ json }) => json && (<>
        <Stats items={[{ label: 'Projects', value: (json.projects || []).length }, { label: 'Team', value: json.contextName }]} />
        <Table rows={json.projects} empty="No projects." columns={[
          { label: 'Name', key: 'name' }, { label: 'Production', key: 'latestProductionUrl', kind: 'link' },
          { label: 'Node', key: 'nodeVersion' }, { label: 'Updated', key: 'updatedAt', kind: 'date' }, { label: 'Id', key: 'id', mono: true },
        ]} />
      </>)}
    </View>
  )
}
