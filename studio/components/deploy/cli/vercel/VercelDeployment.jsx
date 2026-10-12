'use client'

import { Rocket } from 'lucide-react'
import { View, Card, Facts, Flow, Table, Link, duration, tone } from '../parts'

/** One deployment in full: its journey from queued to live, the machine that built it, and where it is served. */
export default function VercelDeployment({ project, item }) {
  return (
    <View project={project} item={item} icon={Rocket} title="Deployment" about="The current production deployment: how it was built, how long each stage took, and the addresses it answers on.">
      {({ json }) => {
        if (!json) return null
        const d = json.duration || {}
        const state = json.readyState
        const built = d.startTime && d.endTime
        return (<>
          <Flow title="Its journey" steps={[
            { label: 'Queued', sub: json.createdAt ? new Date(json.createdAt).toLocaleTimeString() : '', tone: 'ok' },
            { label: 'Building', sub: json.buildMachine ? `${json.buildMachine.cores} cores · ${Math.round(json.buildMachine.memory / 1024)} GB` : '', tone: 'ok' },
            { label: state || 'Ready', sub: d.timeToReady ? `after ${duration(d.timeToReady)}` : '', tone: tone(state) },
            { label: 'Aliased', sub: `${(json.aliases || []).length} address${(json.aliases || []).length === 1 ? '' : 'es'}`, tone: (json.aliases || []).length ? 'ok' : 'mute' },
          ]} />
          <Card title="Details">
            <Facts items={[
              ['State', state, 'status'], ['Environment', json.target, 'chips'], ['Address', json.url, 'link'], ['Created', json.createdAt, 'datetime'],
              ['Time to ready', d.timeToReady, 'duration'], ['Running time', built ? d.endTime - d.startTime : null, 'duration'], ['Billed time', d.timeForBilling, 'duration'],
              ['Build machine', json.buildMachine ? `${json.buildMachine.machine} · ${json.buildMachine.cores} cores · ${Math.round(json.buildMachine.memory / 1024)} GB` : null],
              ['Deployment id', json.id, 'mono'], ['Project', json.name],
            ]} />
          </Card>
          <Card title="Addresses it answers on">
            <div className="flex flex-col gap-1.5 text-[12.5px]">{(json.aliases || []).map(alias => <Link key={alias} href={`https://${alias}`}>{alias}</Link>)}</div>
          </Card>
          {(json.builds || []).length > 0 && (
            <Table rows={json.builds} columns={[{ label: 'Build', key: 'entrypoint', mono: true }, { label: 'State', key: 'readyState', kind: 'status' }, { label: 'Kind', key: 'use', kind: 'chips' }, { label: 'Ready', key: 'readyStateAt', kind: 'date' }]} />
          )}
        </>)
      }}
    </View>
  )
}
