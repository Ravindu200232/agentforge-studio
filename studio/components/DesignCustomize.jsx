'use client'

import { useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/api'
import { Button, Input, Modal, TextArea } from './ui'
import WireframeStylePreview from './WireframeStylePreview'
import { ArrowLeft, Check, Palette, Search, Sparkles, Type, Wand2 } from 'lucide-react'

const ASSETS = '/__agentforge/design-themes'
const LIVE = '/__agentforge/api/design-theme-preview'
const RADII = [['Sharp', '0px'], ['Slight', '6px'], ['Rounded', '12px'], ['Pill', '9999px']]
const DENSITIES = ['Ultra Compact', 'Compact', 'Comfortable', 'Spacious']
const SWATCHES = ['primary', 'secondary', 'surface', 'text']
const STATUS_SWATCHES = ['success', 'warning', 'danger']
const APPEARANCES = ['Light', 'Dark', 'Light and dark']
const BORDERS = ['None', 'Hairline', 'Bold']
const SHADOWS = ['Flat', 'Soft', 'Dramatic']
const MOTIONS = ['None', 'Subtle', 'Expressive']

const DEFAULT_PALETTE = {
  primary: '#2563eb', secondary: '#64748b', surface: '#ffffff', text: '#0f172a',
  button: '#2563eb', success: '#16a34a', warning: '#d97706', danger: '#dc2626',
}

const COLOR_PRESETS = [
  { name: 'Modern SaaS', tag: 'Popular', colors: { ...DEFAULT_PALETTE } },
  { name: 'Fintech Emerald', tag: 'Finance', colors: { primary: '#059669', secondary: '#10b981', surface: '#f8fafc', text: '#064e3b', button: '#059669', success: '#16a34a', warning: '#f59e0b', danger: '#e11d48' } },
  { name: 'Creative Violet', tag: 'AI / Tech', colors: { primary: '#7c3aed', secondary: '#a855f7', surface: '#faf5ff', text: '#1e1b4b', button: '#7c3aed', success: '#10b981', warning: '#f59e0b', danger: '#ef4444' } },
  { name: 'Warm Sunset', tag: 'Editorial', colors: { primary: '#d97706', secondary: '#f59e0b', surface: '#fffbeb', text: '#292524', button: '#d97706', success: '#16a34a', warning: '#f59e0b', danger: '#dc2626' } },
  { name: 'Crimson Bold', tag: 'Energy', colors: { primary: '#e11d48', secondary: '#f43f5e', surface: '#fff1f2', text: '#18181b', button: '#e11d48', success: '#16a34a', warning: '#eab308', danger: '#be123c' } },
  { name: 'Monochrome', tag: 'Minimal', colors: { primary: '#18181b', secondary: '#71717a', surface: '#ffffff', text: '#09090b', button: '#18181b', success: '#15803d', warning: '#b45309', danger: '#b91c1c' } },
  { name: 'Cyber Dark', tag: 'Dark Mode', colors: { primary: '#38bdf8', secondary: '#818cf8', surface: '#0f172a', text: '#f8fafc', button: '#38bdf8', success: '#34d399', warning: '#fbbf24', danger: '#f87171' } },
]

const POPULAR_FONTS = [
  'Inter', 'Roboto', 'Poppins', 'Open Sans', 'Montserrat', 'Lato', 'Plus Jakarta Sans',
  'Outfit', 'Space Grotesk', 'Playfair Display', 'Merriweather', 'Lora', 'DM Sans',
  'DM Serif Display', 'IBM Plex Sans', 'Nunito', 'Work Sans', 'Syne', 'Cinzel',
  'JetBrains Mono', 'Fira Code',
]

const PAIRINGS = [
  ['Default sans', 'Inter', 'Inter'],
  ['Inter / Inter', 'Inter', 'Inter'],
  ['Poppins / Roboto', 'Poppins', 'Roboto'],
  ['Playfair Display / Lato', 'Playfair Display', 'Lato'],
  ['Space Grotesk / IBM Plex Sans', 'Space Grotesk', 'IBM Plex Sans'],
  ['DM Serif Display / DM Sans', 'DM Serif Display', 'DM Sans'],
  ['Outfit / Outfit', 'Outfit', 'Outfit'],
]

const BLANK = {
  mode: 'theme', slug: '', direction: '', density: 'Comfortable', radius: '12px',
  colors: {}, button: '', headingFont: 'Inter', bodyFont: 'Inter', custom: false,
  appearance: '', border: '', shadow: '', motion: '',
}

function normalizeState(raw = {}) {
  const mode = raw.mode === 'theme' || raw.mode === 'custom' ? raw.mode : raw.slug ? 'theme' : raw.custom ? 'custom' : 'theme'
  const current = { ...raw }
  for (const key of ['icons', 'width', 'nav', 'advanced', 'aiCommands']) delete current[key]
  return {
    ...BLANK, ...current, mode, slug: mode === 'theme' ? (raw.slug || '') : '', custom: mode === 'custom',
    colors: raw.colors && typeof raw.colors === 'object' ? raw.colors : {},
  }
}

function loadGoogleFont(fontName) {
  if (!fontName || typeof document === 'undefined') return
  const clean = fontName.trim()
  if (!clean || clean.toLowerCase() === 'system-ui' || clean.toLowerCase() === 'sans-serif') return
  const id = `gfont-${clean.replace(/\s+/g, '-').toLowerCase()}`
  if (document.getElementById(id)) return
  const link = document.createElement('link')
  link.id = id
  link.rel = 'stylesheet'
  link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(clean)}:wght@400;500;600;700&display=swap`
  document.head.appendChild(link)
}

function designSpecFor(state, theme) {
  const invariant = { source: 'approved-low-fidelity-wireframe-html' }
  if (state.mode === 'theme') {
    return {
      mode: 'theme',
      theme: { slug: state.slug || '', name: theme?.name || '' },
      wireframe: invariant,
    }
  }
  return {
    mode: 'custom',
    theme: { slug: '', name: '' },
    colors: { ...state.colors, button: state.button || '' },
    typography: { heading_font: state.headingFont || '', body_font: state.bodyFont || '' },
    layout: {
      density: state.density || '', radius: state.radius || '', appearance: state.appearance || '',
      border: state.border || '', shadow: state.shadow || '',
    },
    motion: state.motion || '',
    controls: {},
    ai_assist: [],
    direction: state.direction.trim(),
    wireframe: invariant,
  }
}

function stateFromDesignSpec(spec) {
  if (!spec || typeof spec !== 'object') return null
  const theme = spec.theme || {}, colors = spec.colors || {}, type = spec.typography || {}, layout = spec.layout || {}
  const mode = spec.mode || (theme.slug ? 'theme' : 'custom')
  return normalizeState({
    mode, slug: theme.slug || '', colors, button: colors.button || '',
    headingFont: type.heading_font || BLANK.headingFont, bodyFont: type.body_font || BLANK.bodyFont,
    density: layout.density || BLANK.density, radius: layout.radius || BLANK.radius,
    appearance: layout.appearance || '', border: layout.border || '', shadow: layout.shadow || '',
    motion: spec.motion || '',
    direction: spec.direction || '',
  })
}

function composeDirection(state, theme) {
  const lines = []
  if (state.mode === 'theme') {
    if (theme) lines.push(`Selected design theme: ${theme.name} (${theme.slug}). ${theme.description || ''}`)
    return lines.join('\n\n')
  }
  lines.push('Selected custom design:')
  const colors = { ...state.colors, ...(state.button ? { button: state.button } : {}) }
  if (Object.keys(colors).length) lines.push(`Colors: ${Object.entries(colors).map(([k, v]) => `${k} ${v}`).join(', ')}.`)
  lines.push(`Typography: headings ${state.headingFont || 'Inter'}, body ${state.bodyFont || 'Inter'}. Button/global radius ${state.radius}. Density ${state.density}.`)
  const core = [
    state.appearance && `Appearance ${state.appearance}`,
    state.border && `Borders ${state.border}`,
    state.shadow && `Shadows ${state.shadow}`,
    state.motion && `Motion ${state.motion}`,
  ].filter(Boolean)
  if (core.length) lines.push(`Core system: ${core.join('; ')}.`)
  if (state.direction.trim()) lines.push(`Additional customizer prompt: ${state.direction.trim()}`)
  return lines.join('\n')
}

function Swatch({ label, value, fallback = '', onChange }) {
  const shown = value || fallback || DEFAULT_PALETTE[label] || '#2563eb'
  return (
    <label className="flex items-center gap-2 text-xs capitalize text-muted">
      <input type="color" value={shown} onChange={e => onChange(e.target.value)} aria-label={label}
        className="h-7 w-7 cursor-pointer rounded border border-line bg-transparent p-0" />
      <span className="min-w-14 font-medium">{label}</span>
      <code className="text-[11px] text-ink/70 font-mono">{shown}</code>
    </label>
  )
}

function Choice({ label, options, value, onPick, allowClear = true }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
        {label} {!value && <span className="font-normal normal-case text-muted2">default</span>}
      </p>
      <div className="flex flex-wrap gap-2">
        {options.map(option => (
          <button key={option} type="button" onClick={() => onPick(allowClear && value === option ? '' : option)}
            className={`rounded-ctl border px-3 py-1.5 text-xs transition cursor-pointer ${value === option ? 'border-accent bg-accent text-ink font-medium shadow-sm' : 'border-line text-muted hover:text-ink hover:bg-panel2'}`}>
            {option}
          </button>
        ))}
      </div>
    </div>
  )
}

function FontPicker({ label, value, placeholder, catalog, onChange }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return catalog.slice(0, 50)
    return catalog.filter(f => f.toLowerCase().includes(q)).slice(0, 50)
  }, [catalog, query])
  return (
    <div className="relative">
      <div className="mb-1 flex items-center justify-between">
        <label className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</label>
        {value && <span className="max-w-[140px] truncate text-[11px] text-accent">{value}</span>}
      </div>
      <div className="flex items-center gap-1.5">
        <Input value={value} onChange={e => { onChange(e.target.value); setQuery(e.target.value); loadGoogleFont(e.target.value) }}
          onFocus={() => setOpen(true)} placeholder={placeholder}
          className="w-full rounded-lg border border-line bg-panel p-2 text-sm font-normal text-ink" />
        <button type="button" onClick={() => setOpen(v => !v)}
          className="shrink-0 rounded-lg border border-line bg-panel px-2.5 py-2 text-xs text-muted hover:border-accent hover:text-ink">
          <Search className="size-3.5" />
        </button>
      </div>
      {open && <>
        <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
        <div className="absolute left-0 top-full z-40 mt-1 max-h-60 w-full overflow-y-auto rounded-xl border border-line bg-panel p-2 shadow-2xl ring-1 ring-black/20">
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search Google fonts…" autoFocus
            className="mb-2 w-full rounded-md border border-line bg-panel2 px-2.5 py-1.5 text-xs text-ink outline-none" />
          <div className="space-y-0.5">
            {filtered.map(font => <button key={font} type="button" onClick={() => { onChange(font); loadGoogleFont(font); setOpen(false) }}
              className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-xs ${value === font ? 'bg-accent font-semibold text-ink' : 'text-ink hover:bg-panel2'}`}>
              <span style={{ fontFamily: font }}>{font}</span>{value === font && <Check className="size-3 shrink-0" />}
            </button>)}
            {!filtered.length && <p className="py-3 text-center text-xs text-muted">No fonts match “{query}”</p>}
          </div>
        </div>
      </>}
    </div>
  )
}




function SiteImages({ projectId }) {
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState('')
  const [draft, setDraft] = useState({})

  useEffect(() => {
    if (!projectId) return
    let open = true
    api.siteImages(projectId).then(answer => { if (open) setRows(answer?.images || []) }).catch(() => {})
    return () => { open = false }
  }, [projectId])

  async function add(files, purpose = '') {
    const picked = [...(files || [])]
    if (!picked.length || !projectId) return
    setBusy(true); setProblem('')
    try {
      let answer = null
      for (const file of picked) {
        try { answer = await api.siteImageSave(projectId, file, purpose) }
        catch (failure) { setProblem(`${file.name}: ${failure?.message || 'could not be uploaded'}`) }
      }
      if (answer?.images) setRows(answer.images)
    } finally { setBusy(false) }
  }

  async function describe(file, purpose) {
    setDraft(prev => ({ ...prev, [file]: undefined }))
    try { const answer = await api.siteImageDescribe(projectId, file, purpose); if (answer?.images) setRows(answer.images) }
    catch (failure) { setProblem(failure?.message || 'That note could not be saved.') }
  }
  async function drop(file) {
    try { const answer = await api.siteImageDrop(projectId, file); setRows(answer?.images || []) }
    catch (failure) { setProblem(failure?.message || 'That image could not be removed.') }
  }

  const unexplained = rows.filter(row => !row.purpose).length
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="mr-auto"><p className="text-xs font-semibold uppercase tracking-wide text-muted">Brand & site images</p><p className="mt-1 text-[11px] text-muted2">Saved in the project’s media/ folder; names and usage notes are kept in media/IMAGES.md for prototype and build.</p></div>
        {[['Upload logo', 'Brand logo'], ['Upload favicon', 'Favicon'], [rows.length ? 'Add images' : 'Upload images', '']].map(([label, purpose]) => <label key={label} className={`cursor-pointer rounded-ctl border border-line px-3 py-1.5 text-xs text-muted transition hover:text-ink ${busy ? 'opacity-50' : ''}`}>{label}<input type="file" accept="image/*" multiple={!purpose} className="hidden" disabled={busy || !projectId} onChange={e => { add(e.target.files, purpose); e.target.value = '' }} /></label>)}
      </div>
      <p className="mb-2 text-[11px] text-muted2">{rows.length ? `${rows.length} image${rows.length === 1 ? '' : 's'}${unexplained ? ` · ${unexplained} with no usage note` : ''}` : 'No images uploaded yet.'}</p>
      {rows.length > 0 && <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(150px,1fr))]">{rows.map(row => <div key={row.file} className="overflow-hidden rounded-lg border border-line bg-panel"><img src={api.siteImageUrl(projectId, row.file)} alt={row.purpose || row.file} className="h-24 w-full border-b border-line bg-panel2 object-contain" /><div className="space-y-1.5 p-2"><div className="flex items-baseline justify-between gap-2"><code className="truncate text-[10px] text-ink/70" title={row.file}>{row.file}</code><button type="button" onClick={() => drop(row.file)} className="shrink-0 text-[10px] text-muted underline hover:text-ink">remove</button></div><code className="block truncate text-[10px] text-muted2" title={row.path}>{row.path}</code><Input value={draft[row.file] ?? row.purpose} onChange={e => setDraft(prev => ({ ...prev, [row.file]: e.target.value }))} onBlur={e => e.target.value !== row.purpose && describe(row.file, e.target.value)} onKeyDown={e => e.key === 'Enter' && e.currentTarget.blur()} placeholder="What is this for?" className="w-full rounded border border-line bg-panel2 px-2 py-1 text-[11px]" /></div></div>)}</div>}
      {problem && <p role="alert" className="mt-2 text-[11px] text-bad">{problem}</p>}
    </div>
  )
}

function ThemeCard({ theme, selected, onOpen }) {
  return <button type="button" onClick={onOpen} className={`group overflow-hidden rounded-xl border text-left transition ${selected ? 'border-accent ring-2 ring-accent shadow-md' : 'border-line hover:border-accent/60'}`}>
    <span className="block aspect-[16/10] overflow-hidden bg-panel2">{theme.hasPreview ? <img src={`${ASSETS}/${theme.slug}.png`} alt="" loading="lazy" className="h-full w-full object-cover object-top transition group-hover:scale-[1.03]" /> : <span className="flex h-full items-center justify-center text-xs text-muted">No preview</span>}</span>
    <span className="flex items-center justify-between gap-2 px-3 py-2"><span className="truncate text-sm font-medium text-ink">{theme.name}</span><span className="flex shrink-0 gap-1">{SWATCHES.map(key => theme.colors?.[key] && <span key={key} className="h-3 w-3 rounded-full border border-line" style={{ background: theme.colors[key] }} />)}</span></span>
  </button>
}

export default function DesignCustomize({ projectId, onContinue, onBack }) {
  const [srsId, setSrsId] = useState(/^prj_/.test(projectId || '') ? projectId : '')
  const [themes, setThemes] = useState([])
  const [query, setQuery] = useState('')
  const [preview, setPreview] = useState(null)
  const [screen, setScreen] = useState('choice')
  const [customizerOpen, setCustomizerOpen] = useState(false)
  const [live, setLive] = useState({ slug: '', drawing: false, error: '' })
  const [fontCatalog, setFontCatalog] = useState(POPULAR_FONTS)
  const [state, setState] = useState(BLANK)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`${ASSETS}/themes.json`).then(r => r.ok ? r.json() : {}).then(data => setThemes(Object.values(data))).catch(() => setThemes([]))
  }, [])

  useEffect(() => {
    let active = true
    fetch('https://cdn.jsdelivr.net/gh/hasinhayder/google-fonts/fonts.json').then(r => r.ok ? r.json() : null).then(data => { if (active && Array.isArray(data?.fonts)) setFontCatalog(data.fonts) }).catch(() => {})
    return () => { active = false }
  }, [])

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(`agentforge-design-${projectId}`) || '{}')
      const normalized = normalizeState(saved)
      setState(normalized)
      loadGoogleFont(normalized.headingFont); loadGoogleFont(normalized.bodyFont)
    } catch {}
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    if (/^prj_/.test(projectId)) { setSrsId(projectId); return }
    let active = true
    setSrsId('')
    api.srsResults(projectId).then(answer => {
      if (active) setSrsId(answer?.link?.srs_id || '')
    }).catch(() => { if (active) setSrsId('') })
    return () => { active = false }
  }, [projectId])

  // Server copy wins over a browser-only draft once a Design Spec has been approved.
  useEffect(() => {
    if (!srsId) return
    let active = true
    api.designSpec(srsId).then(answer => {
      const restored = stateFromDesignSpec(answer?.current?.spec)
      if (!active || !restored) return
      setState(restored)
      try { localStorage.setItem(`agentforge-design-${projectId}`, JSON.stringify(restored)) } catch {}
      loadGoogleFont(restored.headingFont); loadGoogleFont(restored.bodyFont)
    }).catch(() => {})
    return () => { active = false }
  }, [projectId, srsId])

  useEffect(() => {
    const slug = preview?.slug
    if (!slug || live.drawing || live.slug === slug) return
    let open = true
    fetch(`${LIVE}/${encodeURIComponent(slug)}`, { method: 'GET' }).then(answer => { if (open && answer.ok) setLive({ slug, drawing: false, error: '' }) }).catch(() => {})
    return () => { open = false }
  }, [preview, live.drawing, live.slug])

  function save(patch) {
    setState(prev => {
      const next = normalizeState({ ...prev, ...patch })
      try { localStorage.setItem(`agentforge-design-${projectId}`, JSON.stringify(next)) } catch {}
      return next
    })
  }

  const theme = useMemo(() => themes.find(item => item.slug === state.slug) || null, [themes, state.slug])
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? themes.filter(item => `${item.name} ${item.description}`.toLowerCase().includes(q)) : themes
  }, [themes, query])

  function switchMode(mode) {
    save({ mode, custom: mode === 'custom', slug: mode === 'custom' ? '' : state.slug })
    setError('')
  }

  function openThemes() {
    switchMode('theme')
    setScreen('themes')
  }

  function openCustomizer() {
    switchMode('custom')
    setCustomizerOpen(true)
  }

  function choose(picked) {
    save({ mode: 'theme', slug: picked.slug, custom: false })
    setPreview(null)
    setScreen('choice')
  }

  async function draw(slug) {
    if (live.drawing) return
    setLive({ slug: '', drawing: true, error: '' })
    let refused = ''
    api.drawThemePreview(slug, '').catch(failure => { refused = failure?.message || '' })
    const deadline = Date.now() + 240000
    while (Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 2000))
      try {
        if ((await fetch(`${LIVE}/${encodeURIComponent(slug)}`, { method: 'GET' })).ok) { setLive({ slug, drawing: false, error: '' }); return }
      } catch {}
    }
    setLive({ slug: '', drawing: false, error: refused || 'The preview took too long to draw.' })
  }

  async function apply() {
    if (saving) return
    if (state.mode === 'theme' && !theme) { setError('Choose a theme or switch to custom design.'); return }
    setSaving(true); setError('')
    try { await onContinue({ direction: composeDirection(state, theme), designSpec: designSpecFor(state, theme) }) }
    catch (failure) { setError(failure.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto px-2.5 py-4 sm:px-4 sm:py-5 lg:px-5">
      <section className="mx-auto w-full max-w-[1680px] shrink-0 rounded-2xl border border-line bg-panel p-4 text-ink shadow-2xl ring-1 ring-white/10 sm:p-5 lg:p-6">
        <p className="text-xs font-semibold text-accent">SRS approved · Designer</p>
        <h1 className="mt-2 text-2xl font-semibold">Choose one design path</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted">Choose a theme or customize the look. Your approved wireframes and design choices will guide the prototype.</p>

        {screen === 'choice' ? <>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <button type="button" onClick={openThemes} className={`group min-h-48 rounded-2xl border p-6 text-left transition ${state.mode === 'theme' ? 'border-accent bg-accent/10 ring-1 ring-accent' : 'border-line bg-panel2 hover:border-accent/50 hover:bg-panel'}`}>
              <span className="grid size-11 place-items-center rounded-xl bg-accent text-ink"><Palette className="size-5" /></span>
              <span className="mt-5 flex items-center justify-between gap-3"><span className="text-lg font-semibold">Select design theme</span>{state.mode === 'theme' && theme && <Check className="size-5 text-accent" />}</span>
              <span className="mt-2 block text-sm text-muted">Browse the design-theme grid, inspect a theme, then select it from its preview.</span>
              <span className="mt-5 inline-flex text-xs font-semibold text-accent">Browse themes →</span>
            </button>
            <button type="button" onClick={openCustomizer} className={`group min-h-48 rounded-2xl border p-6 text-left transition ${state.mode === 'custom' ? 'border-accent bg-accent/10 ring-1 ring-accent' : 'border-line bg-panel2 hover:border-accent/50 hover:bg-panel'}`}>
              <span className="grid size-11 place-items-center rounded-xl bg-accent text-ink"><Wand2 className="size-5" /></span>
              <span className="mt-5 flex items-center justify-between gap-3"><span className="text-lg font-semibold">Customize design</span>{state.mode === 'custom' && <Check className="size-5 text-accent" />}</span>
              <span className="mt-2 block text-sm text-muted">Open the full design workspace to set color, type, layout, motion and visual direction.</span>
              <span className="mt-5 inline-flex text-xs font-semibold text-accent">Open customizer →</span>
            </button>
          </div>
          <div className="mt-4 rounded-xl border border-line bg-panel2 px-4 py-3 text-sm text-muted">
            {state.mode === 'theme' && theme ? <><strong className="text-ink">Selected theme:</strong> {theme.name}. Click the card above to change it.</>
              : state.mode === 'custom' ? <><strong className="text-ink">Selected path:</strong> Custom design. Click Customize design to continue editing it.</>
                : 'Choose one path. Only the approved choice is sent to the prototype.'}
          </div>
        </> : <div className="mt-5 flex items-center justify-between gap-4 rounded-xl border border-line bg-panel2 px-4 py-3"><div><p className="font-semibold">Design themes</p><p className="mt-0.5 text-xs text-muted">Open a card to inspect it, then select it from the preview.</p></div><Button variant="outline" size="sm" onClick={() => setScreen('choice')}><ArrowLeft className="size-3.5" /> Design paths</Button></div>}

        <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3.5 py-2.5 text-xs text-muted">The prototype will read the approved wireframe HTML, the one selected design path, and any extra visual direction you add here.</div>

        {screen === 'themes' && <>
          <div className="mt-6 flex flex-wrap items-center gap-3"><Input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search themes…" className="w-full max-w-xs rounded-lg border border-line bg-panel2 p-2 text-sm" /><span className="text-xs text-muted">{shown.length} of {themes.length}</span>{state.slug && <button type="button" onClick={() => save({ slug: '' })} className="ml-auto text-xs text-muted underline hover:text-ink">Clear theme</button>}</div>
          <div className="mt-4 grid max-h-[48vh] grid-cols-2 gap-3 overflow-y-auto pr-1 sm:grid-cols-3 lg:grid-cols-4">{shown.map(item => <ThemeCard key={item.slug} theme={item} selected={item.slug === state.slug} onOpen={() => { setPreview(item); setLive({ slug: '', drawing: false, error: '' }) }} />)}{!themes.length && <p className="col-span-full py-8 text-center text-sm text-muted">Loading themes…</p>}</div>
        </>}

        {customizerOpen && <Modal
          onClose={() => setCustomizerOpen(false)}
          overlayClassName="!p-0 backdrop-blur-none"
          style={{ maxWidth: 'none', width: '100%', height: '100%', maxHeight: '100%' }}
          className="overflow-hidden rounded-none border-0 p-0"
        ><div className="flex h-full min-h-0 flex-col bg-[#F2F0EF] text-ink"><header className="flex shrink-0 items-center justify-between gap-4 border-b border-line bg-panel px-5 py-3"><div><p className="text-xs font-semibold text-accent">Design customizer</p><h2 className="mt-0.5 text-lg font-semibold">Build the visual system</h2></div><div className="flex items-center gap-2"><Button variant="outline" size="sm" onClick={() => setCustomizerOpen(false)}>Close</Button><Button size="sm" onClick={() => { save({ mode: 'custom', custom: true, slug: '' }); setCustomizerOpen(false) }}>Use custom design</Button></div></header><div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5"><div className="mx-auto max-w-[1680px] space-y-5">
          <div className="design-customize-workspace grid min-w-0 gap-4">
            <aside className="design-customize-sidebar min-w-0 space-y-4">
              <div className="rounded-xl border border-line bg-panel2 p-4">
                <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Sparkles className="size-3.5 text-accent" /> 1-click color mood presets</p>
                <div className="grid grid-cols-2 gap-2">{COLOR_PRESETS.map(preset => <button key={preset.name} type="button" onClick={() => save({ colors: { ...preset.colors }, button: preset.colors.button })} className="rounded-xl border border-line bg-panel p-2.5 text-left transition hover:border-accent"><div className="flex items-center justify-between gap-2"><span className="truncate text-xs font-semibold">{preset.name}</span><span className="text-[9px] text-muted2">{preset.tag}</span></div><div className="mt-1.5 flex h-3 overflow-hidden rounded border border-line/60"><span className="flex-1" style={{ background: preset.colors.primary }} /><span className="flex-1" style={{ background: preset.colors.secondary }} /><span className="flex-1" style={{ background: preset.colors.surface }} /><span className="flex-1" style={{ background: preset.colors.button }} /><span className="flex-1" style={{ background: preset.colors.success }} /></div></button>)}</div>
              </div>

              <div className="rounded-xl border border-line bg-panel2 p-4 space-y-4"><p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted"><Palette className="size-3.5 text-accent" /> Colors & appearance</p><div className="grid gap-3 sm:grid-cols-2">{SWATCHES.map(key => <Swatch key={key} label={key} value={state.colors[key]} onChange={value => save({ colors: { ...state.colors, [key]: value } })} />)}<Swatch label="button" value={state.button} onChange={value => save({ button: value })} />{STATUS_SWATCHES.map(key => <Swatch key={key} label={key} value={state.colors[key]} onChange={value => save({ colors: { ...state.colors, [key]: value } })} />)}</div><div className="grid gap-4 border-t border-line/60 pt-4 sm:grid-cols-2"><Choice label="Appearance" options={APPEARANCES} value={state.appearance} onPick={value => save({ appearance: value })} /><Choice label="Borders" options={BORDERS} value={state.border} onPick={value => save({ border: value })} /><Choice label="Shadows" options={SHADOWS} value={state.shadow} onPick={value => save({ shadow: value })} /></div></div>

              <div className="rounded-xl border border-line bg-panel2 p-4 space-y-4"><p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted"><Type className="size-3.5 text-accent" /> Typography & core layout</p><label className="block text-xs font-semibold uppercase tracking-wide text-muted">Quick Font Pairing<select value={PAIRINGS.some(([, h, b]) => h === state.headingFont && b === state.bodyFont) ? `${state.headingFont}|${state.bodyFont}` : 'custom'} onChange={e => { if (e.target.value === 'custom') return; const [heading, body] = e.target.value.split('|'); loadGoogleFont(heading); loadGoogleFont(body); save({ headingFont: heading, bodyFont: body }) }} className="mt-1.5 block w-full rounded-lg border border-line bg-panel p-2 text-sm font-normal text-ink outline-none">{PAIRINGS.map(([label, heading, body]) => <option key={label} value={`${heading}|${body}`}>{label}</option>)}<option value="custom">Custom (search below)</option></select></label><div className="grid gap-3 sm:grid-cols-2"><FontPicker label="Heading font" value={state.headingFont} placeholder="e.g. Playfair Display" catalog={fontCatalog} onChange={value => save({ headingFont: value })} /><FontPicker label="Body font" value={state.bodyFont} placeholder="e.g. Inter" catalog={fontCatalog} onChange={value => save({ bodyFont: value })} /></div><div className="border-t border-line/60 pt-4"><Choice label="Button corners" options={RADII.map(([label]) => label)} value={(RADII.find(([, value]) => value === state.radius) || [])[0] || ''} onPick={label => save({ radius: (RADII.find(([name]) => name === label) || [, '12px'])[1] })} allowClear={false} /></div><label className="block text-xs font-semibold uppercase tracking-wide text-muted">Spacing & Density<select value={state.density} onChange={e => save({ density: e.target.value })} className="mt-1.5 block w-full rounded-lg border border-line bg-panel p-2 text-sm font-normal text-ink outline-none">{DENSITIES.map(value => <option key={value}>{value}</option>)}</select></label><Choice label="Motion" options={MOTIONS} value={state.motion} onPick={value => save({ motion: value })} /></div>

            </aside>
            <div className="min-w-0"><div className="sticky top-3"><WireframeStylePreview projectId={srsId} imageOwner={projectId} state={state} /></div></div>
          </div>

          <label className="block text-sm font-medium">Anything else about the custom look and feel<TextArea value={state.direction} onChange={e => save({ direction: e.target.value })} rows={3} placeholder="Reference sites, imagery, tone, specific UI rules…" className="mt-2 w-full rounded-lg border border-line bg-panel2 p-3 text-ink" /></label>
        </div></div></div></Modal>}

        <div className="mt-6 rounded-xl border border-line bg-panel2 p-5"><SiteImages projectId={projectId} /></div>
        {error && <p role="alert" className="mt-3 text-sm text-bad">{error}</p>}
        <div className="mt-6 flex justify-between gap-3"><Button variant="outline" onClick={onBack}>Back to wireframes</Button><Button disabled={saving} onClick={apply}>{saving ? 'Applying design…' : 'Approve design → Generate prototype'}</Button></div>

        {preview && <Modal onClose={() => setPreview(null)} className="max-w-3xl overflow-hidden p-0"><div className="flex items-start justify-between gap-4 border-b border-line p-4"><div><h2 className="text-lg font-semibold">{preview.name}</h2><p className="mt-1 max-w-xl text-sm text-muted">{preview.description}</p></div><Button onClick={() => choose(preview)}>{preview.slug === state.slug ? 'Selected' : 'Use this theme'}</Button></div>{live.slug === preview.slug ? <iframe title={`${preview.name} live preview`} src={`${LIVE}/${preview.slug}`} className="h-[60vh] w-full border-0 bg-white" /> : preview.hasPreview ? <div className="max-h-[60vh] overflow-y-auto bg-panel2"><img src={`${ASSETS}/${preview.slug}.png`} alt={`${preview.name} preview`} className="w-full" /></div> : <p className="flex h-40 items-center justify-center bg-panel2 text-sm text-muted">No screenshot for this theme — draw a live page to see it.</p>}<div className="flex flex-wrap gap-5 border-t border-line p-4 text-xs text-muted"><span className="flex items-center gap-2">{SWATCHES.map(key => preview.colors?.[key] && <span key={key} title={`${key} ${preview.colors[key]}`} className="h-4 w-4 rounded-full border border-line" style={{ background: preview.colors[key] }} />)}</span>{preview.fonts?.length > 0 && <span>Fonts: {preview.fonts.join(', ')}</span>}<span className="ml-auto flex items-center gap-3">{live.error && <span role="alert" className="text-bad">{live.error}</span>}<button type="button" onClick={() => draw(preview.slug)} disabled={live.drawing} className="text-accent underline disabled:opacity-50">{live.drawing ? 'Drawing…' : live.slug === preview.slug ? 'Redraw live page' : 'Live preview'}</button></span></div></Modal>}

      </section>
    </div>
  )
}
