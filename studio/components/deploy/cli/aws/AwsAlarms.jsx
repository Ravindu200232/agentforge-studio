'use client'

import { Bell } from 'lucide-react'
import { View, Table, Stats, Empty } from '../parts'

/** CloudWatch alarms for the stack. */
export default function AwsAlarms({ project, item }) {
  return (
    <View project={project} item={item} icon={Bell} title="Alarms" about="CloudWatch alarms watching this deployment, and whether any is firing.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <><Stats items={[{ label: 'Alarms', value: json.length }, { label: 'Firing', value: json.filter(a => a.State === 'ALARM').length, tone: json.some(a => a.State === 'ALARM') ? 'bad' : 'ok' }]} /><Table rows={json} columns={[{ label: 'State', key: 'State', kind: 'status' }, { label: 'Alarm', key: 'Name' }, { label: 'Metric', key: 'Metric', mono: true }, { label: 'Why', key: 'Reason' }, { label: 'Changed', key: 'Updated', kind: 'date' }]} /></>
        : <Empty title="No alarms" hint="Nothing is alarmed on for this stack. A CPU or health-check alarm is worth adding." />)}
    </View>
  )
}
