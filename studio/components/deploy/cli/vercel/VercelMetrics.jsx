'use client'

import { Gauge } from 'lucide-react'
import { View, Table, Stats } from '../parts'

/** Every metric Vercel can report for the project. */
export default function VercelMetrics({ project, item }) {
  return (
    <View project={project} item={item} icon={Gauge} title="Metrics" about="The observability metrics that can be queried for this project, with what each measures.">
      {({ json }) => {
        const rows = Array.isArray(json) ? json : json?.metrics || []
        return (<>
          <Stats items={[{ label: 'Metrics', value: rows.length }]} />
          <Table rows={rows} filter columns={[{ label: 'Metric', key: 'id', mono: true }, { label: 'What it measures', key: 'description' }]} />
        </>)
      }}
    </View>
  )
}
