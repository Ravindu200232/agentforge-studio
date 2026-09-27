'use client'

import { Package } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Published releases. */
export default function GithubReleases({ project, item }) {
  return (
    <View project={project} item={item} icon={Package} title="Releases" about="Versions published from the repository.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={json} columns={[{ label: 'Tag', key: 'tagName', mono: true }, { label: 'Name', key: 'name' }, { label: 'Latest', key: 'isLatest', kind: 'yesno' }, { label: 'Pre-release', key: 'isPrerelease', kind: 'yesno' }, { label: 'Published', key: 'publishedAt', kind: 'date' }]} />
        : <Empty title="No releases" hint="Nothing has been published from this repository yet." />)}
    </View>
  )
}
