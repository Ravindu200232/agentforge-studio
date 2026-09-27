'use client'

/**
 * The project's versions: every update approved in the chat is saved as v1, v2, ... with its summary,
 * the stages and files it changed, and what the tests said before and after. A list you can open and
 * close; the newest is open. The same record is a file in the project (`.agentforge/versions/`).
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Check, ChevronDown, CircleAlert, FileText, FlaskConical, History, Loader2, RefreshCw, X } from 'lucide-react'

import { api } from '@/lib/api'
import { useStore } from '@/lib/store'
import { cn } from '@/lib/utils'

const when = value => {
  const date = value ? new Date(value) : null
  return date && !Number.isNaN(+date) ? date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : ''
}

function testLine(counts) {
  const parts = []
  if (counts?.unit) parts.push(`unit ${counts.unit.passed}/${counts.unit.total}`)
  if (counts?.browser) parts.push(`browser ${counts.browser.passed}/${counts.browser.total}`)
  return parts.join(' · ')
}

/** How many tests the update added: only where the record existed before, so a first record is not "all new". */
function added(tests) {
  return ['unit', 'browser'].reduce((sum, kind) => {
    const before = tests?.before?.[kind]?.total
    const after = tests?.after?.[kind]?.total
    return before == null || after == null ? sum : sum + Math.max(0, after - before)
  }, 0)
}

export default function VersionsPanel() {
  const project = useStore(s => s.project)
  const chat = useStore(s => s.chat)
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(() => new Set())
  const [seeded, setSeeded] = useState(false)

  // A finished update adds a row to the stream: that is the moment to look for its version.
  const finished = useMemo(() => chat.filter(row => row.role === 'change' && row.status === 'done').length, [chat])

  const load = useCallback(async () => {
    if (!project) return
    try {
      const result = await api.versions(project)
      setRows(Array.isArray(result?.versions) ? result.versions : [])
      setError('')
    } catch (e) {
      setError(e.message || 'Could not read the versions.')
      setRows(current => current || [])
    }
  }, [project])

  useEffect(() => { setRows(null); setSeeded(false); setOpen(new Set()); load() }, [project, load])
  useEffect(() => { load() }, [finished, load])
  // The newest version is open the first time the list arrives.
  useEffect(() => {
    if (rows?.length && !seeded) { setOpen(new Set([rows[0].number])); setSeeded(true) }
  }, [rows, seeded])

  const toggle = number => setOpen(current => {
    const next = new Set(current)
    if (next.has(number)) next.delete(number); else next.add(number)
    return next
  })
  const allOpen = rows?.length > 0 && open.size === rows.length

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top_right,rgba(191, 185, 255,.07),transparent_30%)] p-5">
      <div className="mx-auto max-w-[860px]">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-lg font-semibold text-ink"><History className="size-[18px] text-accent" /> Versions</h1>
            <p className="mt-1 max-w-[560px] text-xs leading-relaxed text-muted">
              Every update you approve in the chat is saved here as v1, v2, and so on, with its summary, the files it
              changed and what the tests said. Each one is also a file in the project, in <code className="font-mono text-[11px]">.agentforge/versions/</code>.
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            {rows?.length > 0 && (
              <button type="button" onClick={() => setOpen(allOpen ? new Set() : new Set(rows.map(row => row.number)))}
                      className="h-8 rounded-xl border border-line px-3 text-[11.5px] font-semibold text-muted transition-colors hover:text-ink">
                {allOpen ? 'Collapse all' : 'Expand all'}
              </button>
            )}
            <button type="button" onClick={load} title="Read the versions again"
                    className="grid size-8 place-items-center rounded-xl border border-line text-muted transition-colors hover:text-ink">
              <RefreshCw className="size-3.5" />
            </button>
          </div>
        </div>

        {error && <p className="mb-3 rounded-xl bg-bad/10 px-3 py-2 text-xs text-bad">{error}</p>}
        {rows === null && (
          <p className="flex items-center gap-2 py-10 text-xs text-muted"><Loader2 className="size-3.5 animate-spin" /> Reading the versions…</p>
        )}
        {rows?.length === 0 && (
          <div className="rounded-2xl border border-dashed border-line px-6 py-12 text-center">
            <History className="mx-auto mb-2 size-6 text-muted2" />
            <p className="text-[13px] font-semibold text-ink">No updates yet</p>
            <p className="mx-auto mt-1 max-w-[380px] text-xs leading-relaxed text-muted">
              Type a change in the chat, read the plan, and approve it. When it has been carried out it appears here as v1.
            </p>
          </div>
        )}

        <ol className="space-y-2.5">
          {(rows || []).map(row => {
            const isOpen = open.has(row.number)
            const files = row.files || { counts: {} }
            const total = (files.counts?.added || 0) + (files.counts?.changed || 0) + (files.counts?.removed || 0)
            const line = testLine(row.tests?.after)
            const extra = added(row.tests)
            return (
              <li key={row.number} className={cn('rounded-2xl border bg-panel shadow-sm', isOpen ? 'border-accent/35' : 'border-line')}>
                <button type="button" onClick={() => toggle(row.number)} aria-expanded={isOpen}
                        className="flex w-full items-start gap-3 px-4 py-3 text-left">
                  <span className="mt-0.5 grid h-7 min-w-[34px] shrink-0 place-items-center rounded-lg bg-accent px-1.5 font-mono text-[12px] font-bold text-ink">v{row.number}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-semibold leading-snug text-ink">{row.title}</span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted2">
                      <span>{when(row.created)}</span>
                      <span>{total} file{total === 1 ? '' : 's'}</span>
                      {line && <span className="inline-flex items-center gap-1"><FlaskConical className="size-3" />{line}{extra > 0 && <b className="font-semibold text-ok"> +{extra} new</b>}</span>}
                      {row.warnings?.length > 0 && <span className="inline-flex items-center gap-1 text-warn"><CircleAlert className="size-3" /> check the results</span>}
                    </span>
                    {!isOpen && row.summary && <span className="mt-1 line-clamp-2 block text-[12px] leading-relaxed text-muted">{row.summary}</span>}
                  </span>
                  <ChevronDown className={cn('mt-1.5 size-3.5 shrink-0 text-muted2 transition-transform', isOpen && 'rotate-180')} />
                </button>

                {isOpen && (
                  <div className="space-y-4 border-t border-line/70 px-4 py-3.5">
                    {row.request && (
                      <p className="border-l-2 border-accent/40 pl-3 text-[12px] italic leading-relaxed text-muted">{row.request}</p>
                    )}
                    {row.summary && <p className="text-[12.5px] leading-relaxed text-ink">{row.summary}</p>}

                    {Array.isArray(row.impact) && row.impact.length > 0 && (
                      <section>
                        <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-[.14em] text-muted2">What it touched</h4>
                        <div className="flex flex-wrap gap-1.5">
                          {row.impact.map((item, i) => (
                            <span key={i} title={item.why || ''}
                                  className={cn('inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold',
                                    item.affected ? 'border-accent/40 bg-accent text-ink' : 'border-line bg-black/[.03] text-muted2 dark:bg-black/[.04]')}>
                              {item.affected ? <Check className="size-2.5" /> : <X className="size-2.5" />}{item.stage}
                            </span>
                          ))}
                        </div>
                      </section>
                    )}

                    {total > 0 && (
                      <section>
                        <h4 className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[.14em] text-muted2"><FileText className="size-3" /> Files</h4>
                        <div className="space-y-1.5">
                          {['added', 'changed', 'removed'].filter(kind => files.counts?.[kind] > 0).map(kind => (
                            <details key={kind} className="group rounded-xl border border-line/70 px-3 py-1.5">
                              <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[11.5px] font-semibold text-ink">
                                <ChevronDown className="size-3 -rotate-90 text-muted2 transition-transform group-open:rotate-0" />
                                <span className="capitalize">{kind}</span>
                                <span className="rounded-full bg-black/[.05] px-1.5 py-px font-mono text-[9.5px] text-muted dark:bg-black/[.07]">{files.counts[kind]}</span>
                              </summary>
                              <ul className="mt-1.5 max-h-48 space-y-0.5 overflow-auto pb-1 font-mono text-[10.5px] text-muted">
                                {(files[kind] || []).map(path => <li key={path} className="truncate" title={path}>{path}</li>)}
                              </ul>
                            </details>
                          ))}
                        </div>
                      </section>
                    )}

                    {(line || row.tests?.before) && (
                      <section>
                        <h4 className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[.14em] text-muted2"><FlaskConical className="size-3" /> Tests</h4>
                        <p className="text-[12px] leading-relaxed text-muted">
                          Before: <span className="text-ink">{testLine(row.tests?.before) || 'no test record'}</span>
                          <span className="mx-2 text-muted2">→</span>
                          After: <span className="text-ink">{line || 'no test record'}</span>
                        </p>
                        {row.tests?.files?.length > 0 && (
                          <p className="mt-1.5 flex flex-wrap gap-1">
                            {row.tests.files.map(path => (
                              <code key={path} className="max-w-full truncate rounded-md bg-black/[.05] px-1.5 py-0.5 font-mono text-[10px] text-muted dark:bg-black/[.07]" title={path}>{path}</code>
                            ))}
                          </p>
                        )}
                      </section>
                    )}

                    {(row.warnings || []).map((warning, i) => (
                      <p key={i} className="flex items-start gap-2 rounded-xl bg-warn-tint px-3 py-2 text-[11.5px] leading-relaxed text-warn">
                        <CircleAlert className="mt-0.5 size-3.5 shrink-0" />{warning}
                      </p>
                    ))}

                    {row.account && (
                      <details className="group rounded-xl border border-line/70 px-3 py-2">
                        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[11.5px] font-semibold text-ink">
                          <ChevronDown className="size-3 -rotate-90 text-muted2 transition-transform group-open:rotate-0" />
                          The agent&rsquo;s account
                        </summary>
                        <p className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-[11.5px] leading-relaxed text-muted">{row.account}</p>
                      </details>
                    )}
                    <p className="font-mono text-[10px] text-muted2">.agentforge/versions/v{row.number}.md</p>
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}
