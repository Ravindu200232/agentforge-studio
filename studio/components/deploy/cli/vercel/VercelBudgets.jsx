'use client'

import { Wallet } from 'lucide-react'
import { View, Table, Empty, Stats } from '../parts'

/** Spend limits set on the team. */
export default function VercelBudgets({ project, item }) {
  return (
    <View project={project} item={item} icon={Wallet} title="Budgets" about="Spend Management limits on this team's on-demand usage.">
      {({ json }) => json && (<>
        <Stats items={[{ label: 'Team', value: json.teamSlug }, { label: 'Budgets', value: (json.budgets || []).length }]} />
        {(json.budgets || []).length ? <Table rows={json.budgets} columns={Object.keys(json.budgets[0]).slice(0, 5).map(key => ({ label: key, key }))} /> : <Empty title="No spend limits" hint="On-demand usage is not capped by a budget." />}
      </>)}
    </View>
  )
}
