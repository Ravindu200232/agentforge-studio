'use client'

import { Workflow } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** The workflows the repository defines. */
export default function GithubWorkflows({ project, item }) {
  return (
    <View project={project} item={item} icon={Workflow} title="Workflows" about="The automation defined in the repository's workflow files.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={json} columns={[{ label: 'Name', key: 'name' }, { label: 'State', key: 'state', kind: 'status' }, { label: 'File', key: 'path', mono: true }, { label: 'Id', key: 'id', mono: true }]} />
        : <Empty title="No workflows" hint="The repository defines no GitHub Actions workflows." />)}
    </View>
  )
}
