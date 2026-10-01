'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Search, Plus, ChevronDown, Layers, FileText, Globe, Trash2,
  Calendar, ArrowRight, Play, FolderCode, Star,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useStore } from '@/lib/store'

function ProjectVisualThumbnail({ project, name }) {
  const containerRef = useRef(null)
  const [scale, setScale] = useState(0.28)
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)

  // Use explicit html_url from server or prototype endpoint
  const htmlUrl = project.html_url || (project.has_html !== false && !project.spec_only
    ? `/__agentforge/api/prototype/${encodeURIComponent(name)}/index.html`
    : null)

  useEffect(() => {
    if (!containerRef.current) return
    const el = containerRef.current
    const calc = () => {
      const w = el.clientWidth || 360
      setScale(w / 1280)
    }
    calc()
    const ro = new ResizeObserver(calc)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  if (failed || !htmlUrl) {
    return (
      <div className="flex h-full w-full items-center justify-center p-4">
        {/* Project Visual Mockup / Illustration Fallback */}
        <div className="h-full w-full rounded-xl border border-black/10 bg-black/[.03] p-3 shadow-inner transition-transform duration-300 group-hover:scale-[1.02]">
          <div className="flex items-center gap-1.5 border-b border-black/5 pb-2">
            <span className="size-2 rounded-full bg-red-500/60" />
            <span className="size-2 rounded-full bg-amber-500/60" />
            <span className="size-2 rounded-full bg-emerald-500/60" />
            <span className="ml-2 font-mono text-[9px] text-muted2 truncate max-w-[120px]">
              {name}.app
            </span>
          </div>
          <div className="mt-2.5 grid grid-cols-12 gap-2">
            <div className="col-span-3 space-y-1.5">
              <div className="h-2 w-full rounded bg-black/10" />
              <div className="h-2 w-3/4 rounded bg-black/5" />
              <div className="h-2 w-4/5 rounded bg-black/5" />
            </div>
            <div className="col-span-9 space-y-2">
              <div className="h-3 w-3/4 rounded bg-blue-500/20" />
              <div className="grid grid-cols-2 gap-1.5">
                <div className="h-10 rounded-md border border-black/5 bg-black/[.04]" />
                <div className="h-10 rounded-md border border-black/5 bg-black/[.04]" />
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden bg-panel">
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-panel/90 backdrop-blur-sm z-[1]">
          <div className="flex items-center gap-2 text-[11px] text-muted2">
            <span className="size-2.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span>Loading preview…</span>
          </div>
        </div>
      )}
      <iframe
        src={htmlUrl}
        title={`${name} preview`}
        scrolling="no"
        tabIndex={-1}
        aria-hidden="true"
        onLoad={() => setLoaded(true)}
        onError={() => setFailed(true)}
        style={{
          width: '1280px',
          height: '800px',
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
          pointerEvents: 'none',
        }}
        className={cn(
          'pointer-events-none absolute left-0 top-0 border-0 bg-white transition-opacity duration-300',
          loaded ? 'opacity-100' : 'opacity-0'
        )}
      />
    </div>
  )
}

export default function ProjectsView({
  projects = [],
  activeProject = null,
  busyProject = '',
  onOpen,
  onCreateNew,
  onDelete,
  onBuildProject,
}) {
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('mtime_desc')
  const [filterTag, setFilterTag] = useState('all') // 'all', 'app', 'prototype', 'srs'
  const [confirmDelete, setConfirmDelete] = useState('')

  // Filter projects by active sidebar shelf selection.
  const shelf = useStore(s => s.projectFilter)
  const setShelf = useStore(s => s.setProjectFilter)
  const starred = useStore(s => s.starred)
  const recent = useStore(s => s.recent)
  const toggleStar = useStore(s => s.toggleStar)

  const counts = useMemo(() => {
    let apps = 0, prototypes = 0, srs = 0
    for (const p of projects) {
      if (p.spec_only) srs++
      else if (p.prototype_only) prototypes++
      else apps++
    }
    return { all: projects.length, app: apps, prototype: prototypes, srs }
  }, [projects])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return projects.filter(p => {
      const name = String(p.name || '').toLowerCase()
      const title = String(p.title || '').toLowerCase()
      const matchSearch = !q || name.includes(q) || title.includes(q)
      if (!matchSearch) return false

      if (shelf === 'starred' && !starred.includes(p.name)) return false
      if (shelf === 'recent' && !recent.includes(p.name)) return false

      if (filterTag === 'srs') return Boolean(p.spec_only)
      if (filterTag === 'prototype') return Boolean(p.prototype_only)
      if (filterTag === 'app') return !p.spec_only && !p.prototype_only
      return true
    }).sort((a, b) => {
      // Recently viewed has its own order: the order you viewed them in.
      if (shelf === 'recent') return recent.indexOf(a.name) - recent.indexOf(b.name)
      if (sortBy === 'mtime_desc') return (b.mtime || 0) - (a.mtime || 0)
      if (sortBy === 'mtime_asc') return (a.mtime || 0) - (b.mtime || 0)
      if (sortBy === 'title_asc') return String(a.title || a.name).localeCompare(String(b.title || b.name))
      if (sortBy === 'title_desc') return String(b.title || b.name).localeCompare(String(a.title || a.name))
      return 0
    })
  }, [projects, search, filterTag, sortBy, shelf, starred, recent])

  function formatDate(mtime) {
    if (!mtime) return 'Recent'
    const d = new Date(mtime * 1000)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-bg px-4 sm:px-8 py-5 sm:py-8 text-ink">
      <div className="mx-auto w-full max-w-[1240px]">
        {/* Header Row */}
        <div className="flex flex-wrap items-center justify-between gap-3 sm:gap-4">
          <div>
            <h1 className="text-[24px] sm:text-[30px] font-bold tracking-tight text-ink">
              {shelf === 'starred' ? 'Starred' : shelf === 'recent' ? 'Recently viewed' : 'All projects'}
            </h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-[12px] sm:text-[13px] text-muted">
              {shelf === 'starred'
                ? 'The projects you marked with a star.'
                : shelf === 'recent'
                  ? 'The projects you opened, most recent first.'
                  : 'Manage, preview, and build your AI-generated applications and prototypes.'}
              {shelf && (
                <button onClick={() => setShelf('')}
                        className="text-accent underline-offset-2 hover:underline">
                  show all projects
                </button>
              )}
            </p>
          </div>
          <button
            onClick={onCreateNew}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-3.5 sm:px-4 py-2 sm:py-2.5 text-[12.5px] sm:text-[13px] font-semibold text-ink shadow-lg shadow-accent/20 transition-all hover:bg-press active:scale-95 shrink-0 cursor-pointer"
          >
            <Plus className="size-4" />
            Create project
          </button>
        </div>

        {/* Filter and Search Bar */}
        <div className="mt-5 sm:mt-6 flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-3">
          <div className="relative min-w-0 sm:min-w-[260px] flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted2" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search for a project"
              className="h-10 w-full rounded-xl border border-line bg-panel2/60 pl-10 pr-4 text-[13px] text-ink placeholder:text-muted2 focus:border-accent focus:bg-panel focus:outline-none focus:ring-2 focus:ring-accent/20 transition-colors"
            />
          </div>

          <div className="flex items-center justify-between sm:justify-start gap-2.5 overflow-x-auto no-scrollbar">
            <div className="flex items-center rounded-xl border border-line bg-panel2/40 p-1 text-[12px] shrink-0">
              {[
                { id: '', label: 'All projects', count: projects.length },
                { id: 'starred', label: 'Starred', count: starred.length, Icon: Star },
                { id: 'recent', label: 'Recent', count: recent.length, Icon: Calendar },
              ].map(option => {
                const active = shelf === option.id
                return (
                  <button key={option.id || 'all-projects'} type="button" onClick={() => setShelf(option.id)} aria-pressed={active}
                          className={cn('inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11.5px] font-medium whitespace-nowrap transition-colors',
                            active ? 'text-deep' : 'text-muted hover:text-ink')}>
                    {option.Icon && <option.Icon className="size-3.5" />}
                    <span>{option.label}</span>
                    <span className="font-mono text-[10px] opacity-60">({option.count})</span>
                  </button>
                )
              })}
            </div>

            {/* Filter Pills */}
            <div className="flex items-center rounded-xl border border-line bg-panel2/40 p-1 text-[12px] shrink-0">
              {[
                { id: 'all', label: 'All', count: counts.all },
                { id: 'app', label: 'Apps', count: counts.app },
                { id: 'prototype', label: 'Prototypes', count: counts.prototype },
                { id: 'srs', label: 'SRS Specs', count: counts.srs },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setFilterTag(tab.id)}
                  className={cn(
                    'flex items-center gap-1.5 rounded-lg px-2.5 sm:px-3 py-1.5 font-medium whitespace-nowrap transition-colors text-[11.5px] sm:text-[12px]',
                    filterTag === tab.id
                      ? 'bg-panel text-ink shadow-sm'
                      : 'text-muted hover:text-ink'
                  )}
                >
                  <span>{tab.label}</span>
                  <span className="text-[10px] opacity-60">({tab.count})</span>
                </button>
              ))}
            </div>

            {/* Sort Dropdown */}
            <div className="relative shrink-0">
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                className="h-10 cursor-pointer appearance-none rounded-xl border border-line bg-panel2/60 pl-3 sm:pl-3.5 pr-7 sm:pr-8 text-[12px] sm:text-[12.5px] font-medium text-ink transition-colors hover:border-line2 focus:outline-none"
              >
                <option value="mtime_desc" className="bg-panel text-ink">Last edited</option>
                <option value="mtime_asc" className="bg-panel text-ink">Oldest first</option>
                <option value="title_asc" className="bg-panel text-ink">Name (A-Z)</option>
                <option value="title_desc" className="bg-panel text-ink">Name (Z-A)</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 sm:right-3 top-1/2 size-3.5 -translate-y-1/2 text-muted2" />
            </div>
          </div>
        </div>

        {/* Project Cards Grid */}
        <div className="mt-7">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-panel/30 py-20 text-center">
              <div className="grid size-12 place-items-center rounded-2xl bg-panel2 text-muted2">
                <FolderCode className="size-6" />
              </div>
              <h3 className="mt-4 text-[15px] font-semibold text-ink">
                {search ? `No projects match "${search}"` : 'No projects yet'}
              </h3>
              <p className="mt-1 max-w-sm text-[12.5px] text-muted">
                {search
                  ? 'Try changing your search query or clear the filter.'
                  : 'Start by creating your first application, prototype, or SRS specification.'}
              </p>
              <button
                onClick={onCreateNew}
                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-[12.5px] font-semibold text-ink shadow-sm transition hover:bg-press cursor-pointer"
              >
                <Plus className="size-3.5" />
                Create project
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map(p => {
                const name = p.name || p
                const isBusy = busyProject === name
                const isCurrent = activeProject === name
                const isSpec = Boolean(p.spec_only)
                const isProto = Boolean(p.prototype_only)
                const isDeleting = confirmDelete === name

                return (
                  <div
                    key={name}
                    className={cn(
                      'group relative flex flex-col overflow-hidden rounded-2xl border bg-panel transition-all duration-200 hover:-translate-y-0.5 hover:border-line2 hover:shadow-xl',
                      isCurrent ? 'border-accent ring-1 ring-accent/40' : 'border-line'
                    )}
                  >
                    {/* Thumbnail Preview Area */}
                    <div
                      onClick={() => onOpen?.(name, p)}
                      className="relative flex h-[195px] sm:h-[210px] cursor-pointer items-center justify-center overflow-hidden border-b border-line bg-panel2/60"
                    >
                      <ProjectVisualThumbnail project={p} name={name} />

                      {/* Type Badge */}
                      <div className="absolute left-3 top-3 z-10">
                        {isProto ? (
                          <span className="inline-flex items-center gap-1 rounded-md border border-purple-500/45 bg-panel/95 px-2 py-0.5 text-[10.5px] font-semibold text-purple-600 backdrop-blur-md">
                            <Layers className="size-3" /> Prototype
                          </span>
                        ) : isSpec ? (
                          <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/45 bg-panel/95 px-2 py-0.5 text-[10.5px] font-semibold text-amber-700 backdrop-blur-md">
                            <FileText className="size-3" /> SRS Spec
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-md border border-blue-500/45 bg-panel/95 px-2 py-0.5 text-[10.5px] font-semibold text-blue-600 backdrop-blur-md">
                            <Globe className="size-3" /> Full App
                          </span>
                        )}
                      </div>

                      {/* Working Status Spinner */}
                      {isBusy && (
                        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                          <div className="flex items-center gap-2 rounded-full bg-panel px-3.5 py-1.5 text-[11px] font-medium text-accent border border-accent/30 shadow-lg">
                            <span className="size-2 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                            Building…
                          </div>
                        </div>
                      )}

                      {/* Hover Action Buttons */}
                      <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 bg-black/40 opacity-0 backdrop-blur-[2px] transition-opacity group-hover:opacity-100">
                        <button
                          onClick={e => { e.stopPropagation(); onOpen?.(name, p) }}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3.5 py-1.5 text-[12px] font-semibold text-black shadow-md transition hover:bg-black/90 cursor-pointer"
                        >
                          Open <ArrowRight className="size-3" />
                        </button>
                        {(isSpec || isProto) && onBuildProject && (
                          <button
                            onClick={e => { e.stopPropagation(); onBuildProject(name, p) }}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[12px] font-semibold text-ink shadow-md transition hover:bg-press cursor-pointer"
                            title="Build full application from this"
                          >
                            <Play className="size-3" /> Build App
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Card Footer / Details */}
                    <div className="flex flex-1 flex-col justify-between p-4">
                      <div>
                        <div className="flex items-start justify-between gap-2">
                          <button
                            onClick={() => onOpen?.(name, p)}
                            className="text-left font-semibold text-[14px] text-ink hover:text-accent transition-colors line-clamp-1 cursor-pointer"
                          >
                            {p.title || name}
                          </button>
                          
                          {/* Star. Always visible once set, so the shelf it
                              feeds is not a list you cannot see the source of. */}
                          <button
                            onClick={() => toggleStar(name)}
                            title={starred.includes(name) ? 'Remove from Starred' : 'Add to Starred'}
                            aria-pressed={starred.includes(name)}
                            className={cn('cursor-pointer p-1 transition-colors',
                              starred.includes(name)
                                ? 'text-warn'
                                : 'text-muted2 opacity-70 hover:text-ink sm:opacity-0 group-hover:opacity-100')}
                          >
                            <Star className={cn('size-3.5', starred.includes(name) && 'fill-current')} />
                          </button>

                          {/* Delete Action */}
                          {!isDeleting ? (
                            <button
                              onClick={() => setConfirmDelete(name)}
                              className="text-muted2 hover:text-red-400 transition-colors p-1 opacity-70 sm:opacity-0 group-hover:opacity-100 cursor-pointer"
                              title="Delete project"
                            >
                              <Trash2 className="size-3.5" />
                            </button>
                          ) : (
                            <div className="flex items-center gap-1 bg-red-950/80 px-2 py-0.5 rounded border border-red-500/40">
                              <button
                                onClick={() => { onDelete?.(name); setConfirmDelete('') }}
                                className="text-[10px] font-bold text-red-300 hover:text-ink cursor-pointer"
                              >
                                delete
                              </button>
                              <span className="text-muted2 text-[10px]">/</span>
                              <button
                                onClick={() => setConfirmDelete('')}
                                className="text-[10px] text-muted hover:text-ink cursor-pointer"
                              >
                                keep
                              </button>
                            </div>
                          )}
                        </div>

                        <p className="mt-1 font-mono text-[11px] text-muted2 truncate">
                          {p.name}
                        </p>
                      </div>

                      <div className="mt-3 flex items-center justify-between border-t border-line pt-2.5 text-[11px] text-muted2">
                        <span className="flex items-center gap-1.5">
                          <Calendar className="size-3 text-muted2" />
                          {formatDate(p.mtime)}
                        </span>
                        <span>
                          {isSpec
                            ? 'SRS Specification'
                            : isProto
                            ? 'HTML Prototype'
                            : p.file_count
                            ? `${p.file_count} files`
                            : 'App project'}
                        </span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
