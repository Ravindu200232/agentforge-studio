'use client'

import { Settings } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Global Config stores: small key-value stores read at the edge. */
export default function VercelGlobalConfig({ project, item }) {
  return (
    <View project={project} item={item} icon={Settings} title="Global config" about="Key-value stores the edge can read without a deployment.">
      {({ json }) => {
        const rows = Array.isArray(json) ? json : json?.stores || []
        return rows.length
          ? <Table rows={rows} columns={[{ label: 'Store', get: r => r.slug || r.id }, { label: 'Items', key: 'itemCount' }, { label: 'Created', key: 'createdAt', kind: 'date' }]} />
          : <Empty title="No Global Config stores" hint="None has been created on this team." />
      }}
    </View>
  )
}
