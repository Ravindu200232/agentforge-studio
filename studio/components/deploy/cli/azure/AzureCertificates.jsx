'use client'

import { BadgeCheck } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** The TLS certificates in the resource group. */
export default function AzureCertificates({ project, item }) {
  return (
    <View project={project} item={item} icon={BadgeCheck} title="Certificates" about="TLS certificates for the web app's custom domains and when each expires.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={json} columns={[{ label: 'Name', key: 'Name' }, { label: 'For', key: 'Subject', mono: true }, { label: 'Hosts', key: 'Hosts', kind: 'chips' }, { label: 'Expires', key: 'Expires', kind: 'date' }]} />
        : <Empty title="No certificates" hint="The default azurewebsites.net address has one built in." />)}
    </View>
  )
}
