'use client'

import { Clock } from 'lucide-react'
import { View, Table, Empty, Stats } from '../parts'

/** Scheduled jobs the project runs. */
export default function VercelCron({ project, item }) {
  return (
    <View project={project} item={item} icon={Clock} title="Cron jobs" about="Requests Vercel makes to the application on a schedule.">
      {({ json }) => json && (<>
        <Stats items={[{ label: 'Cron', value: json.enabled ? 'Enabled' : 'Off', tone: json.enabled ? 'ok' : undefined }, { label: 'Jobs', value: (json.crons || []).length }, { label: 'Not deployed yet', value: (json.undeployed || []).length }]} />
        {(json.crons || []).length ? <Table rows={json.crons} columns={[{ label: 'Path', key: 'path', mono: true }, { label: 'Schedule', key: 'schedule', mono: true }]} /> : <Empty title="No cron jobs" hint="Add a crons entry to vercel.json to run something on a schedule." />}
      </>)}
    </View>
  )
}
