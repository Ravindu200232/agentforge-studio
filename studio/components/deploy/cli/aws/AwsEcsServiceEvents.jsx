'use client'

import { History } from 'lucide-react'
import { View, Timeline, Empty } from '../parts'

/** What the service scheduler reports. */
export default function AwsEcsServiceEvents({ project, item }) {
  return (
    <View project={project} item={item} icon={History} title="Service events" about="What the ECS scheduler says about the service, newest first: tasks started, stopped, and why.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Timeline events={json.map(e => ({ title: e.Message, time: e.Time, tone: /unable|fail|error|stopped/i.test(e.Message) ? 'bad' : /steady|started|reached/i.test(e.Message) ? 'ok' : 'mute' }))} />
        : <Empty title="No events" />)}
    </View>
  )
}
