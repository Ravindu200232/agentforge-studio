'use client'

import { HeartPulse } from 'lucide-react'
import { View, Table, Stats, Empty } from '../parts'

/** Whether the load balancer sees each task as healthy. */
export default function AwsTargetHealth({ project, item }) {
  return (
    <View project={project} item={item} icon={HeartPulse} title="Target health" about="Whether the load balancer considers each task healthy enough to receive requests.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <><Stats items={[{ label: 'Healthy', value: json.filter(t => t.State === 'healthy').length, tone: 'ok' }, { label: 'Not healthy', value: json.filter(t => t.State !== 'healthy').length, tone: json.some(t => t.State !== 'healthy') ? 'bad' : 'ok' }]} /><Table rows={json} columns={[{ label: 'Target', key: 'Target', mono: true }, { label: 'Port', key: 'Port' }, { label: 'State', key: 'State', kind: 'status' }, { label: 'Reason', key: 'Reason' }]} /></>
        : <Empty title="No targets registered" />)}
    </View>
  )
}
