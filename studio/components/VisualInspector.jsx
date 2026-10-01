'use client'

import {useEffect, useState} from 'react'
import {
  X, ChevronDown, ChevronUp, Undo2, Redo2, Copy, Trash2, Save, Check,
  AlignLeft, AlignCenter, AlignRight,
} from 'lucide-react'
import {api, API} from '@/lib/api'
import {editorFor, serializePrototype} from '@/lib/visual-editor'
import {STYLE_GROUPS, ATTRIBUTES, MEDIA_ATTRIBUTES, FORM_ATTRIBUTES} from '@/lib/visual-controls'

const inputClass = 'w-full min-w-0 rounded-lg border border-line bg-panel px-2 py-1.5 text-[11px] text-ink outline-none focus:border-accent dark:border-black/10 dark:bg-black/20 dark:text-ink'
const buttonClass = 'rounded-lg border border-line px-2 py-1.5 text-[11px] text-ink hover:bg-accent disabled:opacity-30 dark:border-black/10 dark:text-ink'

export default function VisualInspector({element, doc, project, currentFile, onClose, onLog, onSelect}) {
  const [minimized, setMinimized] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [version, setVersion] = useState(0)
  const [breakpoint, setBreakpoint] = useState('all')
  const [pseudo, setPseudo] = useState('')
  const [insertTag, setInsertTag] = useState('p')
  const [attributeName, setAttributeName] = useState('data-testid')
  const [attributeValue, setAttributeValue] = useState('')
  const [customProperty, setCustomProperty] = useState('')
  const [customValue, setCustomValue] = useState('')
  useEffect(() => { setError(''); setSaved(false); setVersion(v => v + 1) }, [element, doc, project, currentFile])
  if (!element || !doc || !doc.defaultView || element.ownerDocument !== doc) return null
  const editor = editorFor(doc)
  const computed = doc.defaultView.getComputedStyle(element)
  const tag = element.tagName.toLowerCase()
  const isForm = ['input', 'textarea', 'select', 'button'].includes(tag)
  const isMedia = ['img', 'video', 'audio', 'source'].includes(tag)
  const run = action => {
    try { action(); setError(''); setSaved(false); setVersion(v => v + 1) }
    catch (e) { setError(e.message) }
  }
  const style = (property, value) => run(() => breakpoint === 'all' && !pseudo
    ? editor.style(element, property, value.trim()) : editor.responsive(element, breakpoint, property, value.trim(), pseudo))
  const attr = (name, value) => run(() => editor.attribute(element, name, value))
  const selectNode = node => { if (node) onSelect?.(node, doc) }
  const field = ({property, label, options}) => {
    const value = computed.getPropertyValue(property).trim()
    return <label key={property + version} className="flex min-w-0 flex-col gap-1">
      <span className="text-[10px] text-muted">{label}</span><div className="flex gap-1">
        {options ? <select aria-label={label} defaultValue={value} className={inputClass} onChange={e => style(property, e.target.value)}>
          {!options.includes(value) && <option value={value}>{value || 'Inherited'}</option>}
          {options.map(option => <option key={option}>{option}</option>)}
        </select> : <input aria-label={label} className={inputClass} defaultValue={value} placeholder="CSS value"
          onBlur={e => { if (e.target.value !== e.target.defaultValue) style(property, e.target.value) }}
          onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }} />}
        <button type="button" title={`Reset ${label}`} aria-label={`Reset ${label}`} className="px-1 text-muted hover:text-accent"
          onClick={e => { e.preventDefault(); style(property, '') }}>×</button>
      </div></label>
  }
  const attributeField = name => <label key={name + version} className="flex min-w-0 flex-col gap-1">
    <span className="text-[10px] text-muted">{name}</span><input aria-label={name} className={inputClass}
      defaultValue={name === 'class' ? [...element.classList].filter(c => !/^__(vf|lc)_/.test(c)).join(' ') : element.getAttribute(name) || ''}
      onBlur={e => { if (e.target.value !== e.target.defaultValue) attr(name, e.target.value || null) }}
      onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }} /></label>
  async function save() {
    if (!project || saving) return
    const expected = new URL(`${API}/prototype/${encodeURIComponent(project)}/${currentFile || 'index.html'}`, window.location.href)
    const actual = new URL(doc.URL)
    if (!doc.defaultView?.frameElement || doc.defaultView.frameElement.contentDocument !== doc ||
        actual.origin !== expected.origin || actual.pathname !== expected.pathname) {
      setError('This page has changed. Select an element in the current preview.'); return
    }
    const selectedProject = project, selectedFile = currentFile || 'index.html'
    const changeSequence = editor.sequence
    setSaving(true); setError('')
    try {
      await api.saveFile(selectedProject, `.agentforge/prototype/${selectedFile}`, serializePrototype(doc),
        `Direct HTML customization in ${selectedFile}: ${editor.summary() || 'Updated the prototype interface'}`)
      editor.markSaved(changeSequence)
      setSaved(true); onLog?.('SUCCESS', `Saved ${selectedFile} directly to HTML`)
    } catch (e) { setError(e.message); onLog?.('WARN', `Could not save HTML: ${e.message}`) }
    finally { setSaving(false) }
  }
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
  return <aside aria-label="HTML visual editor" className="absolute right-4 top-16 z-50 flex max-h-[calc(100%-5rem)] w-[min(390px,calc(100%-2rem))] flex-col overflow-hidden rounded-2xl border border-line bg-panel p-3 shadow-2xl dark:border-black/10">
    <div className="flex items-center justify-between gap-2 border-b border-line pb-2 dark:border-black/10">
      <div className="min-w-0"><span className="text-sm font-semibold text-ink dark:text-ink">HTML editor</span>
        <div className="truncate text-[10px] text-muted">&lt;{tag}&gt; · {currentFile || 'index.html'}</div></div>
      <div className="flex gap-1">
        <button className={buttonClass} title="Undo" aria-label="Undo" disabled={!editor.canUndo} onClick={() => run(() => editor.undo())}><Undo2 size={13}/></button>
        <button className={buttonClass} title="Redo" aria-label="Redo" disabled={!editor.canRedo} onClick={() => run(() => editor.redo())}><Redo2 size={13}/></button>
        <button className={buttonClass} aria-label={minimized ? 'Expand editor' : 'Minimize editor'} onClick={() => setMinimized(!minimized)}>{minimized ? <ChevronDown size={13}/> : <ChevronUp size={13}/>}</button>
        <button className={buttonClass} aria-label="Close editor" onClick={onClose}><X size={13}/></button>
      </div></div>
    {!minimized && <div className="min-h-0 overflow-y-auto overscroll-contain py-3">
      <div className="mb-3 flex flex-wrap gap-1">
        <button className={buttonClass} onClick={() => run(() => selectNode(editor.duplicate(element)))}><Copy size={12}/> Duplicate</button>
        <button className={buttonClass} onClick={() => style('display', computed.display === 'none' ? '' : 'none')}>Hide / show</button>
        <button className={buttonClass} onClick={() => run(() => editor.remove(element))} aria-label="Delete selected element"><Trash2 size={12}/></button>
        <button className={buttonClass} onClick={() => selectNode(element.parentElement)}>Select parent</button>
      </div>

      {/* Alignment */}
      <div className="mb-3 flex items-center gap-1">
        <span className="mr-1 text-[10.5px] font-semibold text-muted">Align</span>
        <button type="button" title="Align Left" className={buttonClass} onClick={() => run(() => {
          element.style.marginLeft = ''
          element.style.marginRight = 'auto'
        })}><AlignLeft size={12}/></button>
        <button type="button" title="Align Center" className={buttonClass} onClick={() => run(() => {
          element.style.marginLeft = 'auto'
          element.style.marginRight = 'auto'
          element.style.textAlign = 'center'
        })}><AlignCenter size={12}/></button>
        <button type="button" title="Align Right" className={buttonClass} onClick={() => run(() => {
          element.style.marginLeft = 'auto'
          element.style.marginRight = ''
        })}><AlignRight size={12}/></button>
      </div>

      <input aria-label="Find customization tools" placeholder="Find a tool or CSS property…" className={inputClass} value={search} onChange={e => setSearch(e.target.value)}/>
      {!search && <div className="mt-3 flex items-center gap-3">{['color', 'background-color', 'border-color'].map(property => {
        const rgb = computed.getPropertyValue(property).match(/\d+/g)
        const hex = rgb?.length >= 3 ? '#' + rgb.slice(0,3).map(n => Number(n).toString(16).padStart(2,'0')).join('') : '#000000'
        return <label key={property} className="flex items-center gap-1 text-[10px] text-muted">{property === 'color' ? 'Text' : property === 'background-color' ? 'Background' : 'Border'}
          <input aria-label={`${property} picker`} type="color" value={hex} onChange={e => style(property,e.target.value)} className="size-5 cursor-pointer rounded border-0 p-0"/></label>
      })}</div>}
      <div className="my-3 grid grid-cols-2 gap-2">
        <label className="text-[10px] text-muted">Apply styles to<select aria-label="Style breakpoint" className={inputClass} value={breakpoint} onChange={e => setBreakpoint(e.target.value)}>
          <option value="all">All sizes</option><option value="1024">Tablet ≤1024px</option><option value="640">Mobile ≤640px</option></select></label>
        <label className="text-[10px] text-muted">State<select aria-label="Style state" className={inputClass} value={pseudo} onChange={e => setPseudo(e.target.value)}>
          <option value="">Default</option><option value="hover">Hover</option><option value="focus-visible">Keyboard focus</option><option value="active">Pressed</option><option value="disabled">Disabled</option></select></label>
      </div>
      <p className="mb-2 text-[10px] text-muted">Press Enter or leave a field to apply. Size and state rules preview when they match.</p>
      {!search && <details open className="border-t border-line py-2 dark:border-black/10"><summary className="cursor-pointer text-xs font-medium text-ink dark:text-ink">Content & structure</summary>
        <label className="mt-2 flex flex-col gap-1 text-[10px] text-muted">Text (select inner text to keep nested elements)
          <textarea key={'text' + version} aria-label="Text content" className={inputClass} rows={3}
            defaultValue={['INPUT', 'TEXTAREA'].includes(element.tagName) ? element.defaultValue : [...element.childNodes].find(n => n.nodeType === 3 && n.textContent.trim())?.textContent || ''}
            onBlur={e => { if (e.target.value !== e.target.defaultValue) run(() => editor.text(element, e.target.value)) }}/></label>
        <div className="mt-2 flex gap-2"><select aria-label="New element type" className={inputClass} value={insertTag} onChange={e => setInsertTag(e.target.value)}>
          {['div','section','p','h2','span','a','button','img','input','ul','li','hr'].map(t => <option key={t}>{t}</option>)}</select>
          <button className={buttonClass} onClick={() => run(() => selectNode(editor.insert(element, insertTag)))}>Insert child</button></div>
      </details>}
      {STYLE_GROUPS.map(group => {
        const matching = group.fields.filter(f => !search || `${group.name} ${f.label} ${f.property}`.toLowerCase().includes(search.toLowerCase()))
        if (!matching.length) return null
        return <details key={group.name + !!search} open={search ? true : undefined} className="border-t border-line py-2 dark:border-black/10">
          <summary className="cursor-pointer text-xs font-medium text-ink dark:text-ink">{group.name}<span className="ml-2 text-[10px] text-muted">{matching.length}</span></summary>
          <div className="mt-2 grid grid-cols-2 gap-2">{matching.map(field)}</div></details>
      })}
      {!search && <><details className="border-t border-line py-2 dark:border-black/10"><summary className="cursor-pointer text-xs font-medium text-ink dark:text-ink">HTML attributes & accessibility</summary>
        <div className="mt-2 grid grid-cols-2 gap-2">{ATTRIBUTES.map(attributeField)}
          {tag === 'a' && ['href','target','rel'].map(attributeField)}
          {isMedia && MEDIA_ATTRIBUTES.map(attributeField)}
          {isForm && FORM_ATTRIBUTES.map(attributeField)}</div>
        <div className="mt-3 flex gap-2"><input aria-label="Attribute name" className={inputClass} value={attributeName} onChange={e => setAttributeName(e.target.value)}/>
          <input aria-label="Attribute value" className={inputClass} value={attributeValue} onChange={e => setAttributeValue(e.target.value)}/>
          <button className={buttonClass} onClick={() => attr(attributeName, attributeValue || null)}>Set</button></div>
        {isForm && <div className="mt-2 flex flex-wrap gap-2">{['disabled','required','checked'].map(name => <label key={name} className="text-[11px] text-muted">
          <input type="checkbox" checked={element.hasAttribute(name)} onChange={e => attr(name, e.target.checked ? '' : null)}/> {name}</label>)}</div>}
        {tag === 'img' && <label className="mt-3 flex flex-col gap-1 text-[10px] text-muted">Upload image (saved inside HTML)<input aria-label="Upload image" type="file" accept="image/png,image/jpeg,image/gif,image/webp,image/avif" onChange={e => upload(e.target.files[0])}/></label>}
      </details><details className="border-t border-line py-2 dark:border-black/10"><summary className="cursor-pointer text-xs font-medium text-ink dark:text-ink">Any CSS property</summary>
        <p className="my-2 text-[10px] text-muted">Any property or CSS variable supported by this browser.</p>
        <div className="flex gap-2"><input aria-label="CSS property" className={inputClass} placeholder="Property / --variable" value={customProperty} onChange={e => setCustomProperty(e.target.value)}/>
          <input aria-label="CSS value" className={inputClass} placeholder="Value" value={customValue} onChange={e => setCustomValue(e.target.value)}/>
          <button className={buttonClass} onClick={() => style(customProperty, customValue)}>Apply</button></div>
      </details></>}
    </div>}
    {error && <p role="alert" className="py-2 text-[11px] text-red-500">{error}</p>}
    <button onClick={save} disabled={saving} className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-2.5 text-xs font-semibold text-ink disabled:opacity-50">
      {saved ? <Check size={14}/> : <Save size={14}/>} {saving ? 'Saving…' : saved ? 'Saved to HTML' : 'Save to HTML (Instant)'}
    </button>
  </aside>
}
