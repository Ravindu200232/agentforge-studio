'use client'

import { Database } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Storage the project can use: Blob stores and the like. */
export default function VercelStorage({ project, item }) {
  return (
    <View project={project} item={item} icon={Database} title="Storage" about="Blob and other storage stores on the team.">
      {({ json }) => json && ((json.stores || []).length
        ? <Table rows={json.stores} columns={[{ label: 'Name', key: 'name' }, { label: 'Type', key: 'type', kind: 'chips' }, { label: 'Region', key: 'region' }, { label: 'Created', key: 'createdAt', kind: 'date' }]} />
        : <Empty title="No storage stores" hint="The team has no Blob or other storage set up." />)}
    </View>
  )
}
