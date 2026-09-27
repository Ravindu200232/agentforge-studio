'use client'

import { Activity } from 'lucide-react'
import { View, Timeline, Empty } from '../parts'

/** What has happened in this project lately: deployments, settings changes, who did them. */
export default function VercelActivity({ project, item }) {
  return (
    <View project={project} item={item} icon={Activity} title="Activity" about="The project's recent events: deployments, changes to settings, domains and variables, and who made them.">
      {({ json }) => json && ((json.events || []).length
        ? <Timeline events={json.events.map(event => ({
            title: String(event.text || event.type || '').replace(/<[^>]+>/g, ''),
            sub: [event.principal?.username || event.user?.username, event.type].filter(Boolean).join(' · '),
            time: event.createdAt ?? event.created, tone: /fail|error|delete|remove/i.test(event.type || '') ? 'bad' : /deploy|creat|add/i.test(event.type || '') ? 'ok' : 'mute',
            badges: (event.categories || []).slice(0, 2).map(label => ({ label })),
          }))} />
        : <Empty title="No recent activity" />)}
    </View>
  )
}
