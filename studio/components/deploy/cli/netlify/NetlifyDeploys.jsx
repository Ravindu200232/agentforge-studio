'use client'

import { Rocket } from 'lucide-react'
import { View, Table, Stats, Bars, duration, tone } from '../parts'

/** Every deploy of the site. */
export default function NetlifyDeploys({ project, item }) {
  return (
    <View project={project} item={item} icon={Rocket} title="Deploys" about="Every deploy of the site, newest first, with its state and how long it took.">
      {({ json }) => Array.isArray(json) && (<>
        <Stats items={[{ label: 'Deploys', value: json.length }, { label: 'Ready', value: json.filter(d => d.state === 'ready').length, tone: 'ok' }, { label: 'Failed', value: json.filter(d => tone(d.state) === 'bad').length, tone: json.some(d => tone(d.state) === 'bad') ? 'bad' : undefined }, { label: 'Latest', value: json[0]?.state || '—', tone: json[0] ? tone(json[0].state) : undefined }]} />
        {json.filter(d => d.deploy_time).length > 1 && <Bars title="Deploy time" items={json.filter(d => d.deploy_time).slice(0, 12).map(d => ({ label: d.title || d.commit_ref || d.id.slice(0, 8), value: d.deploy_time * 1000, tone: tone(d.state) }))} format={duration} />}
        <Table rows={json} empty="No deploys." columns={[
          { label: 'State', key: 'state', kind: 'status' }, { label: 'Context', key: 'context', kind: 'chips' }, { label: 'Branch', key: 'branch', mono: true }, { label: 'Title', key: 'title' },
          { label: 'Created', key: 'created_at', kind: 'date' }, { label: 'Address', key: 'deploy_ssl_url', kind: 'link' }, { label: 'Problem', key: 'error_message' },
        ]} />
      </>)}
    </View>
  )
}
