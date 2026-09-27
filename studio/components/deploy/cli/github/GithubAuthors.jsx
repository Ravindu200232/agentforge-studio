'use client'

import { Users } from 'lucide-react'
import { View, Bars, Empty } from '../parts'

/** Who wrote how many commits. */
export default function GithubAuthors({ project, item }) {
  return (
    <View project={project} item={item} icon={Users} title="Authors" about="Commits per author, from the history on this branch. Each commit carries the author's own name and email.">
      {({ text }) => {
        const rows = text.split('\n').map(line => line.trim().match(/^(\d+)\s+(.+?)\s*<(.+)>$/)).filter(Boolean).map(m => ({ label: `${m[2]} <${m[3]}>`, value: Number(m[1]), tone: 'run' }))
        return rows.length ? <Bars title="Commits per author" items={rows} /> : <Empty title="No commits" />
      }}
    </View>
  )
}
