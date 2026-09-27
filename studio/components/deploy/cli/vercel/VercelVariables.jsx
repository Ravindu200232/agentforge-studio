'use client'

import { KeyRound } from 'lucide-react'
import { View, Table, Stats, Note } from '../parts'

/** The environment variables the project has, by name and where they apply. Values are never shown. */
export default function VercelVariables({ project, item }) {
  return (
    <View project={project} item={item} icon={KeyRound} title="Variables" about="The environment variables set on the project and which environments they reach. Their values are never shown here or anywhere.">
      {({ json }) => {
        if (!json) return null
        const rows = json.envs || []
        return (<>
          <Stats items={[{ label: 'Variables', value: rows.length }, { label: 'Sensitive', value: rows.filter(r => /sensitive|secret/i.test(r.type || r.visibility || '')).length, tone: 'ok' }, { label: 'Production', value: rows.filter(r => (r.target || []).includes('production')).length }]} />
          <Note>A sensitive variable can be replaced but not read back, so a value that was typed wrongly has to be set again.</Note>
          <Table rows={rows} empty="No variables." columns={[
            { label: 'Name', key: 'key', mono: true }, { label: 'Kind', get: r => r.type || r.visibility, kind: 'chips' },
            { label: 'Applies to', key: 'target', kind: 'chips' }, { label: 'Created', key: 'createdAt', kind: 'date' }, { label: 'Changed', key: 'updatedAt', kind: 'date' },
          ]} />
        </>)
      }}
    </View>
  )
}
