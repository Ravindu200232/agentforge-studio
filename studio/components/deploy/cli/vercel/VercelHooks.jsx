'use client'

import { Webhook } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** URLs that trigger a deployment when called. */
export default function VercelHooks({ project, item }) {
  return (
    <View project={project} item={item} icon={Webhook} title="Deploy hooks" about="Secret URLs that start a deployment of a branch when they are called.">
      {({ json }) => json && ((json.hooks || []).length
        ? <Table rows={json.hooks} columns={[{ label: 'Name', key: 'name' }, { label: 'Branch', key: 'ref', kind: 'chips' }, { label: 'Created', key: 'createdAt', kind: 'date' }]} />
        : <Empty title="No deploy hooks" hint={json.message} />)}
    </View>
  )
}
