'use client'

/** SRS revisions panel for already built projects, coordinating document changes with prototypes and code. */
import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { Empty } from '../ui'
import { SrsRevisions } from './SrsRevisions'
import SrsApprovalModal from './SrsApprovalModal'

export default function SrsRevisionsPanel() {
  const project = useStore(s => s.project)
  const srsStamp = useStore(s => s.srsStamp[s.project])
  const addLog = useStore(s => s.addLog)
  // Track revision completion via sync_state events until built artifacts reconcile.
  const sync = useStore(s => s.projectSync[s.project])
  const carrying = sync?.status === 'running' && sync?.source === 'srs'
  const [link, setLink] = useState(null)
  const [state, setState] = useState('loading')
  const [ask, setAsk] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    if (!project) return
    setState(current => current === 'ready' ? 'ready' : 'loading')
    api.srsResults(project)
      .then(found => {
        setLink({ srsId: found?.link?.srs_id || '', targets: found?.targets || {} })
        setState('ready')
      })
      .catch(() => setState('error'))
  }, [project])

  useEffect(() => { load() }, [load, srsStamp])

  async function carry(roles) {
    setBusy(true)
    try {
      await api.approveChangeRequest(project, ask.requestId, roles)
      const parallel = Object.fromEntries(['srs', ...roles].map(role => [role, 'running']))
      useStore.getState().applyProjectEvent({ type: 'sync_state', project, status: 'running', source: 'srs', srs_status: 'running', parallel })
      addLog('INFO', `Approved — SRS${roles.length ? `, ${roles.join(' and ')}` : ''} started in parallel`)
      setAsk(null)
    } catch (e) {
      addLog('WARN', `Could not start that update — ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  if (!project) return <Empty>Open a project to see its specification.</Empty>
  if (state === 'loading') return <Empty>Reading the specification…</Empty>
  if (state === 'error' || !link?.srsId) {
    return (
      <Empty>
        This project has no specification to revise — it was built straight from
        a prompt. Ask for changes in the Designer or Developer tab instead.
      </Empty>
    )
  }

  const built = ['designer', 'developer'].filter(role => link.targets?.[role])

  return (
    <>
      <SrsRevisions srsId={link.srsId} className="min-h-0 flex-1" working={carrying} refreshKey={srsStamp}
        onRequestChange={async (prompt) => {
          // Always validate the requested SRS edit first. This is local and
          // non-mutating: it checks the linked SRS plus existing artifacts and
          // only opens a popup when Prototype/Builder consistency is affected.
          const created = await api.createChangeRequest({
            project, kind: 'srs', prompt, targets: built, summary: [],
          })
          const request = created?.request || {}
          const targets = request.requested_targets || request.impact?.affected_targets || []
          if (!targets.length) {
            await api.approveChangeRequest(project, request.id, [])
            useStore.getState().applyProjectEvent({
              type: 'sync_state', project, status: 'running', source: 'srs',
              srs_status: 'running', parallel: { srs: 'running' },
            })
            addLog('INFO', 'SRS validated — no Prototype or Builder impact detected. SRS update started.')
            return { started: true }
          }
          setAsk({ requestId: request.id, prompt, targets, impact: request.impact || {} })
          return { pendingApproval: true, impact: request.impact || {} }
        }} />
      {ask && (
        <SrsApprovalModal targets={ask.targets} version={ask.version} impact={ask.impact} busy={busy}
          defaultTargets={ask.impact?.recommended_targets || ask.targets}
          onApprove={carry} onKeepDraft={() => setAsk(null)} />
      )}
    </>
  )
}
