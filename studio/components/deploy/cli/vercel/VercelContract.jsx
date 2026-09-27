'use client'

import { FileText } from 'lucide-react'
import { View, Stats, Empty, Table } from '../parts'

/** The commitments on the team's billing contract, if it has one. */
export default function VercelContract({ project, item }) {
  return (
    <View project={project} item={item} icon={FileText} title="Contract" about="Prepaid commitments on the team's billing contract. A personal or free account has none.">
      {({ json }) => json && (<>
        <Stats items={[{ label: 'Team', value: json.context }, { label: 'Commitments', value: json.totalCommitments ?? (json.commitments || []).length }]} />
        {(json.commitments || []).length
          ? <Table rows={json.commitments} columns={Object.keys(json.commitments[0]).slice(0, 6).map(key => ({ label: key, key }))} />
          : <Empty title="No commitments" hint="Nothing is prepaid: usage is billed as it happens, within the plan's included allowance." />}
      </>)}
    </View>
  )
}
