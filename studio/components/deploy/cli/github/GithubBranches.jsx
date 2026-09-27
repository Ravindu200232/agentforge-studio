'use client'

import { GitBranch } from 'lucide-react'
import { View, Table, Empty } from '../parts'

const parse = text => text.split('\n').filter(line => line.includes('\t')).map(line => {
  const [name, sha, date, upstream, head, ...subject] = line.split('\t')
  return { name, sha, date, upstream, current: head.trim() === '*', remote: name.startsWith('origin/'), subject: subject.join('\t') }
})

/** Local and remote branches, and where each one stands. */
export default function GithubBranches({ project, item }) {
  return (
    <View project={project} item={item} icon={GitBranch} title="Branches" about="Local branches and the remote ones they track, with each one's latest commit.">
      {({ text }) => {
        const rows = parse(text)
        return rows.length ? <Table rows={rows} columns={[
          { label: 'Branch', get: r => (r.current ? `${r.name}  ← current` : r.name), mono: true }, { label: 'Kind', get: r => (r.remote ? 'remote' : 'local'), kind: 'chips' },
          { label: 'Tracks', key: 'upstream', mono: true }, { label: 'Commit', key: 'sha', mono: true }, { label: 'Message', key: 'subject' }, { label: 'When', key: 'date', kind: 'date' },
        ]} /> : <Empty title="No branches" />
      }}
    </View>
  )
}
