'use client'

import { PAGES } from './index'
import { Auto, View } from './parts'

/** The page for one command: the one written for it, or (for a command without one) its answer laid out automatically. */
export default function CommandPage({ project, item }) {
  const Page = PAGES[`${item.set}/${item.id}`]
  if (Page) return <Page project={project} item={item} />
  return (
    <View project={project} item={item} title={item.label} about={`What \`${item.display}\` reports.`}>
      {({ json }) => (json ? <Auto json={json} /> : null)}
    </View>
  )
}
