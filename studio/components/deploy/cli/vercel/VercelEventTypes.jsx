'use client'

import { List } from 'lucide-react'
import { View, Table } from '../parts'

/** Every kind of event Vercel records, with what it means. */
export default function VercelEventTypes({ project, item }) {
  return (
    <View project={project} item={item} icon={List} title="Event types" about="The kinds of event the activity log can hold, so a filter can name them.">
      {({ json }) => json && (
        <Table rows={json.types} filter columns={[
          { label: 'Type', key: 'name', mono: true }, { label: 'What it is', key: 'description' }, { label: 'Category', key: 'categories', kind: 'chips' },
        ]} />
      )}
    </View>
  )
}
