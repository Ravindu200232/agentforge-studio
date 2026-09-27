'use client'

/** Impact-aware approval gate before any SRS or artifact mutation starts. */
import { useMemo, useState } from 'react'
import { CheckCircle2, FileText, Layers3, ShieldCheck, Wrench } from 'lucide-react'
import { Button, Modal } from '../ui'

const WHAT = {
  designer: {
    label: 'Prototype',
    detail: 'wireframes, page structure and visible UI behaviour',
    Icon: Layers3,
  },
  developer: {
    label: 'Builder',
    detail: 'implemented UI/logic, code and its tests',
    Icon: Wrench,
  },
}

/**
 * The request has already been validated against the linked SRS and current
 * artifact inventory. Approval starts SRS + every checked affected artifact as
 * independent parallel branches. Artifacts that were not detected as affected
 * are never shown here.
 */
export default function SrsApprovalModal({
  targets = [],
  version,
  impact = {},
  busy,
  defaultTargets = targets,
  onApprove,
  onKeepDraft,
}) {
  const [picked, setPicked] = useState(() => new Set(defaultTargets))
  const recommended = useMemo(() => new Set(impact?.recommended_targets || targets), [impact, targets])
  const labels = targets.map(role => WHAT[role]?.label).filter(Boolean)

  const toggle = role => setPicked(was => {
    const next = new Set(was)
    next.has(role) ? next.delete(role) : next.add(role)
    return next
  })

  const skippedRecommended = [...recommended].filter(role => !picked.has(role))
  const scope = impact?.affected_pages || []
  const terms = impact?.matched_srs_terms || []

  return (
    <Modal onClose={busy ? () => { } : onKeepDraft} className="max-w-[520px]">
      <div role="dialog" aria-modal="true" aria-label="Approve validated project update">
        <div className="flex items-start gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-none bg-black/10 text-ink">
            <ShieldCheck className="size-4.5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold uppercase tracking-wider text-ink">SRS validated</p>
            <h3 className="mt-0.5 text-sm font-semibold text-ink">
              Review detected change impact{version ? ` · v${version}` : ''}
            </h3>
            <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">
              No project files have changed yet. The request was checked against the linked SRS and the artifacts that currently exist.
            </p>
          </div>
        </div>

        <div className="mt-3 rounded-none border border-black/10 bg-black/[.03] px-3 py-2.5">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-ink" />
            <div className="min-w-0">
              <p className="text-[11.5px] font-medium text-ink">Impact analysis complete</p>
              <p className="mt-0.5 text-[10.5px] leading-relaxed text-muted">
                {impact?.reason || `The SRS change affects ${labels.join(' and ')}.`}
              </p>
            </div>
          </div>
        </div>

        {(scope.length > 0 || terms.length > 0) && (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {scope.length > 0 && (
              <div className="rounded-none border border-line bg-panel2 px-3 py-2.5">
                <p className="text-[9.5px] font-bold uppercase tracking-wider text-muted2">Affected screens</p>
                <p className="mt-1 text-[10.5px] leading-relaxed text-muted">{scope.slice(0, 6).join(', ')}</p>
              </div>
            )}
            {terms.length > 0 && (
              <div className="rounded-none border border-line bg-panel2 px-3 py-2.5">
                <p className="text-[9.5px] font-bold uppercase tracking-wider text-muted2">Matched SRS scope</p>
                <p className="mt-1 text-[10.5px] leading-relaxed text-muted">{terms.slice(0, 6).join(', ')}</p>
              </div>
            )}
          </div>
        )}

        <div className="mt-4 flex items-center gap-2 text-[11px] text-muted">
          <FileText className="size-3.5 text-accent" />
          <span><b className="font-medium text-ink">SRS</b> is always included.</span>
        </div>

        <div className="mt-2.5 space-y-1.5">
          {targets.map(role => {
            const item = WHAT[role]
            if (!item) return null
            const Icon = item.Icon
            const isRecommended = recommended.has(role)
            return (
              <label key={role}
                className="flex cursor-pointer items-start gap-2.5 rounded-none border border-line bg-panel2 px-3 py-2.5 transition-colors hover:border-accent">
                <input type="checkbox" checked={picked.has(role)} disabled={busy}
                  onChange={() => toggle(role)} className="mt-1 accent-[#BFB9FF]" />
                <Icon className="mt-0.5 size-3.5 shrink-0 text-accent" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="text-[12px] font-medium text-ink">{item.label}</span>
                    {isRecommended && (
                      <span className="rounded-full bg-accent px-1.5 py-0.5 text-[8.5px] font-bold uppercase tracking-wide text-ink">
                        Sync recommended
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-[10.5px] text-muted2">{item.detail}</span>
                </span>
              </label>
            )
          })}
        </div>

        {skippedRecommended.length > 0 && (
          <p className="mt-2.5 rounded-none border border-amber-500/20 bg-amber-500/[.06] px-2.5 py-2 text-[10px] leading-relaxed text-amber-300">
            Skipping {skippedRecommended.map(role => WHAT[role]?.label).filter(Boolean).join(' and ')} may leave that artifact inconsistent with the newly approved SRS.
          </p>
        )}

        <div className="mt-4 flex items-center justify-end gap-2">
          <Button variant="outline" disabled={busy} onClick={onKeepDraft}>Not now</Button>
          <Button disabled={busy} onClick={() => onApprove([...picked])}>
            {busy ? 'Starting update…' : picked.size === 0
              ? 'Approve SRS only'
              : `Approve & sync ${picked.size === targets.length && targets.length > 1 ? 'affected artifacts' : [...picked].map(role => WHAT[role]?.label).join(' + ')}`}
          </Button>
        </div>

        <p className="mt-2.5 text-[10px] leading-relaxed text-muted2">
          Approved branches start at the same time. Prototype never waits for Builder, Builder never waits for Prototype, and unaffected artifacts are not regenerated.
        </p>
      </div>
    </Modal>
  )
}
