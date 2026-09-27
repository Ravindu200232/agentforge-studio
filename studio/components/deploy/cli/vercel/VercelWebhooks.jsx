'use client'

import { Webhook } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Addresses Vercel calls when something happens on the team. */
export default function VercelWebhooks({ project, item }) {
  return (
    <View project={project} item={item} icon={Webhook} title="Webhooks" about="Addresses Vercel notifies when deployments and other events happen.">
      {({ json }) => json && ((json.webhooks || []).length
        ? <Table rows={json.webhooks} columns={[{ label: 'Address', key: 'url', kind: 'link' }, { label: 'Events', key: 'events', kind: 'chips' }, { label: 'Created', key: 'createdAt', kind: 'date' }]} />
        : <Empty title="No webhooks" hint={json.message} />)}
    </View>
  )
}
