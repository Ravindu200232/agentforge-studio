'use client'

import { GitCommit } from 'lucide-react'
import { View, CommitGraph, Stats, Empty } from '../parts'

const parse = text => text.split('\n').filter(line => line.includes('\t')).map(line => {
  const [hash, short, author, email, date, refs, ...subject] = line.split('\t')
  return { hash, short, author, email, date, refs: refs ? refs.split(', ').filter(Boolean) : [], subject: subject.join('\t') }
})

/** The commit history as a line of commits, with the branches and tags at each. */
export default function GithubCommits({ project, item }) {
  return (
    <View project={project} item={item} icon={GitCommit} title="Commits" about="The latest commits on this branch, newest first, with the branches and tags that point at them.">
      {({ text }) => {
        const commits = parse(text)
        if (!commits.length) return <Empty title="No commits yet" />
        const authors = new Set(commits.map(c => c.author))
        return (<>
          <Stats items={[{ label: 'Commits shown', value: commits.length }, { label: 'Authors', value: authors.size }, { label: 'Latest', value: commits[0].short }, { label: 'First shown', value: commits[commits.length - 1].short }]} />
          <CommitGraph commits={commits} />
        </>)
      }}
    </View>
  )
}
