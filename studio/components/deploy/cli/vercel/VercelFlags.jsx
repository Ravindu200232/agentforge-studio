'use client'

import { Flag } from 'lucide-react'
import { View, Table, Empty, parseTable } from '../parts'

/** Feature flags defined for the project. */
export default function VercelFlags({ project, item }) {
  return (
    <View project={project} item={item} icon={Flag} title="Feature flags" about="Flags that switch features on or off without a deployment.">
      {({ text }) => {
        const { columns, rows } = parseTable(text)
        return rows.length ? <Table rows={rows} columns={columns.map(name => ({ label: name, key: name }))} /> : <Empty title="No feature flags" hint="The project defines none." />
      }}
    </View>
  )
}
