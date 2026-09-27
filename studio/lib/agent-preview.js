'use client'

import { useMemo } from 'react'
import { useStore } from './store'
import { emptySession } from './agent-session'

const EMPTY = emptySession()

// Hidden previews and late screenshot responses still belong to their own agent.
export function useAgentPreview(project, role) {
  const epoch = useStore(s => s.accountEpoch)
  const session = useStore(state => state.project === project && state.agentRole === role
    ? state : state.projectSessions[project]?.[role] || EMPTY)
  const actions = useMemo(() => {
    const patch = value => {
      const state = useStore.getState()
      if (state.accountEpoch === epoch) state.patchAgentSession(project, role, value)
    }
    return {
      addLog: (level, text) => patch(s => ({ logs: [...s.logs.slice(-799), { level, text, at: Date.now() }] })),
      setPreviewRoute: previewRoute => patch({ previewRoute }),
      setUndo: undo => patch({ undo }),
      setDrawing: drawing => patch({ drawing }),
      addSelection: item => patch(s => ({ selection: s.selection.some(x => x.key === item.key)
        ? s.selection : [...s.selection, item].slice(-8) })),
      patchSelection: (key, value) => patch(s => ({ selection: s.selection.map(item =>
        item.key === key ? { ...item, ...value } : item) })),
      clearSelection: () => patch({ selection: [] }),
    }
  }, [project, role, epoch])
  return { ...session, ...actions }
}
