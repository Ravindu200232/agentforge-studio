'use client'

import { Tag } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Tagged versions of the code. */
export default function GithubTags({ project, item }) {
  return (
    <View project={project} item={item} icon={Tag} title="Tags" about="Named points in the history, usually releases.">
      {({ text }) => {
        const rows = text.split('\n').filter(line => line.includes('\t')).map(line => { const [name, sha, date, ...subject] = line.split('\t'); return { name, sha, date, subject: subject.join('\t') } })
        return rows.length ? <Table rows={rows} columns={[{ label: 'Tag', key: 'name', mono: true }, { label: 'Commit', key: 'sha', mono: true }, { label: 'Message', key: 'subject' }, { label: 'Created', key: 'date', kind: 'date' }]} />
          : <Empty title="No tags" hint="Nothing has been tagged as a release yet." />
      }}
    </View>
  )
}
