'use client'

import { Radio } from 'lucide-react'
import { View, Card, Pill } from '../parts'

/** Whether the Vercel command line tool reports anonymous usage. */
export default function VercelTelemetry({ project, item }) {
  return (
    <View project={project} item={item} icon={Radio} title="Telemetry" about="Whether the Vercel command line tool sends anonymous usage data to Vercel.">
      {({ text }) => {
        const on = /enabled/i.test(text) && !/disabled/i.test(text)
        return (
          <Card>
            <div className="flex items-center gap-3">
              <Pill tone={on ? 'ok' : 'mute'}>{on ? 'Enabled' : 'Disabled'}</Pill>
              <p className="text-[12px] text-ink">{on ? 'Anonymous usage data is sent from the command line tool.' : 'Nothing is sent from the command line tool.'}</p>
            </div>
          </Card>
        )
      }}
    </View>
  )
}
