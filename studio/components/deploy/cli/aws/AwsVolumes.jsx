'use client'

import { HardDrive } from 'lucide-react'
import { View, Table } from '../parts'

/** The disks attached to the instance. */
export default function AwsVolumes({ project, item }) {
  return (
    <View project={project} item={item} icon={HardDrive} title="Volumes" about="The disks attached to the instance.">
      {({ json }) => Array.isArray(json) && <Table rows={json} empty="No volumes." columns={[{ label: 'Volume', key: 'Id', mono: true }, { label: 'Size (GB)', key: 'Size' }, { label: 'Type', key: 'Type', kind: 'chips' }, { label: 'State', key: 'State', kind: 'status' }, { label: 'Encrypted', key: 'Encrypted', kind: 'yesno' }, { label: 'IOPS', key: 'Iops' }]} />}
    </View>
  )
}
