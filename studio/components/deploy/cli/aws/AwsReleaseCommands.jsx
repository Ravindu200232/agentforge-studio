'use client'

import { History } from 'lucide-react'
import { View, Timeline, Empty, tone } from '../parts'

/** The commands sent to the instance to release: what ran and how it ended. */
export default function AwsReleaseCommands({ project, item }) {
  return (
    <View project={project} item={item} icon={History} title="Release commands" about="The commands Systems Manager ran on the instance, newest first: each release is one of them.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Timeline events={json.map(c => ({ title: c.Comment || c.Document, sub: c.Command, time: c.Requested, tone: tone(c.Status), badges: [{ label: c.Status, tone: tone(c.Status) }] }))} />
        : <Empty title="No commands yet" />)}
    </View>
  )
}
