'use client'

import { Eye } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * The mark beside a model that can look at pictures. Such a model can be shown the prototype's screens (the Studio
 * photographs every page and has it check them), and can see the screenshots its own screenshot tool takes.
 */
export default function VisionBadge({ className }) {
  return (
    <span title="Can look at pictures: the prototype's screens are checked by looking at them"
          className={cn('inline-flex shrink-0 items-center gap-0.5 rounded-full px-1.5 py-px text-[9px] font-bold uppercase tracking-wide',
            'bg-[color-mix(in_srgb,var(--green)_14%,transparent)] text-ok', className)}>
      <Eye className="size-2.5" aria-hidden="true" /> vision
    </span>
  )
}
