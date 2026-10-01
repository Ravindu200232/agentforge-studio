'use client'

import {useEffect, useState} from 'react'
import {X, Undo2, Redo2, Copy, MoveUp, MoveDown, Trash2, Save, Check, Move, ArrowLeft, ArrowRight, ArrowUp, ArrowDown, AlignLeft, AlignCenter, AlignRight, Maximize2, Eye, EyeOff, Palette, Minus, Plus, RotateCcw, Type, Ruler, SquareDashed, LayoutTemplate, SlidersHorizontal, Search, TextCursorInput, ImageUp} from 'lucide-react'
import {api, API} from '@/lib/api'
import {editorFor, serializePrototype} from '@/lib/visual-editor'
import {STYLE_GROUPS, ATTRIBUTES, MEDIA_ATTRIBUTES, FORM_ATTRIBUTES} from '@/lib/visual-controls'

const inputClass = 'w-full min-w-0 rounded-lg border border-line bg-white px-2 py-1.5 text-[11px] text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/15'
const buttonClass = 'inline-flex items-center justify-center gap-1 rounded-lg border border-line bg-panel px-2 py-1.5 text-[11px] text-ink hover:bg-black/[.04] disabled:opacity-30'
const iconClass = active => `grid size-9 place-items-center rounded-lg transition-colors ${active ? 'bg-accent/15 text-deep' : 'text-ink hover:bg-black/[.05]'}`
const colorFields = new Set(['color', 'background-color', 'border-color', 'text-decoration-color', 'accent-color'])
const POPULAR_FONTS = ['Inter', 'Roboto', 'Poppins', 'Open Sans', 'Montserrat', 'Lato', 'Plus Jakarta Sans', 'Outfit', 'Space Grotesk', 'Playfair Display', 'Merriweather', 'Lora', 'DM Sans', 'DM Serif Display', 'IBM Plex Sans', 'Nunito', 'Work Sans', 'Syne', 'Cinzel', 'JetBrains Mono', 'Fira Code']

function hex(value) {
  const rgb = String(value || '').match(/\d+(?:\.\d+)?/g)
  return rgb?.length >= 3 ? '#' + rgb.slice(0, 3).map(n => Math.round(Number(n)).toString(16).padStart(2, '0')).join('') : '#000000'
}

export default function VisualInspector({element, doc, project, currentFile, onClose, onLog, onSelect}) {
  const [tool, setTool] = useState('content')
  const [version, setVersion] = useState(0)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [breakpoint, setBreakpoint] = useState('all')
  const [pseudo, setPseudo] = useState('')
  const [insertTag, setInsertTag] = useState('p')
  const [attributeName, setAttributeName] = useState('data-testid')
  const [attributeValue, setAttributeValue] = useState('')
  const [customProperty, setCustomProperty] = useState('')
  const [customValue, setCustomValue] = useState('')
  const [fontCatalog, setFontCatalog] = useState(POPULAR_FONTS)
  const [fontQuery, setFontQuery] = useState('')

  useEffect(() => { setTool('content'); setSaved(false); setError(''); setVersion(v => v + 1) }, [element, doc, project, currentFile])
  useEffect(() => {
    const view = doc?.defaultView
    if (!view) return
    const openContent = () => setTool('content')
    const refresh = () => { setSaved(false); setVersion(v => v + 1) }
    view.addEventListener('agentforge:open-content-tool', openContent)
    view.addEventListener('agentforge:inspector-change', refresh)
    return () => {
      view.removeEventListener('agentforge:open-content-tool', openContent)
      view.removeEventListener('agentforge:inspector-change', refresh)
    }
  }, [doc])
  useEffect(() => {
    let active = true
    fetch('https://cdn.jsdelivr.net/gh/hasinhayder/google-fonts/fonts.json')
      .then(response => response.ok ? response.json() : null)
      .then(data => { if (active && Array.isArray(data?.fonts)) setFontCatalog(data.fonts) })
      .catch(() => {})
    return () => { active = false }
  }, [])
  if (!element || !doc?.defaultView || element.ownerDocument !== doc) return null
  const editor = editorFor(doc)
  const computed = doc.defaultView.getComputedStyle(element)
  const tag = element.tagName.toLowerCase()
  const isForm = ['input', 'textarea', 'select', 'button'].includes(tag)
  const isMedia = ['img', 'video', 'audio', 'source'].includes(tag)
  const run = action => { try { action(); setError(''); setSaved(false); setVersion(v => v + 1) } catch (e) { setError(e.message) } }
  const style = (property, value) => run(() => breakpoint === 'all' && !pseudo ? editor.style(element, property, String(value).trim()) : editor.responsive(element, breakpoint, property, String(value).trim(), pseudo))
  const previewColor = (property, value) => {
    try {
      if (breakpoint === 'all' && !pseudo) editor.style(element, property, String(value).trim())
      else editor.responsive(element, breakpoint, property, String(value).trim(), pseudo)
      setError('')
      setSaved(false)
    } catch (e) { setError(e.message) }
  }
  const attr = (name, value) => run(() => editor.attribute(element, name, value))
  const select = node => { if (node) onSelect?.(node, doc) }
  const nudge = (x, y) => run(() => { if (computed.position === 'static') element.style.position = 'relative'; element.style.left = `${Math.round((parseFloat(element.style.left) || 0) + x)}px`; element.style.top = `${Math.round((parseFloat(element.style.top) || 0) + y)}px` })
  const setAxis = (axis, value) => run(() => { if (computed.position === 'static') element.style.position = 'relative'; element.style[axis] = value.trim() || '0px' })
  const loadGoogleFont = fontName => {
    const clean = String(fontName || '').trim().replace(/^['"]|['"]$/g, '')
    if (!clean || /^(system-ui|sans-serif|serif|monospace)$/i.test(clean)) return clean
    const id = `gfont-visual-${clean.replace(/\s+/g, '-').toLowerCase()}`
    if (!doc.getElementById(id)) {
      const link = doc.createElement('link')
      link.id = id
      link.rel = 'stylesheet'
      link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(clean)}:wght@400;500;600;700&display=swap`
      doc.head.appendChild(link)
    }
    return clean
  }
  const adjust = (property, value, direction) => {
    const matched = String(value || '').trim().match(/^(-?(?:\d+\.?\d*|\.\d+))(.*)$/)
    const opacity = property === 'opacity', weight = property === 'font-weight', step = weight ? 100 : opacity ? .1 : 1
    const number = matched ? Number(matched[1]) : 0, unit = matched ? matched[2] : (opacity || weight || property === 'z-index' ? '' : 'px')
    style(property, `${Math.round((number + direction * step) * (opacity ? 10 : 1)) / (opacity ? 10 : 1)}${unit}`)
  }
  const Color = ({property, label}) => {
    const value = computed.getPropertyValue(property).trim(), valueHex = hex(value), rgb = value.match(/\d+/g)
    return <label className="flex min-w-0 flex-col gap-1"><span className="text-[10px] text-muted">{label}</span><div className="flex gap-1.5"><input aria-label={`${label} color picker`} type="color" className="size-8 shrink-0 cursor-pointer rounded-lg border border-line bg-white p-1" value={valueHex} onInput={e => previewColor(property, e.currentTarget.value)} onChange={e => previewColor(property, e.currentTarget.value)} onBlur={() => setVersion(v => v + 1)} /><input className={inputClass} aria-label={`${label} hex`} defaultValue={valueHex} onBlur={e => /^#[0-9a-f]{6}$/i.test(e.target.value.trim()) && style(property, e.target.value)} onKeyDown={e => e.key === 'Enter' && e.currentTarget.blur()} /></div><span className="text-[9px] text-muted">{rgb?.length >= 3 ? `RGB ${rgb.slice(0,3).join(' · ')}` : 'Inherited color'}</span></label>
  }
  const Field = ({property, label, options}) => {
    const value = computed.getPropertyValue(property).trim()
    if (property === 'font-family') {
      const selected = value.split(',')[0].trim().replace(/^['"]|['"]$/g, '')
      const filteredFonts = fontCatalog.filter(font => font.toLowerCase().includes(fontQuery.trim().toLowerCase())).slice(0, 36)
      const chooseFont = font => { const clean = loadGoogleFont(font); style(property, `'${clean}', sans-serif`); setFontQuery('') }
      return <label className="col-span-2 flex min-w-0 flex-col gap-1"><span className="text-[10px] text-muted">Font family · Google Fonts</span><div className="flex gap-1"><input aria-label="Search Google fonts" className={inputClass} value={fontQuery} placeholder={selected || 'Search Google fonts…'} onChange={e => setFontQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && fontQuery.trim()) chooseFont(fontQuery.trim()) }} /><button className={buttonClass} title="Apply typed font" onClick={() => fontQuery.trim() && chooseFont(fontQuery.trim())}>Apply</button></div><div className="max-h-32 overflow-y-auto rounded-lg border border-line bg-white p-1">{filteredFonts.map(font => <button key={font} type="button" onClick={() => chooseFont(font)} className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-[11px] ${selected === font ? 'bg-accent/15 text-deep' : 'text-ink hover:bg-black/[.04]'}`}><span style={{fontFamily: font}}>{font}</span>{selected === font && <Check size={12}/>}</button>)}</div></label>
    }
    if (colorFields.has(property)) return <Color property={property} label={label} />
    return <label className="flex min-w-0 flex-col gap-1"><span className="text-[10px] text-muted">{label}</span><div className="flex gap-1">{options ? <select className={inputClass} aria-label={label} defaultValue={value} onChange={e => style(property, e.target.value)}>{!options.includes(value) && <option value={value}>{value || 'Inherited'}</option>}{options.map(option => <option key={option}>{option}</option>)}</select> : <input className={inputClass} aria-label={label} defaultValue={value} placeholder="CSS value" onBlur={e => e.target.value !== e.target.defaultValue && style(property, e.target.value)} onKeyDown={e => e.key === 'Enter' && e.currentTarget.blur()} />}{!options && <><button className="grid size-7 shrink-0 place-items-center rounded-lg border border-line bg-panel text-muted hover:text-ink" title={`Decrease ${label}`} onClick={() => adjust(property, value, -1)}><Minus size={11}/></button><button className="grid size-7 shrink-0 place-items-center rounded-lg border border-line bg-panel text-muted hover:text-ink" title={`Increase ${label}`} onClick={() => adjust(property, value, 1)}><Plus size={11}/></button></>}<button className="grid size-7 shrink-0 place-items-center rounded-lg border border-line bg-panel text-muted hover:text-accent" title={`Reset ${label}`} onClick={() => style(property, '')}><RotateCcw size={11}/></button></div></label>
  }
  const Attribute = ({name}) => <label className="flex min-w-0 flex-col gap-1"><span className="text-[10px] text-muted">{name}</span><input className={inputClass} aria-label={name} defaultValue={name === 'class' ? [...element.classList].filter(c => !/^__(vf|lc)_/.test(c)).join(' ') : element.getAttribute(name) || ''} onBlur={e => e.target.value !== e.target.defaultValue && attr(name, e.target.value || null)} onKeyDown={e => e.key === 'Enter' && e.currentTarget.blur()} /></label>
  const groups = tool === 'type' ? ['Typography'] : tool === 'colors' ? ['Colors & backgrounds'] : tool === 'size' ? ['Size & spacing'] : tool === 'layout' ? ['Layout & position', 'Flex & grid'] : tool === 'border' ? ['Borders & effects'] : tool === 'more' ? ['Transform & interaction', 'Images & media'] : []
  const title = {content: 'Content & structure', move: 'Position & alignment', type: 'Typography', colors: 'Colors & backgrounds', size: 'Size & spacing', layout: 'Layout & grid', border: 'Borders & effects', more: 'More controls', image: 'Image upload'}[tool]

  function upload(file) {
    if (!file) return
    if (!/^image\/(png|jpeg|gif|webp|avif)$/.test(file.type) || file.size > 2 * 1024 * 1024) {
      setError('Choose a PNG, JPEG, GIF, WebP or AVIF image under 2 MB'); return
    }
    const reader = new FileReader()
    reader.onload = () => attr('src', String(reader.result))
    reader.onerror = () => setError('Could not read the image')
    reader.readAsDataURL(file)
  }

  async function save() {
    if (!project || saving) return
    const expected = new URL(`${API}/prototype/${encodeURIComponent(project)}/${currentFile || 'index.html'}`, window.location.href), actual = new URL(doc.URL)
    if (!doc.defaultView.frameElement || doc.defaultView.frameElement.contentDocument !== doc || actual.origin !== expected.origin || actual.pathname !== expected.pathname) { setError('This page has changed. Select an element in the current preview.'); return }
    setSaving(true); setError('')
    try { const sequence = editor.sequence; await api.saveFile(project, `.agentforge/prototype/${currentFile || 'index.html'}`, serializePrototype(doc), `Direct HTML customization in ${currentFile || 'index.html'}: ${editor.summary() || 'Updated the prototype interface'}`); editor.markSaved(sequence); setSaved(true); onLog?.('SUCCESS', `Saved ${currentFile || 'index.html'} directly to HTML`) } catch (e) { setError(e.message); onLog?.('WARN', `Could not save HTML: ${e.message}`) } finally { setSaving(false) }
  }

  return <aside aria-label="HTML visual editor" className="absolute inset-x-3 bottom-3 z-50">
    {tool && <section className="absolute bottom-12 left-1/2 max-h-[min(470px,calc(100vh-9rem))] w-[min(430px,calc(100vw-2rem))] -translate-x-1/2 overflow-y-auto rounded-2xl border border-line bg-panel p-3 shadow-2xl"><div className="mb-3 flex items-center justify-between border-b border-line pb-2"><div><p className="text-xs font-semibold text-ink">{title}</p><p className="text-[10px] text-muted">Selected &lt;{tag}&gt; · {currentFile || 'index.html'}</p></div><button className="grid size-7 place-items-center rounded-lg border border-line bg-panel text-muted hover:text-ink" title="Close controls" onClick={() => setTool('')}><X size={13}/></button></div>
      {tool === 'content' && <><div className="mb-3 flex flex-wrap gap-1"><button className={buttonClass} onClick={() => run(() => editor.move(element, 'up'))}><MoveUp size={12}/> Up</button><button className={buttonClass} onClick={() => run(() => editor.move(element, 'down'))}><MoveDown size={12}/> Down</button><button className={buttonClass} onClick={() => run(() => select(editor.duplicate(element)))}><Copy size={12}/> Duplicate</button><button className={buttonClass} aria-pressed={computed.display === 'none'} onClick={() => style('display', computed.display === 'none' ? '' : 'none')}>{computed.display === 'none' ? <Eye size={12}/> : <EyeOff size={12}/>} {computed.display === 'none' ? 'Show' : 'Hide'}</button><button className={buttonClass} onClick={() => select(element.parentElement)}>Select parent</button><button className={buttonClass} title="Delete selected element" onClick={() => run(() => editor.remove(element))}><Trash2 size={12}/></button></div><label className="flex flex-col gap-1 text-[10px] text-muted">Text (select inner text to keep nested elements)<textarea key={`text-${version}`} className={inputClass} aria-label="Text content" rows={3} defaultValue={['INPUT','TEXTAREA'].includes(element.tagName) ? element.defaultValue : [...element.childNodes].find(node => node.nodeType === 3 && node.textContent.trim())?.textContent || ''} onBlur={e => e.target.value !== e.target.defaultValue && run(() => editor.text(element, e.target.value))} /></label><div className="mt-2 flex gap-2"><select className={inputClass} aria-label="New element type" value={insertTag} onChange={e => setInsertTag(e.target.value)}>{['div','section','p','h2','span','a','button','img','input','ul','li','hr'].map(item => <option key={item}>{item}</option>)}</select><button className={buttonClass} onClick={() => run(() => select(editor.insert(element, insertTag)))}>Insert child</button></div></>}
      {tool === 'move' && <><p className="mb-2 text-[10px] text-muted">Type a value or use − / + to move precisely.</p><div className="grid grid-cols-2 gap-2">{[['X','left'],['Y','top']].map(([label, axis]) => <div key={axis} className="flex items-center justify-between rounded-lg border border-line bg-white px-1.5 py-1"><span className="text-[9px] font-bold text-muted">{label}</span><button className="p-1 text-muted hover:text-ink" onClick={() => axis === 'left' ? nudge(-5,0) : nudge(0,-5)}><Minus size={10}/></button><input key={`${axis}-${version}`} className="w-[46px] bg-transparent text-center text-[11px] font-semibold text-ink outline-none" aria-label={`${label} position`} defaultValue={`${Math.round(parseFloat(element.style[axis]) || 0)}px`} onBlur={e => setAxis(axis, e.target.value)} onKeyDown={e => e.key === 'Enter' && e.currentTarget.blur()} /><button className="p-1 text-muted hover:text-ink" onClick={() => axis === 'left' ? nudge(5,0) : nudge(0,5)}><Plus size={10}/></button></div>)}</div><div className="mt-2 flex items-center justify-between"><div className="flex rounded-lg border border-line bg-white p-0.5"><button className="p-1 text-muted hover:text-ink" onClick={() => nudge(-1,0)}><ArrowLeft size={13}/></button><button className="p-1 text-muted hover:text-ink" onClick={() => nudge(0,-1)}><ArrowUp size={13}/></button><button className="p-1 text-muted hover:text-ink" onClick={() => nudge(0,1)}><ArrowDown size={13}/></button><button className="p-1 text-muted hover:text-ink" onClick={() => nudge(1,0)}><ArrowRight size={13}/></button></div><div className="flex rounded-lg border border-line bg-white p-0.5"><button className="p-1 text-muted hover:text-ink" onClick={() => run(() => { element.style.marginLeft = ''; element.style.marginRight = 'auto' })}><AlignLeft size={13}/></button><button className="p-1 text-muted hover:text-ink" onClick={() => run(() => { element.style.marginLeft = 'auto'; element.style.marginRight = 'auto'; element.style.textAlign = 'center' })}><AlignCenter size={13}/></button><button className="p-1 text-muted hover:text-ink" onClick={() => run(() => { element.style.marginLeft = 'auto'; element.style.marginRight = '' })}><AlignRight size={13}/></button><button className="p-1 text-muted hover:text-ink" onClick={() => run(() => { element.style.width = '100%'; element.style.display = 'block' })}><Maximize2 size={13}/></button></div></div></>}
      {tool === 'image' && <div><p className="mb-3 text-[10px] text-muted">Upload a replacement image. It will be embedded in this prototype when you save.</p><label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-line bg-white px-3 py-6 text-xs font-medium text-ink hover:border-accent hover:text-deep"><ImageUp size={16}/> Choose image<input aria-label="Upload replacement image" className="sr-only" type="file" accept="image/png,image/jpeg,image/gif,image/webp,image/avif" onChange={e => upload(e.target.files?.[0])} /></label><label className="mt-3 flex flex-col gap-1 text-[10px] text-muted">Image description (alt text)<input className={inputClass} aria-label="Image description" defaultValue={element.getAttribute('alt') || ''} onBlur={e => attr('alt', e.target.value)} /></label></div>}
      {groups.length > 0 && <><label className="mb-2 flex items-center gap-2 rounded-lg border border-line bg-white px-2"><Search size={13} className="text-muted"/><input aria-label="Find customization tools" className="min-w-0 flex-1 bg-transparent py-2 text-[11px] outline-none" placeholder="Find a tool or CSS property…" value={search} onChange={e => setSearch(e.target.value)} /></label><div className="mb-3 grid grid-cols-2 gap-2"><label className="text-[10px] text-muted">Apply styles to<select className={inputClass} value={breakpoint} onChange={e => setBreakpoint(e.target.value)}><option value="all">All sizes</option><option value="1024">Tablet ≤1024px</option><option value="640">Mobile ≤640px</option></select></label><label className="text-[10px] text-muted">State<select className={inputClass} value={pseudo} onChange={e => setPseudo(e.target.value)}><option value="">Default</option><option value="hover">Hover</option><option value="focus-visible">Keyboard focus</option><option value="active">Pressed</option><option value="disabled">Disabled</option></select></label></div>{groups.map(name => { const group = STYLE_GROUPS.find(item => item.name === name), fields = group.fields.filter(item => !search || `${item.label} ${item.property}`.toLowerCase().includes(search.toLowerCase())); return <div key={name} className="mb-3"><p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted">{name}</p><div className="grid grid-cols-2 gap-2">{fields.map(item => <Field key={item.property} {...item} />)}</div></div> })}</>}
      {tool === 'more' && <div className="border-t border-line pt-3"><p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted">HTML attributes & accessibility</p><div className="grid grid-cols-2 gap-2">{ATTRIBUTES.map(name => <Attribute key={name} name={name} />)}{tag === 'a' && ['href','target','rel'].map(name => <Attribute key={name} name={name} />)}{isMedia && MEDIA_ATTRIBUTES.map(name => <Attribute key={name} name={name} />)}{isForm && FORM_ATTRIBUTES.map(name => <Attribute key={name} name={name} />)}</div><div className="mt-3 flex gap-2"><input className={inputClass} aria-label="Attribute name" value={attributeName} onChange={e => setAttributeName(e.target.value)} /><input className={inputClass} aria-label="Attribute value" value={attributeValue} onChange={e => setAttributeValue(e.target.value)} /><button className={buttonClass} onClick={() => attr(attributeName, attributeValue || null)}>Set</button></div><div className="mt-3 flex gap-2"><input className={inputClass} aria-label="CSS property" placeholder="CSS property" value={customProperty} onChange={e => setCustomProperty(e.target.value)} /><input className={inputClass} aria-label="CSS value" placeholder="Value" value={customValue} onChange={e => setCustomValue(e.target.value)} /><button className={buttonClass} onClick={() => style(customProperty, customValue)}>Apply</button></div></div>}
      {error && <p role="alert" className="mt-3 text-[11px] text-red-500">{error}</p>}
    </section>}
    <nav aria-label="Visual editing toolbar" className="relative mx-auto flex w-fit max-w-full items-center gap-0.5 overflow-x-auto rounded-xl border border-line bg-panel p-1 shadow-xl"><button className={iconClass(tool === 'content')} aria-pressed={tool === 'content'} title="Content & structure" onClick={() => setTool(tool === 'content' ? '' : 'content')}><TextCursorInput size={15}/></button><button className={iconClass(tool === 'colors')} aria-pressed={tool === 'colors'} title="Colors & backgrounds" onClick={() => setTool(tool === 'colors' ? '' : 'colors')}><Palette size={15}/></button><button className={iconClass(tool === 'type')} aria-pressed={tool === 'type'} title="Typography" onClick={() => setTool(tool === 'type' ? '' : 'type')}><Type size={15}/></button><button className={iconClass(tool === 'border')} aria-pressed={tool === 'border'} title="Border & radius" onClick={() => setTool(tool === 'border' ? '' : 'border')}><SquareDashed size={15}/></button><button className={iconClass(tool === 'size')} aria-pressed={tool === 'size'} title="Size & spacing" onClick={() => setTool(tool === 'size' ? '' : 'size')}><Ruler size={15}/></button><button className={iconClass(tool === 'layout')} aria-pressed={tool === 'layout'} title="Layout & grid" onClick={() => setTool(tool === 'layout' ? '' : 'layout')}><LayoutTemplate size={15}/></button><button className={iconClass(tool === 'move')} aria-pressed={tool === 'move'} title="Move & align" onClick={() => setTool(tool === 'move' ? '' : 'move')}><Move size={15}/></button>{tag === 'img' && <button className={iconClass(tool === 'image')} aria-pressed={tool === 'image'} title="Replace image" onClick={() => setTool(tool === 'image' ? '' : 'image')}><ImageUp size={15}/></button>}<button className={iconClass(tool === 'more')} aria-pressed={tool === 'more'} title="More controls" onClick={() => setTool(tool === 'more' ? '' : 'more')}><SlidersHorizontal size={15}/></button><span className="mx-1 h-6 w-px bg-line"/><button className={iconClass(false)} title="Undo" disabled={!editor.canUndo} onClick={() => run(() => editor.undo())}><Undo2 size={14}/></button><button className={iconClass(false)} title="Redo" disabled={!editor.canRedo} onClick={() => run(() => editor.redo())}><Redo2 size={14}/></button><button className={iconClass(false)} title="Deselect element" onClick={onClose}><X size={15}/></button><button className="ml-1 inline-flex h-9 items-center gap-1 rounded-lg border border-line bg-panel px-3 text-[11px] font-semibold text-ink hover:bg-black/[.04] disabled:opacity-50" onClick={save} disabled={saving}>{saved ? <Check size={14}/> : <Save size={14}/>} {saving ? 'Saving…' : saved ? 'Saved' : 'Save'}</button></nav>
  </aside>
}
