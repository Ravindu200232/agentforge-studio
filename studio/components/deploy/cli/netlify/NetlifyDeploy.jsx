'use client'

import { Rocket } from 'lucide-react'
import { View, Card, Facts, Flow, duration, tone } from '../parts'

/** One deploy in full. */
export default function NetlifyDeploy({ project, item }) {
  return (
    <View project={project} item={item} icon={Rocket} title="Deploy" about="The latest deploy: its state, its commit, how long it took, and where it is served.">
      {({ json }) => json && (<>
        <Flow title="Its journey" steps={[
          { label: 'Created', sub: json.created_at ? new Date(json.created_at).toLocaleTimeString() : '', tone: 'ok' },
          { label: 'Building', sub: json.branch || '', tone: 'ok' },
          { label: json.state, sub: json.deploy_time ? duration(json.deploy_time * 1000) : '', tone: tone(json.state) },
          { label: 'Published', sub: json.published_at ? new Date(json.published_at).toLocaleTimeString() : 'not published', tone: json.published_at ? 'ok' : 'mute' },
        ]} />
        <Card title="Details">
          <Facts items={[
            ['State', json.state, 'status'], ['Context', json.context, 'chips'], ['Branch', json.branch, 'mono'], ['Commit', json.commit_ref, 'mono'], ['Title', json.title],
            ['Address', json.deploy_ssl_url || json.deploy_url, 'link'], ['Created', json.created_at, 'datetime'], ['Published', json.published_at, 'datetime'],
            ['Deploy time', json.deploy_time ? duration(json.deploy_time * 1000) : null], ['Problem', json.error_message], ['Deploy id', json.id, 'mono'],
          ]} />
        </Card>
      </>)}
    </View>
  )
}
