'use client'

import { Bell } from 'lucide-react'
import { View, Table, Empty, Stats } from '../parts'

/** Alerts raised for the project. */
export default function VercelAlerts({ project, item }) {
  return (
    <View project={project} item={item} icon={Bell} title="Alerts" about="Anomalies and errors Vercel has raised for this project.">
      {({ json }) => json && (<>
        <Stats items={[{ label: 'Alert groups', value: (json.groups || []).length, tone: (json.groups || []).length ? 'warn' : 'ok' }]} />
        {(json.groups || []).length
          ? <Table rows={json.groups} columns={Object.keys(json.groups[0]).slice(0, 6).map(key => ({ label: key, key }))} />
          : <Empty title="No alerts" hint="Nothing has been flagged for this project." />}
      </>)}
    </View>
  )
}
