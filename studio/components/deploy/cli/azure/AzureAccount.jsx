'use client'

import { User } from 'lucide-react'
import { View, Card, Facts } from '../parts'

/** Who the Azure command line tool is signed in as. */
export default function AzureAccount({ project, item }) {
  return (
    <View project={project} item={item} icon={User} title="Azure account" about="The account and subscription the Azure command line tool is using.">
      {({ json }) => json && <Card><Facts items={[['User', json.User], ['Subscription', json.Subscription], ['Subscription id', json.Id, 'mono'], ['Tenant', json.Tenant, 'mono']]} /></Card>}
    </View>
  )
}
