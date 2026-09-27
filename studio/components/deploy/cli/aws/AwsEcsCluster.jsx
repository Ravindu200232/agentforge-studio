'use client'

import { Boxes } from 'lucide-react'
import { View, Stats, tone } from '../parts'

/** The ECS cluster: how many services and tasks it runs. */
export default function AwsEcsCluster({ project, item }) {
  return (
    <View project={project} item={item} icon={Boxes} title="Cluster" about="The ECS cluster the service runs in.">
      {({ json }) => Array.isArray(json) && json.map(c => (
        <Stats key={c.Name} items={[{ label: 'Cluster', value: c.Name }, { label: 'Status', value: c.Status, tone: tone(c.Status) }, { label: 'Services', value: c.Services }, { label: 'Running tasks', value: c.Running, sub: `${c.Pending} pending` }]} />
      ))}
    </View>
  )
}
