'use client'

import { Layers } from 'lucide-react'
import { View, Card, Facts, Table, Stats, tone } from '../parts'

/** The CloudFormation stack that holds the deployment's infrastructure. */
export default function AwsStack({ project, item }) {
  return (
    <View project={project} item={item} icon={Layers} title="Stack" about="The CloudFormation stack that holds this deployment's infrastructure, and the addresses and names it exports.">
      {({ json }) => json && (<>
        <Stats items={[{ label: 'Stack', value: json.Name }, { label: 'State', value: json.Status, tone: tone(json.Status) }, { label: 'Outputs', value: (json.Outputs || []).length }]} />
        <Card title="Details"><Facts items={[['Created', json.Created, 'datetime'], ['Last updated', json.Updated, 'datetime']]} /></Card>
        {(json.Outputs || []).length > 0 && <Table rows={json.Outputs} columns={[{ label: 'Output', key: 'OutputKey', mono: true }, { label: 'Value', key: 'OutputValue', mono: true }, { label: 'What it is', key: 'Description' }]} />}
      </>)}
    </View>
  )
}
