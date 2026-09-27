'use client'

import { MapPin } from 'lucide-react'
import { View, Table } from '../parts'

/** The fixed addresses attached to the instance. */
export default function AwsElasticIps({ project, item }) {
  return (
    <View project={project} item={item} icon={MapPin} title="Elastic IPs" about="Fixed public addresses attached to the instance. This is the address to allow-list in a database.">
      {({ json }) => Array.isArray(json) && <Table rows={json} empty="No Elastic IP attached." columns={[{ label: 'Address', key: 'Ip', mono: true }, { label: 'Allocation', key: 'Allocation', mono: true }, { label: 'Association', key: 'Association', mono: true }, { label: 'Instance', key: 'Instance', mono: true }]} />}
    </View>
  )
}
