'use client'

import { Settings } from 'lucide-react'
import { View, Card, Facts } from '../parts'

/** The web app's runtime settings. */
export default function AzureConfig({ project, item }) {
  return (
    <View project={project} item={item} icon={Settings} title="Runtime config" about="How the web app runs: the runtime, its start command, and its security settings.">
      {({ json }) => json && <Card><Facts items={[['Runtime', json.Runtime, 'chips'], ['Start command', json.StartCommand, 'mono'], ['Always on', json.AlwaysOn, 'yesno'], ['Minimum TLS', json.MinTls], ['FTP', json.Ftps], ['HTTP/2', json.Http2, 'yesno']]} all /></Card>}
    </View>
  )
}
