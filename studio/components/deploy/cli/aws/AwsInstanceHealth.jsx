'use client'

import { HeartPulse } from 'lucide-react'
import { View, Flow, Empty, tone } from '../parts'

/** The two health checks AWS runs on an instance. */
export default function AwsInstanceHealth({ project, item }) {
  return (
    <View project={project} item={item} icon={HeartPulse} title="Health checks" about="AWS's system check (the hardware and network) and instance check (the operating system).">
      {({ json }) => Array.isArray(json) && (json.length ? json.map(i => (
        <Flow key={i.Id} title={i.Id} steps={[{ label: 'Instance', sub: i.State, tone: tone(i.State) }, { label: 'System check', sub: i.System, tone: tone(i.System) }, { label: 'Instance check', sub: i.Instance, tone: tone(i.Instance) }]} />
      )) : <Empty title="No status reported" />)}
    </View>
  )
}
