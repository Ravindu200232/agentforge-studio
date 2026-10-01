'use client'

import { useEffect, useRef, useState } from 'react'
import {
  ArrowRight, Image as ImageIcon, Loader2, RefreshCw, Sparkles,
  UploadCloud, X, WandSparkles,
} from 'lucide-react'
import { api } from '@/lib/api'
import { Button, Modal, Tag, TextArea } from './ui'
import SitePictures from './SitePictures'
import { uploadMap } from '@/lib/picture-keys'
import { cn } from '@/lib/utils'

const ACCEPT_LOGO = '.png,.jpg,.jpeg,.webp,.gif,.bmp,image/*'

export default function LogoPanel({ idea, model, onAccept, onSkip }) {
  const [pictures, setPictures] = useState([])
  const [prompt, setPrompt] = useState('')
  const [state, setState] = useState('writing')
  const [img, setImg] = useState(null)
  const [file, setFile] = useState('')
  const [error, setError] = useState('')
  const [own, setOwn] = useState('')
  const [dragging, setDragging] = useState(false)
  const picker = useRef(null)
  const [waited, setWaited] = useState(0)
  const [draft, setDraft] = useState(0)

  useEffect(() => {
    let alive = true
    api.logoPrompt(idea, model)
      .then(r => {
        if (!alive) return
        setPrompt(r.prompt || idea.slice(0, 90))
        setState('ready')
      })
      .catch(e => { if (alive) { setError(e.message); setState('ready') } })
    return () => { alive = false }
  }, [idea, model])

  async function draw() {
    setState('drawing')
    setError('')
    setWaited(0)
    try {
      const r = await api.image(
        { prompt, name: 'logo', aspect: 'square', force: true },
        { onWait: setWaited })
      setImg(r.data_uri || '')
      setFile(r.file || '')
      setOwn('')
      setDraft(n => n + 1)
    } catch (e) {
      setError(e.message)
    }
    setState('ready')
  }

  async function upload(chosen) {
    if (!chosen) return
    if (!String(chosen.type || '').startsWith('image/')) {
      setError('Choose an image file for the logo.')
      return
    }
    setState('uploading')
    setError('')
    try {
      const r = await api.imageUpload(chosen, { name: 'logo' })
      setImg(r.data_uri || '')
      setFile(r.file || '')
      setOwn(chosen.name || 'your file')
    } catch (e) {
      setError(e.message)
    }
    setState('ready')
  }

  const waiting = state === 'drawing' || state === 'uploading' || state === 'writing'

  return (
    <Modal onClose={() => onSkip(uploadMap(pictures))} className="max-w-[1040px] overflow-hidden p-0">
      <div className="relative overflow-hidden bg-[radial-gradient(circle_at_8%_0%,rgba(191, 185, 255,.16),transparent_30%),linear-gradient(180deg,rgba(255,255,255,.97),rgba(247,249,253,.95))] dark:bg-[radial-gradient(circle_at_8%_0%,rgba(191, 185, 255,.15),transparent_30%),var(--bg2)]">
        <button onClick={() => onSkip(uploadMap(pictures))}
                className="absolute right-5 top-5 z-10 grid size-9 place-items-center rounded-full bg-black/80 text-muted shadow-sm ring-1 ring-line/70 backdrop-blur transition hover:text-ink dark:bg-black/25"
                title="Skip logo">
          <X className="size-4" />
        </button>

        <header className="px-7 pb-5 pt-7 pr-16">
          <div className="flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-[16px] bg-accent text-ink shadow-[0_12px_30px_rgba(191, 185, 255,.28)]"><WandSparkles className="size-5" /></span>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[.2em] text-accent">Brand identity</p>
              <h3 className="mt-1 text-[24px] font-semibold tracking-[-.035em] text-ink">Give the app a recognisable mark</h3>
              <p className="mt-1 text-[11px] text-muted">Generate one from the brief, upload your own, or continue without it.</p>
            </div>
          </div>
        </header>

        <div className="grid gap-5 px-7 pb-7 lg:grid-cols-[1.02fr_.98fr]">
          <section className="rounded-[28px] bg-black/76 p-5 shadow-[0_18px_50px_rgba(30,41,59,.08)] ring-1 ring-white/80 backdrop-blur-xl dark:bg-black/[.045] dark:ring-black/[.06]">
            <div className="flex items-center gap-2"><Sparkles className="size-4 text-accent" /><p className="text-[13px] font-semibold text-ink">Generate from the product brief</p></div>
            <p className="mt-1 text-[10.5px] leading-relaxed text-muted">The image agent turns the product direction into a concise logo prompt. You can edit it before drawing.</p>

            <TextArea value={prompt} rows={4} disabled={state === 'writing'}
                      placeholder={state === 'writing' ? 'Writing a visual brief…' : ''}
                      onChange={e => setPrompt(e.target.value)}
                      className="mt-4 w-full resize-y rounded-[20px] bg-black/[.025] px-4 py-3 text-[12px] leading-[1.65] text-ink outline-none ring-1 ring-line/70 placeholder:text-muted2 focus:ring-accent/40 dark:bg-black/[.035]" />

            <Button variant="solid" className="mt-3 rounded-full" onClick={draw}
                    disabled={state !== 'ready' || !prompt.trim()}>
              {state === 'drawing' ? <><Loader2 className="size-3.5 animate-spin" /> Drawing{waited ? ` · ${Math.round(waited)}s` : '…'}</>
                : img && !own ? <><RefreshCw className="size-3.5" /> Generate another</>
                  : <><Sparkles className="size-3.5" /> Generate logo</>}
            </Button>

            <div className="my-5 flex items-center gap-3"><span className="h-px flex-1 bg-line" /><span className="text-[9.5px] font-semibold uppercase tracking-[.18em] text-muted2">or use your own</span><span className="h-px flex-1 bg-line" /></div>

            <button type="button"
                    onDragOver={e => { e.preventDefault(); setDragging(true) }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={e => {
                      e.preventDefault(); setDragging(false)
                      upload(e.dataTransfer.files?.[0])
                    }}
                    onClick={() => picker.current?.click()}
                    disabled={waiting}
                    className={cn('group grid w-full place-items-center rounded-[24px] border border-dashed px-5 py-7 text-center transition',
                      dragging ? 'border-accent bg-accent shadow-[0_12px_35px_rgba(191, 185, 255,.12)]' : 'border-line2 bg-black/[.018] hover:border-accent/45 hover:bg-accent dark:bg-black/[.02]')}>
              <span className="grid size-11 place-items-center rounded-[16px] bg-white text-accent shadow-sm ring-1 ring-line/70 transition group-hover:-translate-y-0.5 dark:bg-black/[.06]"><UploadCloud className="size-5" /></span>
              <p className="mt-3 text-[12px] font-semibold text-ink">Drop an image here or choose a file</p>
              <p className="mt-1 text-[10.5px] text-muted">PNG, JPG, WEBP, GIF or BMP</p>
            </button>

            <div className="mt-5 grid grid-cols-3 gap-2">
              {USES.map(([where, what]) => <div key={where} className="rounded-[17px] bg-black/[.025] px-3 py-3 dark:bg-black/[.03]"><p className="text-[10.5px] font-semibold text-ink">{where}</p><p className="mt-1 text-[9.5px] leading-relaxed text-muted">{what}</p></div>)}
            </div>
          </section>

          <section className="flex min-h-[520px] flex-col rounded-[28px] bg-[linear-gradient(145deg,rgba(26,33,49,.97),rgba(50,58,85,.96))] p-5 text-ink shadow-[0_22px_56px_rgba(15,23,42,.16)] ring-1 ring-black/5">
            <div className="flex items-center gap-2"><ImageIcon className="size-4 text-muted" /><p className="text-[12px] font-semibold">Logo preview</p><span className="flex-1" />{own ? <Tag>{own}</Tag> : draft > 0 ? <Tag>draft {draft}</Tag> : null}</div>
            <div className="mt-4 grid min-h-[330px] flex-1 place-items-center overflow-hidden rounded-[24px] bg-[radial-gradient(circle_at_50%_30%,rgba(255,255,255,.11),transparent_40%),rgba(255,255,255,.055)] p-7 ring-1 ring-white/10">
              {state === 'drawing' || state === 'uploading' ? (
                <div className="text-center"><Loader2 className="mx-auto size-6 animate-spin text-ink" /><p className="mt-3 text-[12px] font-semibold">{state === 'drawing' ? 'Creating your mark' : 'Preparing your image'}</p><p className="mt-1 text-[10px] text-muted2">{waited ? `${Math.round(waited)} seconds` : 'This can take a moment.'}</p></div>
              ) : img ? (
                <img src={img} alt={own ? `Uploaded logo ${own}` : 'Generated logo'} className="max-h-[360px] max-w-full rounded-[18px] object-contain shadow-[0_20px_45px_rgba(0,0,0,.22)]" />
              ) : file ? (
                <p className="max-w-[260px] text-center text-[11px] leading-relaxed text-muted">The image was saved but this preview could not render it. Choose another file if you are unsure.</p>
              ) : (
                <div className="text-center"><span className="mx-auto grid size-14 place-items-center rounded-[20px] bg-black/[.08] ring-1 ring-white/10"><ImageIcon className="size-6 text-muted2" /></span><p className="mt-3 text-[12px] font-semibold text-white/78">Your logo will appear here</p><p className="mt-1 text-[10px] text-white/38">Nothing is committed until you accept it.</p></div>
              )}
            </div>

            {error && <p className="mt-3 rounded-[17px] bg-red-400/10 px-3.5 py-2.5 text-[10.5px] leading-relaxed text-red-100 ring-1 ring-red-300/15">{error}</p>}

            <div className="mt-4">
              <SitePictures pictures={pictures} onChange={setPictures} />
            </div>
          </section>
        </div>

        <footer className="flex flex-wrap items-center gap-3 border-t border-line/70 bg-black/58 px-7 py-4 backdrop-blur-xl dark:bg-black/15">
          <p className="min-w-0 flex-1 text-[10.5px] text-muted">Skipping keeps the SRS visual direction and uses a clean text wordmark.</p>
          <button onClick={() => onSkip(uploadMap(pictures))} className="rounded-full px-4 py-2 text-[11px] font-semibold text-muted transition hover:bg-black/[.04] hover:text-ink dark:hover:bg-black/[.05]">{pictures.length ? 'No logo · keep pictures' : 'Skip logo'}</button>
          <button disabled={!file} onClick={() => onAccept(file, uploadMap(pictures))}
                  className="inline-flex h-10 items-center gap-2 rounded-full bg-accent px-5 text-[11.5px] font-semibold text-ink shadow-[0_10px_24px_rgba(191, 185, 255,.28)] transition hover:bg-press disabled:pointer-events-none disabled:opacity-40">
            Use this logo <ArrowRight className="size-3.5" />
          </button>
        </footer>
      </div>

      <input ref={picker} type="file" hidden accept={ACCEPT_LOGO}
             onChange={e => {
               const chosen = e.target.files?.[0]
               e.target.value = ''
               upload(chosen)
             }} />
    </Modal>
  )
}

const USES = [
  ['App icon', 'favicon and header lockup'],
  ['Sign-in', 'brand anchor above auth forms'],
  ['Product UI', 'consistent mark across the app'],
]
