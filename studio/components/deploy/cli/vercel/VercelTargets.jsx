'use client'

import { Target } from 'lucide-react'
import { View, Table } from '../parts'

/** The environments a deployment can target: production, preview, and any custom ones. */
export default function VercelTargets({ project, item }) {
  return (
    <View project={project} item={item} icon={Target} title="Targets" about="The environments this project can deploy to.">
      {({ json }) => json && (
        <Table rows={json.targets} empty="No targets." columns={[
          { label: 'Name', key: 'slug' }, { label: 'Type', key: 'type', kind: 'chips' }, { label: 'What it is', key: 'description' }, { label: 'Created', key: 'createdAt', kind: 'date' },
        ]} />
      )}
    </View>
  )
}
