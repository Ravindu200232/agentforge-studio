'use client'

import { KeyRound } from 'lucide-react'
import { View, Table, Empty, Note } from '../parts'

/** The secrets stored for the application: names and dates only. */
export default function AwsSecrets({ project, item }) {
  return (
    <View project={project} item={item} icon={KeyRound} title="Secrets" about="Secrets Manager entries for this application. Only their names and dates are shown; a value is never read.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <><Note>The application reads these at start; the values are not displayed here.</Note><Table rows={json} columns={[{ label: 'Name', key: 'Name', mono: true }, { label: 'Changed', key: 'Changed', kind: 'date' }, { label: 'Last read', key: 'Accessed', kind: 'date' }, { label: 'Rotation', key: 'Rotation', kind: 'yesno' }]} /></>
        : <Empty title="No secrets found" hint="Nothing is stored in Secrets Manager under this deployment's path." />)}
    </View>
  )
}
