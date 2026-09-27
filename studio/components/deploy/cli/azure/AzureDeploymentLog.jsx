'use client'

import { ScrollText } from 'lucide-react'
import { View, Timeline, LogView, Empty } from '../parts'

/** What the last deployments printed. */
export default function AzureDeploymentLog({ project, item }) {
  return (
    <View project={project} item={item} icon={ScrollText} title="Deployment log" about="The log of the latest deployments to the web app: unpacking, building, starting.">
      {({ json, lines }) => (Array.isArray(json)
        ? (json.length ? <Timeline events={json.map(e => ({ title: e.message, sub: e.details_url, time: e.log_time, tone: /fail|error/i.test(e.message || '') ? 'bad' : 'mute' }))} /> : <Empty title="No deployment log yet" />)
        : <LogView lines={lines} />)}
    </View>
  )
}
