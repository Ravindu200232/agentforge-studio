'use client'

import { ScrollText } from 'lucide-react'
import { View, LogView, Stats, duration } from '../parts'

/** What the build printed, line by line, with errors and warnings picked out. */
export default function VercelBuildLogs({ project, item }) {
  return (
    <View project={project} item={item} icon={ScrollText} title="Build logs" about="Everything the deployment's build printed: installing, compiling, and packaging. Errors and warnings are picked out.">
      {({ lines }) => {
        const body = lines.filter(line => !/claude-code-hint|^Vercel CLI|^Fetching deployment/.test(line))
        const stamps = body.map(line => Date.parse((line.match(/^(\d{4}-\d{2}-\d{2}T[\d:.]+Z)/) || [])[1])).filter(Number.isFinite)
        const errors = body.filter(line => /\b(error|failed)\b/i.test(line)).length
        const warnings = body.filter(line => /\bwarn/i.test(line)).length
        return (<>
          <Stats items={[
            { label: 'Lines', value: body.length }, { label: 'Errors', value: errors, tone: errors ? 'bad' : 'ok' },
            { label: 'Warnings', value: warnings, tone: warnings ? 'warn' : 'ok' }, { label: 'Took', value: stamps.length > 1 ? duration(stamps[stamps.length - 1] - stamps[0]) : '—' },
          ]} />
          <LogView lines={body} />
        </>)
      }}
    </View>
  )
}
