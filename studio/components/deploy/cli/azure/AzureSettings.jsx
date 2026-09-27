'use client'

import { KeyRound } from 'lucide-react'
import { View, Table, Note, Empty } from '../parts'

/** The application settings, by name only. */
export default function AzureSettings({ project, item }) {
  return (
    <View project={project} item={item} icon={KeyRound} title="App settings" about="The names of the application settings (environment variables) on the web app. Their values are never shown.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <><Note>Values stay in Azure and are not displayed here.</Note><Table rows={json.map(name => ({ name }))} columns={[{ label: 'Setting', key: 'name', mono: true }]} /></>
        : <Empty title="No settings" />)}
    </View>
  )
}
