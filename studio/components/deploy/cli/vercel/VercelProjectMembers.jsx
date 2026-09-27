'use client'

import { Users } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** The people with access to this project. */
export default function VercelProjectMembers({ project, item }) {
  return (
    <View project={project} item={item} icon={Users} title="Project members" about="People given access to this project in particular, beyond the team.">
      {({ json }) => json && ((json.members || []).length
        ? <Table rows={json.members} columns={[{ label: 'Person', get: m => m.username || m.email || m.uid }, { label: 'Role', key: 'role', kind: 'chips' }, { label: 'Team role', key: 'teamRole', kind: 'chips' }]} />
        : <Empty title="No project-level members" hint="Access comes from the team. A personal account has no one else on it." />)}
    </View>
  )
}
