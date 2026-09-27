'use client'

import { Globe } from 'lucide-react'
import { View, Card, Facts, Flow, tone } from '../parts'

/** The CloudFront distribution that gives the deployment its HTTPS address. */
export default function AwsCloudFront({ project, item }) {
  return (
    <View project={project} item={item} icon={Globe} title="CloudFront" about="The content delivery network in front of the application: it gives it an HTTPS address and forwards requests to it.">
      {({ json }) => json && (<>
        <Flow title="A request's path" steps={[
          { label: 'Visitor', sub: 'browser', tone: 'mute' },
          { label: 'CloudFront', sub: json.Domain, tone: tone(json.Status) === 'ok' || json.Status === 'Deployed' ? 'ok' : 'run' },
          { label: 'Origin', sub: 'the application', tone: 'ok' },
        ]} />
        <Card title="Details"><Facts items={[['Status', json.Status, 'status'], ['Enabled', json.Enabled, 'yesno'], ['Address', json.Domain, 'link'], ['Custom names', json.Aliases, 'chips'], ['Distribution id', json.Id, 'mono']]} /></Card>
      </>)}
    </View>
  )
}
