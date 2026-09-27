'use client'

import { Shield } from 'lucide-react'
import { View, Card, Facts, Flow, human } from '../parts'

const WHO = {
  all: 'every deployment, production included',
  all_except_custom_domains: 'every deployment except your production domains',
  prod_deployment_urls_and_all_previews: 'previews and the production deployment addresses',
  preview: 'preview deployments only',
}

/** Who can open the deployment without signing in to Vercel. */
export default function VercelProtection({ project, item }) {
  return (
    <View project={project} item={item} icon={Shield} title="Protection" about="Whether visitors must sign in to Vercel to open a deployment. Protection is left as it is; nothing here changes it.">
      {({ json }) => {
        if (!json) return null
        const type = json.ssoProtection?.deploymentType
        return (<>
          <Flow title="A visitor's path" steps={[
            { label: 'Visitor', sub: 'anyone on the internet', tone: 'mute' },
            { label: type ? 'Vercel sign-in' : 'No sign-in', sub: type ? `required for ${WHO[type] || human(type)}` : 'every deployment is public', tone: type ? 'warn' : 'ok' },
            { label: 'Your application', sub: 'the deployment', tone: 'ok' },
          ]} />
          <Card title="Settings">
            <Facts items={[['Vercel authentication', type ? human(type) : 'Off'], ['Git fork protection', json.gitForkProtection, 'yesno'], ['Project', json.name], ['Project id', json.projectId, 'mono']]} all />
          </Card>
        </>)
      }}
    </View>
  )
}
