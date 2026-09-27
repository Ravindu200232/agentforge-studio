'use client'

import { TrendingUp } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** How far the service may scale in and out. */
export default function AwsAutoScaling({ project, item }) {
  return (
    <View project={project} item={item} icon={TrendingUp} title="Auto scaling" about="The least and the most tasks the service may run when it scales automatically.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={json} columns={[{ label: 'Service', key: 'Resource', mono: true }, { label: 'Fewest tasks', key: 'Min' }, { label: 'Most tasks', key: 'Max' }, { label: 'Scales', key: 'Dimension', mono: true }]} />
        : <Empty title="Auto scaling is off" hint="The service runs a fixed number of tasks. Scaling up later means changing that number or adding a policy." />)}
    </View>
  )
}
