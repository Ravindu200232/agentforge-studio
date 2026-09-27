'use client'

import { Hammer } from 'lucide-react'
import { View, Table, Stats } from '../parts'

/** The builds Netlify ran. */
export default function NetlifyBuilds({ project, item }) {
  return (
    <View project={project} item={item} icon={Hammer} title="Builds" about="The builds Netlify ran for the site and whether each finished.">
      {({ json }) => Array.isArray(json) && (<>
        <Stats items={[{ label: 'Builds', value: json.length }, { label: 'Failed', value: json.filter(b => b.error).length, tone: json.some(b => b.error) ? 'bad' : 'ok' }]} />
        <Table rows={json} empty="No builds." columns={[{ label: 'Done', key: 'done', kind: 'yesno' }, { label: 'Started', key: 'created_at', kind: 'date' }, { label: 'Commit', key: 'sha', mono: true }, { label: 'Problem', key: 'error' }, { label: 'Deploy', key: 'deploy_id', mono: true }]} />
      </>)}
    </View>
  )
}
