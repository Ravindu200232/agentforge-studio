'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, Check, Heart, ImagePlus, Loader2, Sparkles, Upload, X } from 'lucide-react'
import { api } from '@/lib/api'
import { Button, Modal } from './ui'

const PALETTES = [
  { id: 'pastel', name: 'Pastel', group: 'Pastel', colors: ['#a14646', '#da6556', '#eb895b', '#fdb773'] },
  { id: 'violet', name: 'Violet bloom', group: 'Popular', colors: ['#8c1cab', '#bd51c8', '#df89d1', '#f7b0d3'] },
  { id: 'heritage', name: 'Heritage', group: 'Vintage', colors: ['#8f0b14', '#e5d1aa', '#f5f1e8', '#a9c0d1'] },
  { id: 'gold', name: 'Golden hour', group: 'Warm', colors: ['#ffe8a3', '#f6b000', '#ce7200', '#593000'] },
  { id: 'garden', name: 'Garden', group: 'Nature', colors: ['#87a66b', '#bf3333', '#ff9d4d', '#fff09b'] },
  { id: 'berry', name: 'Berry pop', group: 'Popular', colors: ['#e91547', '#dca5bc', '#f1ead2', '#eccf21'] },
  { id: 'midnight', name: 'Midnight', group: 'Dark', colors: ['#020202', '#8c0505', '#d00000', '#ff1008'] },
  { id: 'peach', name: 'Peach cream', group: 'Pastel', colors: ['#fff7c8', '#ffd19e', '#ffc0af', '#f8a0a4'] },
  { id: 'ocean', name: 'Ocean blue', group: 'Cold', colors: ['#102a43', '#1d70a2', '#2f80ed', '#9ed5ff'] },
  { id: 'clay', name: 'Terracotta', group: 'Earth', colors: ['#5a3020', '#b65f3b', '#df9561', '#f3d3af'] },
  { id: 'forest', name: 'Forest', group: 'Nature', colors: ['#12372a', '#436850', '#a3bc9f', '#f1f8e8'] },
  { id: 'neon', name: 'Neon dusk', group: 'Neon', colors: ['#130f40', '#6c2bd9', '#ed3b9d', '#ffbd59'] },
  { id: 'summer', name: 'Summer punch', group: 'Summer', colors: ['#ff5d5d', '#ff9f1c', '#ffe66d', '#4ecdc4'] },
  { id: 'seafoam', name: 'Seafoam', group: 'Cold', colors: ['#003049', '#0077b6', '#90e0ef', '#caf0f8'] },
  { id: 'coffee', name: 'Coffee house', group: 'Earth', colors: ['#38220f', '#7b4f2c', '#b6895b', '#f3e5c8'] },
  { id: 'lavender', name: 'Lavender sky', group: 'Pastel', colors: ['#5b4b8a', '#8b7fba', '#c8b6e2', '#f4ecff'] },
  { id: 'citrus', name: 'Citrus pop', group: 'Warm', colors: ['#245501', '#8cc63f', '#f7e733', '#ffb703'] },
  { id: 'rosewood', name: 'Rosewood', group: 'Vintage', colors: ['#4a0e0e', '#8d2b2b', '#d26a6a', '#f5d0c5'] },
  { id: 'arctic', name: 'Arctic light', group: 'Light', colors: ['#eaf6ff', '#b9e6ff', '#6cb6e5', '#2b6cb0'] },
  { id: 'plum', name: 'Plum night', group: 'Dark', colors: ['#1f102f', '#54236e', '#a43ca7', '#f3a9d2'] },
  { id: 'coral', name: 'Coral reef', group: 'Summer', colors: ['#003b46', '#07575b', '#66a5ad', '#c4dfe6'] },
  { id: 'spring', name: 'Spring field', group: 'Nature', colors: ['#1b4332', '#52b788', '#b7e4c7', '#f1faee'] },
  { id: 'retro', name: 'Retro arcade', group: 'Retro', colors: ['#202040', '#543864', '#ff6363', '#ffa600'] },
  { id: 'sherbet', name: 'Sherbet', group: 'Pastel', colors: ['#f9c5d1', '#f999b7', '#b3e5fc', '#fdfd96'] },
  { id: 'ink', name: 'Ink and paper', group: 'Dark', colors: ['#0c0c0c', '#313131', '#d0d0d0', '#f6f1e9'] },
  { id: 'sunset', name: 'Sunset route', group: 'Warm', colors: ['#5e1b89', '#f15bb5', '#fee440', '#00bbf9'] },
  { id: 'moss', name: 'Moss stone', group: 'Earth', colors: ['#344e41', '#588157', '#a3b18a', '#dad7cd'] },
  { id: 'galaxy', name: 'Galaxy', group: 'Neon', colors: ['#10002b', '#3c096c', '#7b2cbf', '#c77dff'] },
  { id: 'blueprint', name: 'Blueprint', group: 'Cold', colors: ['#001f3f', '#0074d9', '#7fdbff', '#ffffff'] },
  { id: 'cinnamon', name: 'Cinnamon', group: 'Vintage', colors: ['#542f0a', '#9e5a24', '#dba159', '#fff0d2'] },
  { id: 'aurora', name: 'Aurora', group: 'Popular', colors: ['#001219', '#005f73', '#0a9396', '#94d2bd'] },
  { id: 'bubblegum', name: 'Bubblegum', group: 'Neon', colors: ['#ff006e', '#fb5607', '#ffbe0b', '#8338ec'] },
]

const GROUPS = ['All', 'Popular', 'Pastel', 'Vintage', 'Retro', 'Neon', 'Warm', 'Cold', 'Nature', 'Earth', 'Light', 'Dark', 'Summer']

// These families are served on demand through the Google Fonts CSS API. Keeping
// the popular catalogue locally means the picker is fast and needs no API key.
const FONT_OPTIONS = [
  'ABeeZee', 'Abril Fatface', 'Acme', 'Alata', 'Albert Sans', 'Alegreya', 'Alegreya Sans', 'Alex Brush', 'Alfa Slab One', 'Amatic SC',
  'Anton', 'Archivo', 'Archivo Black', 'Archivo Narrow', 'Arimo', 'Arsenal', 'Asap', 'Assistant', 'B612', 'Bebas Neue',
  'Bitter', 'Bodoni Moda', 'Cabin', 'Cairo', 'Candal', 'Cardo', 'Chakra Petch', 'Cinzel', 'Comfortaa', 'Cormorant Garamond',
  'Courier Prime', 'Crimson Pro', 'DM Mono', 'DM Sans', 'DM Serif Display', 'Dancing Script', 'Dela Gothic One', 'Domine', 'EB Garamond', 'Exo 2',
  'Figtree', 'Fira Code', 'Fira Sans', 'Fjalla One', 'Francois One', 'Fraunces', 'Gabarito', 'Geist', 'Great Vibes', 'IBM Plex Mono',
  'IBM Plex Sans', 'IBM Plex Serif', 'Inconsolata', 'Indie Flower', 'Instrument Sans', 'Inter', 'Josefin Sans', 'Jost', 'Karla', 'Khand',
  'Lato', 'League Spartan', 'Lexend', 'Libre Baskerville', 'Libre Franklin', 'Lilita One', 'Lobster', 'Lora', 'Manrope', 'Merriweather',
  'Merriweather Sans', 'Montserrat', 'Mukta', 'Mulish', 'Noto Sans', 'Noto Serif', 'Nunito', 'Nunito Sans', 'Open Sans', 'Oswald',
  'Outfit', 'Overpass', 'Pacifico', 'Permanent Marker', 'Playfair Display', 'Plus Jakarta Sans', 'Poppins', 'PT Sans', 'PT Serif', 'Public Sans',
  'Quicksand', 'Raleway', 'Red Hat Display', 'Red Hat Text', 'Roboto', 'Roboto Condensed', 'Roboto Mono', 'Roboto Slab', 'Rubik', 'Satisfy',
  'Sen', 'Shadows Into Light', 'Signika', 'Source Code Pro', 'Source Sans 3', 'Space Grotesk', 'Space Mono', 'Spectral', 'Teko', 'Titillium Web',
  'Ubuntu', 'Ubuntu Mono', 'Unbounded', 'Varela Round', 'Work Sans', 'Yanone Kaffeesatz', 'Zilla Slab',
]
const COLOR_LABELS = ['Primary', 'Secondary', 'Accent', 'Surface']
const EMPTY = { palette: 'pastel', colors: PALETTES[0].colors, headingFont: 'Plus Jakarta Sans', bodyFont: 'DM Sans', prompt: '', images: [] }
const ACCEPT_IMAGES = '.png,.jpg,.jpeg,.webp,.gif,.svg,image/*'

function paletteFor(id) {
  return PALETTES.find(item => item.id === id) || PALETTES[0]
}

function isHex(value) {
  return /^#[0-9a-f]{6}$/i.test(String(value || ''))
}

function colorsFor(value, fallback) {
  return Array.isArray(value) && value.length === 4 && value.every(isHex) ? value : fallback
}

function fontStack(font) {
  return `"${font}", ui-sans-serif, system-ui, sans-serif`
}

function loadGoogleFont(font) {
  if (!font || typeof document === 'undefined') return
  const id = `google-font-${font.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
  if (document.getElementById(id)) return
  const link = document.createElement('link')
  link.id = id
  link.rel = 'stylesheet'
  link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(font).replace(/%20/g, '+')}&display=swap`
  document.head.appendChild(link)
}

function normalize(raw = {}) {
  const palette = paletteFor(raw.palette)
  return {
    ...EMPTY,
    palette: PALETTES.some(item => item.id === raw.palette) ? raw.palette : EMPTY.palette,
    colors: colorsFor(raw.colors, palette.colors),
    headingFont: FONT_OPTIONS.includes(raw.headingFont) ? raw.headingFont : EMPTY.headingFont,
    bodyFont: FONT_OPTIONS.includes(raw.bodyFont) ? raw.bodyFont : EMPTY.bodyFont,
    prompt: typeof raw.prompt === 'string' ? raw.prompt : '',
    images: Array.isArray(raw.images) ? raw.images : [],
  }
}

function directionFor(state) {
  const palette = paletteFor(state.palette)
  const note = state.prompt.trim()
  return [
    `Use the selected ${palette.name} colour theme: ${state.colors.join(', ')}.`,
    `Use ${state.headingFont} for headings and ${state.bodyFont} for body text.`,
    note && `Customer design direction: ${note}`,
    state.images.length && `Use the ${state.images.length} uploaded reference image${state.images.length === 1 ? '' : 's'} where appropriate.`,
  ].filter(Boolean).join('\n')
}

function specFor(state) {
  const palette = paletteFor(state.palette)
  return {
    mode: 'theme',
    theme: { slug: palette.id, title: palette.name },
    summary: [`${palette.name} palette selected`, state.prompt.trim() || 'No extra design direction'],
    tokens: {
      colors: { primary: state.colors[0], secondary: state.colors[1], accent: state.colors[2], surface: state.colors[3] },
      typography: { heading_font: state.headingFont, body_font: state.bodyFont },
      layout: { source: 'design-customizer-palette' },
    },
    customizer_prompt: state.prompt.trim(),
    reference_images: state.images.map(image => ({ file: image.file, purpose: image.purpose || 'Design reference' })),
  }
}

function PaletteCard({ palette, selected, onPick }) {
  return <button type="button" onClick={() => onPick(palette)} aria-pressed={selected}
    className={`group overflow-hidden rounded-2xl border text-left transition ${selected ? 'border-accent ring-2 ring-accent/35' : 'border-line hover:-translate-y-0.5 hover:border-line2'}`}>
    <span className="block overflow-hidden rounded-[14px] bg-panel">
      {palette.colors.map((color, index) => <i key={color} className="block h-10 sm:h-12" style={{ background: color, borderTop: index ? '1px solid rgba(255,255,255,.08)' : 'none' }} />)}
    </span>
    <span className="flex items-center justify-between gap-2 px-2.5 py-2">
      <span className="truncate text-[11px] font-semibold text-ink">{palette.name}</span>
      <Heart className={`size-3.5 ${selected ? 'fill-accent text-accent' : 'text-muted2 group-hover:text-accent'}`} />
    </span>
  </button>
}

export default function DesignCustomize({ projectId, onContinue, onBack }) {
  const [state, setState] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [group, setGroup] = useState('All')
  const [step, setStep] = useState(0)
  const [paletteDialog, setPaletteDialog] = useState(null)
  const [draftColors, setDraftColors] = useState([])
  const [fontTarget, setFontTarget] = useState('heading')
  const [fontQuery, setFontQuery] = useState('')
  const [pendingImage, setPendingImage] = useState(null)
  const [imagePurpose, setImagePurpose] = useState('')
  const picker = useRef(null)

  useEffect(() => {
    try { setState(normalize(JSON.parse(localStorage.getItem(`agentforge-design-${projectId}`) || '{}'))) } catch { setState(EMPTY) }
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    let active = true
    api.siteImages(projectId).then(answer => {
      if (!active || !answer?.images?.length) return
      setState(previous => normalize({ ...previous, images: answer.images }))
    }).catch(() => {})
    return () => { active = false }
  }, [projectId])

  useEffect(() => {
    loadGoogleFont(state.headingFont)
    loadGoogleFont(state.bodyFont)
  }, [state.headingFont, state.bodyFont])

  function save(patch) {
    setState(previous => {
      const next = normalize({ ...previous, ...patch })
      try { localStorage.setItem(`agentforge-design-${projectId}`, JSON.stringify(next)) } catch {}
      return next
    })
  }

  function requestImage(file) {
    if (!file || uploading) return
    if (!String(file.type || '').startsWith('image/')) {
      setError('Choose a PNG, JPEG, WebP, GIF or SVG image.')
      return
    }
    setError('')
    setPendingImage(file)
    setImagePurpose('')
  }

  async function addImage(file, purpose) {
    if (!file || uploading) return
    if (!String(file.type || '').startsWith('image/')) {
      setError('Choose a PNG, JPEG, WebP, GIF or SVG image.')
      return
    }
    setUploading(true); setError('')
    try {
      const answer = await api.siteImageSave(projectId, file, purpose.trim() || 'Design reference image')
      save({ images: answer?.images || [...state.images, answer?.image].filter(Boolean) })
      setPendingImage(null)
    } catch (failure) { setError(failure?.message || 'The image could not be uploaded.') }
    finally { setUploading(false) }
  }

  async function removeImage(file) {
    if (!file) return
    setError('')
    try {
      // Dropping an image removes both its manifest entry and its project-media
      // file, so it cannot appear again after visiting another design step.
      const answer = await api.siteImageDrop(projectId, file)
      save({ images: answer?.images || state.images.filter(image => image.file !== file) })
    } catch (failure) {
      setError(failure?.message || 'The image could not be removed.')
    }
  }

  function openPalette(palette) {
    setPaletteDialog(palette)
    setDraftColors([...palette.colors])
  }

  function updateDraftColor(index, value) {
    if (!isHex(value)) return
    const colors = [...draftColors]
    colors[index] = value.toUpperCase()
    setDraftColors(colors)
  }

  function applyPalette() {
    if (!paletteDialog || draftColors.length !== 4) return
    save({ palette: paletteDialog.id, colors: draftColors })
    setPaletteDialog(null)
  }

  function chooseFont(font) {
    save(fontTarget === 'heading' ? { headingFont: font } : { bodyFont: font })
  }

  async function approve() {
    if (saving) return
    setSaving(true); setError('')
    try { await onContinue({ direction: directionFor(state), designSpec: specFor(state) }) }
    catch (failure) { setError(failure?.message || 'The design could not be approved.') }
    finally { setSaving(false) }
  }

  const selected = useMemo(() => paletteFor(state.palette), [state.palette])
  const shownPalettes = useMemo(() => group === 'All' ? PALETTES : PALETTES.filter(palette => palette.group === group), [group])
  const shownFonts = useMemo(() => FONT_OPTIONS.filter(font => font.toLowerCase().includes(fontQuery.trim().toLowerCase())), [fontQuery])
  const currentFont = fontTarget === 'heading' ? state.headingFont : state.bodyFont
  const stepCopy = [
    { eyebrow: 'Step 1 of 4', title: 'Choose your colours', text: 'Choose a palette, open it, then adjust all four colours in the editor.' },
    { eyebrow: 'Step 2 of 4', title: 'Choose your typography', text: 'Pick separate Google Fonts for headings and body text, with a live sample.' },
    { eyebrow: 'Step 3 of 4', title: 'Upload image references', text: 'Add images that the prototype can use as visual references.' },
    { eyebrow: 'Step 4 of 4', title: 'Add a design brief', text: 'Optionally add an extra design prompt, then continue directly to your prototype.' },
  ][step]
  return <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-panel text-ink">
    <header className="sticky top-0 z-10 flex shrink-0 items-center justify-between gap-3 border-b border-line bg-panel/95 px-4 py-3 backdrop-blur sm:px-6">
      <div className="flex min-w-0 items-center gap-2.5"><button type="button" onClick={onBack} className="grid size-8 place-items-center rounded-md text-muted hover:bg-panel2 hover:text-ink" title="Back to wireframes"><ArrowLeft className="size-4" /></button><div><p className="text-[10px] font-semibold uppercase tracking-[.12em] text-muted2">Wireframe → Design</p><h1 className="text-sm font-semibold">Choose a visual theme</h1></div></div>
      <span className="text-xs font-medium text-muted">{stepCopy.eyebrow}</span>
    </header>

    <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
      <nav className="mb-7 flex flex-wrap gap-1" aria-label="Design customizer steps">{['Colours', 'Fonts', 'Images', 'Design brief'].map((label, index) => <div key={label} className="flex items-center gap-1"><button type="button" onClick={() => setStep(index)} aria-current={index === step ? 'step' : undefined} className={`flex items-center gap-2 rounded-lg px-1.5 py-1 text-xs font-semibold transition hover:bg-panel2 ${index === step ? 'text-ink' : index < step ? 'text-accent' : 'text-muted2'}`}><i className={`grid size-5 place-items-center rounded-full text-[10px] not-italic ${index <= step ? 'bg-accent text-ink' : 'bg-panel2 text-muted'}`}>{index < step ? <Check className="size-3" /> : index + 1}</i>{label}</button>{index < 3 && <b className="h-px w-6 bg-line" />}</div>)}</nav>
      <section className="mb-6 max-w-2xl"><p className="text-[11px] font-semibold uppercase tracking-[.12em] text-accent">{stepCopy.eyebrow}</p><h2 className="mt-2 text-2xl font-semibold tracking-[-.035em] text-ink">{stepCopy.title}</h2><p className="mt-2 text-sm leading-relaxed text-muted">{stepCopy.text} No web page is generated or previewed in this customizer.</p></section>

      {step === 0 && <><nav aria-label="Palette categories" className="mb-5 flex flex-wrap gap-1.5">{GROUPS.map(item => <button key={item} type="button" onClick={() => setGroup(item)} aria-pressed={group === item} className={`rounded-full border px-3 py-1.5 text-xs transition ${group === item ? 'border-accent bg-accent text-ink' : 'border-line bg-panel text-muted hover:border-line2 hover:text-ink'}`}>{item}</button>)}</nav><section aria-label="Colour theme gallery" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">{shownPalettes.map(palette => <PaletteCard key={palette.id} palette={palette} selected={selected.id === palette.id} onPick={openPalette} />)}</section><section className="mt-5 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-panel2 p-4"><div className="flex overflow-hidden rounded-lg border border-line">{state.colors.map((color, index) => <i key={`${color}-${index}`} className="block size-9 sm:size-10" style={{ background: color }} title={color} />)}</div><div className="min-w-0 flex-1"><p className="text-sm font-semibold">{selected.name}</p><p className="mt-0.5 text-xs text-muted">Click any palette to open its four-colour editor.</p></div><Button onClick={() => setStep(1)}>Approve colours</Button></section></>}

      {step === 1 && <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_260px]"><div className="rounded-2xl border border-line bg-panel2 p-4 sm:p-5"><div className="flex rounded-xl border border-line bg-panel p-1"><button type="button" onClick={() => setFontTarget('heading')} className={`flex-1 rounded-lg px-3 py-2 text-left text-xs transition ${fontTarget === 'heading' ? 'bg-accent font-semibold text-ink' : 'text-muted'}`}>Heading<br /><span className="font-normal">{state.headingFont}</span></button><button type="button" onClick={() => setFontTarget('body')} className={`flex-1 rounded-lg px-3 py-2 text-left text-xs transition ${fontTarget === 'body' ? 'bg-accent font-semibold text-ink' : 'text-muted'}`}>Body<br /><span className="font-normal">{state.bodyFont}</span></button></div><div className="mt-4 flex items-center justify-between gap-3"><p className="text-xs text-muted">Selecting a font applies it to the active {fontTarget} role.</p><span className="shrink-0 text-[11px] text-muted">{FONT_OPTIONS.length} Google Fonts</span></div><input aria-label="Search Google Fonts" value={fontQuery} onChange={event => setFontQuery(event.target.value)} placeholder="Search 100+ fonts…" className="mt-3 w-full rounded-xl border border-line bg-panel px-3 py-2 text-sm text-ink outline-none placeholder:text-muted2 focus:border-accent" /><div className="mt-3 grid max-h-[480px] gap-2 overflow-y-auto pr-1 sm:grid-cols-2">{shownFonts.map(font => <button key={font} type="button" onMouseEnter={() => loadGoogleFont(font)} onFocus={() => loadGoogleFont(font)} onClick={() => chooseFont(font)} aria-pressed={currentFont === font} style={{ fontFamily: fontStack(font) }} className={`rounded-xl border px-3 py-3 text-left text-lg transition ${currentFont === font ? 'border-accent bg-accent/15' : 'border-line bg-panel hover:border-line2'}`}>{font}<span className="mt-1 block text-[11px] text-muted">Aa Bb Cc 123</span></button>)}{shownFonts.length === 0 && <p className="col-span-2 rounded-xl border border-dashed border-line p-4 text-sm text-muted">No fonts match that search.</p>}</div></div><aside className="flex flex-col rounded-2xl border border-line bg-panel2 p-4 sm:p-5"><p className="text-sm font-semibold">Live sample</p><div className="mt-4 rounded-xl border border-line bg-panel p-4"><p className="text-2xl font-bold leading-tight" style={{ color: state.colors[0], fontFamily: fontStack(state.headingFont) }}>Make your product memorable.</p><p className="mt-3 text-sm leading-relaxed text-muted" style={{ fontFamily: fontStack(state.bodyFont) }}>The quick brown fox jumps over the lazy dog — a live sample of your selected typeface.</p></div><div className="mt-auto flex gap-2 pt-5"><Button variant="outline" onClick={() => setStep(0)}>Back</Button><Button className="flex-1" onClick={() => setStep(2)}>Approve fonts</Button></div></aside></section>}

      {step === 2 && <section className="mx-auto max-w-3xl rounded-2xl border border-line bg-panel2 p-4 sm:p-6"><div className="flex items-center gap-2"><ImagePlus className="size-4 text-accent" /><h3 className="text-sm font-semibold">Image upload queue</h3></div><p className="mt-1 text-xs leading-relaxed text-muted">These images are visual references for the prototype designer.</p><input ref={picker} hidden type="file" accept={ACCEPT_IMAGES} onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; requestImage(file) }} /><div role="button" tabIndex={0} aria-label="Upload design reference image" onClick={() => picker.current?.click()} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') picker.current?.click() }} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); requestImage(event.dataTransfer.files?.[0]) }} className="mt-5 grid min-h-44 cursor-pointer place-items-center rounded-2xl border-2 border-dashed border-line2 bg-panel p-5 text-center transition hover:border-accent hover:bg-accent/5"><div><Upload className="mx-auto size-7 text-accent" /><p className="mt-3 text-sm font-semibold">Drag or click to upload image</p><p className="mt-1 text-xs text-muted">PNG, JPEG, WebP, GIF or SVG</p></div></div>{uploading && <p className="mt-3 flex items-center gap-2 text-xs text-muted"><Loader2 className="size-3.5 animate-spin" />Uploading image…</p>}{state.images.length > 0 && <ul className="mt-4 divide-y divide-line rounded-xl border border-line bg-panel">{state.images.map(image => <li key={image.file} className="flex items-center gap-2 px-3 py-2.5 text-xs"><span className="min-w-0 flex-1 truncate" title={image.file}>{image.file}</span><span className="text-muted">ready</span><button type="button" onClick={() => removeImage(image.file)} className="rounded p-1 text-muted hover:bg-panel2 hover:text-ink" title={`Remove ${image.file} from this design`}><X className="size-3.5" /></button></li>)}</ul>}<div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setStep(1)}>Back</Button><Button onClick={() => setStep(3)}>Continue to design brief</Button></div></section>}

      {step === 3 && <section className="mx-auto grid max-w-3xl gap-5 lg:grid-cols-[minmax(0,1fr)_260px]"><div className="rounded-2xl border border-line bg-panel2 p-4 sm:p-6"><div className="flex items-center gap-2"><Sparkles className="size-4 text-accent" /><h3 className="text-sm font-semibold">Design prompt</h3></div><p className="mt-1 text-xs leading-relaxed text-muted">Optional — leave this empty if your colours, fonts and reference images already describe the design.</p><textarea aria-label="Additional design direction" value={state.prompt} onChange={event => save({ prompt: event.target.value })} rows={9} placeholder="Example: Friendly marketplace, rounded cards, warm and welcoming, generous whitespace…" className="mt-4 w-full resize-y rounded-xl border border-line bg-panel px-3 py-2.5 text-sm leading-relaxed text-ink outline-none placeholder:text-muted2 focus:border-accent" /></div><aside className="flex flex-col rounded-2xl border border-line bg-panel2 p-4 sm:p-6"><p className="text-sm font-semibold">Ready for prototype</p><p className="mt-2 text-xs leading-relaxed text-muted">{selected.name} colours, {state.headingFont}/{state.bodyFont}, and {state.images.length} image reference{state.images.length === 1 ? '' : 's'} will go to the prototype generation stage.</p><div className="mt-4 flex overflow-hidden rounded-lg border border-line">{state.colors.map((color, index) => <i key={`${color}-${index}`} className="block size-8" style={{ background: color }} />)}</div><div className="mt-auto flex gap-2 pt-5"><Button variant="outline" onClick={() => setStep(2)}>Back</Button><Button className="flex-1" disabled={saving} onClick={approve}>{saving ? 'Saving…' : 'Generate prototype'}</Button></div></aside></section>}
      {error && <p role="alert" className="mt-4 rounded-xl border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}
    </main>
    {paletteDialog && <Modal onClose={() => setPaletteDialog(null)} className="max-w-2xl p-0" overlayClassName="bg-black/55"><div className="border-b border-line px-5 py-4"><p className="text-[11px] font-semibold uppercase tracking-[.12em] text-accent">Colour editor</p><h3 className="mt-1 text-lg font-semibold">{paletteDialog.name} palette</h3><p className="mt-1 text-xs text-muted">Change any swatch and review all four colours live before applying.</p></div><div className="p-5"><div className="grid gap-3 sm:grid-cols-2">{draftColors.map((color, index) => <label key={`${COLOR_LABELS[index]}-${color}`} className="flex items-center gap-3 rounded-xl border border-line bg-panel2 p-3"><input aria-label={`${COLOR_LABELS[index]} draft colour`} type="color" value={color} onChange={event => updateDraftColor(index, event.target.value)} className="size-10 cursor-pointer rounded border-0 bg-transparent p-0" /><span className="min-w-0 flex-1"><span className="block text-xs font-semibold">{COLOR_LABELS[index]}</span><input aria-label={`${COLOR_LABELS[index]} draft hex`} key={color} defaultValue={color} onBlur={event => updateDraftColor(index, event.target.value)} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }} className="mt-1 w-full bg-transparent text-xs uppercase text-muted outline-none focus:text-ink" /></span></label>)}</div><div className="mt-5 overflow-hidden rounded-xl border border-line"><div className="grid grid-cols-4">{draftColors.map((color, index) => <div key={`${color}-${index}`} className="h-24 sm:h-32" style={{ background: color }} />)}</div><div className="grid grid-cols-4 bg-panel">{draftColors.map((color, index) => <p key={`${color}-${index}`} className="truncate px-2 py-2 text-center text-[10px] font-medium uppercase text-muted">{color}</p>)}</div></div><div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setPaletteDialog(null)}>Cancel</Button><Button onClick={applyPalette}>Apply colours</Button></div></div></Modal>}
    {pendingImage && <Modal onClose={() => setPendingImage(null)} className="max-w-lg p-0" overlayClassName="bg-black/55"><div className="border-b border-line px-5 py-4"><p className="text-[11px] font-semibold uppercase tracking-[.12em] text-accent">Describe image</p><h3 className="mt-1 text-lg font-semibold">What is this image for?</h3><p className="mt-1 truncate text-xs text-muted" title={pendingImage.name}>{pendingImage.name}</p></div><div className="p-5"><label className="block text-xs font-semibold text-ink">Reference purpose <span className="font-normal text-muted">(optional)</span><input autoFocus aria-label="Image reference purpose" value={imagePurpose} onChange={event => setImagePurpose(event.target.value)} placeholder="Example: Product photography style, brand logo, dashboard inspiration…" className="mt-2 w-full rounded-xl border border-line bg-panel2 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-muted2 focus:border-accent" /></label><p className="mt-3 text-xs leading-relaxed text-muted">This label helps the prototype designer use the image in the right way.</p><div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setPendingImage(null)}>Cancel</Button><Button disabled={uploading} onClick={() => addImage(pendingImage, imagePurpose)}>{uploading ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}{uploading ? 'Uploading…' : 'Add image'}</Button></div></div></Modal>}
  </div>
}
