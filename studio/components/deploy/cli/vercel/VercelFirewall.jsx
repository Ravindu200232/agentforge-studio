'use client'

import { Flame } from 'lucide-react'
import { View, Card } from '../parts'

/** The project's firewall: rules and bot protection. */
export default function VercelFirewall({ project, item }) {
  return (
    <View project={project} item={item} icon={Flame} title="Firewall" about="The firewall configuration Vercel applies in front of the project.">
      {({ text }) => (
        <Card>
          <pre className="whitespace-pre-wrap break-words font-mono text-[11.5px] leading-[1.6] text-ink">
            {text.split('\n').filter(line => !/claude-code-hint|^Vercel CLI|^Retrieving/.test(line)).join('\n').trim() || 'No firewall rules are configured.'}
          </pre>
        </Card>
      )}
    </View>
  )
}
