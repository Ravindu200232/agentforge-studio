'use client'

import { KeyRound } from 'lucide-react'
import { View, Table, Empty, Note } from '../parts'

/** The secrets set for the repository's workflows: their names only. */
export default function GithubSecrets({ project, item }) {
  return (
    <View project={project} item={item} icon={KeyRound} title="Secrets" about="Secrets available to the repository's workflows. Only names and dates are shown; a value can never be read back.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <><Note>Values are stored encrypted by GitHub and cannot be displayed.</Note><Table rows={json} columns={[{ label: 'Name', key: 'name', mono: true }, { label: 'Updated', key: 'updatedAt', kind: 'date' }]} /></>
        : <Empty title="No secrets" hint="The repository's workflows use no stored secrets." />)}
    </View>
  )
}
