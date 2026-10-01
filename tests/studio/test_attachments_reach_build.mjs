/**
 * What was attached has to reach the build.
 *
 * Both senders in `useAttachments` used to learn their queue inside a
 * `setItems` updater — a side effect in a place React only promises to run
 * while the component is mounted. Starting a build unmounts the home screen,
 * so the updater never ran, the queue was empty, and the files were dropped in
 * silence: the build then searched its own workspace for a PDF that had never
 * left the browser.
 *
 * This drives the hook with a React that refuses to run updaters after
 * unmount, which is the condition that produced the bug.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '../../studio')
const source = readFileSync(join(ROOT, 'lib/use-attachments.js'), 'utf8')

const failures = []
const check = (what, ok) => { if (!ok) failures.push(what) }

// The queue must not be read through a state updater in either sender.
const senders = source.slice(source.indexOf('const upload'))
check('upload() reads its queue outside setItems',
      !/setItems\(list => \{[\s\S]{0,200}queue =/.test(senders))
check('stage() reads its queue outside setItems',
      !/queue = \[\][\s\S]{0,200}setItems\(list => \{[\s\S]{0,120}queue =/.test(senders))
check('a ref mirrors what was picked', /current\.current = items/.test(source))
check('stage reads that ref', /const queue = current\.current/.test(source))
check('upload reads that ref', /const held = current\.current/.test(source))

// And the build stages them. Starting a build may unmount the home screen first (onStarted): that is safe now,
// because stage() reads the ref above, not a state updater that no longer runs once unmounted.
const home = readFileSync(join(ROOT, 'components/Home.jsx'), 'utf8')
const start = home.slice(home.indexOf('async function startBuild'))
check('the build sends the picked files', start.indexOf('attach.stage(') > 0)

if (failures.length) {
  console.error('Attachments would not reach a build:\n' + failures.map(f => '  ' + f).join('\n'))
  process.exit(1)
}
console.log('Attachments reach the build: queue read from a ref, so they are sent even after the home screen unmounts')
