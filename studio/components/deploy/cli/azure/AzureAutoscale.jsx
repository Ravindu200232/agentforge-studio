'use client'

import { TrendingUp } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Automatic scaling rules. */
export default function AzureAutoscale({ project, item }) {
  return (
    <View project={project} item={item} icon={TrendingUp} title="Auto scale" about="Rules that add or remove instances by themselves.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={json} columns={[{ label: 'Setting', key: 'Name' }, { label: 'Enabled', key: 'Enabled', kind: 'yesno' }, { label: 'Fewest', get: a => a.Profiles?.[0]?.Min }, { label: 'Most', get: a => a.Profiles?.[0]?.Max }, { label: 'Start with', get: a => a.Profiles?.[0]?.Default }]} />
        : <Empty title="No automatic scaling" hint="The number of instances is set by hand." />)}
    </View>
  )
}
