'use client'

import { useCallback, useRef, useState } from 'react'
import { api, isJobCancelled } from './api'

export function useElementLayout() {
  const pending = useRef(false)
  const latest = useRef(null)
  const [layoutDraft, setLayoutDraft] = useState(null)
  const [layoutOperation, setLayoutOperation] = useState('')
  const [layoutError, setLayoutError] = useState('')
  const stageLayout = useCallback((draft, project, kind, route, refresh) => {
    latest.current = draft && { ...draft, project, kind, route, refresh }
    setLayoutDraft(latest.current)
    if (!pending.current) setLayoutError('')
  }, [])
  const cancelLayout = useCallback(() => {
    if (!pending.current) latest.current?.cancel()
  }, [])
  const saveLayout = useCallback(async () => {
    const draft = latest.current
    if (!draft?.project || pending.current) return
    if (!draft.valid()) { draft.cancel(); return }
    const { project, kind, route, operation, details, refresh } = draft
    pending.current = true
    setLayoutOperation(operation)
    setLayoutError('')
    try {
      if (draft.apply) await draft.apply(details)
      else await api.editAppLayout(project, kind, route, operation, details)
      await refresh()
      if (latest.current?.cancel === draft.cancel) draft.cancel()
    } catch (error) {
      if (!isJobCancelled(error)) setLayoutError(error.message || 'The element could not be updated.')
    } finally {
      pending.current = false
      setLayoutOperation('')
    }
  }, [])
  return { stageLayout, saveLayout, cancelLayout, layoutDraft, layoutOperation, layoutError }
}
