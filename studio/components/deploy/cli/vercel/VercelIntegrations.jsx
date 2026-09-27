'use client'

import { Plug } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Marketplace integrations connected to the project. */
export default function VercelIntegrations({ project, item }) {
  return (
    <View project={project} item={item} icon={Plug} title="Integrations" about="Databases and services added from the Vercel Marketplace and connected to the project.">
      {({ json }) => json && ((json.resources || []).length
        ? <Table rows={json.resources} columns={[{ label: 'Resource', key: 'name' }, { label: 'Integration', get: r => r.integration?.name || r.integration }, { label: 'Status', key: 'status', kind: 'status' }, { label: 'Created', key: 'createdAt', kind: 'date' }]} />
        : <Empty title="No integrations" hint="Nothing from the Marketplace is connected to this project." />)}
    </View>
  )
}
