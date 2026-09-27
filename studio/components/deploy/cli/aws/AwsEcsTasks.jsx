'use client'

import { Cpu } from 'lucide-react'
import { View, Table, Stats, Empty } from '../parts'

/** The tasks (containers) running now. */
export default function AwsEcsTasks({ project, item }) {
  return (
    <View project={project} item={item} icon={Cpu} title="Tasks" about="The tasks the service is running right now.">
      {({ json }) => {
        const arns = json?.taskArns
        if (!arns) return null
        return arns.length
          ? <><Stats items={[{ label: 'Running tasks', value: arns.length, tone: 'ok' }]} /><Table rows={arns.map(arn => ({ id: arn.split('/').pop(), arn }))} columns={[{ label: 'Task', key: 'id', mono: true }, { label: 'ARN', key: 'arn', mono: true }]} /></>
          : <Empty title="No tasks running" hint="The service has nothing running: check its events for why." />
      }}
    </View>
  )
}
