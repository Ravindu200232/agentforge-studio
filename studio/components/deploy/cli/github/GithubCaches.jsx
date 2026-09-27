'use client'

import { HardDrive } from 'lucide-react'
import { View, Table, Stats, Empty, bytes } from '../parts'

/** Build caches GitHub keeps for the workflows. */
export default function GithubCaches({ project, item }) {
  return (
    <View project={project} item={item} icon={HardDrive} title="Caches" about="Dependency and build caches the workflows saved to run faster.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <><Stats items={[{ label: 'Caches', value: json.length }, { label: 'Total size', value: bytes(json.reduce((n, c) => n + (c.sizeInBytes || 0), 0)) }]} /><Table rows={json} columns={[{ label: 'Key', key: 'key', mono: true }, { label: 'Size', key: 'sizeInBytes', kind: 'bytes' }, { label: 'Created', key: 'createdAt', kind: 'date' }, { label: 'Last used', key: 'lastAccessedAt', kind: 'date' }]} /></>
        : <Empty title="No caches" />)}
    </View>
  )
}
