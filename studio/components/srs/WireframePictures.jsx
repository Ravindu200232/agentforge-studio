'use client'

import { useEffect, useRef, useState } from 'react'
import { ImagePlus, Loader2, Redo2, Undo2, X } from 'lucide-react'
import { PICTURE_SHAPES, PICTURE_TYPES, clamp } from '@/lib/picture-editor'
import { usePictureEditor } from '@/lib/use-picture-editor'
import { Button } from '../ui'

const inputStyle = 'w-full min-w-0 rounded-md border border-line bg-transparent px-2 py-1 text-xs text-ink outline-none focus:border-accent disabled:opacity-50'
const actionStyle = 'rounded-md border border-line px-2 py-1 text-xs text-ink hover:bg-ink/[.06] disabled:opacity-40'

function Action({ children, active, ...props }) {
  return <button type="button" className={actionStyle + (active ? ' bg-accent' : '')}
    aria-pressed={active} {...props}>{children}</button>
}

function NumberField({ label, value, min, max, step = 1, onChange }) {
  const [text, setText] = useState(String(value))
  useEffect(() => { setText(String(value)) }, [value])
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-1 text-[11px] text-muted">
      {label}
      <input className={inputStyle} type="number" value={text} min={min} max={max} step={step}
        onChange={event => {
          const raw = event.target.value
          setText(raw)
          if (raw !== '' && Number.isFinite(Number(raw)) && Number(raw) >= min && Number(raw) <= max) onChange(Number(raw))
        }} onBlur={() => {
          const next = text.trim() ? clamp(Number(text), min, max) : value
          if (Number.isFinite(next)) onChange(next)
          setText(String(Number.isFinite(next) ? next : value))
        }} />
    </label>
  )
}

function Slider({ label, value, min = 0, max = 200, step = 1, onChange }) {
  return (
    <label className="flex min-w-0 flex-col gap-0.5 text-[11px] text-muted">
      <span className="flex justify-between gap-2"><span>{label}</span><span className="tabular-nums text-ink">{Math.round(value * 100) / 100}</span></span>
      <input type="range" className="w-full accent-current" min={min} max={max} step={step} value={value}
        onChange={event => onChange(Number(event.target.value))} />
    </label>
  )
}

function Section({ label, children, open }) {
  return (
    <details open={open} className="min-w-0 border-b border-line px-3 py-2">
      <summary className="cursor-pointer text-xs font-semibold text-ink">{label}</summary>
      <div className="mt-2 flex flex-col gap-2">{children}</div>
    </details>
  )
}

export default function WireframePictures(props) {
  const editor = usePictureEditor(props)
  const { rows, picked, selected, waiting, locked, saving, dirty, error } = editor
  const fileInput = useRef(null)
  const replacing = useRef('')
  const browse = (replace = '') => {
    replacing.current = replace
    if (fileInput.current) {
      fileInput.current.multiple = !replace
      fileInput.current.click()
    }
  }
  const field = (key, label, min, max, step) =>
    <NumberField label={label} value={selected[key]} min={min} max={max} step={step} onChange={value => editor.update(key, value)} />
  const slider = (key, label, max, min, step) =>
    <Slider label={label} value={selected[key]} min={min} max={max} step={step} onChange={value => editor.update(key, value)} />
  const toggle = (key, label) => <Action active={selected[key]} onClick={() => editor.update(key, !selected[key])}>{label}</Action>
  const drop = event => {
    if (!event.dataTransfer.files.length) return
    event.preventDefault()
    editor.add([...event.dataTransfer.files])
  }

  return (
    <aside ref={editor.panel} aria-label="Wireframe picture editor"
      onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault() }} onDrop={drop}
      className="flex w-64 shrink-0 flex-col border-l border-line bg-panel sm:w-72">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <h2 className="text-sm font-semibold text-ink">Pictures</h2>
        <div className="flex gap-1">
          <Action aria-label="Undo picture change" title="Undo" disabled={!editor.canUndo || locked} onClick={() => editor.history('undo')}><Undo2 className="size-3.5" /></Action>
          <Action aria-label="Redo picture change" title="Redo" disabled={!editor.canRedo || locked} onClick={() => editor.history('redo')}><Redo2 className="size-3.5" /></Action>
          <Action aria-label="Close picture editor" disabled={saving} onClick={props.onClose}><X className="size-3.5" /></Action>
        </div>
      </div>
      <input ref={fileInput} type="file" accept={PICTURE_TYPES} multiple hidden onChange={event => {
        editor.add([...event.target.files], null, replacing.current)
        event.target.value = ''
      }} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-2 border-b border-line p-3">
          <Button type="button" variant="outline" disabled={locked} onClick={() => browse()}>
            <ImagePlus className="mr-1.5 size-4" /> Upload picture
          </Button>
          <p className="text-[11px] text-muted">Drop or paste pictures into the wireframe. Shift-click to select several.</p>
          {waiting && <p role="status" className="text-xs text-muted">Loading pictures…</p>}
          {error && <p role="alert" className="text-xs text-rose-500">{error}</p>}
        </div>
        {!!rows.length && (
          <Section label="Layers" open>
            <div className="max-h-32 overflow-auto" aria-label="Picture layers">
              {[...rows].reverse().map(row => (
                <button key={row.id} type="button" aria-pressed={editor.ids.includes(row.id)}
                  className={'block w-full truncate rounded px-2 py-1 text-left text-xs text-ink ' + (editor.ids.includes(row.id) ? 'bg-accent' : 'hover:bg-ink/[.06]')}
                  onClick={event => editor.choose(row.id, event.shiftKey || event.ctrlKey || event.metaKey)}>
                  {row.group ? 'Group · ' : ''}{row.name}
                </button>
              ))}
            </div>
          </Section>
        )}
        {!!picked.length && <fieldset disabled={locked} className="min-w-0">
          {selected && <>
            <Section label="Frame" open>
              <div className="flex gap-2">{field('x', 'X', 0, 50000)}{field('y', 'Y', 0, 50000)}</div>
              <div className="flex gap-2">{field('w', 'Width', 8, 10000)}{field('h', 'Height', 8, 10000)}</div>
              <div className="flex flex-wrap gap-1">{toggle('locked', 'Lock ratio')}<Action onClick={() => browse(selected.id)}>Replace</Action></div>
              <label className="flex flex-col gap-1 text-[11px] text-muted">
                Frame shape
                <select value={selected.shape} onChange={event => editor.update('shape', event.target.value)} className={inputStyle}>
                  {PICTURE_SHAPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              {selected.shape === 'rounded' && field('radius', 'Corner radius', 0, 5000)}
              <label className="flex flex-col gap-1 text-[11px] text-muted">
                Alt text
                <input className={inputStyle} value={selected.alt} maxLength={300} onChange={event => editor.update('alt', event.target.value)} />
              </label>
            </Section>
            <Section label="Crop and transform" open>
              <div className="flex flex-wrap gap-1">
                <Action active={selected.fit === 'fit'} onClick={() => editor.update('fit', 'fit')}>Fit</Action>
                <Action active={selected.fit === 'fill'} onClick={() => editor.update('fit', 'fill')}>Fill</Action>
                <Action active={editor.crop} onClick={() => editor.setCrop(!editor.crop)}>Crop</Action>
                <Action onClick={() => editor.update('fit', selected.fit)}>Reset crop</Action>
              </div>
              {editor.crop && <p className="text-[11px] text-muted">Drag the picture inside its frame to pan.</p>}
              {slider('zoom', 'Crop zoom', 5, 1, 0.05)}
              {field('rotation', 'Rotation (°)', -360, 360)}
              <div className="flex flex-wrap gap-1">{toggle('flipX', 'Flip horizontal')}{toggle('flipY', 'Flip vertical')}</div>
            </Section>
            <Section label="Appearance">
              <div className="flex items-end gap-2">
                {field('border', 'Border thickness', 0, 100)}
                <label className="flex flex-col gap-1 text-[11px] text-muted">Border color
                  <input className="h-7 w-full cursor-pointer rounded border border-line" type="color" value={selected.color}
                    onChange={event => editor.update('color', event.target.value)} />
                </label>
              </div>
              {slider('opacity', 'Opacity', 100)}
              {slider('shadow', 'Shadow', 64)}
              {slider('brightness', 'Brightness')}
              {slider('contrast', 'Contrast')}
              {slider('saturation', 'Saturation')}
            </Section>
          </>}
          <Section label="Arrange" open={picked.length > 1 ? true : undefined}>
            <div className="flex flex-wrap gap-1">
              <Action onClick={() => editor.arrange('forward')}>Bring forward</Action>
              <Action onClick={() => editor.arrange('backward')}>Send backward</Action>
              <Action onClick={editor.duplicate}>Duplicate</Action>
              <Action onClick={editor.remove}>Delete</Action>
              <Action disabled={picked.length < 2} onClick={() => editor.arrange('group')}>Group</Action>
              <Action disabled={!picked.some(row => row.group)} onClick={() => editor.arrange('ungroup')}>Ungroup</Action>
            </div>
            {picked.length > 1 && <>
              <div className="flex flex-wrap gap-1">
                {[['x', 'start', 'Left'], ['x', 'center', 'Center'], ['x', 'end', 'Right'],
                  ['y', 'start', 'Top'], ['y', 'center', 'Middle'], ['y', 'end', 'Bottom']].map(([axis, edge, label]) =>
                  <Action key={label} onClick={() => editor.arrange('align', axis, edge)}>Align {label.toLowerCase()}</Action>)}
              </div>
              <div className="flex flex-wrap gap-1">
                <Action disabled={picked.length < 3} onClick={() => editor.arrange('distribute', 'x')}>Distribute horizontally</Action>
                <Action disabled={picked.length < 3} onClick={() => editor.arrange('distribute', 'y')}>Distribute vertically</Action>
              </div>
            </>}
          </Section>
        </fieldset>}
      </div>
      <div className="flex items-center justify-end gap-2 border-t border-line p-3">
        <span role="status" className="mr-auto text-xs text-muted">{dirty ? 'Unsaved changes' : ''}</span>
        <Button type="button" variant="outline" disabled={saving} onClick={props.onClose}>Cancel</Button>
        <Button type="button" variant="solid" disabled={locked || !dirty} onClick={editor.save}>
          {saving && <Loader2 className="mr-1.5 size-3.5 animate-spin" />}Save
        </Button>
      </div>
    </aside>
  )
}
