'use client'

import { KeyRound } from 'lucide-react'
import { View, Table, Note } from '../parts'

/** The personal access tokens on the account: their names and dates, never the tokens themselves. */
export default function VercelTokens({ project, item }) {
  return (
    <View project={project} item={item} icon={KeyRound} title="Tokens" about="Personal access tokens on this account. Only their names and dates are shown; a token's value can never be read back.">
      {({ json }) => json && (<>
        <Note>Old tokens you no longer use are worth removing in the Vercel dashboard.</Note>
        <Table rows={json.tokens} empty="No tokens." columns={[
          { label: 'Name', key: 'name' }, { label: 'Type', key: 'type', kind: 'chips' }, { label: 'Origin', key: 'origin' },
          { label: 'Created', key: 'createdAt', kind: 'date' }, { label: 'Last active', key: 'activeAt', kind: 'date' }, { label: 'Expires', key: 'expiresAt', kind: 'date' },
        ]} />
      </>)}
    </View>
  )
}
