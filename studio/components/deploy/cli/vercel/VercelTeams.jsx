'use client'

import { Users } from 'lucide-react'
import { View, Table, Stats } from '../parts'

/** The teams this account can deploy to, and which one is current. */
export default function VercelTeams({ project, item }) {
  return (
    <View project={project} item={item} icon={Users} title="Teams" about="Every team this account belongs to. A deployment goes to the current one unless another is named.">
      {({ json }) => json && (<>
        <Stats items={[{ label: 'Teams', value: (json.teams || []).length }, { label: 'Current', value: (json.teams || []).find(t => t.current)?.name || '—' }]} />
        <Table rows={json.teams} empty="No teams." columns={[
          { label: 'Name', key: 'name' }, { label: 'Slug', key: 'slug', mono: true }, { label: 'Plan', key: 'plan', kind: 'chips' },
          { label: 'Current', key: 'current', kind: 'yesno' }, { label: 'Id', key: 'id', mono: true },
        ]} />
      </>)}
    </View>
  )
}
