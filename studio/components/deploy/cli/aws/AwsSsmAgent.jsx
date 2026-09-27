'use client'

import { Radio } from 'lucide-react'
import { View, Table, Stats, Empty } from '../parts'

/** Whether Systems Manager can reach the instance: the way releases are delivered. */
export default function AwsSsmAgent({ project, item }) {
  return (
    <View project={project} item={item} icon={Radio} title="SSM agent" about="Whether AWS Systems Manager can reach the instance. Releases are delivered through it, so the instance must be Online.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <><Stats items={[{ label: 'Status', value: json[0].Ping, tone: json[0].Ping === 'Online' ? 'ok' : 'bad' }, { label: 'Agent', value: json[0].Agent }]} /><Table rows={json} columns={[{ label: 'Instance', key: 'Id', mono: true }, { label: 'Ping', key: 'Ping', kind: 'status' }, { label: 'Agent', key: 'Agent' }, { label: 'Platform', key: 'Platform' }, { label: 'Last ping', key: 'LastPing', kind: 'date' }]} /></>
        : <Empty title="The instance is not registered" hint="Systems Manager cannot reach it, so a release cannot be delivered." />)}
    </View>
  )
}
