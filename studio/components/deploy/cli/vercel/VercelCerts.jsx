'use client'

import { BadgeCheck } from 'lucide-react'
import { View, Table, Empty, parseTable } from '../parts'

/** The TLS certificates on the account and when each expires. */
export default function VercelCerts({ project, item }) {
  return (
    <View project={project} item={item} icon={BadgeCheck} title="Certificates" about="TLS certificates for custom domains, and when they expire. Vercel renews the ones it issued.">
      {({ text }) => {
        const { columns, rows } = parseTable(text)
        return rows.length ? <Table rows={rows} columns={columns.map(name => ({ label: name, key: name, mono: /id|cns/i.test(name) }))} /> : <Empty title="No certificates" hint="Certificates are issued when a custom domain is added." />
      }}
    </View>
  )
}
