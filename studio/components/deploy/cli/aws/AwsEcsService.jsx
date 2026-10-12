'use client'

import { Layers } from 'lucide-react'
import { View, Card, Facts, Flow, Stats, tone } from '../parts'

/** The ECS service: what it wants to run, what runs, and how the last release rolled out. */
export default function AwsEcsService({ project, item }) {
  return (
    <View project={project} item={item} icon={Layers} title="Service" about="The service keeps a set number of tasks running. Its rollout shows whether the latest release has replaced the old one.">
      {({ json }) => Array.isArray(json) && json.map(s => (
        <div key={s.Name} className="space-y-3">
          <Stats items={[{ label: 'Status', value: s.Status, tone: tone(s.Status) }, { label: 'Wanted', value: s.Desired }, { label: 'Running', value: s.Running, tone: s.Running === s.Desired ? 'ok' : 'warn' }, { label: 'Starting', value: s.Pending }]} />
          <Flow title="Rollout" steps={(s.Deployments || []).map((d, i) => ({ label: i === 0 ? 'Newest release' : 'Earlier release', sub: `${d.State || 'in progress'} · ${d.Running}/${d.Desired} running`, tone: tone(d.State) }))} />
          <Card title="Details"><Facts items={[['Service', s.Name], ['Task definition', s.TaskDefinition, 'mono']]} /></Card>
        </div>
      ))}
    </View>
  )
}
