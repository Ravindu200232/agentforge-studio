'use client'

import { Users } from 'lucide-react'
import { View, Table } from '../parts'

/** Who has access to the repository and how much. */
export default function GithubPeople({ project, item }) {
  return (
    <View project={project} item={item} icon={Users} title="People" about="The people with access to the repository and what each may do.">
      {({ json }) => Array.isArray(json) && (
        <Table rows={json} empty="No collaborators." columns={[
          { label: 'Person', key: 'login' }, { label: 'Role', key: 'role_name', kind: 'chips' },
          { label: 'Can', get: p => Object.entries(p.permissions || {}).filter(([, on]) => on).map(([name]) => name), kind: 'chips' }, { label: 'Profile', key: 'html_url', kind: 'link' },
        ]} />
      )}
    </View>
  )
}
