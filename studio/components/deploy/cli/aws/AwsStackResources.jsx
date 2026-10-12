'use client'

import { Boxes } from 'lucide-react'
import { View, Card, Table, Stats, tone } from '../parts'

const service = type => String(type || '').split('::').slice(1, 2)[0] || 'Other'

/** Everything the stack created, grouped by AWS service. */
export default function AwsStackResources({ project, item }) {
  return (
    <View project={project} item={item} icon={Boxes} title="Stack resources" about="Every resource the stack created, grouped by the AWS service it belongs to.">
      {({ json }) => {
        if (!Array.isArray(json)) return null
        const groups = {}
        json.forEach(r => { (groups[service(r.Type)] ||= []).push(r) })
        return (<>
          <Stats items={[{ label: 'Resources', value: json.length }, { label: 'Services', value: Object.keys(groups).length }, { label: 'Not healthy', value: json.filter(r => tone(r.Status) === 'bad').length, tone: json.some(r => tone(r.Status) === 'bad') ? 'bad' : 'ok' }]} />
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(groups).map(([name, rows]) => (
              <Card key={name} title={`${name} · ${rows.length}`}>
                <ul className="space-y-1.5">{rows.map(r => (
                  <li key={r.Logical} className="flex items-center gap-2 text-[11.5px]">
                    <span className="size-2 shrink-0 rounded-full" style={{ background: { ok: 'var(--green)', bad: 'var(--red)', warn: 'var(--yellow)', run: 'var(--green)', mute: 'var(--muted2)' }[tone(r.Status)] }} />
                    <span className="min-w-0 flex-1 truncate text-ink" title={r.Id}>{r.Logical}</span>
                    <span className="shrink-0 font-mono text-[10px] text-muted2">{String(r.Type).split('::').pop()}</span>
                  </li>
                ))}</ul>
              </Card>
            ))}
          </div>
          <Table rows={json} columns={[{ label: 'Resource', key: 'Logical' }, { label: 'Type', key: 'Type', mono: true }, { label: 'Status', key: 'Status', kind: 'status' }, { label: 'Id', key: 'Id', mono: true }]} />
        </>)
      }}
    </View>
  )
}
