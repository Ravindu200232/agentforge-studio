'use client'

import { Route } from 'lucide-react'
import { View, Table, Empty, parseTable } from '../parts'

/** Routing rules the project defines: redirects, rewrites and headers. */
export default function VercelRoutes({ project, item }) {
  return (
    <View project={project} item={item} icon={Route} title="Routes" about="Routing rules defined for this project: redirects, rewrites and headers.">
      {({ text }) => {
        const { columns, rows } = parseTable(text)
        return rows.length
          ? <Table rows={rows} columns={columns.map(name => ({ label: name, key: name }))} />
          : <Empty title="No routing rules" hint="The project defines no redirects, rewrites or custom headers of its own." />
      }}
    </View>
  )
}
