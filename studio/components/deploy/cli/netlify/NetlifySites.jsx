'use client'

import { Cloud } from 'lucide-react'
import { View, Table, Stats } from '../parts'

/** Every site on the account. */
export default function NetlifySites({ project, item }) {
  return (
    <View project={project} item={item} icon={Cloud} title="All sites" about="Every site on the Netlify account, with its address.">
      {({ json }) => Array.isArray(json) && (<>
        <Stats items={[{ label: 'Sites', value: json.length }]} />
        <Table rows={json} empty="No sites." columns={[
          { label: 'Name', key: 'name' }, { label: 'Address', get: s => s.ssl_url || s.url, kind: 'link' }, { label: 'Custom domain', key: 'custom_domain' },
          { label: 'Updated', key: 'updated_at', kind: 'date' }, { label: 'Id', key: 'id', mono: true },
        ]} />
      </>)}
    </View>
  )
}
