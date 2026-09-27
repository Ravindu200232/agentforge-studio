'use client'

import { User } from 'lucide-react'
import { View, Card, Facts } from '../parts'

/** Who the AWS command line tool is signed in as. */
export default function AwsAccount({ project, item }) {
  return (
    <View project={project} item={item} icon={User} title="AWS account" about="The account and role the AWS command line tool is using on this computer.">
      {({ json }) => json && (
        <Card>
          <Facts items={[
            ['Account', json.Account, 'mono'], ['Role or user', String(json.Arn || '').split('/').slice(-2, -1)[0] || String(json.Arn || '').split('/').pop()],
            ['Kind', /assumed-role/.test(json.Arn || '') ? 'temporary role session' : 'user'], ['ARN', json.Arn, 'mono'], ['Id', json.UserId, 'mono'],
          ]} />
        </Card>
      )}
    </View>
  )
}
