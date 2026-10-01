'use client'

import { Boxes } from 'lucide-react'
import { View, Card, Table, Stats } from '../parts'

const kind = type => String(type || '').split('/').slice(-1)[0]

/** Everything in the resource group, grouped by kind. */
export default function AzureResources({ project, item }) {
  return (
    <View project={project} item={item} icon={Boxes} title="Resources" about="Everything in the deployment's resource group, grouped by kind.">
      {({ json }) => {
        if (!Array.isArray(json)) return null
        const groups = {}
        json.forEach(r => { (groups[kind(r.Type)] ||= []).push(r) })
        return (<>
          <Stats items={[{ label: 'Resources', value: json.length }, { label: 'Kinds', value: Object.keys(groups).length }]} />
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(groups).map(([name, rows]) => (
              <Card key={name} title={`${name} · ${rows.length}`}>
                <ul className="space-y-1">{rows.map(r => <li key={r.Name} className="flex items-center gap-2 text-[11.5px]"><span className="size-2 rounded-full bg-ok" /><span className="min-w-0 flex-1 truncate text-ink">{r.Name}</span><span className="text-[10.5px] text-muted2">{r.Location}</span></li>)}</ul>
              </Card>
            ))}
          </div>
          <Table rows={json} columns={[{ label: 'Name', key: 'Name' }, { label: 'Type', key: 'Type', mono: true }, { label: 'Location', key: 'Location' }]} />
        </>)
      }}
    </View>
  )
}
