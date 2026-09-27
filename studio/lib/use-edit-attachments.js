'use client'

/** Files attached to an editing chat. */
import { useCallback, useRef, useState } from 'react'

import { api } from './api'

let seq = 0

export function useEditAttachments(project) {
  const [items, setItems] = useState([])
  const current = useRef([])
  const pending = useRef(new Map())

  const update = useCallback(change => {
    current.current = change(current.current)
    setItems(current.current)
  }, [])

  const add = useCallback(files => {
    const fresh = Array.from(files || []).map(file => ({
      key: `ea-${++seq}`, file, name: file.name || 'upload',
      state: 'reading', read: '', kind: '', note: '', path: '',
    }))
    if (!fresh.length) return
    update(list => [...list, ...fresh])
    for (const it of fresh) {
      const task = api.attach(it.file, { project })
        .then(saved => update(list => list.map(row => row.key === it.key
          ? { ...row, name: saved.filename || row.name, state: 'done',
              read: saved.text || '', kind: saved.kind || '', path: saved.path || '' }
          : row)))
        .catch(error => update(list => list.map(row => row.key === it.key
          ? { ...row, state: 'failed', note: error.message || 'Upload failed' }
          : row)))
        .finally(() => pending.current.delete(it.key))
      pending.current.set(it.key, task)
    }
  }, [project, update])

  const remove = useCallback(key => update(list => list.filter(i => i.key !== key)), [update])
  const reset = useCallback(() => update(() => []), [update])

  /** Wait for selected uploads, then put their saved paths in the agent request. */
  const collect = useCallback(async () => {
    await Promise.all([...pending.current.values()])
    const failed = current.current.find(item => item.state === 'failed')
    if (failed) throw new Error(`${failed.name}: ${failed.note || 'Upload failed'}`)
    return blockFor(current.current)
  }, [])

  return { items, add, remove, reset, collect,
           busy: items.some(i => i.state === 'reading') }
}

/** What each kind of attachment is, said once, in the prompt. */
const KIND_SAID = {
  audio: 'a recording',
  pdf: 'a document',
  document: 'a document',
  archive: 'an archive, listed and read',
  text: 'a file',
}

/**
 * The text appended to the instruction.
 *
 * Every attached file is written into the project before this runs, so the
 * agent can open it with the same tools it uses on the rest of the code.
 * The prompt carries its path and, for small text files, a readable excerpt.
 */
function blockFor(items) {
  const usable = (items || []).filter(i => i.state === 'done' && i.path)
  if (!usable.length) return ''

  const parts = usable.map(i => {
    if (i.kind === 'image') {
      return `### ${i.name} — a picture saved in this project at \`${i.path}\`\n`
        + 'This is a binary image, not a text file. If it belongs in the application, '
        + 'copy it into the app stack’s public assets and use that served path in the UI.'
    }
    const what = KIND_SAID[i.kind] || 'a file'
    const head = [`### ${i.name} — ${what}`]
    if (i.path) head.push(`Saved in this project at \`${i.path}\` — open it there for the whole file.`)
    if (i.read) head.push(i.truncated ? `The opening of it:\n${i.read}\n…` : i.read)
    else if (i.path) head.push('Nothing could be extracted from it here; read it from that path.')
    return head.join('\n')
  })

  return `\n\n## What they attached\n\n${parts.join('\n\n')}`
}
