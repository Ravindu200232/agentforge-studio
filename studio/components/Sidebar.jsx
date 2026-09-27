'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  FolderUp, Settings, Download, ExternalLink, Search, Play, Trash2,
  PanelLeftClose, PanelLeftOpen, Home, LayoutGrid, Star, Clock,
  BookOpen, FileText, Activity, ChevronDown, CreditCard, LogOut,
  X, Menu, Plus,
} from 'lucide-react'
import { useStore, KEYS } from '@/lib/store'
import { api } from '@/lib/api'
import { Badge, Button, Input, SectionLabel, Tag, Tip } from './ui'
import { cn } from '@/lib/utils'

export default function Sidebar({
  projects = [],
  onOpen,
  onImport,
  onSettings,
  onZip,
  onResume,
  onDeleted,
  screen = 'home',
  onScreenChange,
  user = null,
  onLogout = null,
  mobileOpen = false,
  onMobileClose = null,
}) {
  const project = useStore(z => z.project)
  const status = useStore(z => z.status)
  const statusText = useStore(z => z.statusText)
  const busyProject = useStore(z => z.busyProject)
  const busy = useStore(z => z.busy)
  const persist = useStore(z => z.persist)
  const starred = useStore(z => z.starred)
  const addLog = useStore(z => z.addLog)

  const [collapsed, setCollapsed] = useState(false)
  const folderRef = useRef(null)
  const [q, setQ] = useState('')
  const [confirming, setConfirming] = useState('')
  const [removing, setRemoving] = useState('')

  const [accountOpen, setAccountOpen] = useState(false)
  const accountMenuRef = useRef(null)

  const initial = (user?.name || user?.username || 'R')[0]?.toUpperCase() || 'R'
  const displayName = user?.name || user?.username || 'Ravindu'
  const displaySubtitle = user?.email || 'Developer Workspace'

  useEffect(() => {
    if (!accountOpen) return
    const handleClickAway = (e) => {
      if (accountMenuRef.current && !accountMenuRef.current.contains(e.target)) {
        setAccountOpen(false)
      }
    }
    window.addEventListener('mousedown', handleClickAway)
    return () => window.removeEventListener('mousedown', handleClickAway)
  }, [accountOpen])

  async function openInNewTab() {
    if (!project) return
    const tab = window.open('about:blank', '_blank')
    try {
      const runtime = await api.open(project)
      useStore.getState().setRuntime(runtime)
      if (tab) { tab.opener = null; tab.location.href = runtime.previewUrl }
    } catch (error) {
      tab?.close()
      useStore.getState().addLog('WARN', `Could not open app: ${error.message}`)
    }
  }

  async function remove(name) {
    setRemoving(name)
    try {
      await api.deleteProject(name)
      addLog('SUCCESS', `Deleted ${name}`)
    } catch (e) {
      addLog('WARN', `Delete of ${name} did not report back — ${e.message}. `
                     + 'Checking whether it went.')
    }
    if (project === name) useStore.getState().reset(null)
    onDeleted?.(name)
    setRemoving('')
    setConfirming('')
  }

  useEffect(() => {
    api.settings()
      .then(cfg => {
        if (!cfg || !('image_enabled' in cfg)) return
        useStore.setState({ images: !!cfg.image_enabled })
        persist(KEYS.images, cfg.image_enabled ? '1' : '0')
      })
      .catch(() => { })
  }, [persist])

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return projects
    return projects.filter(p =>
      String(p.title || p.name || p).toLowerCase().includes(needle) ||
      String(p.name || '').toLowerCase().includes(needle))
  }, [projects, q])

  const dot = { live: 'bg-[#22C55E]', busy: 'bg-[#FFAB00]', connecting: 'bg-[#1877F2]' }[status]
    || 'bg-[#FF5630]'

  const renderBody = (isMobile = false) => (
    <>
      {/* Primary Navigation Menu */}
      <nav className="flex flex-col gap-0.5 p-2 border-b border-line text-[13px]">
        <button
          onClick={() => {
            useStore.getState().resetSrs()
            useStore.getState().reset(null)
            onScreenChange?.('home')
            if (isMobile) onMobileClose?.()
          }}
          className="flex items-center gap-3 rounded-xl px-3 py-2 font-medium transition-all text-left bg-white hover:bg-white text-ink font-semibold shadow-sm mb-1 cursor-pointer"
        >
          <Plus className="size-4 shrink-0 text-ink" />
          <span>New Project</span>
        </button>

        <button
          onClick={() => {
            onScreenChange?.('home')
            if (isMobile) onMobileClose?.()
          }}
          className={cn(
            'flex items-center gap-3 rounded-xl px-3 py-2 font-medium transition-all text-left',
            screen === 'home'
              ? 'bg-black/[.06] text-ink font-semibold'
              : 'text-muted hover:bg-ink/[.05] hover:text-ink'
          )}
        >
          <Home className="size-4 shrink-0 text-muted2" />
          <span>Home</span>
        </button>

        <button
          onClick={() => {
            onScreenChange?.('projects')
            if (isMobile) onMobileClose?.()
          }}
          className={cn(
            'flex items-center justify-between rounded-xl px-3 py-2 font-medium transition-all text-left',
            screen === 'projects'
              ? 'bg-black/[.06] text-ink font-semibold'
              : 'text-muted hover:bg-ink/[.05] hover:text-ink'
          )}
        >
          <div className="flex items-center gap-3">
            <LayoutGrid className="size-4 shrink-0 text-muted2" />
            <span>Projects</span>
          </div>
          <span className={cn(
            "rounded-full px-2 py-0.5 font-mono text-[10px]",
            screen === 'projects' ? "bg-[#BFB9FF] text-ink font-bold" : "bg-panel2 text-muted"
          )}>
            {projects.length}
          </span>
        </button>

        <button
          onClick={() => {
            onSettings?.()
            if (isMobile) onMobileClose?.()
          }}
          className="flex items-center gap-3 rounded-xl px-3 py-1.5 text-muted hover:bg-ink/[.05] hover:text-ink text-left"
        >
          <Settings className="size-4 shrink-0 text-muted2" />
          <span>Settings</span>
        </button>

        {/* Both open the Projects screen on a shelf of their own. "Shared with
            you" used to sit here too and was removed: accounts on this server
            are isolated by design - `auth_db` says nothing is shared between
            them - so it was a door onto a room that cannot exist. */}
        <button
          onClick={() => {
            useStore.getState().setProjectFilter('starred')
            onScreenChange?.('projects')
            if (isMobile) onMobileClose?.()
          }}
          className="flex items-center justify-between rounded-xl px-3 py-1.5 text-left text-muted hover:bg-ink/[.05] hover:text-ink">
          <div className="flex items-center gap-3">
            <Star className="size-4 shrink-0 text-muted2" />
            <span>Starred</span>
          </div>
          {starred.length > 0 && (
            <span className="rounded-full bg-panel2 px-2 py-0.5 font-mono text-[10px] text-muted">
              {starred.length}
            </span>
          )}
        </button>

        <button
          onClick={() => {
            useStore.getState().setProjectFilter('recent')
            onScreenChange?.('projects')
            if (isMobile) onMobileClose?.()
          }}
          className="flex items-center gap-3 rounded-xl px-3 py-1.5 text-left text-muted hover:bg-ink/[.05] hover:text-ink">
          <Clock className="size-4 shrink-0 text-muted2" />
          <span>Recently viewed</span>
        </button>
      </nav>

      {/* Secondary Resources & Status */}
      <div className="flex flex-col gap-0.5 p-2 border-b border-line text-[12px]">
        <button className="flex items-center gap-3 rounded-xl px-3 py-1.5 text-muted hover:bg-ink/[.05] hover:text-ink">
          <BookOpen className="size-3.5 shrink-0 text-muted2" />
          <span>Help Center</span>
        </button>
        <button className="flex items-center gap-3 rounded-xl px-3 py-1.5 text-muted hover:bg-ink/[.05] hover:text-ink">
          <FileText className="size-3.5 shrink-0 text-muted2" />
          <span>Release notes</span>
        </button>
        <div className="flex items-center justify-between rounded-xl px-3 py-1.5 text-muted">
          <div className="flex items-center gap-3">
            <Activity className="size-3.5 shrink-0 text-muted2" />
            <span>Status</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={cn('size-2 rounded-full', dot)} />
            <span className="font-mono text-[10px] text-muted">{status}</span>
          </div>
        </div>
      </div>

      {/* Active Project Card */}
      {project && (() => {
        const name = project
        const title = projects.find(row => row && typeof row === 'object' && row.name === project)?.title || name
        // `busyProject` is only ever set, never cleared: it says which project the last run was started on.
        const working = busy && busyProject === name
        return (
          <div className="p-3 border-b border-line">
            <div className="mb-1.5 px-1 text-[10px] font-bold uppercase tracking-wider text-muted2">
              Active Workspace
            </div>
            <div className="flex items-center justify-between gap-2 rounded-xl border border-line bg-panel2 p-2.5 shadow-sm">
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12.5px] font-semibold text-ink" title={title}>{title}</div>
              </div>
              {working ? (
                <span className="flex items-center gap-1.5 rounded-full bg-[#BFB9FF] px-2 py-0.5 text-[10px] font-semibold text-ink">
                  <span className="size-1.5 rounded-full bg-[#BFB9FF] animate-pulse" />
                  working
                </span>
              ) : (
                <button
                  onClick={() => {
                    onScreenChange?.('projects')
                    if (isMobile) onMobileClose?.()
                  }}
                  className="text-[11px] font-medium text-[#BFB9FF] hover:underline"
                >
                  Change
                </button>
              )}
            </div>
          </div>
        )
      })()}

      {/* Spacer */}
      <div className="flex-1" />

      {/* User Account Row */}
      <div className="relative border-t border-line px-3 py-2.5" ref={accountMenuRef}>
        {/* Hidden folder input for import */}
        <input ref={folderRef} type="file" hidden
               webkitdirectory="" directory="" multiple
               onChange={e => {
                 const list = e.target.files
                 e.target.value = ''
                 if (list?.length) onImport(list)
               }} />

        {/* Account Menu Popover */}
        {accountOpen && (
          <div
            className="absolute bottom-full left-3 mb-2 w-56 rounded-2xl border border-line bg-[#F2F0EF] p-1.5 shadow-[0_20px_40px_-4px_rgba(0,0,0,0.48)] backdrop-blur-2xl z-50 animate-in fade-in zoom-in-95"
          >
            <button
              onClick={() => { setAccountOpen(false); onSettings?.(); if (isMobile) onMobileClose?.() }}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-black/[.06] hover:text-ink transition-colors"
            >
              <Settings className="size-4 text-ink" />
              <span>Settings</span>
            </button>
            <button
              onClick={() => { setAccountOpen(false); folderRef.current?.click(); if (isMobile) onMobileClose?.() }}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-black/[.06] hover:text-ink transition-colors"
            >
              <FolderUp className="size-4 text-ink" />
              <span>Import project folder</span>
            </button>
            <button
              onClick={() => { setAccountOpen(false); onResume?.(); if (isMobile) onMobileClose?.() }}
              disabled={!project || status === 'busy'}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-ink/[.06] disabled:opacity-40 disabled:pointer-events-none transition-colors"
            >
              <Play className="size-4 text-muted2" />
              <span>Resume build</span>
            </button>
            <button
              onClick={() => { setAccountOpen(false); onZip?.(); if (isMobile) onMobileClose?.() }}
              disabled={!project}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-ink/[.06] disabled:opacity-40 disabled:pointer-events-none transition-colors"
            >
              <Download className="size-4 text-muted2" />
              <span>Download project as zip</span>
            </button>
            <button
              onClick={() => { setAccountOpen(false); openInNewTab(); if (isMobile) onMobileClose?.() }}
              disabled={!project}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-ink/[.06] disabled:opacity-40 disabled:pointer-events-none transition-colors"
            >
              <ExternalLink className="size-4 text-muted2" />
              <span>Open in new tab</span>
            </button>
            {onLogout && (
              <>
                <div className="my-1 border-t border-line" />
                <button
                  onClick={() => { setAccountOpen(false); onLogout?.(); if (isMobile) onMobileClose?.() }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-[#FF5630] hover:bg-[#FF5630]/10 hover:text-[#FF5630] transition-colors"
                >
                  <LogOut className="size-4" />
                  <span>Sign out</span>
                </button>
              </>
            )}
          </div>
        )}

        <button
          onClick={() => setAccountOpen(v => !v)}
          className="flex w-full items-center justify-between gap-2.5 rounded-xl p-1.5 hover:bg-ink/[.06] transition-colors group"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[#BFB9FF] font-bold text-[13px] text-ink shadow-sm transition-transform group-hover:scale-105">
              {initial}
            </div>
            <div className="min-w-0 text-left">
              <div className="truncate text-[12.5px] font-semibold text-ink">{displayName}</div>
              <div className="truncate text-[10.5px] text-muted2">{displaySubtitle}</div>
            </div>
          </div>
          <ChevronDown className={cn("size-3.5 text-muted2 transition-transform", accountOpen && "rotate-180")} />
        </button>
      </div>
    </>
  )

  const renderMobileDrawer = () => (
    <div className={cn(
      "fixed inset-0 z-50 md:hidden transition-all duration-300",
      mobileOpen ? "visible opacity-100" : "invisible opacity-0 pointer-events-none"
    )}>
      <div
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        onClick={onMobileClose}
      />
      <aside className={cn(
        "absolute top-0 bottom-0 left-0 w-[280px] max-w-[85vw] flex flex-col bg-panel border-r border-line shadow-2xl transition-transform duration-300 ease-out z-10",
        mobileOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[#BFB9FF] ring-1 ring-[#BFB9FF]/20 shadow-sm overflow-hidden">
              <img src="/__agentforge/agentforge-mark.png" alt="AgentForge" width={22} height={22} className="size-5 object-contain" />
            </div>
            <span className="font-display text-[14.5px] font-bold tracking-tight text-ink">
              agentforge<span className="text-accent text-[12px] font-normal ml-0.5">.ai</span>
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={onMobileClose}
              className="grid size-7 place-items-center rounded-lg border border-line bg-panel2/80 text-muted hover:bg-raised hover:text-ink"
            >
              <X className="size-3.5" />
            </button>
          </div>
        </header>
        {renderBody(true)}
      </aside>
    </div>
  )

  if (collapsed) {
    return (
      <>
        {renderMobileDrawer()}
        <aside className="hidden md:flex w-[52px] shrink-0 flex-col items-center gap-2 overflow-hidden h-full border-r border-line bg-panel py-3">
          <Tip text="Show the sidebar" side="right">
            <button onClick={() => setCollapsed(false)}
                    className="grid size-9 place-items-center rounded-xl text-muted transition-colors hover:bg-raised hover:text-ink">
              <PanelLeftOpen className="size-4" />
            </button>
          </Tip>
          <span className={cn('size-2 shrink-0 rounded-full', dot)} title={statusText} />
          <span className="my-1 h-px w-6 bg-line" />

          <Tip text="Home" side="right">
            <button onClick={() => onScreenChange?.('home')}
                    className={cn('grid size-9 place-items-center rounded-xl transition-colors',
                      screen === 'home' ? 'bg-[#BFB9FF] text-ink font-semibold' : 'text-muted hover:bg-raised hover:text-ink')}>
              <Home className="size-4" />
            </button>
          </Tip>

          <Tip text="All Projects" side="right">
            <button onClick={() => onScreenChange?.('projects')}
                    className={cn('grid size-9 place-items-center rounded-xl transition-colors',
                      screen === 'projects' ? 'bg-[#BFB9FF] text-ink font-semibold' : 'text-muted hover:bg-raised hover:text-ink')}>
              <LayoutGrid className="size-4" />
            </button>
          </Tip>

          <Tip text="Settings" side="right">
            <button onClick={onSettings}
                    className="grid size-9 place-items-center rounded-xl text-muted transition-colors hover:bg-raised hover:text-ink">
              <Settings className="size-3.5" />
            </button>
          </Tip>
          <Tip text="Resume this build where it stopped" side="right">
            <button onClick={onResume} disabled={!project || status === 'busy'}
                    className="grid size-9 place-items-center rounded-xl text-muted transition-colors hover:bg-raised hover:text-ink disabled:pointer-events-none disabled:opacity-30">
              <Play className="size-3.5" />
            </button>
          </Tip>
          <span className="flex-1" />
          {project && (
            <span className="max-h-[220px] [writing-mode:vertical-rl] truncate text-[10px] font-semibold text-muted2"
                  title={project}>
              {project}
            </span>
          )}

          {/* Collapsed Account Avatar Button with Popover */}
          <div className="relative mt-auto" ref={accountMenuRef}>
            {accountOpen && (
              <div
                className="absolute bottom-0 left-full ml-3 w-56 rounded-2xl border border-line bg-panel p-1.5 shadow-[0_20px_40px_-4px_rgba(0,0,0,0.48)] backdrop-blur-2xl z-50 animate-in fade-in zoom-in-95"
              >
                <button
                  onClick={() => { setAccountOpen(false); onSettings?.() }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-ink/[.06] transition-colors"
                >
                  <Settings className="size-4 text-muted2" />
                  <span>Settings</span>
                </button>
                <button
                  onClick={() => { setAccountOpen(false); folderRef.current?.click() }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-ink/[.06] transition-colors"
                >
                  <FolderUp className="size-4 text-muted2" />
                  <span>Import project folder</span>
                </button>
                <button
                  onClick={() => { setAccountOpen(false); onResume?.() }}
                  disabled={!project || status === 'busy'}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-ink/[.06] disabled:opacity-40 disabled:pointer-events-none transition-colors"
                >
                  <Play className="size-4 text-muted2" />
                  <span>Resume build</span>
                </button>
                <button
                  onClick={() => { setAccountOpen(false); onZip?.() }}
                  disabled={!project}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-black/[.06] hover:text-ink disabled:opacity-40 disabled:pointer-events-none transition-colors"
                >
                  <Download className="size-4 text-ink" />
                  <span>Download project as zip</span>
                </button>
                <button
                  onClick={() => { setAccountOpen(false); openInNewTab() }}
                  disabled={!project}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink hover:bg-black/[.06] hover:text-ink disabled:opacity-40 disabled:pointer-events-none transition-colors"
                >
                  <ExternalLink className="size-4 text-ink" />
                  <span>Open in new tab</span>
                </button>
                {onLogout && (
                  <>
                    <div className="my-1 border-t border-line" />
                    <button
                      onClick={() => { setAccountOpen(false); onLogout?.() }}
                      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-[#FF5630] hover:bg-[#FF5630]/10 hover:text-[#FF5630] transition-colors"
                    >
                      <LogOut className="size-4" />
                      <span>Sign out</span>
                    </button>
                  </>
                )}
              </div>
            )}
            <button
              onClick={() => setAccountOpen(v => !v)}
              title={`Account: ${displayName}`}
              className="flex size-8 items-center justify-center rounded-lg bg-[#BFB9FF] font-bold text-[13px] text-ink shadow-sm transition-transform hover:scale-105 active:scale-95"
            >
              {initial}
            </button>
          </div>
        </aside>
      </>
    )
  }

  return (
    <>
      {renderMobileDrawer()}
      <aside className="hidden md:flex w-[var(--sidebar-w)] shrink-0 flex-col overflow-hidden h-full border-r border-line bg-panel">
        {/* Top Header: Brand and Controls */}
        <header className="grid grid-cols-[auto_1fr_auto] items-center gap-3 border-b border-line px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[#BFB9FF] ring-1 ring-[#BFB9FF]/20 shadow-sm overflow-hidden">
              <img src="/__agentforge/agentforge-mark.png" alt="AgentForge"
                   width={22} height={22}
                   className="size-5 object-contain" />
            </div>
            <span className="font-display text-[14.5px] font-bold tracking-tight text-ink">
              agentforge<span className="text-accent text-[12px] font-normal ml-0.5">.ai</span>
            </span>
          </div>

          <div className="flex justify-end items-center gap-1.5 col-span-2">
            <Tip text="Hide the sidebar">
              <button
                className="grid size-[26px] place-items-center rounded-lg border border-line bg-panel2/80 text-muted transition-colors hover:bg-raised hover:text-ink"
                onClick={() => setCollapsed(true)}
              >
                <PanelLeftClose className="size-3" />
              </button>
            </Tip>
          </div>
        </header>
        {renderBody(false)}
      </aside>
    </>
  )
}




function DeployTag({ deployed }) {
  if (!deployed) return null
  const gone = deployed.state === 'deleted'
  const where = deployed.target?.startsWith('aws') ? 'aws'
              : deployed.target === 'vercel' ? 'vercel'
              : ''
  return (
    <Tip text={gone ? 'Deployed, then deleted'
                    : `Deployed${where ? ` to ${where}` : ''}`}>
      <Tag tone={gone ? 'mute' : 'solid'}>{gone ? 'gone' : (where || 'deployed')}</Tag>
    </Tip>
  )
}
