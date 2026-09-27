'use client'

import { Rocket } from 'lucide-react'
import { View, Table, Stats, Bars, duration, tone } from '../parts'

/** The project's deployments, newest first: their state, where they went, how long they took to build. */
export default function VercelDeployments({ project, item }) {
  return (
    <View project={project} item={item} icon={Rocket} title="Deployments" about="Every deployment of this project, newest first, with its state and how long it took to be ready.">
      {({ json }) => {
        if (!json) return null
        const rows = (json.deployments || []).map(d => ({ ...d, took: d.ready && d.buildingAt ? d.ready - d.buildingAt : null }))
        const ready = rows.filter(d => /ready/i.test(d.state)).length
        return (<>
          <Stats items={[
            { label: 'Deployments', value: rows.length }, { label: 'Ready', value: ready, tone: 'ok' },
            { label: 'Failed', value: rows.filter(d => tone(d.state) === 'bad').length, tone: rows.some(d => tone(d.state) === 'bad') ? 'bad' : undefined },
            { label: 'Latest', value: rows[0]?.state || '—', tone: rows[0] ? tone(rows[0].state) : undefined },
          ]} />
          {rows.filter(d => d.took).length > 1 && <Bars title="Time to be ready" items={rows.filter(d => d.took).slice(0, 12).map(d => ({ label: d.url.replace(/^https?:\/\//, ''), value: d.took, tone: tone(d.state) }))} format={duration} />}
          <Table rows={rows} empty="No deployments yet." columns={[
            { label: 'State', key: 'state', kind: 'status' }, { label: 'Environment', key: 'target', kind: 'chips' }, { label: 'Address', key: 'url', kind: 'link' },
            { label: 'Created', key: 'createdAt', kind: 'date' }, { label: 'Build time', key: 'took', kind: 'duration' }, { label: 'By', get: d => d.creator?.username || d.creator?.uid },
          ]} />
        </>)
      }}
    </View>
  )
}
