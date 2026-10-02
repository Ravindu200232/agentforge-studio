'use client'

import { useState } from 'react'
import { X, Mail, Lock, User, ArrowLeft, Loader2, AlertCircle } from 'lucide-react'
import { useAuthStore } from '@/lib/auth'

export default function AuthModal({ isOpen, onClose, onSuccess, initialScreen = 'methods' }) {
  const { login, signup, loading, error, clearError } = useAuthStore()

  // screen: 'methods' | 'email'
  const [screen, setScreen] = useState(initialScreen)
  // mode: 'signin' | 'signup'
  const [mode, setMode] = useState('signin')

  const [formLogin, setFormLogin] = useState('')
  const [formEmail, setFormEmail] = useState('')
  const [formPassword, setFormPassword] = useState('')
  const [formName, setFormName] = useState('')
  const [localError, setLocalError] = useState('')

  if (!isOpen) return null

  function handleClose() {
    clearError()
    setLocalError('')
    onClose?.()
  }

  async function handleSubmit(e) {
    e?.preventDefault()
    setLocalError('')
    clearError()

    if (mode === 'signin') {
      if (!formLogin.trim() || !formPassword) {
        setLocalError('Please enter your email or username and password')
        return
      }
      const res = await login(formLogin.trim(), formPassword)
      if (res.ok) {
        onSuccess?.(res.user)
        handleClose()
      }
    } else {
      if (!formLogin.trim()) {
        setLocalError('Please choose a username')
        return
      }
      if (!formEmail.trim() || !formEmail.includes('@')) {
        setLocalError('Please enter a valid email address')
        return
      }
      if (!formPassword || formPassword.length < 8) {
        setLocalError('Password must be at least 8 characters')
        return
      }
      const res = await signup(formLogin.trim(), formEmail.trim(), formPassword, formName.trim())
      if (res.ok) {
        onSuccess?.(res.user)
        handleClose()
      }
    }
  }

  function go(next) {
    clearError()
    setLocalError('')
    setMode(next)
    setScreen('email')
  }

  const activeError = localError || error

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-[440px] rounded-3xl border border-line bg-panel p-7 shadow-[0_0_2px_0_rgba(145,158,171,0.2),0_24px_48px_0_rgba(0,0,0,0.24)] backdrop-blur-2xl transition-all"
        role="dialog"
        aria-modal="true"
      >
        {/* Close Button */}
        <button
          onClick={handleClose}
          className="absolute right-5 top-5 flex size-8 items-center justify-center rounded-xl text-muted hover:bg-raised hover:text-ink transition-colors"
          aria-label="Close"
        >
          <X className="size-4" />
        </button>

        {/* Brand Logo */}
        <div className="flex flex-col items-center justify-center pt-2">
          <div className="flex items-center gap-2">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent ring-1 ring-accent/30">
              <img src="/__agentforge/agentforge-mark.png" alt="AgentForge" className="size-5 object-contain" />
            </div>
            <span className="font-display text-[22px] font-bold italic tracking-tight text-ink">
              agentforge<span className="text-accent font-normal">.ai</span>
            </span>
          </div>
        </div>

        {/* Error Alert */}
        {activeError && (
          <div className="mt-4 flex items-center gap-2 rounded-xl border border-bad/30 bg-bad/10 px-3.5 py-2.5 text-[12.5px] text-bad">
            <AlertCircle className="size-4 shrink-0" />
            <span>{activeError}</span>
          </div>
        )}

        {/* Screen 1: Method Selection (Matching media_1789153674897.png) */}
        {screen === 'methods' && (
          <div className="mt-5 text-center">
            <p className="px-3 text-[13px] leading-relaxed text-muted">
              Sign in to reach your own projects, specifications and deployments.
              Each account sees only its own.
            </p>

            <div className="mt-6 flex flex-col gap-2.5">
              {/* Email & Password */}
              <button
                type="button"
                onClick={() => go('signin')}
                className="flex h-11 w-full items-center justify-center gap-3 rounded-xl border border-line bg-panel/50 px-4 font-display text-[13px] font-semibold text-ink shadow-sm transition-all hover:border-[rgba(145,158,171,0.28)] hover:bg-raised/60"
              >
                <Mail className="size-4 text-muted" />
                <span>Sign in with email and password</span>
              </button>

              <button
                type="button"
                onClick={() => go('signup')}
                className="flex h-11 w-full items-center justify-center gap-3 rounded-xl border border-line bg-panel/50 px-4 font-display text-[13px] font-semibold text-ink shadow-sm transition-all hover:border-[rgba(145,158,171,0.28)] hover:bg-raised/60"
              >
                <User className="size-4 text-muted" />
                <span>Create an account</span>
              </button>
            </div>

            <p className="mt-6 text-[11px] text-muted/70">
              By signing in, you accept the{' '}
              <a href="#" className="text-ink underline hover:text-ink">Terms of Service</a>{' '}
              and acknowledge our{' '}
              <a href="#" className="text-ink underline hover:text-ink">Privacy Policy</a>.
            </p>
          </div>
        )}

        {/* Screen 2: Credentials Form (Matching media_1789153671638.png) */}
        {screen === 'email' && (
          <div className="mt-4">
            <h2 className="text-center font-display text-[18px] font-bold text-ink">
              {mode === 'signin' ? 'Sign in' : 'Create an account'}
            </h2>

            <form onSubmit={handleSubmit} className="mt-5 space-y-3.5">
              {mode === 'signup' && (
                <div>
                  <label className="mb-1 block text-[11.5px] font-medium text-muted">
                    Full name
                  </label>
                  <div className="relative flex items-center">
                    <User className="pointer-events-none absolute left-3 size-4 text-muted/60" />
                    <input
                      type="text"
                      value={formName}
                      onChange={e => setFormName(e.target.value)}
                      placeholder="Ravindu"
                      className="h-10 w-full rounded-xl border border-line bg-panel pl-9 pr-3 text-[13px] text-ink placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-colors"
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="mb-1 block text-[11.5px] font-medium text-muted">
                  {mode === 'signup' ? 'Username *' : 'Email or username *'}
                </label>
                <div className="relative flex items-center">
                  <User className="pointer-events-none absolute left-3 size-4 text-muted/60" />
                  <input
                    type="text"
                    required
                    autoFocus
                    value={formLogin}
                    onChange={e => setFormLogin(e.target.value)}
                    placeholder={mode === 'signup' ? 'ravindu2232' : 'Enter email or username'}
                    className="h-10 w-full rounded-xl border border-line bg-panel pl-9 pr-3 text-[13px] text-ink placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-colors"
                  />
                </div>
              </div>

              {mode === 'signup' && (
                <div>
                  <label className="mb-1 block text-[11.5px] font-medium text-muted">
                    Email address *
                  </label>
                  <div className="relative flex items-center">
                    <Mail className="pointer-events-none absolute left-3 size-4 text-muted/60" />
                    <input
                      type="email"
                      required
                      value={formEmail}
                      onChange={e => setFormEmail(e.target.value)}
                      placeholder="user@example.com"
                      className="h-10 w-full rounded-xl border border-line bg-panel pl-9 pr-3 text-[13px] text-ink placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-colors"
                    />
                  </div>
                </div>
              )}

              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label className="text-[11.5px] font-medium text-muted">
                    Password *
                  </label>
                  {mode === 'signin' && (
                    <button
                      type="button"
                      onClick={() => setLocalError('Please contact support to reset your password.')}
                      className="text-[11px] text-accent hover:underline"
                    >
                      Forgot password?
                    </button>
                  )}
                </div>
                <div className="relative flex items-center">
                  <Lock className="pointer-events-none absolute left-3 size-4 text-muted/60" />
                  <input
                    type="password"
                    required
                    value={formPassword}
                    onChange={e => setFormPassword(e.target.value)}
                    placeholder="••••••••"
                    className="h-10 w-full rounded-xl border border-line bg-panel pl-9 pr-3 text-[13px] text-ink placeholder:text-muted/40 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-colors"
                  />
                </div>
              </div>

              <div className="pt-2 flex flex-col gap-2">
                <button
                  type="submit"
                  disabled={loading}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-accent font-display text-[13px] font-semibold text-ink shadow-[0_8px_16px_0_rgba(191, 185, 255,0.24)] transition-all hover:bg-press active:scale-95 disabled:pointer-events-none disabled:opacity-50"
                >
                  {loading && <Loader2 className="size-4 animate-spin" />}
                  <span>{mode === 'signin' ? 'Sign in' : 'Create account'}</span>
                </button>

                <button
                  type="button"
                  onClick={() => { setScreen('methods'); clearError(); setLocalError('') }}
                  className="flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-line bg-panel/50 text-[13px] font-medium text-muted hover:bg-raised/60 hover:text-ink transition-all"
                >
                  <ArrowLeft className="size-3.5" />
                  <span>Back</span>
                </button>
              </div>
            </form>

            <div className="mt-5 text-center text-[12.5px] text-muted">
              {mode === 'signin' ? (
                <>
                  Don't have an account?{' '}
                  <button
                    onClick={() => { setMode('signup'); clearError(); setLocalError('') }}
                    className="font-semibold text-accent hover:underline"
                  >
                    Sign up
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{' '}
                  <button
                    onClick={() => { setMode('signin'); clearError(); setLocalError('') }}
                    className="font-semibold text-accent hover:underline"
                  >
                    Sign in
                  </button>
                </>
              )}
            </div>

            <p className="mt-5 text-center text-[11px] text-muted/70">
              By signing in, you accept the{' '}
              <a href="#" className="text-ink underline hover:text-ink">Terms of Service</a>{' '}
              and acknowledge our{' '}
              <a href="#" className="text-ink underline hover:text-ink">Privacy Policy</a>.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
