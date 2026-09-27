'use client'

import { User } from 'lucide-react'
import { View, Auto } from '../parts'

/** Who the Netlify command line tool is signed in as, and the site linked to this project. */
export default function NetlifyAccount({ project, item }) {
  return (
    <View project={project} item={item} icon={User} title="Netlify account" about="The account the Netlify command line tool is signed in as and the site this project is linked to.">
      {({ json }) => (json ? <Auto json={json} /> : null)}
    </View>
  )
}
