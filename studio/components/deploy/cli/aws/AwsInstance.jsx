'use client'

import { Server } from 'lucide-react'
import { View, Card, Facts, Stats, Flow, tone } from '../parts'

/** The EC2 instance the application runs on. */
export default function AwsInstance({ project, item }) {
  return (
    <View project={project} item={item} icon={Server} title="Instance" about="The EC2 instance running the application: its size, state and fixed address.">
      {({ json }) => Array.isArray(json) && json.map(i => (
        <div key={i.Id} className="space-y-3">
          <Stats items={[{ label: 'State', value: i.State, tone: tone(i.State) }, { label: 'Type', value: i.Type }, { label: 'Public address', value: i.PublicIp || '—' }, { label: 'Zone', value: i.Az }]} />
          <Flow title="Where it sits" steps={[{ label: 'Internet', tone: 'mute' }, { label: 'Public address', sub: i.PublicIp, tone: tone(i.State) }, { label: 'Web server', sub: 'on the instance', tone: tone(i.State) }, { label: 'Application', sub: i.Id, tone: tone(i.State) }]} />
          <Card title="Details"><Facts items={[['Instance id', i.Id, 'mono'], ['Launched', i.Launched, 'datetime']]} /></Card>
        </div>
      ))}
    </View>
  )
}
