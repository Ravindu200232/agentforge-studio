'use client'

import { useMemo, useState } from 'react'
import { api } from '@/lib/api'
import { Badge, Button, Empty, Modal } from '../ui'

/** Displays UI usability and quality findings recorded during journey execution. */
function UiQuality({ qa }) {
  const rows = []
  const recordedSummary = qa?.uiQualitySummary
  for (const flow of (qa?.report?.e2e || {}).flows || []) {
    // Newer runs carry the checks beside the stages; older ones left them
    // inline among the steps, so both are read.
    for (const seen of flow.ui_quality || [])
      rows.push({ journey: flow.title, page: seen.page, note: seen.note })
    for (const stage of flow.stages || []) {
      const found = String(stage.label || stage.name || '').match(/^ui-quality\s+(\S+):\s*(.+)$/)
      if (found) rows.push({ journey: flow.title, page: found[1], note: found[2] })
    }
  }
  // Declared pages read on the running preview.
  for (const row of qa?.ui_sweep || []) {
    rows.push({ journey: 'declared-route sample',
                page: row.route || row.page,
                note: row.error ? `could not be opened — ${row.error}`
                                : [row.note || 'not checked', row.mobileNote && row.mobileNote !== 'clean' ? `mobile: ${row.mobileNote}` : ''].filter(Boolean).join(' · ') })
  }
  // One row per page: a page opened by four journeys was checked four times and
  // is still one page. A finding anywhere outranks a clean reading elsewhere.
  const byPage = new Map()
  for (const row of rows) {
    const held = byPage.get(row.page)
    if (!held || (held.note === 'clean' && row.note !== 'clean')) byPage.set(row.page, row)
  }
  const pages = [...byPage.values()].sort((a, b) => a.page.localeCompare(b.page))
  const flagged = pages.filter(row => row.note !== 'clean')
  if (!pages.length) {
    return (
      <div className="rounded-none border border-line bg-panel px-4 py-3 text-[11.5px] text-muted">
        {recordedSummary ? <>
          <p className="font-semibold text-ink">Visual quality check recorded</p>
          <p className="mt-1">{recordedSummary.detail || `${recordedSummary.count || 0} public screens were checked.`} Detailed per-page usability notes were not saved by that earlier build, so this view cannot honestly invent them.</p>
        </> : <>
          No page-level usability notes were saved. Screenshots are still available below; run the Testing stage to record a fresh page-by-page usability sweep.
        </>}
      </div>
    )
  }
  return (
    <div className="space-y-2">
      <p className="text-[11.5px] text-muted">
        {pages.length} page{pages.length === 1 ? '' : 's'} read — declared routes
        plus whatever the journeys had open; parameterized routes need fixtures — {flagged.length
          ? `${flagged.length} with findings, ${pages.length - flagged.length} clean`
          : 'all clean: no unnamed control, missing alt text, broken image, dead link or sideways scroll'}.
      </p>
      <div className="space-y-1.5">
        {pages.map((row, i) => (
          <div key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-none
                                  border border-line bg-panel px-4 py-2.5">
            <Badge tone={row.note === 'clean' ? 'ok' : 'warn'}>
              {row.note === 'clean' ? 'clean' : 'findings'}
            </Badge>
            <code className="font-mono text-[11px] text-ink">{row.page}</code>
            <span className="text-[10px] text-muted2">{row.journey}</span>
            {row.note !== 'clean' && <span className="text-[11.5px] text-warn">{row.note}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

/** Renders a visual chronological filmstrip of journey step screenshots. */
function Timeline({ frames, url, onPick }) {
  const suites = useMemo(() => {
    const groups = new Map()
    for (const frame of frames) {
      if (!groups.has(frame.suite)) groups.set(frame.suite, [])
      groups.get(frame.suite).push(frame)
    }
    for (const rows of groups.values()) rows.sort((a, b) => a.step - b.step)
    return [...groups.entries()]
  }, [frames])

  if (!suites.length) return null
  return (
    <div className="space-y-3">
      {suites.map(([suite, rows]) => (
        <section key={suite} className="rounded-none border border-line bg-panel p-3">
          <p className="mb-2 flex items-baseline gap-2">
            <span className="text-[12px] font-semibold text-ink">{suite}</span>
            <span className="text-[10.5px] text-muted2">
              {rows.length} step{rows.length === 1 ? '' : 's'}
            </span>
          </p>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {rows.map(frame => (
              <button key={frame.path} onClick={() => onPick(frame)}
                      title={`Step ${frame.step} — ${frame.action}`}
                      className="group w-[132px] shrink-0 overflow-hidden rounded-none border border-line bg-panel2 text-left hover:border-accent">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={url(frame)} alt={`step ${frame.step}`} loading="lazy"
                     className="h-[80px] w-full border-b border-line object-cover object-top" />
                <span className="flex items-baseline gap-1.5 px-2 py-1.5">
                  <span className="font-mono text-[9.5px] text-accent">{frame.step}</span>
                  <span className="truncate text-[10px] text-muted">{frame.action}</span>
                </span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

export default function Screenshots({ qa }) {
  const [selected, setSelected] = useState(null)
  const all = qa?.screenshots || []
  const url = shot => api.qaScreenshotUrl(qa.project, shot.path, shot.at)
  // A frame is a record of a step; a shot is evidence somebody asked for. They
  // are read differently, so they are shown differently.
  const frames = all.filter(shot => shot.frame)
  const shots = all.filter(shot => !shot.frame)
  if (!all.length) {
    return (
      <div className="space-y-4">
        <UiQuality qa={qa} />
        <Empty>No saved screenshots for this project yet.</Empty>
      </div>
    )
  }
  return (
    <div className="space-y-4">
      <UiQuality qa={qa} />
      <Timeline frames={frames} url={url} onPick={setSelected} />
      {shots.length > 0 && (
        <p className="text-[11.5px] text-muted">{shots.length} saved screenshots · Select a capture to inspect it at full size.</p>
      )}
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(230px,1fr))]">
        {shots.map(shot => (
          <button key={shot.path} onClick={() => setSelected(shot)} className="overflow-hidden rounded-none border border-line bg-panel text-left hover:border-accent">
            {/* Captured local artifacts have dynamic project paths and dimensions. */}
            <img src={url(shot)} alt={shot.name} loading="lazy" className="h-44 w-full border-b border-line bg-panel2 object-contain object-top" />
            <div className="space-y-2 p-3">
              <p className="break-all text-[12px] font-medium text-ink">{shot.name}</p>
              <div className="flex items-center justify-between gap-2 text-[10px] text-muted">
                <span>{shot.width} × {shot.height}</span><Badge tone={shot.status === 'failed' ? 'bad' : 'mute'}>{shot.status}</Badge>
              </div>
              <p className="text-[10px] text-muted2">{new Date(shot.at).toLocaleString()}</p>
            </div>
          </button>
        ))}
      </div>
      {selected && <Modal onClose={() => setSelected(null)} className="max-w-[1100px]">
        <div role="dialog" aria-modal="true" aria-label={selected.name}>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="break-all text-sm font-semibold text-ink">{selected.name}</h3>
            <Button onClick={() => setSelected(null)}>Close screenshot</Button>
          </div>
          <p className="mb-3 text-[11px] text-muted">
            {selected.width} × {selected.height}
            {selected.frame
              ? ` · step ${selected.step} of ${selected.suite}, after ${selected.action}`
              : selected.findings ? ` · ${selected.findings}` : ''}
          </p>
          <img src={url(selected)} alt={selected.name} className="h-auto w-full" />
        </div>
      </Modal>}
    </div>
  )
}
