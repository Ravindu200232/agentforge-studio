'use client'

import { FileDiff } from 'lucide-react'
import { View, Table, Stats, Empty, Note } from '../parts'

const KIND = { M: 'Modified', A: 'Added', D: 'Deleted', R: 'Renamed', '?': 'Untracked', U: 'Conflict' }

/** What differs between the files on this computer and the last commit. */
export default function GithubWorkingTree({ project, item }) {
  return (
    <View project={project} item={item} icon={FileDiff} title="Working tree" about="Files that differ from the last commit, and whether this branch is ahead of or behind the one on GitHub.">
      {({ text }) => {
        const lines = text.split('\n').filter(Boolean)
        const head = (lines.find(line => line.startsWith('##')) || '').replace(/^##\s*/, '')
        const files = lines.filter(line => !line.startsWith('##')).map(line => ({ code: line.slice(0, 2).trim() || '?', path: line.slice(3) }))
        const ahead = Number((head.match(/ahead (\d+)/) || [])[1] || 0)
        const behind = Number((head.match(/behind (\d+)/) || [])[1] || 0)
        return (<>
          <Stats items={[{ label: 'Branch', value: head.split('...')[0] || '—' }, { label: 'Changed files', value: files.length, tone: files.length ? 'warn' : 'ok' }, { label: 'Ahead', value: ahead, tone: ahead ? 'warn' : undefined }, { label: 'Behind', value: behind, tone: behind ? 'bad' : undefined }]} />
          {files.length
            ? <><Note tone="warn">These changes are not committed, so what is on GitHub does not include them.</Note><Table rows={files} columns={[{ label: 'Change', get: f => KIND[f.code[0]] || f.code, kind: 'chips' }, { label: 'File', key: 'path', mono: true }]} /></>
            : <Empty title="Working tree clean" hint="Everything on this computer is committed." />}
        </>)
      }}
    </View>
  )
}
