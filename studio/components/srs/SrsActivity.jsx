'use client'

import { Loader2 } from 'lucide-react'

const TITLES = {
  planning: 'Preparing your interview',
  reviewing: 'Generating your plan',
  generating: 'Writing your specification',
}

/** One calm, classic working state: a spinner, what is being made and the latest update. No box and no
 * checklist of its own — every detail of the work streams in the chat. */
export default function SrsActivity({ phase = 'planning', title = '', message = '', seconds = 0 }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col items-center px-6 py-10 text-center">
      <Loader2 className="size-7 animate-spin text-accent" />
      <h2 className="mt-4 font-display text-[18px] font-bold text-ink">{title || TITLES[phase] || TITLES.planning}</h2>
      {message && <p className="mt-1.5 max-w-md text-[12px] leading-relaxed text-muted">{message}</p>}
      <p className="mt-3 text-[10.5px] font-medium text-muted2">
        {seconds ? `${seconds}s · ` : ''}Live updates are in the chat stream.
      </p>
    </div>
  )
}
