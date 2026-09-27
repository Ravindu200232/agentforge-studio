'use client'

import { Network } from 'lucide-react'
import { View, Card, Table, Empty } from '../parts'

/** The DNS records Vercel holds for each domain. */
export default function VercelDns({ project, item }) {
  return (
    <View project={project} item={item} icon={Network} title="DNS records" about="DNS records held by Vercel for the domains that use its nameservers.">
      {({ json }) => {
        if (!json) return null
        const groups = (json.records || []).filter(group => (group.records || []).length)
        return groups.length ? groups.map(group => (
          <Card key={group.domainName} title={group.domainName} pad={false}>
            <Table rows={group.records} filter={false} columns={[
              { label: 'Type', key: 'type', kind: 'chips' }, { label: 'Name', get: r => r.name || '@', mono: true }, { label: 'Value', key: 'value', mono: true },
              { label: 'TTL', key: 'ttl' }, { label: 'Created', key: 'createdAt', kind: 'date' },
            ]} />
          </Card>
        )) : <Empty title="No DNS records held by Vercel" hint="Your domains use another provider's nameservers, so their records are managed there." />
      }}
    </View>
  )
}
