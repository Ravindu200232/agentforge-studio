'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowRight, Check, CloudUpload, FileText, FlaskConical, FolderOpen, Languages, PencilLine, Rocket, Search,
} from 'lucide-react'
import { useStore, KEYS } from '@/lib/store'
import { send } from '@/lib/ws'
import { api } from '@/lib/api'
import { Modal, TextArea } from './ui'
import { cn } from '@/lib/utils'
import { useAttachments } from '@/lib/use-attachments'
import { AttachButtons, AttachList } from './srs/Attachments'
import LogoPanel from './LogoPanel'
import BuildSetup from './BuildSetup'
import PluginAccounts from './PluginAccounts'
import DesignCustomize from './DesignCustomize'
import AgentChat from './AgentChat'
import Interview from './srs/Interview'
import PlanReview from './srs/PlanReview'
import SrsReview from './srs/SrsReview'
import SrsActivity from './srs/SrsActivity'
import { displaySrsLanguages, SRS_LANGUAGES } from '@/lib/languages'
import { TIERS, tierDisplayName } from '@/lib/models'
import { DEFAULT_STACK, stackNeeds } from '@/lib/stacks'

const CONNECTION_NAMES = { supabase: 'Supabase', mongodb: 'MongoDB' }

function attachToken() {
  const raw = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
  return raw.replace(/[^a-z0-9]/gi, '').slice(0, 24)
}

export default function Home({
  onStarted,
  onKept,
  modelOptions = [],
  user = null,
  onRequireAuth = null,
  onSignIn = null,
  onSignUp = null,
  onSettings = null,
  connectionsVersion = 0,
}) {
  const s = useStore()
  const { think, models, srsId, srsPhase } = s
  const [prompt, setPrompt] = useState('')
  const [logoFor, setLogoFor] = useState(null)
  const [srsError, setSrsError] = useState('')
  const [srsLanguage, setSrsLanguage] = useState('en')
  const [langOpen, setLangOpen] = useState(false)
  const [langSearch, setLangSearch] = useState('')
  const [stack, setStack] = useState('')
  const [locationDialog, setLocationDialog] = useState(false)
  const [workspacePath, setWorkspacePath] = useState('')
  const [pickingWorkspace, setPickingWorkspace] = useState(false)
  const [workspaceError, setWorkspaceError] = useState('')
  // Providers this build should start with. Held here because the app they
  // belong to does not exist yet, and the sheet is here rather than in
  // BuildSetup because that row opens no dialog of its own.
  const [plugins, setPlugins] = useState([])
  const [pluginsOpen, setPluginsOpen] = useState(false)
  const [languageOptions, setLanguageOptions] = useState(SRS_LANGUAGES)
  const box = useRef(null)

  // The account connections a build of the chosen stack needs (`stacks.js` `needs`). Start waits
  // for them, the way the Deploy panel waits for its accounts. null = still being checked. They are
  // made in Settings › Integrations, so they are read again when Settings closes and on focus.
  const [connections, setConnections] = useState({ supabase: null, mongodb: null })
  useEffect(() => {
    let live = true
    const check = () => Promise.all([
      api.supabaseOauthStatus().then(d => Boolean(d?.connected)).catch(() => false),
      api.settings().then(d => Boolean(d?.deploy?.deploy_mongodb_uri_set)).catch(() => false),
    ]).then(([supabase, mongodb]) => { if (live) setConnections({ supabase, mongodb }) })
    check()
    window.addEventListener('focus', check)
    return () => { live = false; window.removeEventListener('focus', check) }
  }, [connectionsVersion])
  const needs = stackNeeds(stack)
  const missing = needs.filter(need => connections[need] !== true)
  const langRef = useRef(null)
  const planning = useRef(false)
  const attach = useAttachments()
  const builderModel = models.builder || models.agent || TIERS.medium.model
  const plannerModel = models.planner || models.agent || builderModel
  const designModel = models.design || models.agent || builderModel

  useEffect(() => { setLanguageOptions(displaySrsLanguages()) }, [])
  // The interview is a project stage, not a temporary chat. Make its project
  // active early and restore the durable stream that continues through SRS,
  // wireframe, prototype, build, QA and deploy.
  useEffect(() => {
    if (!srsId) return
    const current = useStore.getState()
    if (current.project !== srsId) current.reset(srsId)
    let live = true
    api.workflow(srsId).then(snapshot => {
      if (live && useStore.getState().project === srsId) useStore.getState().restoreProject(snapshot)
    }).catch(() => {})
    return () => { live = false }
  }, [srsId])
  useEffect(() => {
    if (!user || srsPhase !== 'planning' || planning.current) return
    planning.current = true
    const epoch = useStore.getState().accountEpoch
    const resume = async () => {
      try {
        let id = srsId
        if (!id) {
          const pending = await api.resumeSrs('/projects')
          id = pending.result?.project?.id
          if (!id) throw new Error('The project was not saved yet. Submit your idea again.')
          if (useStore.getState().accountEpoch !== epoch) return
          s.setSrs({ srsId: id, srsBusy: 'Resuming the interview…' })
        }
        await api.srs(`/projects/${id}/analyze`, {})
        const current = useStore.getState()
        if (current.accountEpoch === epoch && current.srsId === id && current.srsPhase === 'planning')
          s.setSrs({ srsPhase: 'interview', srsBusy: '' })
      } catch (error) {
        if (useStore.getState().accountEpoch === epoch) {
          setSrsError(error.message)
          s.setSrs({ srsPhase: srsId ? 'interview' : 'idle', srsBusy: '' })
        }
      } finally { planning.current = false }
    }
    resume()
  }, [user, srsPhase, srsId])
  useEffect(() => {
    if (!srsId) return
    let live = true
    api.srs(`/projects/${srsId}`).then(result => {
      if (live && result?.project?.stack) setStack(result.project.stack)
    }).catch(() => {})
    return () => { live = false }
  }, [srsId])

  useEffect(() => {
    function handleClickOutside(e) {
      if (langRef.current && !langRef.current.contains(e.target)) {
        setLangOpen(false)
        setLangSearch('')
      }
    }
    if (langOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [langOpen])

  const currentLang = languageOptions.find(l => l.code === srsLanguage)
  const currentLangLabel = currentLang ? currentLang.name : 'English'

  const filteredLanguages = useMemo(() => {
    const q = langSearch.trim().toLowerCase()
    if (!q) return languageOptions
    return languageOptions.filter(l =>
      l.name.toLowerCase().includes(q) || l.code.toLowerCase().includes(q)
    )
  }, [languageOptions, langSearch])

  // One implementation, shared with Settings, so a model chosen in either
  // place reaches the same set of agents.
  const chooseModel = model => useStore.getState().applyModel(model)

  function chooseThinking(value) {
    const level = ['low', 'high', 'xhigh'].includes(value) ? value : value ? 'high' : 'low'
    useStore.getState().setThinkingLevel(level)
    s.persist(KEYS.think, level === 'low' ? '0' : '1')
  }

  function submit() {
    const hasBrief = prompt.trim() || attach.items.length
    if (!hasBrief) return box.current?.focus()
    // Ctrl/Cmd+Enter reaches here without the Start button, so the same rule holds here.
    if (missing.length) return
    setWorkspacePath('')
    setWorkspaceError('')
    setLocationDialog(true)
  }

  async function startBuild(p, logo, srs = '', uploads = null, config = null, prototypeOnly = false) {
    onStarted?.()
    setLogoFor(null)
    s.reset(null)
    s.switchAgent(prototypeOnly ? 'designer' : 'developer')
    s.setBusy(true)

    let token = ''
    // Files already uploaded during the SRS interview live in this project's
    // workspace. Do not re-stage them under a throwaway token when the build
    // starts; the first agent turn has already received their real locations.
    if (attach.items.length && !srs) {
      const wanted = attachToken()
      s.setProgress(attach.items.length === 1
        ? 'Sending your attachment…' : `Sending your ${attach.items.length} attachments…`, 0)
      const { staged, failed } = await attach.stage(wanted)
      if (failed) {
        s.addLog('WARN', `${failed} attachment(s) could not be sent — building with what did arrive.`)
      }
      if (staged) {
        token = wanted
        s.addLog('INFO', `${staged} attachment(s) go into the build`)
      }
    } else if (attach.items.length && srs) {
      s.addLog('INFO', `${attach.items.length} attachment(s) are available in the project workspace`)
    }

    s.setProgress('Starting…', 0)
    const selected = config?.model || builderModel
    s.addLog('INFO', `Build mode — ${tierDisplayName(selected)} · Thinking — ${(config?.think ?? think) ? 'on' : 'off'}`)
    if (prototypeOnly) s.addLog('INFO', '🎨 Prototype Build mode — generating interactive HTML prototype first')
    if (logo) s.addLog('INFO', 'Building around the logo you accepted')
    if (srs) s.addLog('INFO', 'Building from the SRS you approved')

    send({
      type: 'agent_build',
      prompt: p,
      model: selected,
      builder_model: selected,
      planner_model: config?.model || plannerModel,
      design_model: config?.model || designModel,
      stack: config?.stack || stack,
      think: config?.think ?? think,
      thinking_level: config?.thinking_level || s.thinkingLevel,
      qa_model: models.qa,
      logo,
      srs_id: srs || '',
      attachments: token || undefined,
      uploads: uploads && Object.keys(uploads).length ? uploads : undefined,
      prototype_only: Boolean(prototypeOnly),
      agent: prototypeOnly ? 'designer' : 'developer',
      // There is no project yet to tick these against, so they travel with the
      // request and are written onto the workspace the moment it is made.
      plugins: plugins.length ? plugins : undefined,
    })
  }

  async function chooseWorkspace() {
    setPickingWorkspace(true)
    setWorkspaceError('')
    try {
      const result = await api.chooseWorkspace()
      if (result?.path) setWorkspacePath(result.path)
    } catch (error) {
      setWorkspaceError(error.message)
    } finally {
      setPickingWorkspace(false)
    }
  }

  async function planFirst(workspace = '') {
    const idea = prompt.trim()
    const files = attach.items.length
    if (!idea && !files) return box.current?.focus()
    if (planning.current) return
    planning.current = true
    const epoch = useStore.getState().accountEpoch
    setSrsError('')
    s.setSrs({ srsId: null, srsPhase: 'planning', srsBusy: 'Reading your idea…' })
    try {
      const created = await api.srs('/projects', {
        idea: idea || 'See the attached files.',
        language: languageOptions.find(item => item.code === srsLanguage)?.name || srsLanguage,
        stack: stack || DEFAULT_STACK,
        workspace_path: workspace || undefined,
        // What is picked beside this input is what the interview and the specification run on.
        model: builderModel,
        thinking_level: s.thinkingLevel,
      })
      const id = created.project.id
      if (useStore.getState().accountEpoch !== epoch || useStore.getState().srsPhase !== 'planning') return
      s.reset(id)
      s.setSrs({ srsId: id })

      if (files) {
        s.setSrs({ srsId: id, srsBusy: `Reading your ${files === 1 ? 'attachment' : `${files} attachments`}…` })
        const { ids, failed } = await attach.upload(id)

        if (failed && !ids.length && !idea) {
          throw new Error(files === 1
            ? 'that file could not be read, and there is nothing typed to go on'
            : 'none of those files could be read, and there is nothing typed to go on')
        }
        if (failed) {
          s.addLog('WARN', `${failed} of ${files} attachments could not be read — carrying on with the rest.`)
        }
      }

      if (useStore.getState().accountEpoch !== epoch || useStore.getState().srsId !== id) return
      s.setSrs({ srsId: id, srsBusy: 'Working out what to ask you…' })
      await api.srs(`/projects/${id}/analyze`, {})
      if (useStore.getState().accountEpoch !== epoch || useStore.getState().srsId !== id) return
      s.setSrs({ srsPhase: 'interview', srsBusy: '' })
    } catch (e) {
      if (useStore.getState().accountEpoch !== epoch) return
      setSrsError(e.message)
      const id = useStore.getState().srsId
      s.setSrs({ srsPhase: id ? 'interview' : 'idle', srsBusy: '' })
    } finally { planning.current = false }
  }

  function acceptSrs(handoffPrompt, id) {
    s.setSrs({ srsId: id, srsPhase: 'design', srsBusy: '' })
  }

  if (srsPhase === 'design' && srsId) {
    return (
      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-panel text-ink">
        <DesignCustomize key={srsId} projectId={srsId}
          onBack={() => s.setSrs({ srsPhase: 'review' })}
          onContinue={async ({ direction, designSpec }) => {
            // The customizer's concise visual summary is persisted with the
            // Design Spec and becomes part of the prototype agent's prompt.
            const design = await api.draftDesignSpec(srsId, designSpec, direction)
            await api.approveDesignSpec(srsId, design.version)
            // Keep the operation ID across transport retries and reloads.
            const key = `agentforge-design-change-${srsId}`
            let saved
            try { saved = JSON.parse(localStorage.getItem(key) || 'null') } catch { }
            const summary = `${direction}\n\nApproved Design Spec v${design.version}.`
            if (saved?.summary !== summary) saved = { change_id: `design-${crypto.randomUUID()}`, summary }
            localStorage.setItem(key, JSON.stringify(saved))
            await api.srs(`/projects/${srsId}/changes`, { ...saved, source: 'design-customizer' })
            localStorage.removeItem(key)
            onStarted?.()
            startBuild(direction, '', srsId, null, { model: designModel, stack, think }, true)
            s.setSrs({ srsPhase: 'idle', srsBusy: '' })
          }} />
      </div>
    )
  }

  if (srsPhase === 'review' && srsId) {
    return (
      <SrsReview key={srsId} projectId={srsId}
                 onApproved={acceptSrs}
                 onKept={(project) => { s.resetSrs(); setPrompt(''); onKept?.(project) }}
                 onNewProject={() => { s.resetSrs(); setPrompt('') }}
                 onBack={() => s.setSrs({ srsPhase: 'plan' })} />
    )
  }

  if (srsPhase === 'interview' && srsId) {
    return (
      <Interview key={srsId} projectId={srsId}
                 onDone={() => s.setSrs({ srsPhase: 'plan' })}
                 onCancel={() => s.resetSrs()} />
    )
  }

  if (srsPhase === 'plan' && srsId) {
    return (
      <div className="flex min-h-0 flex-1 overflow-hidden bg-panel text-ink">
        <AgentChat projectTitle="Plan conversation" readOnly className="hidden lg:flex lg:w-[360px]" />
        <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-6 sm:px-6 sm:py-10">
          <PlanReview key={srsId} projectId={srsId}
                      onGenerated={() => s.setSrs({ srsPhase: 'review' })}
                      onGenerating={(project) => { s.resetSrs(); setPrompt(''); onKept?.(project) }}
                      onCancel={() => s.setSrs({ srsPhase: 'interview' })} />
        </div>
      </div>
    )
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto bg-panel px-3.5 sm:px-6 py-6 sm:py-10 text-ink">
      {/* Bolt.new Public Top Navigation (When signed out, matching media_1789153650649.png) */}
      {!user && (
        <header className="absolute top-0 inset-x-0 z-30 flex items-center justify-between px-4 py-3 sm:px-6 sm:py-4 md:px-10 border-b border-black/[.07] bg-panel/60 backdrop-blur-md">
          <div className="flex items-center gap-2.5">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent ring-1 ring-accent/30">
              <img src="/__agentforge/agentforge-mark.png" alt="AgentForge" className="size-5 object-contain" />
            </div>
            <span className="font-display text-[17px] font-bold italic tracking-tight text-ink">
              agentforge<span className="text-accent font-normal">.ai</span>
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-7 text-[13px] font-medium text-muted">
            <button type="button" onClick={onSignIn} className="hover:text-ink transition-colors">Solutions</button>
            <button type="button" onClick={onSignIn} className="hover:text-ink transition-colors">Resources</button>
            <button type="button" onClick={onSignIn} className="hover:text-ink transition-colors">Careers</button>
            <button type="button" onClick={onSignIn} className="hover:text-ink transition-colors">Pricing</button>
          </nav>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onSignIn}
              className="px-3.5 py-1.5 text-[13px] font-medium text-ink hover:text-ink transition-colors"
            >
              Sign in
            </button>
            <button
              type="button"
              onClick={onSignUp}
              className="rounded-xl bg-accent px-3.5 sm:px-4 py-1.5 sm:py-2 font-display text-[12px] sm:text-[13px] font-semibold text-ink shadow-md shadow-accent/25 hover:bg-accent transition-all active:scale-95"
            >
              Get Started
            </button>
          </div>
        </header>
      )}

      <div className={cn("relative mx-auto my-auto w-full max-w-[940px]", !user && "pt-12")}>
        {/* Bolt.new Style Hero */}
        <div className="text-center px-2">
          <h1 className="font-display text-[28px] sm:text-[44px] md:text-[56px] font-bold tracking-tight text-ink leading-[1.12]">
            What will you build today?
          </h1>
          <p className="mt-2 sm:mt-3 text-[14px] sm:text-[16px] text-muted">
            Create stunning apps & websites by chatting with AI.
          </p>
        </div>

        {srsPhase === 'planning' && (
          <div className="mt-6">
            <SrsActivity phase="planning" message={s.srsBusy || 'Reading your idea…'} />
          </div>
        )}

        {srsPhase === 'idle' && (
          <>
            {/* Main Central Prompt Box */}
            <div className="mt-8 relative z-30 rounded-[26px] border border-line bg-panel shadow-2xl backdrop-blur-2xl transition-all focus-within:border-accent/60 focus-within:shadow-[0_20px_60px_rgba(191, 185, 255,.2)]">
              <TextArea
                value={prompt}
                autoFocus
                rows={4}
                ref={box}
                aria-label="Describe your app"
                placeholder="How can AgentForge help you today? Describe an app, prototype, or SRS..."
                onChange={e => {
                  setPrompt(e.target.value)
                  if (!user && onRequireAuth && e.target.value.length > 0) {
                    onRequireAuth()
                  }
                }}
                onKeyDown={e => {
                  if (!user && onRequireAuth) {
                    onRequireAuth()
                    return
                  }
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    submit()
                  }
                }}
                className="min-h-[130px] w-full resize-none rounded-t-[26px] bg-transparent p-5 text-[15px] leading-[1.6] text-ink caret-accent outline-none placeholder:text-muted2"
              />

              <AttachList attach={attach} className="mx-5 mb-2" />

              {/* All composer controls live in one quiet, icon-only rail. */}
              <div className="relative z-20 flex flex-wrap items-center justify-between gap-2 rounded-b-[26px] bg-panel2/40 p-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <BuildSetup
                    compact
                    model={builderModel}
                    stack={stack}
                    think={think}
                    thinkingLevel={s.thinkingLevel}
                    options={modelOptions}
                    onModelChange={chooseModel}
                    onStackChange={setStack}
                    onThinkChange={chooseThinking}
                    onThinkingLevelChange={chooseThinking}
                    plugins={plugins}
                    onPluginsOpen={() => setPluginsOpen(true)}
                  />
                  <AttachButtons attach={attach} cell />

                  {/* Language stays available without adding another text label. */}
                  <div className="relative" ref={langRef}>
                    <button
                      type="button"
                      onClick={() => setLangOpen(!langOpen)}
                      aria-label={`Interview language: ${currentLangLabel}`}
                      className="grid size-8 place-items-center rounded-xl border border-line bg-panel2 text-muted shadow-sm transition-all hover:bg-raised hover:border-line2 hover:text-ink"
                      title={`Interview language: ${currentLangLabel}. SRS and builder handoff stay in English.`}
                    >
                      <Languages className="size-3 shrink-0 text-accent" aria-hidden="true" />
                    </button>

                    {/* Hidden contract select */}
                    <select
                      id="srs-language"
                      value={srsLanguage}
                      onChange={event => setSrsLanguage(event.target.value)}
                      className="sr-only"
                      tabIndex={-1}
                      aria-hidden="true"
                    >
                      {languageOptions.map(language => (
                        <option key={language.code} value={language.code}>
                          {language.name}
                        </option>
                      ))}
                    </select>

                    {langOpen && (
                      <div className="absolute top-full mt-2 left-0 w-64 rounded-2xl border border-line bg-panel p-2 shadow-[0_20px_50px_rgba(0,0,0,0.75)] backdrop-blur-2xl z-50 animate-in fade-in zoom-in-95 duration-150">
                        {/* Search Input */}
                        <div className="relative mb-2">
                          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 size-2.5 text-muted2" />
                          <input
                            type="text"
                            value={langSearch}
                            onChange={e => setLangSearch(e.target.value)}
                            placeholder="Search language..."
                            autoFocus
                            className="w-full rounded-xl border border-line bg-panel2/60 py-1.5 pl-7 pr-2.5 text-[11px] text-ink outline-none placeholder:text-muted2 focus:border-accent"
                          />
                        </div>

                        {/* Scrollable Language List */}
                        <div className="max-h-48 overflow-y-auto space-y-0.5 pr-1 custom-scrollbar">
                          {filteredLanguages.map(language => {
                            const isSelected = language.code === srsLanguage
                            return (
                              <button
                                key={language.code}
                                type="button"
                                onClick={() => {
                                  setSrsLanguage(language.code)
                                  setLangOpen(false)
                                  setLangSearch('')
                                }}
                                className={cn(
                                  "w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-left text-[11.5px] transition-colors",
                                  isSelected
                                    ? "bg-accent text-ink font-semibold border border-accent/30"
                                    : "text-muted hover:bg-ink/[.06] hover:text-ink border border-transparent"
                                )}
                              >
                                <span className="truncate">{language.name}</span>
                                {isSelected && <Check className="size-2.5 shrink-0 text-accent ml-2" />}
                              </button>
                            )
                          })}
                          {filteredLanguages.length === 0 && (
                            <p className="px-2 py-3 text-center text-[11px] text-muted2">No languages found</p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* What this stack builds on: connected, or one click from Settings › Integrations. */}
                  {needs.map(need => {
                    const name = CONNECTION_NAMES[need] || need
                    const state = connections[need]
                    return state ? (
                      <span key={need} className="inline-flex h-8 items-center gap-1 rounded-xl border border-ok/35 px-2.5 text-[11px] font-medium text-ok">
                        <Check className="size-3 shrink-0" aria-hidden="true" /> {name} connected
                      </span>
                    ) : (
                      <button key={need} type="button" disabled={state === null}
                              onClick={() => onSettings?.('integrations')}
                              title={`Connect ${name} in Settings › Integrations`}
                              className="inline-flex h-8 items-center gap-1 rounded-xl border border-bad/35 px-2.5 text-[11px] font-medium text-bad transition-colors hover:bg-bad/10 disabled:opacity-60">
                        {state === null ? `Checking ${name}…` : <>{name} not connected · <span className="underline">Connect</span></>}
                      </button>
                    )
                  })}
                </div>

                {/* Right Action: Clean Bolt-style Submit Button */}
                <button
                  disabled={!prompt.trim() || !builderModel.trim() || missing.length > 0}
                  onClick={() => {
                    if (!user && onRequireAuth) {
                      onRequireAuth()
                      return
                    }
                    submit()
                  }}
                  title="Start SRS planning and specification"
                  className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-accent px-3.5 font-display text-[12px] font-medium text-ink shadow-lg shadow-accent/25 transition-all hover:bg-accent active:scale-95 disabled:pointer-events-none disabled:opacity-40"
                >
                  <span>Start</span>
                  <ArrowRight className="size-3 shrink-0" />
                </button>
              </div>
            </div>

            {locationDialog && (
              <Modal onClose={() => !pickingWorkspace && setLocationDialog(false)} className="max-w-md">
                <div className="flex items-start gap-3">
                  <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-accent/35 bg-transparent text-accent">
                    <FolderOpen className="size-5" />
                  </div>
                  <div>
                    <h2 className="text-[17px] font-bold text-ink">Where should this project be saved?</h2>
                    <p className="mt-1 text-[12px] leading-relaxed text-muted">
                      Choose a new empty folder in Explorer, or let AgentForge create it in its own workspace.
                    </p>
                  </div>
                </div>

                <div className="mt-5 rounded-2xl border border-line bg-panel2/60 p-3">
                  {workspacePath ? (
                    <>
                      <p className="text-[10px] font-semibold uppercase tracking-[.12em] text-muted2">Selected folder</p>
                      <p className="mt-1 break-all font-mono text-[11px] leading-relaxed text-ink">{workspacePath}</p>
                    </>
                  ) : (
                    <>
                      <p className="text-[12px] font-semibold text-ink">AgentForge workspace</p>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-muted">A separate project folder will be created automatically.</p>
                    </>
                  )}
                </div>

                {workspaceError && <p className="mt-3 text-[11.5px] text-bad">{workspaceError}</p>}

                <div className="mt-5 flex flex-wrap justify-end gap-2">
                  <button type="button" disabled={pickingWorkspace} onClick={chooseWorkspace}
                          className="inline-flex h-9 items-center gap-2 rounded-xl border border-line px-3 text-[12px] font-semibold text-ink transition-colors hover:bg-raised disabled:opacity-50">
                    <FolderOpen className="size-3.5 text-accent" />
                    {pickingWorkspace ? 'Opening Explorer…' : workspacePath ? 'Choose another folder' : 'Choose folder'}
                  </button>
                  <button type="button" disabled={pickingWorkspace} onClick={() => {
                    const chosen = workspacePath
                    setLocationDialog(false)
                    planFirst(chosen)
                  }}
                          className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-accent bg-accent px-3.5 text-[12px] font-semibold text-ink shadow-sm transition-all hover:bg-press disabled:opacity-50">
                    Start project <ArrowRight className="size-3" />
                  </button>
                </div>
              </Modal>
            )}

            {srsError && srsPhase === 'idle' && (
              <p className="mt-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2 text-[12px] text-red-300">
                The SRS could not start — {srsError}
              </p>
            )}

            {/* Visual Workflow Pipeline Stages */}
            <div className="mt-7 relative z-10 grid grid-cols-2 sm:grid-cols-5 gap-2 sm:gap-3 max-w-[820px] w-full mx-auto">
              {[
                {
                  id: 'srs',
                  label: 'SRS Generate',
                  desc: 'Interview & Spec',
                  Icon: FileText,
                  iconColor: 'text-amber-400',
                  iconBg: 'bg-amber-500/15 ring-1 ring-amber-500/25',
                  border: 'border-line bg-panel',
                },
                {
                  id: 'wireframe',
                  label: 'Wireframe Build',
                  desc: 'Page editing',
                  Icon: PencilLine,
                  iconColor: 'text-ink',
                  iconBg: 'bg-panel2 ring-1 ring-line2',
                  border: 'border-line bg-panel',
                },
                {
                  id: 'prototype',
                  label: 'Prototype Build',
                  desc: 'Fast UI Preview',
                  Icon: FlaskConical,
                  iconColor: 'text-ink',
                  iconBg: 'bg-accent ring-1 ring-accent/25',
                  border: 'border-line bg-panel',
                },
                {
                  id: 'app',
                  label: 'App Build',
                  desc: 'Full-Stack Code',
                  Icon: Rocket,
                  iconColor: 'text-ink',
                  iconBg: 'bg-accent ring-1 ring-accent/25',
                  border: 'border-line bg-panel',
                },
                {
                  id: 'deploy',
                  label: 'Deployment',
                  desc: 'Cloud & CI/CD',
                  Icon: CloudUpload,
                  iconColor: 'text-ink',
                  iconBg: 'bg-emerald-500/15 ring-1 ring-emerald-500/25',
                  border: 'border-line bg-panel',
                },
              ].map(card => (
                <div
                  key={card.id}
                  className={cn(
                    "relative flex flex-col items-center justify-center rounded-2xl border p-2.5 sm:p-3 w-full h-[88px] sm:h-[94px] shadow-sm select-none",
                    card.border
                  )}
                >
                  <div className={cn(
                    "flex size-7 sm:size-8 items-center justify-center rounded-xl",
                    card.iconBg
                  )}>
                    <card.Icon className={cn("size-3.5 sm:size-4", card.iconColor)} />
                  </div>
                  <span className="mt-1.5 text-[10.5px] sm:text-[11.5px] font-semibold text-ink truncate max-w-full">
                    {card.label}
                  </span>
                  <span className="text-[9px] sm:text-[10px] text-muted2 truncate max-w-full">
                    {card.desc}
                  </span>
                </div>
              ))}
            </div>

          </>
        )}
      </div>

      {/* The plugins this build starts with. There is no project yet to tick
          them against, so the picks are held here and travel with the request;
          the workspace records them the moment it is made. After that the
          chat's own plugin icon is where they change. */}
      {pluginsOpen && (
        <Modal onClose={() => setPluginsOpen(false)} className="max-w-[620px]">
          <header className="mb-4">
            <h2 className="text-[14px] font-bold tracking-tight text-ink">Plugins</h2>
            <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
              Set providers up once and select every plugin this build needs. Their settings are
              written into the new app’s environment before it is written, and the
              agent is given each provider’s own page to build against.
            </p>
          </header>
          <div className="max-h-[60vh] overflow-y-auto pr-1">
            <PluginAccounts pending={plugins} onPending={setPlugins} />
          </div>
        </Modal>
      )}

      {logoFor && (
        <LogoPanel
          idea={logoFor.idea}
          model={designModel}
          onAccept={(file, uploads) => startBuild(logoFor.idea, file, logoFor.srs, uploads, logoFor.config, false)}
          onSkip={(uploads) => startBuild(logoFor.idea, '', logoFor.srs, uploads, logoFor.config, false)}
        />
      )}
    </div>
  )
}
