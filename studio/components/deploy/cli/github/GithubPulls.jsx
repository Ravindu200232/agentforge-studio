'use client'

import { GitPullRequest } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Pull requests, open and closed. */
export default function GithubPulls({ project, item }) {
  return (
    <View project={project} item={item} icon={GitPullRequest} title="Pull requests" about="Proposed changes to the repository.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={json} columns={[{ label: '#', key: 'number' }, { label: 'Title', key: 'title' }, { label: 'State', key: 'state', kind: 'status' }, { label: 'Branch', key: 'headRefName', mono: true }, { label: 'Author', get: p => p.author?.login }, { label: 'Opened', key: 'createdAt', kind: 'date' }, { label: 'Link', key: 'url', kind: 'link' }]} />
        : <Empty title="No pull requests" hint="Nobody has proposed a change through a pull request." />)}
    </View>
  )
}
