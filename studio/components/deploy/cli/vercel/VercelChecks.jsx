'use client'

import { BadgeCheck } from 'lucide-react'
import { View, Table, Empty, Card } from '../parts'

/** Deployment checks a release must pass before it is promoted. */
export default function VercelChecks({ project, item }) {
  return (
    <View project={project} item={item} icon={BadgeCheck} title="Checks" about="Checks Vercel runs on every deployment before it goes live.">
      {({ json }) => json && ((json.checks || []).length
        ? <Table rows={json.checks} columns={Object.keys(json.checks[0]).slice(0, 5).map(key => ({ label: key, key }))} />
        : (<>
            <Empty title="No checks configured" hint={json.message} />
            {(json.next || []).length > 0 && (
              <Card title="What you can do next">
                <ul className="space-y-1.5 text-[12px] text-ink">{json.next.map((step, i) => <li key={i}><code className="font-mono text-[11px] text-deep">{step.command}</code> <span className="text-muted">— {step.when}</span></li>)}</ul>
              </Card>
            )}
          </>))}
    </View>
  )
}
