'use client'

/**
 * A live screencast of a browser the app is being driven in, shown in the preview.
 *
 *  - a TEST run (`shot.kind === 'test'`) fills the pane like the website itself: no window chrome,
 *    the page's own background around it, the pointer and the element being used drawn over it;
 *  - the agent's own browser keeps its small window frame, so it is not mistaken for the app.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { MousePointer2 } from 'lucide-react'
import { useStore } from '@/lib/store'

// Fallback timeout to terminate browser stream if disconnected without a close event.
const STALE_MS = 45000

function clamp(value) {
  return Math.max(0, Math.min(1, value))
}

function previewImageBox(stage, image) {
  const parent = stage.getBoundingClientRect()
  const naturalWidth = image.naturalWidth
  const naturalHeight = image.naturalHeight
  if (!parent.width || !parent.height || !naturalWidth || !naturalHeight) return null

  // `object-contain` letterboxes a frame inside the img element. Its DOM box
  // is the full stage, so calculate the actual painted image box before
  // mapping CDP's viewport coordinates into it. `object-top` keeps y at zero.
  const scale = Math.min(parent.width / naturalWidth, parent.height / naturalHeight)
  const width = naturalWidth * scale
  const height = naturalHeight * scale
  return { left: (parent.width - width) / 2, top: 0, width, height }
}

const LABEL = { click: 'click', type: 'typing', key: 'key' }

export default function AgentBrowser() {
  const shot = useStore(s => s.browserFrame)
  const [stale, setStale] = useState(false)
  const stageRef = useRef(null)
  const imageRef = useRef(null)
  const [imageBox, setImageBox] = useState(null)
  const [now, setNow] = useState(() => Date.now())

  useLayoutEffect(() => {
    const stage = stageRef.current
    const image = imageRef.current
    if (!stage || !image) return undefined

    const measure = () => {
      const box = previewImageBox(stage, image)
      if (box) setImageBox(box)
    }

    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(stage)
    observer.observe(image)
    return () => observer.disconnect()
  }, [shot?.frame])

  useEffect(() => {
    if (!shot?.frame) return
    setStale(false)
    const id = setTimeout(() => setStale(true), STALE_MS)
    return () => clearTimeout(id)
  }, [shot])

  // The click ring and the highlight fade after a moment; only this re-renders for it.
  useEffect(() => {
    if (!shot?.cursor?.at) return
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id)
  }, [shot?.cursor?.at])

  if (!shot?.frame || stale) return null

  const bare = shot.kind === 'test'
  const cursor = shot.cursor
  const viewport = shot.viewport
  const canPlaceCursor = cursor && viewport?.width && viewport?.height && imageBox
  const fx = value => imageBox.left + clamp(Number(value) / Number(viewport.width)) * imageBox.width
  const fy = value => imageBox.top + clamp(Number(value) / Number(viewport.height)) * imageBox.height
  const cursorStyle = canPlaceCursor ? { left: fx(cursor.x), top: fy(cursor.y) } : undefined
  const recent = cursor?.at ? now - cursor.at < 1500 : true
  const acting = cursor && cursor.action !== 'move' && recent
  const box = canPlaceCursor && acting && cursor.box ? {
    left: fx(cursor.box.x), top: fy(cursor.box.y),
    width: Math.max(4, (cursor.box.width / viewport.width) * imageBox.width),
    height: Math.max(4, (cursor.box.height / viewport.height) * imageBox.height),
  } : null

  return (
    <div className="absolute inset-0 z-[20] flex flex-col shadow-2xl"
         style={{ background: bare ? (shot.bg || '#ffffff') : 'var(--bg2)' }}>
      {!bare && (
        <div className="flex shrink-0 items-center gap-2 bg-panel px-3 py-2 border-b border-black/10">
          {['#ff5f57', '#febc2e', '#28c840'].map(colour => (
            <span key={colour} className="size-2.5 rounded-full"
                  style={{ background: colour }} />
          ))}
          <span className="ml-1.5 flex min-w-0 flex-1 items-center gap-2 rounded-full bg-black/25 px-3 py-1">
            <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-[#28c840]" />
            <span className="truncate font-mono text-[10px] text-muted">
              {shot.url || 'about:blank'}
            </span>
          </span>
          <span className="shrink-0 rounded-full bg-black/10 px-2 py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.14em] text-muted">
            agent
          </span>
        </div>
      )}

      <div ref={stageRef} className="relative min-h-0 flex-1 overflow-hidden">
        <img ref={imageRef} src={shot.frame} alt={bare ? 'The application, as the running test sees it' : "What the agent's browser is showing"}
             onLoad={() => {
               const stage = stageRef.current
               const image = imageRef.current
               if (!stage || !image) return
               const measured = previewImageBox(stage, image)
               if (measured) setImageBox(measured)
             }}
             className="size-full select-none object-contain object-top" />
        {box ? (
          <div aria-hidden="true" className="pointer-events-none absolute z-[5] rounded-[3px] border-2 border-sky-400 bg-sky-400/10 shadow-[0_0_0_3px_rgba(56,189,248,0.25)] transition-all duration-150"
               style={box} />
        ) : null}
        {canPlaceCursor ? (
          <div aria-hidden="true" className="pointer-events-none absolute z-10 -translate-x-1 -translate-y-1 transition-[left,top] duration-100 ease-out"
               style={cursorStyle}>
            {acting && cursor.action === 'click' ? (
              <span className="absolute left-1 top-1 size-5 animate-ping rounded-full bg-sky-400/45" />
            ) : null}
            <MousePointer2 className="relative size-6 fill-sky-300 text-slate-950 drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]" strokeWidth={2.5} />
            {acting && LABEL[cursor.action] ? (
              <span className="absolute left-5 top-5 whitespace-nowrap rounded bg-slate-950/80 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-sky-100">
                {LABEL[cursor.action]}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
