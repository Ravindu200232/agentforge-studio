'use client'

import { Layers } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Deployment slots, used to release without downtime. */
export default function AzureSlots({ project, item }) {
  return (
    <View project={project} item={item} icon={Layers} title="Slots" about="Staging slots that let a release be checked before it is swapped into production.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={json} columns={[{ label: 'Slot', key: 'Name' }, { label: 'State', key: 'State', kind: 'status' }, { label: 'Address', key: 'Host', kind: 'link' }]} />
        : <Empty title="No slots" hint="This plan has no staging slot. Slots need the Standard tier or above." />)}
    </View>
  )
}
