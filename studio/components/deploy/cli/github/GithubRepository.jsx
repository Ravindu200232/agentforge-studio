'use client'

import { GitBranch } from 'lucide-react'
import { View, Card, Facts, Stats, StackedBar, Pill, Link, bytes } from '../parts'

/** The repository: who owns it, how big it is, what it is written in. */
export default function GithubRepository({ project, item }) {
  return (
    <View project={project} item={item} icon={GitBranch} title="Repository" about="The GitHub repository the code was published to.">
      {({ json }) => {
        if (!json) return null
        const languages = (json.languages || []).map(l => ({ label: l.node?.name || l.name, value: l.size }))
        return (<>
          <Card>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-[16px] font-semibold text-ink">{json.nameWithOwner || json.name}</h3>
              <Pill tone={json.isPrivate ? 'warn' : 'ok'}>{json.visibility || (json.isPrivate ? 'PRIVATE' : 'PUBLIC')}</Pill>
            </div>
            <p className="mt-1 text-[12px] text-muted">{json.description || 'No description.'}</p>
            <div className="mt-2"><Link href={json.url}>{json.url}</Link></div>
          </Card>
          <Stats items={[
            { label: 'Default branch', value: json.defaultBranchRef?.name || '—' }, { label: 'Stars', value: json.stargazerCount ?? 0 },
            { label: 'Forks', value: json.forkCount ?? 0 }, { label: 'Size', value: bytes((json.diskUsage || 0) * 1024) },
          ]} />
          {languages.length > 0 && <StackedBar title="Languages" items={languages} format={bytes} />}
          <Card title="Details">
            <Facts items={[
              ['Owner', json.owner?.login], ['Main language', json.primaryLanguage?.name], ['Licence', json.licenseInfo?.name],
              ['Homepage', json.homepageUrl, 'link'], ['Topics', (json.repositoryTopics || []).map(t => t.name || t.topic?.name), 'chips'],
              ['Created', json.createdAt, 'datetime'], ['Last push', json.pushedAt, 'datetime'], ['Updated', json.updatedAt, 'datetime'],
            ]} />
          </Card>
        </>)
      }}
    </View>
  )
}
