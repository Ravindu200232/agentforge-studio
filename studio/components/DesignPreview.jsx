'use client'

/** Renders an interactive live preview of the design theme using inline styles and component tokens. */

const SHADOWS = {
  flat: 'none',
  subtle: '0 1px 2px rgba(15,23,42,.06), 0 1px 3px rgba(15,23,42,.05)',
  layered: '0 4px 6px -1px rgba(15,23,42,.08), 0 10px 15px -3px rgba(15,23,42,.08)',
  dramatic: '0 10px 20px -5px rgba(15,23,42,.18), 0 20px 35px -10px rgba(15,23,42,.16)',
}

const BORDERS = { hairline: '1px', defined: '1.5px', bold: '2.5px' }
const UNITS = { compact: 6, cozy: 8, comfortable: 11 }
const SCALES = { compact: 0.94, balanced: 1, comfortable: 1.06, dramatic: 1.14 }

// The content column, as a share of the page. The catalogue's widths are for a
// real viewport; shown at this size, what reads is the proportion.
const WIDTHS = { 1120: '78%', 1280: '87%', 1440: '95%', full: '100%' }

// How long anything here takes to react, from the motion choice. Hovering the
// preview is then the setting itself, not a description of it.
const SPEEDS = { none: '0ms', subtle: '150ms', expressive: '260ms' }

/** How the product speaks, in the two places a page always speaks. */
const VOICE = {
  professional: { cta: 'Get started', second: 'Learn more', form: 'Your details' },
  friendly: { cta: 'Jump in', second: 'Have a look', form: 'Tell us about you' },
  playful: { cta: 'Let’s go', second: 'Nose around', form: 'The fun part' },
  bold: { cta: 'Start now', second: 'See how', form: 'Your details' },
  minimal: { cta: 'Start', second: 'More', form: 'Details' },
  luxury: { cta: 'Begin', second: 'Discover', form: 'Your particulars' },
}

/** What the product is called, from the brief, so the preview is about it. */
function productName(goal) {
  const words = String(goal || '').replace(/[^\w\s]/g, ' ').split(/\s+/).filter(Boolean)
  const skip = new Set(['a', 'an', 'the', 'build', 'make', 'create', 'app', 'site',
                        'application', 'website', 'with', 'for', 'that', 'where'])
  const kept = words.filter(w => !skip.has(w.toLowerCase())).slice(0, 2)
  if (!kept.length) return 'Your product'
  return kept.map(w => w[0].toUpperCase() + w.slice(1).toLowerCase()).join(' ')
}

export default function DesignPreview({ tokens, question, pick, screens = [] }) {
  const corner = (question.radii || []).find(r => r.id === pick.radius)?.value || '10px'
  const font = (question.fonts || []).find(f => f.id === pick.font)
  const unit = UNITS[pick.density] || 8
  const scale = SCALES[pick.typeScale] || 1
  const shadow = SHADOWS[pick.elevation] || SHADOWS.subtle
  const line = `${BORDERS[pick.border] || '1px'} solid ${tokens.border}`
  const name = productName(question.goal)
  const nav = screens.slice(0, 4)
  const say = VOICE[pick.tone] || VOICE.professional
  const speed = SPEEDS[pick.motion] || SPEEDS.subtle
  // AAA constrains muted greys, so under it the quiet text stops being quiet.
  const quiet = pick.contrast === 'aaa' ? tokens.text : tokens.textMuted

  const size = (base) => `${Math.round(base * scale * 10) / 10}px`
  const card = {
    background: tokens.surface, borderRadius: corner, border: line,
    boxShadow: shadow, padding: unit * 1.5, transition: `all ${speed} ease`,
  }
  const column = {
    width: WIDTHS[pick.container] || '100%',
    marginInline: 'auto',
    transition: `width ${speed} ease`,
  }

  return (
    <div className="overflow-hidden" style={{ borderRadius: corner, border: line }}>
      <div style={{ background: tokens.background, fontFamily: font?.body,
                    transition: `background ${speed} ease` }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: unit,
                      padding: `${unit}px ${unit * 1.5}px`, borderBottom: line,
                      background: tokens.surface }}>
          <span style={{ fontFamily: font?.heading, color: tokens.primary,
                         fontSize: size(12), fontWeight: 700 }}>{name}</span>
          <span style={{ flex: 1 }} />
          {nav.map(screen => (
            <span key={screen.id} style={{ color: tokens.textMuted, fontSize: size(8.5) }}>
              {screen.label}
            </span>
          ))}
          <span style={{ background: tokens.primary, color: tokens.onPrimary,
                         borderRadius: corner, padding: `${unit * 0.4}px ${unit}px`,
                         fontSize: size(8.5), fontWeight: 600 }}>
            Sign in
          </span>
        </div>

        {/* Hero */}
        <div style={{ padding: unit * 2 }}>
         <div style={column}>
          <p style={{ fontFamily: font?.heading, color: tokens.text,
                      fontSize: size(20), fontWeight: 700, lineHeight: 1.15, margin: 0 }}>
            {nav[0]?.label || 'Everything in one place'}
          </p>
          <p style={{ color: quiet, fontSize: size(9.5), lineHeight: 1.6,
                      margin: `${unit}px 0 0`, maxWidth: '46ch' }}>
            {screens[0]?.what
              || 'This is how the product’s type, spacing and surfaces will read.'}
          </p>
          <div style={{ display: 'flex', gap: unit * 0.75, marginTop: unit * 1.5 }}>
            <span style={{ background: tokens.primary, color: tokens.onPrimary,
                           borderRadius: corner, padding: `${unit * 0.55}px ${unit * 1.4}px`,
                           fontSize: size(9), fontWeight: 600, boxShadow: shadow,
                           transition: `all ${speed} ease` }}>
              {say.cta}
            </span>
            <span style={{ background: 'transparent', color: tokens.text, border: line,
                           borderRadius: corner, padding: `${unit * 0.55}px ${unit * 1.4}px`,
                           fontSize: size(9), transition: `all ${speed} ease` }}>
              {say.second}
            </span>
          </div>
         </div>
        </div>

        {/* Cards */}
        <div style={{ padding: `0 ${unit * 2}px ${unit * 1.5}px` }}>
         <div style={{ ...column, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: unit }}>
          {(screens.length ? screens.slice(0, 2) : [null, null]).map((screen, i) => (
            <div key={i} style={card}>
              <div style={{ height: unit * 3, borderRadius: corner,
                            background: tokens.surfaceAlt, marginBottom: unit }} />
              <p style={{ fontFamily: font?.heading, color: tokens.text, margin: 0,
                          fontSize: size(10), fontWeight: 600 }}>
                {screen?.label || (i ? 'Second item' : 'First item')}
              </p>
              <p style={{ color: quiet, fontSize: size(8.5), margin: `${unit * 0.4}px 0 0`,
                          lineHeight: 1.5 }}>
                {(screen?.what || 'A short line of supporting detail.').slice(0, 64)}
              </p>
            </div>
          ))}
         </div>
        </div>

        {/* A form, because most products have one */}
        <div style={{ padding: `0 ${unit * 2}px ${unit * 1.5}px` }}>
         <div style={column}>
          <div style={card}>
            <p style={{ color: quiet, fontSize: size(8), margin: 0,
                        textTransform: 'uppercase', letterSpacing: '.08em' }}>
              {say.form}
            </p>
            <div style={{ display: 'flex', gap: unit * 0.75, marginTop: unit * 0.75 }}>
              <span style={{ flex: 1, border: line, borderRadius: corner,
                             padding: `${unit * 0.5}px ${unit * 0.8}px`, fontSize: size(8.5),
                             color: quiet, background: tokens.background }}>
                name@example.com
              </span>
              <span style={{ background: tokens.accent || tokens.primary, color: tokens.onPrimary,
                             borderRadius: corner, padding: `${unit * 0.5}px ${unit}px`,
                             fontSize: size(8.5), fontWeight: 600 }}>
                Send
              </span>
            </div>
            <div style={{ display: 'flex', gap: unit * 0.5, marginTop: unit }}>
              {['success', 'warning', 'danger'].map(role => (
                <span key={role} style={{ flex: 1, height: 3, borderRadius: 99,
                                          background: tokens[role] || tokens.border }} />
              ))}
            </div>
          </div>
         </div>
        </div>

        {/* Footer */}
        <div style={{ borderTop: line, background: tokens.surfaceAlt,
                      padding: `${unit}px ${unit * 2}px` }}>
          <span style={{ color: quiet, fontSize: size(8) }}>
            {name} — {screens.length ? `${screens.length} screens` : 'every screen in the plan'}
          </span>
        </div>
      </div>
    </div>
  )
}
