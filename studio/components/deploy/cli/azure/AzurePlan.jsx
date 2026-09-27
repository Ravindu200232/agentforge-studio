'use client'

import { Gauge } from 'lucide-react'
import { View, Stats, tone } from '../parts'

/** The App Service plan: the size, and how many instances. */
export default function AzurePlan({ project, item }) {
  return (
    <View project={project} item={item} icon={Gauge} title="Plan & size" about="The App Service plan the web app runs on: the machine size and how many instances.">
      {({ json }) => json && <Stats items={[{ label: 'Plan', value: json.Name }, { label: 'Size', value: json.Sku, sub: json.Tier }, { label: 'Instances', value: json.Workers }, { label: 'Status', value: json.Status, tone: tone(json.Status) }]} />}
    </View>
  )
}
