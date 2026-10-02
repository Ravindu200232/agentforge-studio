'use client'

import { useState } from 'react'
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'
import { useStore } from '@/lib/store'

/**
 * What stands where a diagram's picture should be when there is none and the saved source is not Mermaid: why, and a
 * way to draw it again. Never the saved text itself — it is whatever the model said instead of drawing (a sentence
 * about reading a file), not something to read as a diagram.
 *
 * The screen reloads on its own when the redraw finishes: the server announces the SRS change.
 */
export default function DiagramMissing({ diagram }) {
  const project = useStore(s => s.project)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function redraw() {
    if (!project || busy) return
    setBusy(true)
    setError('')
    try {
      await api.srs(`/projects/${project}/diagrams/redraw`, { kinds: [diagram.name], deep: true })
    } catch (e) {
      setError(e.message || 'The diagram could not be drawn again')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col items-center gap-3 px-4 py-10 text-center" role="status">
      <AlertTriangle className="size-6 text-amber-700" aria-hidden />
      <p className="text-[14px] font-semibold text-ink">This diagram could not be drawn</p>
      <p className="max-w-[560px] text-[12px] leading-relaxed text-muted">
        {/* Only a reason written for this panel: an older error is Mermaid quoting the very words it could not read. */}
        {(diagram.drawingFailed && diagram.renderError) || 'The model did not return a diagram for it. Redraw it to try again.'}
      </p>
      {error && <p className="text-[12px] text-bad">{error}</p>}
      <button
        type="button"
        onClick={redraw}
        disabled={busy || !project}
        className="inline-flex h-8 items-center gap-1.5 border border-line2 px-3 text-[12px] font-semibold text-ink transition-colors hover:bg-ink/[.07] disabled:opacity-50"
      >
        {busy ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
        {busy ? 'Drawing…' : 'Redraw this diagram'}
      </button>
    </div>
  )
}
