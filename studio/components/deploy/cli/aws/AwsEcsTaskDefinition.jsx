'use client'

import { FileCode } from 'lucide-react'
import { View, Card, Facts } from '../parts'

/** What each task runs: its image, its size, and the names of its variables and secrets. */
export default function AwsEcsTaskDefinition({ project, item }) {
  return (
    <View project={project} item={item} icon={FileCode} title="Task definition" about="The recipe each task follows: the container image, CPU and memory, and the names (never values) of its variables and secrets.">
      {({ json }) => json && (<>
        <Card title="Task"><Facts items={[['Family', json.Family], ['Revision', json.Revision], ['CPU units', json.Cpu], ['Memory (MB)', json.Memory]]} /></Card>
        {(json.Containers || []).map(c => (
          <Card key={c.Name} title={`Container · ${c.Name}`}>
            <Facts items={[['Image', c.Image, 'mono'], ['Port', c.Port], ['Variables', c.Variables, 'chips'], ['Secrets', c.Secrets, 'chips']]} />
          </Card>
        ))}
      </>)}
    </View>
  )
}
