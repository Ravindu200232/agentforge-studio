'use client'

import { Package } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** The release packages stored in the bucket. */
export default function AwsReleaseArtifacts({ project, item }) {
  return (
    <View project={project} item={item} icon={Package} title="Release artifacts" about="The packages uploaded for each release. The newest is what runs; the earlier ones are the way back.">
      {({ text }) => {
        const rows = text.split('\n').map(line => line.trim().match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+([\d.]+\s+\S+)\s+(.+)$/)).filter(Boolean).map(m => ({ when: m[1].replace(' ', 'T'), size: m[2], name: m[3] })).reverse()
        return rows.length ? <Table rows={rows} columns={[{ label: 'Uploaded', key: 'when', kind: 'date' }, { label: 'Size', key: 'size' }, { label: 'Package', key: 'name', mono: true }]} /> : <Empty title="No release packages" />
      }}
    </View>
  )
}
