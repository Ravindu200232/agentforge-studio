'use client'

import { FileText } from 'lucide-react'
import { View, Table, Empty } from '../parts'

/** Forms the site collects. */
export default function NetlifyForms({ project, item }) {
  return (
    <View project={project} item={item} icon={FileText} title="Forms" about="Forms on the site that Netlify collects submissions for.">
      {({ json }) => Array.isArray(json) && (json.length
        ? <Table rows={json} columns={[{ label: 'Name', key: 'name' }, { label: 'Submissions', key: 'submission_count' }, { label: 'Fields', get: f => (f.fields || []).map(x => x.name), kind: 'chips' }, { label: 'Created', key: 'created_at', kind: 'date' }]} />
        : <Empty title="No forms" />)}
    </View>
  )
}
