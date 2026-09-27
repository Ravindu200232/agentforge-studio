'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Monitor, Smartphone, Tablet, RotateCw } from 'lucide-react'
import { api } from '@/lib/api'

const FALLBACK_IMAGES = [
  '/__agentforge/preview-workspace.png',
  '/__agentforge/preview-moodboard.png',
]

function color(value, fallback) {
  return typeof value === 'string' && /^#[0-9a-f]{3}(?:[0-9a-f]{3})?$/i.test(value) ? value : fallback
}

function font(value) {
  return typeof value === 'string' && /^[\w\s-]{1,60}$/.test(value) ? value : 'Inter'
}

function isDark(hex) {
  const value = hex.replace('#', '')
  const channels = value.length === 3 ? [...value].map(part => parseInt(part + part, 16)) : [0, 2, 4].map(index => parseInt(value.slice(index, index + 2), 16))
  return channels.reduce((total, channel, index) => total + channel * [0.2126, 0.7152, 0.0722][index], 0) < 120
}

function preferredPage(pages) {
  return pages.find(page => page.has_html && /^(\/|\/home\/?|\/index\/?|\/landing\/?)$/i.test(page.route))
    || pages.find(page => page.has_html && /home|landing/i.test(page.page_name || ''))
    || pages.find(page => page.has_html)
    || pages.find(page => /^(\/|\/home\/?|\/index\/?|\/landing\/?)$/i.test(page.route))
    || pages[0]
}

function previewCss(state, forceDark) {
  const dark = state.appearance === 'Dark' || (state.appearance === 'Light and dark' && forceDark)
  const primary = color(state.colors?.primary, '#2563eb')
  const secondary = color(state.colors?.secondary, '#64748b')
  const chosenSurface = color(state.colors?.surface, dark ? '#101827' : '#ffffff')
  const surface = dark && !isDark(chosenSurface) ? '#101827' : chosenSurface
  const chosenInk = color(state.colors?.text, dark ? '#f8fafc' : '#0f172a')
  const ink = dark && isDark(chosenInk) ? '#f8fafc' : chosenInk
  const button = color(state.button || state.colors?.button, primary)
  const success = color(state.colors?.success, '#16a34a')
  const warning = color(state.colors?.warning, '#d97706')
  const danger = color(state.colors?.danger, '#dc2626')
  const soft = dark ? '#1c2940' : '#f3f7fc'
  const muted = dark ? '#bac8db' : '#52637a'
  const border = state.border === 'None' ? 'transparent' : state.border === 'Bold' ? (dark ? '#64748b' : '#94a3b8') : (dark ? '#334155' : '#d9e2ef')
  const radius = ['0px', '6px', '12px', '9999px'].includes(state.radius) ? state.radius : '12px'
  const cardRadius = radius === '9999px' ? '24px' : radius
  const shadow = state.shadow === 'Flat' ? 'none' : state.shadow === 'Dramatic' ? '0 28px 65px -25px rgba(15,23,42,.42)' : '0 18px 48px -28px rgba(15,23,42,.28)'
  const spacing = state.density === 'Ultra Compact' ? '.7' : state.density === 'Compact' ? '.85' : state.density === 'Spacious' ? '1.18' : '1'
  const motion = state.motion === 'None' ? '0ms' : state.motion === 'Expressive' ? '650ms' : '300ms'
  const heading = font(state.headingFont)
  const body = font(state.bodyFont)

  return `
    @import url('https://fonts.googleapis.com/css2?family=${encodeURIComponent(heading)}:wght@400;500;600;700;800&family=${encodeURIComponent(body)}:wght@400;500;600;700&display=swap');
    :root{--af-primary:${primary};--af-secondary:${secondary};--af-button:${button};--af-surface:${surface};--af-soft:${soft};--af-ink:${ink};--af-muted:${muted};--af-border:${border};--af-radius:${radius};--af-card-radius:${cardRadius};--af-shadow:${shadow};--af-spacing:${spacing};--af-motion:${motion}}
    html{scroll-behavior:smooth!important}body{margin:0!important;background:radial-gradient(circle at 95% 0%,${primary}18,transparent 36%),var(--af-surface)!important;color:var(--af-ink)!important;font-family:'${body}',Inter,system-ui,sans-serif!important;-webkit-font-smoothing:antialiased}
    body,body *{box-sizing:border-box}body :is(p,li,label,td,th,small){color:var(--af-ink);font-family:'${body}',Inter,system-ui,sans-serif!important}
    body :is(h1,h2,h3,h4,h5,h6){font-family:'${heading}',Inter,system-ui,sans-serif!important;color:var(--af-ink)!important;letter-spacing:-.035em!important;line-height:1.12!important}
    body h1{font-size:clamp(2.1rem,4.8vw,4.5rem)!important;font-weight:750!important}body h2{font-size:clamp(1.65rem,3vw,2.7rem)!important;font-weight:720!important}body h3{font-size:clamp(1.2rem,2vw,1.7rem)!important;font-weight:680!important}
    body :is(header,nav,main,section,article,aside,footer){border-color:var(--af-border)!important}
    body .wf-bg{background:var(--af-surface)!important}body .wf-bg-light{background:var(--af-soft)!important}
    body .wf-border-thin{border-color:var(--af-border)!important;border-radius:var(--af-radius)!important}
    body :is([class*="bg-gray"],[class*="bg-zinc"],[class*="bg-neutral"],[class*="bg-slate"]){background-color:var(--af-soft)!important}
    body :is([class*="bg-white"],[class*="bg-black"]){background-color:var(--af-surface)!important}
    body :is([class*="text-gray"],[class*="text-zinc"],[class*="text-neutral"],[class*="text-slate"],[class*="text-black"]){color:var(--af-ink)!important}
    body :is([class*="text-green"],[class*="text-emerald"]){color:${success}!important}body :is([class*="bg-green"],[class*="bg-emerald"]){background-color:${success}!important}
    body :is([class*="text-amber"],[class*="text-yellow"],[class*="text-orange"]){color:${warning}!important}body :is([class*="bg-amber"],[class*="bg-yellow"],[class*="bg-orange"]){background-color:${warning}!important}
    body :is([class*="text-red"],[class*="text-rose"]){color:${danger}!important}body :is([class*="bg-red"],[class*="bg-rose"]){background-color:${danger}!important}
    body :is([class*="border-black"],[class*="border-gray"],[class*="border-zinc"],[class*="border-slate"]){border-color:var(--af-border)!important}
    body :is(article,section[class*="border"],div[class*="rounded"][class*="border"]){border-radius:var(--af-card-radius)!important;box-shadow:var(--af-shadow);transition:transform var(--af-motion) ease,box-shadow var(--af-motion) ease}
    body :is(header,footer,section)[class*="wf-border"]{border:0!important;box-shadow:none!important}
    body section:has(h1){background:linear-gradient(135deg,${primary}14,${secondary}15,var(--af-surface))!important;border-radius:var(--af-card-radius)!important;padding:clamp(1.5rem,4vw,4rem)!important}
    body :is(button,input[type="button"],input[type="submit"],a[class*="bg-"]){background:linear-gradient(135deg,var(--af-button),var(--af-secondary))!important;color:#fff!important;border:1px solid transparent!important;border-radius:var(--af-radius)!important;padding:calc(.65rem * var(--af-spacing)) calc(1.2rem * var(--af-spacing))!important;font-family:'${body}',Inter,system-ui,sans-serif!important;font-weight:650!important;box-shadow:0 12px 26px -15px var(--af-button)!important;transition:transform var(--af-motion) ease,filter var(--af-motion) ease!important}
    body :is(button,input[type="button"],input[type="submit"],a[class*="bg-"]):hover{transform:translateY(-2px);filter:brightness(1.08)}
    body :is(input:not([type="button"]):not([type="submit"]),select,textarea){background:var(--af-surface)!important;color:var(--af-ink)!important;border:1px solid var(--af-border)!important;border-radius:var(--af-radius)!important;padding:calc(.65rem * var(--af-spacing)) .85rem!important;box-shadow:none!important}
    body :is(input,select,textarea,button,a):focus-visible{outline:3px solid ${primary}66!important;outline-offset:2px!important}
    body :is(a:not([class*="bg-"]),nav a){color:var(--af-primary)!important;text-decoration:none!important}
    body :is(figure,img){border-radius:var(--af-card-radius)!important}body img{object-fit:cover}
    [data-af-preview-photo]{display:block!important;overflow:hidden!important;background:var(--af-soft)!important;border:1px solid var(--af-border)!important;border-radius:var(--af-card-radius)!important;box-shadow:var(--af-shadow)}
    [data-af-preview-photo]:not([class*="h-"]){min-height:180px}
    [data-af-preview-photo] img{display:block;width:100%;height:100%;object-fit:cover}
    [data-af-preview-logo]{display:grid!important;place-items:center;background:var(--af-primary)!important;color:#fff!important;border:0!important;border-radius:var(--af-radius)!important;font-family:'${heading}',Inter,system-ui,sans-serif!important;font-weight:800!important;letter-spacing:-.05em}
    body .annotation{display:none!important}
    @keyframes af-reveal{from{opacity:.55;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
    body :is(header,section,footer){animation:af-reveal var(--af-motion) both}body section:nth-of-type(2){animation-delay:90ms}body section:nth-of-type(3){animation-delay:160ms}
    @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:0ms!important;transition-duration:0ms!important;scroll-behavior:auto!important}}
  `
}

function prepareHtml(html, imageUrls) {
  if (typeof DOMParser === 'undefined' || !html) return ''
  const doc = new DOMParser().parseFromString(html, 'text/html')
  doc.querySelectorAll('script,iframe,object,embed,base,meta[http-equiv],link[rel="stylesheet"]').forEach(node => node.remove())
  doc.querySelectorAll('button').forEach(button => {
    if (/grid\s*\/\s*blueprint guides|ux annotations\s*\/\s*labels/i.test(button.textContent || '')) button.remove()
  })
  doc.querySelectorAll('.utility-bar').forEach(bar => {
    if (/wireframe|blueprint|annotations/i.test(bar.textContent || '')) bar.remove()
  })
  const canvas = doc.querySelector('#canvas, #wireframe-canvas, [data-wireframe-canvas]')
  if (canvas && canvas.querySelector('header,main,section')) {
    canvas.classList.remove('blueprint-grid')
    doc.body.replaceChildren(canvas)
  }
  doc.querySelectorAll('.annotation').forEach(label => label.remove())
  ;[...doc.body.children].forEach(node => {
    if (/^wireframe blueprint\b/i.test((node.textContent || '').trim())) node.remove()
  })
  doc.querySelectorAll('span,p').forEach(label => {
    if (!label.children.length && /^\[[a-z][a-z\d\s-]{2,30}\]$/i.test((label.textContent || '').trim())) label.remove()
  })
  doc.querySelectorAll('*').forEach(node => {
    for (const attr of [...node.attributes]) {
      if (/^on/i.test(attr.name) || attr.name === 'srcdoc' || /^(href|action|formaction)$/i.test(attr.name)) node.removeAttribute(attr.name)
    }
  })

  let imageIndex = 0
  doc.querySelectorAll('.img-placeholder,[class*="image-placeholder"],[class*="media-placeholder"]').forEach(box => {
    if (!box.querySelector('svg') || box.hasAttribute('data-af-preview-photo')) return
    const label = (box.textContent || '').trim()
    box.replaceChildren()
    if (/logo/i.test(label)) {
      box.setAttribute('data-af-preview-logo', '')
      box.textContent = label.replace(/[^a-z0-9]+/gi, ' ').trim().split(/\s+/).slice(0, 2).map(word => word[0]).join('').toUpperCase() || '✦'
      return
    }
    box.setAttribute('data-af-preview-photo', '')
    const image = doc.createElement('img')
    image.src = imageUrls[imageIndex % imageUrls.length]
    image.alt = label.replace(/[\[\]]/g, '').trim() || 'Visual for the approved page layout'
    image.loading = 'lazy'
    box.appendChild(image)
    imageIndex += 1
  })
  doc.querySelectorAll('p,span,div').forEach(label => {
    if (label.children.length || !/\b(image|banner|photo|avatar|media)\b[\s/]*\bplaceholder\b/i.test(label.textContent || '')) return
    const parent = label.parentElement
    const box = parent && parent.children.length <= 4 && parent.querySelector('svg') && !parent.querySelector('button,a,input') ? parent : label
    if (box.hasAttribute('data-af-preview-photo')) return
    box.replaceChildren()
    box.setAttribute('data-af-preview-photo', '')
    const image = doc.createElement('img')
    image.src = imageUrls[imageIndex % imageUrls.length]
    image.alt = 'Visual for the approved page layout'
    image.loading = 'lazy'
    box.appendChild(image)
    imageIndex += 1
  })

  const hostStyles = [...document.querySelectorAll('link[rel="stylesheet"]')]
    .map(link => link.href).filter(href => href.startsWith(location.origin))
  for (const href of hostStyles) {
    const link = doc.createElement('link')
    link.rel = 'stylesheet'
    link.href = href
    doc.head.appendChild(link)
  }
  // The SRS wireframe is authored with Tailwind utilities. Run only this
  // trusted utility compiler; every script supplied by the wireframe is gone.
  const tailwind = doc.createElement('script')
  tailwind.src = 'https://cdn.tailwindcss.com'
  doc.head.appendChild(tailwind)
  const style = doc.createElement('style')
  style.id = 'agentforge-preview-style'
  doc.head.appendChild(style)
  const bridge = doc.createElement('script')
  bridge.textContent = `window.addEventListener('message',function(event){if(event.source!==window.parent||event.data?.type!=='agentforge-preview-style')return;const style=document.getElementById('agentforge-preview-style');if(style)style.textContent=event.data.css;});`
  doc.head.appendChild(bridge)
  return `<!doctype html>${doc.documentElement.outerHTML}`
}

export default function WireframeStylePreview({ projectId, imageOwner, state }) {
  const frame = useRef(null)
  const pagePicked = useRef(false)
  const [pages, setPages] = useState([])
  const [drawing, setDrawing] = useState(false)
  const [route, setRoute] = useState('')
  const [html, setHtml] = useState('')
  const [images, setImages] = useState([])
  const [device, setDevice] = useState('Desktop')
  const [forceDark, setForceDark] = useState(false)
  const [problem, setProblem] = useState('')
  const [requesting, setRequesting] = useState(false)

  useEffect(() => {
    if (!projectId) return
    pagePicked.current = false
    let active = true
    const refresh = () => api.srs(`/projects/${encodeURIComponent(projectId)}/wireframes`)
      .then(answer => {
        if (!active) return
        const next = answer?.pages || []
        setPages(next)
        setDrawing(Boolean(answer?.drawing))
        setRoute(current => {
          const preferred = preferredPage(next)?.route || ''
          return pagePicked.current && next.some(page => page.route === current) ? current : preferred
        })
        setProblem('')
      }).catch(failure => { if (active) setProblem(failure?.message || 'Could not read the SRS wireframes.') })
    refresh()
    const poll = setInterval(refresh, 5000)
    return () => { active = false; clearInterval(poll) }
  }, [projectId])

  const selected = pages.find(page => page.route === route)
  useEffect(() => {
    if (!projectId || !route || !selected?.has_html) { setHtml(''); return }
    let active = true
    fetch(api.wireframeHtmlUrl(projectId, route)).then(response => {
      if (!response.ok) throw new Error(`Wireframe HTML returned ${response.status}`)
      return response.text()
    }).then(markup => { if (active) { setHtml(markup); setProblem('') } })
      .catch(failure => { if (active) { setHtml(''); setProblem(failure?.message || 'Could not load the selected page.') } })
    return () => { active = false }
  }, [projectId, route, selected?.has_html])

  useEffect(() => {
    if (!imageOwner) return
    let active = true
    api.siteImages(imageOwner).then(answer => {
      if (active) setImages((answer?.images || []).filter(row => !/logo|favicon/i.test(row.purpose || '')).map(row => api.siteImageUrl(imageOwner, row.file)))
    }).catch(() => {})
    return () => { active = false }
  }, [imageOwner])

  const css = useMemo(() => previewCss(state, forceDark), [state, forceDark])
  const srcDoc = useMemo(() => prepareHtml(html, images.length ? images : FALLBACK_IMAGES), [html, images])
  const sendStyle = () => frame.current?.contentWindow?.postMessage({ type: 'agentforge-preview-style', css }, '*')
  useEffect(sendStyle, [css, srcDoc])

  async function drawPage() {
    if (!route || requesting) return
    setRequesting(true); setProblem('')
    try {
      await api.drawWireframeHtml(projectId, route)
      const answer = await api.srs(`/projects/${encodeURIComponent(projectId)}/wireframes`)
      setPages(answer?.pages || [])
    } catch (failure) { setProblem(failure?.message || 'The page could not be drawn.') }
    finally { setRequesting(false) }
  }

  const width = device === 'Phone' ? 390 : device === 'Tablet' ? 760 : '100%'
  return <div className="overflow-hidden rounded-2xl border border-line bg-panel shadow-2xl">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-panel2 px-3 py-2.5">
      <div className="flex min-w-0 items-center gap-2"><span className="size-2.5 rounded-full bg-[#ff5f56]" /><span className="size-2.5 rounded-full bg-[#ffbd2e]" /><span className="size-2.5 rounded-full bg-[#27c93f]" /><span className="ml-1 truncate text-[11px] font-semibold text-ink">SRS page · live design preview</span></div>
      <div className="flex items-center gap-1">
        {pages.length > 1 && <select aria-label="Preview page" value={route} onChange={event => { pagePicked.current = true; setRoute(event.target.value) }} className="mr-2 max-w-[150px] rounded-md border border-line bg-panel px-1.5 py-1 text-[11px] text-ink">{pages.map(page => <option key={page.route} value={page.route}>{page.page_name || page.route}</option>)}</select>}
        {[['Desktop', Monitor], ['Tablet', Tablet], ['Phone', Smartphone]].map(([name, Icon]) => <button key={name} type="button" title={name} onClick={() => setDevice(name)} className={`rounded-md border px-1.5 py-1 ${device === name ? 'border-accent bg-accent text-ink' : 'border-line text-muted'}`}><Icon className="size-3" /></button>)}
        {state.appearance === 'Light and dark' && <button type="button" onClick={() => setForceDark(value => !value)} className="ml-1 rounded-md border border-line px-2 py-1 text-[11px] text-muted">{forceDark ? 'Light' : 'Dark'}</button>}
      </div>
    </div>
    <div className="min-h-[650px] overflow-auto bg-[#e9eef6] p-2 sm:p-4">
      {srcDoc ? <iframe ref={frame} title={`${selected?.page_name || route} styled SRS wireframe`} sandbox="allow-scripts" srcDoc={srcDoc} onLoad={sendStyle} className="mx-auto block min-h-[750px] border-0 bg-white shadow-xl" style={{ width, maxWidth: '100%', height: 'min(78vh, 980px)' }} />
        : <div className="flex min-h-[640px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-line bg-panel px-6 text-center text-sm text-muted"><p className="font-medium text-ink">{drawing || requesting ? 'Drawing your SRS page…' : selected ? `The ${selected.page_name || selected.route} wireframe is not ready yet.` : 'Waiting for pages from the approved SRS.'}</p><p className="max-w-sm text-xs">This preview uses the approved page HTML, so its sections and controls stay in the same order.</p>{selected && !selected.has_html && !drawing && <button type="button" onClick={drawPage} disabled={requesting} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-ink"><RotateCw className="size-3" /> Draw this page</button>}</div>}
    </div>
    {problem && <p role="alert" className="border-t border-line px-3 py-2 text-xs text-bad">{problem}</p>}
  </div>
}
