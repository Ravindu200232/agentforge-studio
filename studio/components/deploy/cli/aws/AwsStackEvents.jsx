'use client'

import { History } from 'lucide-react'
import { View, Timeline, Empty, tone } from '../parts'

/** What CloudFormation did, most recent first: created, updated, failed, rolled back. */
export default function AwsStackEvents({ project, item }) {
  return (
    <View project={project} item={item} icon={History} title="Stack events" about="The stack's latest events, most recent first. A failed resource is where to look when a release does not go through.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Timeline events={json.map(e => ({ title: `${e.Resource}`, sub: e.Reason, time: e.Time, tone: tone(e.Status), badges: [{ label: e.Status, tone: tone(e.Status) }] }))} />
        : <Empty title="No events" />)}
    </View>
  )
}
