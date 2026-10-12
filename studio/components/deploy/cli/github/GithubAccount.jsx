'use client'

import { User } from 'lucide-react'
import { View, Card, Facts, Note } from '../parts'

/** Who the GitHub command line tool is signed in as, and what its token may do. */
export default function GithubAccount({ project, item }) {
  return (
    <View project={project} item={item} icon={User} title="GitHub account" about="The account the GitHub command line tool is signed in as, and the permissions its token carries.">
      {({ text }) => {
        const account = (text.match(/account\s+(\S+)/) || [])[1]
        const scopes = ((text.match(/Token scopes:\s*(.+)/) || [])[1] || '').split(',').map(s => s.replace(/['\s]/g, '')).filter(Boolean)
        const host = (text.match(/^(\S+\.\S+)\s*$/m) || [])[1] || 'github.com'
        if (!account) return null
        return (<>
          <Card>
            <div className="mb-4 flex items-center gap-3">
              <span className="grid size-12 place-items-center rounded-full bg-[#24292F] text-[18px] font-bold text-ink ring-1 ring-white/15">{account.slice(0, 1).toUpperCase()}</span>
              <div className="min-w-0"><p className="truncate text-[15px] font-semibold text-ink">{account}</p><p className="text-[12px] text-muted">{host}</p></div>
            </div>
            <Facts items={[['Git protocol', (text.match(/Git operations protocol:\s*(\S+)/) || [])[1]], ['Stored in', /keyring/.test(text) ? 'the system keyring' : 'a config file'], ['Token permissions', scopes, 'chips']]} />
          </Card>
          {!scopes.includes('workflow') && <Note tone="warn">The token cannot push workflow files: adding a CI workflow to a repository needs the <b>workflow</b> permission.</Note>}
        </>)
      }}
    </View>
  )
}
