'use client'

import { Key } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Keys that let another system read (or write) the repository. */
export default function GithubKeys({ project, item }) {
  return (
    <View project={project} item={item} icon={Key} title="Deploy keys" about="SSH keys that give a server access to this one repository.">
      {({ json }) => (Array.isArray(json) && json.length
        ? <Table rows={json} columns={[{ label: 'Title', key: 'title' }, { label: 'Read only', key: 'readOnly', kind: 'yesno' }, { label: 'Added', key: 'createdAt', kind: 'date' }]} />
        : <Empty title="No deploy keys" hint="No server has its own key to this repository." />)}
    </View>
  )
}
