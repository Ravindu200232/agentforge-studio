'use client'

import { forwardRef, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'


/** Shared action button. */
export function Button({ variant = 'ghost', size = 'md', className, ...rest }) {
  const iconOnly = size === 'icon' || size === 'icon-sm'
  return (
    <button
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 rounded-xl font-display font-semibold',
        'transition-all duration-200 disabled:pointer-events-none disabled:opacity-45 cursor-pointer',
        iconOnly ? 'justify-center' : 'justify-start text-left',
        { sm: 'h-[28px] px-2.5 text-[11px]', md: 'h-[34px] px-3.5 text-[12.5px]',
          lg: 'h-[40px] px-4 text-[13.5px]', icon: 'size-[34px] p-0',
          'icon-sm': 'size-[28px] p-0' }[size],
        { solid: 'border border-accent bg-accent text-ink shadow-[0_8px_16px_0_rgba(191, 185, 255,0.24)] '
               + 'hover:bg-press hover:border-press active:bg-deep',
          outline: 'border border-line2 text-ink hover:bg-ink/[.06]',
          ghost: 'border border-transparent text-muted hover:bg-ink/[.06] hover:text-ink',
          accent: 'border border-transparent bg-accent text-ink hover:bg-accent',
          subtle: 'border border-line bg-panel text-ink hover:bg-raised shadow-sm',
        }[variant],
        className)}
      {...rest} />
  )
}

/** Compact status label. */
export function Tag({ tone = 'mute', className, children }) {
  return (
    <span className={cn(
      'inline-flex items-center rounded-full px-2.5 py-[2px]',
      'text-[10.5px] font-bold uppercase tracking-[.06em]',
      { mute: 'bg-panel2 text-muted', ok: 'border border-ok/35 bg-transparent text-ok',
        bad: 'border border-bad/35 bg-transparent text-bad', warn: 'border border-warn/35 bg-transparent text-warn',
        accent: 'border border-accent/35 bg-transparent text-deep',
        solid: 'border border-accent/35 bg-transparent text-deep' }[tone],
      className)}>
      {children}
    </span>
  )
}

/** A count, always in the mono face so columns of them line up. */
export function Badge({ tone = 'mute', className, children }) {
  return (
    <span className={cn(
      'inline-flex items-center rounded-full font-mono text-[10.5px] px-2 py-0.5 font-semibold',
      { mute: 'bg-panel2 text-muted2', ok: 'border border-ok/35 bg-transparent text-ok',
        bad: 'border border-bad/35 bg-transparent text-bad', warn: 'border border-warn/35 bg-transparent text-warn',
        accent: 'border border-accent/35 bg-transparent text-deep' }[tone],
      className)}>
      {children}
    </span>
  )
}

/** Show a section label and count. */
export function SectionLabel({ children, right, className }) {
  return (
    <div className={cn('flex items-center justify-between gap-2',
      'label-xs text-ink', className)}>
      <span>{children}</span>
      {right}
    </div>
  )
}

/** Secondary tab row. */
export function SubTabs({ className, children }) {
  return (
    <div className={cn('flex shrink-0 items-stretch overflow-x-auto',
      'border-b border-line/70 bg-black/35 backdrop-blur-xl dark:bg-black/[.015]', className)}>
      {children}
    </div>
  )
}

export function SubTab({ on, className, children, ...rest }) {
  return (
    <button {...rest}
      className={cn('inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap',
        'm-1 rounded-xl border border-transparent px-[12px] py-[7px]',
        'font-display text-[11px] transition-colors',
        on ? 'border-line bg-white font-semibold text-ink shadow-sm dark:bg-black/8'
           : 'font-medium text-label hover:bg-black/50 hover:text-ink dark:hover:bg-black/5',
        className)}>
      {children}
    </button>
  )
}

export const Panel = ({ className, children }) => (
  <div className={cn('rounded-2xl border border-line bg-panel shadow-[0_0_2px_0_rgba(145,158,171,0.2),0_12px_24px_-4px_rgba(145,158,171,0.12)]', className)}>
    {children}
  </div>
)

export const Empty = ({ children, bad }) => (
  <p className={cn('px-1 py-7 text-[12px]', bad ? 'text-bad' : 'text-muted')}>
    {children}
  </p>
)

export function Modal({ onClose, children, className, style, overlayClassName }) {
  useEffect(() => {
    const key = (e) => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [onClose])
  return (
  // Keep tall dialogs bounded within viewport dimensions.
    <div onClick={onClose}
         className={cn(`fixed inset-0 z-[600] flex items-center justify-center
                    overscroll-contain bg-black/75 backdrop-blur-sm p-4`, overlayClassName)}>
      {/* `style` wins over the size classes, which is the only reliable way for
          a caller to ask for a dialog that fills the window. */}
      <div onClick={e => e.stopPropagation()} style={style}
           className={cn('w-full max-w-[520px] max-h-[90vh] overflow-y-auto',
             'rounded-[24px] border border-line2',
             'bg-panel p-6 shadow-[-40px_40px_80px_-8px_rgba(0,0,0,0.6)] text-ink', className)}>
        {children}
      </div>
    </div>
  )
}

export function Dropdown({ open, onClose, children, className }) {
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const away = (e) => {
      if (!ref.current?.parentElement?.contains(e.target)) onClose()
    }
    const key = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('click', away)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('click', away)
      document.removeEventListener('keydown', key)
    }
  }, [open, onClose])
  if (!open) return null
  return (
    <div ref={ref}
         className={cn('absolute z-[500] overflow-hidden rounded-[16px] border border-line',
           'bg-panel/95 shadow-[0_0_2px_0_rgba(145,158,171,0.24),-20px_20px_40px_-4px_rgba(145,158,171,0.24)] backdrop-blur-xl', className)}>
      {children}
    </div>
  )
}

/** A label for something that has no room for one. */
export function Tip({ text, children, className, side = 'top' }) {
  return (
    <span className={cn('relative inline-flex', className)} title={text || undefined}>
      {children}
    </span>
  )
}

/** What every editable field in the studio has to carry. */
export const plainField = {
  suppressHydrationWarning: true,
  spellCheck: false,
  'data-gramm': 'false',
  'data-gramm_editor': 'false',
  'data-enable-grammarly': 'false',
}

export const Input = ({ className, ...rest }) => (
  <input className={cn('h-10 w-full rounded-xl border border-line bg-panel/60 px-3.5 shadow-sm',
    'text-[13px] text-ink caret-accent transition-all',
    'placeholder:text-muted2 focus:border-accent focus:ring-1 focus:ring-accent focus-visible:outline-none',
    'disabled:opacity-45', className)}
    {...plainField} {...rest} />
)

/** A textarea with the same input protection. */
export const TextArea = forwardRef(function TextArea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={className} {...plainField} {...rest} />
})

export const Table = ({ className, children }) => (
  <div className="w-full overflow-x-auto">
    <table className={cn('w-full border-collapse text-[12.5px]', className)}>
      {children}
    </table>
  </div>
)
export const TR = ({ className, children, ...rest }) => (
  <tr className={cn('border-b border-line last:border-0 hover:bg-ink/[.02] transition-colors', className)} {...rest}>
    {children}
  </tr>
)
/* The column head is the one rule in a table that is drawn strong. */
export const TH = ({ className, children }) => (
  <th className={cn('border-b border-line bg-panel2/50 px-3 py-2.5 text-left',
    'text-[11px] font-semibold uppercase tracking-[.08em] text-muted',
    className)}>{children}</th>
)
export const TD = ({ className, children }) => (
  <td className={cn('px-3 py-2.5 align-middle', className)}>{children}</td>
)
