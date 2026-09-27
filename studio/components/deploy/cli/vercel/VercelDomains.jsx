'use client'

import { Globe } from 'lucide-react'
import { View, Table, Stats } from '../parts'

/** The domains on the account and where each one's DNS is answered. */
export default function VercelDomains({ project, item }) {
  return (
    <View project={project} item={item} icon={Globe} title="Domains" about="Domains registered or added on this account, who answers their DNS, and when they expire.">
      {({ json }) => json && (<>
        <Stats items={[{ label: 'Domains', value: (json.domains || []).length }, { label: 'On Vercel DNS', value: (json.domains || []).filter(d => /vercel/i.test((d.nameservers || []).join(' '))).length }]} />
        <Table rows={json.domains} empty="No domains." columns={[
          { label: 'Domain', key: 'name', kind: 'link' }, { label: 'Registrar', key: 'registrar' }, { label: 'Nameservers', key: 'nameservers', kind: 'chips' },
          { label: 'Expires', key: 'expiresAt', kind: 'date' }, { label: 'Added', key: 'createdAt', kind: 'date' },
        ]} />
      </>)}
    </View>
  )
}
