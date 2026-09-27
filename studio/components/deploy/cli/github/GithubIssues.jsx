'use client'

import { CircleDot } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Issues, open and closed. */
export default function GithubIssues({ project, item }) {
  return (
    <View project={project} item={item} icon={CircleDot} title="Issues" about="Problems and requests filed against the repository.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={json} columns={[{ label: '#', key: 'number' }, { label: 'Title', key: 'title' }, { label: 'State', key: 'state', kind: 'status' }, { label: 'Author', get: i => i.author?.login }, { label: 'Opened', key: 'createdAt', kind: 'date' }, { label: 'Link', key: 'url', kind: 'link' }]} />
        : <Empty title="No issues" />)}
    </View>
  )
}
