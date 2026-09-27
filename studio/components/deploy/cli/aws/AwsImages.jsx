'use client'

import { Package } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** The container images pushed for the service. */
export default function AwsImages({ project, item }) {
  return (
    <View project={project} item={item} icon={Package} title="Images" about="The latest container images in the repository, newest last. The tag is the commit that built it.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={[...json].reverse()} columns={[{ label: 'Tags', key: 'Tags', kind: 'chips' }, { label: 'Pushed', key: 'Pushed', kind: 'date' }, { label: 'Size', key: 'SizeBytes', kind: 'bytes' }]} />
        : <Empty title="No images" />)}
    </View>
  )
}
