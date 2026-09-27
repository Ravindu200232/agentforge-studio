'use client'

import { Users } from 'lucide-react'
import { View, Table } from '../parts'

/** The people on the current team and what each may do. */
export default function VercelTeamMembers({ project, item }) {
  return (
    <View project={project} item={item} icon={Users} title="Team members" about="Who is on the current team, their role, and when they joined.">
      {({ json }) => json && (
        <Table rows={json.members} empty="No members." columns={[
          { label: 'Username', key: 'username' }, { label: 'Email', key: 'email' }, { label: 'Role', key: 'role', kind: 'chips' },
          { label: 'Confirmed', key: 'confirmed', kind: 'yesno' }, { label: 'Joined', key: 'createdAt', kind: 'date' },
        ]} />
      )}
    </View>
  )
}
