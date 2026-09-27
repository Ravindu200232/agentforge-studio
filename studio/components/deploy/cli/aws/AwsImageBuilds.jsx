'use client'

import { Hammer } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** The cloud builds that made the images. */
export default function AwsImageBuilds({ project, item }) {
  return (
    <View project={project} item={item} icon={Hammer} title="Image builds" about="The CodeBuild runs that built the container images (there is no Docker on this computer).">
      {({ json }) => {
        const ids = json?.ids
        if (!ids) return null
        return ids.length ? <Table rows={ids.map(id => ({ id, name: id.split(':')[0], run: id.split(':')[1] }))} columns={[{ label: 'Project', key: 'name' }, { label: 'Build id', key: 'run', mono: true }]} /> : <Empty title="No builds" />
      }}
    </View>
  )
}
