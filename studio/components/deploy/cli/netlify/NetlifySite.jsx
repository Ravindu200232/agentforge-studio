'use client'

import { Cloud } from 'lucide-react'
import { View, Card, Facts, Flow } from '../parts'

/** The site: its address, where its code comes from, how it is built. */
export default function NetlifySite({ project, item }) {
  return (
    <View project={project} item={item} icon={Cloud} title="Site" about="The Netlify site this deployment belongs to: its addresses, its build settings and its published deploy.">
      {({ json }) => json && (<>
        <Flow title="From code to address" steps={[
          { label: 'Source', sub: json.build_settings?.repo_url || 'uploaded by the command line tool', tone: 'mute' },
          { label: 'Build', sub: json.build_settings?.cmd || 'framework default', tone: 'run' },
          { label: 'Publish', sub: json.build_settings?.dir || 'framework default', tone: 'run' },
          { label: json.custom_domain || (json.ssl_url || json.url || '').replace(/^https?:\/\//, ''), sub: json.state, tone: 'ok' },
        ]} />
        <Card title="Details">
          <Facts items={[
            ['Name', json.name], ['Address', json.ssl_url || json.url, 'link'], ['Custom domain', json.custom_domain, 'link'], ['Other names', json.domain_aliases, 'chips'],
            ['Admin page', json.admin_url, 'link'], ['Plan', json.plan, 'chips'], ['Force HTTPS', json.force_ssl, 'yesno'], ['Account', json.account_slug],
            ['Created', json.created_at, 'datetime'], ['Updated', json.updated_at, 'datetime'], ['Site id', json.id, 'mono'],
          ]} />
        </Card>
      </>)}
    </View>
  )
}
