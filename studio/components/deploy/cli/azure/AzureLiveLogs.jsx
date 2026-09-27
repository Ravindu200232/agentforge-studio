'use client'

import { Terminal } from 'lucide-react'
import { View, LogView } from '../parts'

/** The application's log, live. */
export default function AzureLiveLogs({ project, item }) {
  return (
    <View project={project} item={item} icon={Terminal} title="Live logs" about="What the application writes, as it happens. Streams until you stop it or leave the page.">
      {({ lines }) => <LogView lines={lines} follow />}
    </View>
  )
}
