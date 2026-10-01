'use client'

import { User } from 'lucide-react'
import { View, Card, Facts } from '../parts'

/** Who the Vercel command line tool is signed in as, and the team it deploys to. */
export default function VercelAccount({ project, item }) {
  return (
    <View project={project} item={item} icon={User} title="Vercel account" about="The account the Vercel command line tool is signed in as on this computer, and the team a deployment goes to.">
      {({ json }) => json && (
        <Card>
          <div className="mb-4 flex items-center gap-3">
            <span className="grid size-12 place-items-center rounded-full bg-accent text-[18px] font-bold text-ink">{(json.name || json.username || '?').slice(0, 1).toUpperCase()}</span>
            <div className="min-w-0">
              <p className="truncate text-[15px] font-semibold text-ink">{json.name || json.username}</p>
              <p className="truncate text-[12px] text-muted">{json.email}</p>
            </div>
          </div>
          <Facts items={[['Username', json.username, 'mono'], ['Team', json.team?.name], ['Team slug', json.team?.slug, 'mono'], ['Team id', json.team?.id, 'mono']]} />
        </Card>
      )}
    </View>
  )
}
