'use client'

import { Terminal } from 'lucide-react'
import { View, LogView } from '../parts'

/** What the running application logs, as requests reach it. */
export default function VercelRuntimeLogs({ project, item }) {
  return (
    <View project={project} item={item} icon={Terminal} title="Runtime logs" about="What the deployed application prints as requests arrive. Streams until you stop it or leave the page.">
      {({ lines }) => <LogView lines={lines.filter(line => !/claude-code-hint|^Vercel CLI|^Resolving|^Fetching/.test(line))} follow />}
    </View>
  )
}
