'use client'

import { Braces } from 'lucide-react'
import { View, Auto } from '../parts'

/** The server functions the site has. */
export default function NetlifyFunctions({ project, item }) {
  return (
    <View project={project} item={item} icon={Braces} title="Functions" about="Server-side functions deployed with the site.">
      {({ json }) => (json ? <Auto json={json} empty="The site has no functions." /> : null)}
    </View>
  )
}
