'use client'

import { Globe } from 'lucide-react'
import { View, Card, Facts, Flow, tone } from '../parts'

/** The App Service web app. */
export default function AzureWebApp({ project, item }) {
  return (
    <View project={project} item={item} icon={Globe} title="Web app" about="The App Service web app running the application: its address, state and whether HTTP is redirected to HTTPS.">
      {({ json }) => json && (<>
        <Flow title="A request's path" steps={[
          { label: 'Visitor', tone: 'mute' }, { label: json.HttpsOnly ? 'HTTPS only' : 'HTTP allowed', sub: json.Host, tone: json.HttpsOnly ? 'ok' : 'warn' },
          { label: 'App Service', sub: json.Location, tone: tone(json.State) }, { label: 'Application', sub: json.Kind, tone: tone(json.State) },
        ]} />
        <Card title="Details"><Facts items={[['State', json.State, 'status'], ['Address', json.Host, 'link'], ['HTTPS only', json.HttpsOnly, 'yesno'], ['Location', json.Location], ['Kind', json.Kind], ['Outbound addresses', String(json.OutboundIps || '').split(','), 'chips']]} /></Card>
      </>)}
    </View>
  )
}
