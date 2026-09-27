'use client'

import { Globe } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** The names the web app answers to. */
export default function AzureDomains({ project, item }) {
  return (
    <View project={project} item={item} icon={Globe} title="Domains" about="Every host name the web app answers to.">
      {({ json }) => Array.isArray(json) && (json.length ? <Table rows={json.map(name => ({ name }))} columns={[{ label: 'Host name', key: 'name', kind: 'link' }]} /> : <Empty title="No host names" />)}
    </View>
  )
}
