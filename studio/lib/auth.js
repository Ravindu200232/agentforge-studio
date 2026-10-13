'use client'

import { create } from 'zustand'
import { api, setAuthToken, getAuthToken, whenSignedOut } from './api'
import { connect, disconnect } from './ws'
import { useStore } from './store'

export const useAuthStore = create((set, get) => ({
  user: null,
  token: '',
  loading: true,
  error: '',
  // With AgentForge cloud accounts on, signing in is needed before cloud use.
  required: false,
  notice: '',

  init: async () => {
    const token = getAuthToken()
    set({ token, loading: true })
    try {
      // Even with no token kept here, the session cookie may still sign them
      // in - that is what the frames, the pictures and the socket travel on.
      const res = await api.auth.me()
      const required = Boolean(res?.required)
      if (res?.ok && res?.user) {
        set({ user: res.user, loading: false, required })
      } else {
        setAuthToken('')
        set({ user: null, token: '', loading: false, required,
              notice: '' })
      }
    } catch {
      setAuthToken('')
      set({ user: null, token: '', loading: false })
    }
  },

  login: async (login, password) => {
    set({ loading: true, error: '' })
    try {
      const res = await api.auth.login({ login, password })
      if (res?.ok && res?.token) {
        setAuthToken(res.token)
        set({ user: res.user, token: res.token, loading: false, error: '' })
        connect()          // the feed is per person; this one is theirs
        return { ok: true, user: res.user }
      }
      const err = res?.error || 'Login failed'
      set({ loading: false, error: err })
      return { ok: false, error: err }
    } catch (e) {
      const err = e?.message || 'Login failed'
      set({ loading: false, error: err })
      return { ok: false, error: err }
    }
  },

  signup: async (username, email, password, name) => {
    set({ loading: true, error: '' })
    try {
      const res = await api.auth.signup({ username, email, password, name })
      if (res?.ok && res?.token) {
        setAuthToken(res.token)
        set({ user: res.user, token: res.token, loading: false, error: '' })
        connect()
        return { ok: true, user: res.user }
      }
      if (res?.verificationRequired) {
        set({ loading: false, error: '' })
        return { ok: false, verificationRequired: true, email: res.email || email }
      }
      const err = res?.error || 'Registration failed'
      set({ loading: false, error: err })
      return { ok: false, error: err }
    } catch (e) {
      const err = e?.message || 'Registration failed'
      set({ loading: false, error: err })
      return { ok: false, error: err }
    }
  },

  verifySignup: async (email, code) => {
    set({ loading: true, error: '' })
    try {
      const res = await api.auth.verifySignup({ email, code })
      if (res?.ok && res?.token) {
        setAuthToken(res.token)
        set({ user: res.user, token: res.token, loading: false, error: '' })
        connect()
        return { ok: true, user: res.user }
      }
      const err = res?.error || 'The code could not be verified.'
      set({ loading: false, error: err })
      return { ok: false, error: err }
    } catch (e) {
      const err = e?.message || 'The code could not be verified.'
      set({ loading: false, error: err })
      return { ok: false, error: err }
    }
  },

  logout: async () => {
    try {
      await api.auth.logout().catch(() => {})
    } finally {
      setAuthToken('')
      disconnect()
      useStore.getState().clearAccount()
      set({ user: null, token: '', error: '' })
    }
  },

  clearError: () => set({ error: '', notice: '' }),
}))

// A session that ends on the server - it expired, or it was ended from
// somewhere else - ends here too, at the sign-in page.
whenSignedOut(() => {
  if (!useAuthStore.getState().user && !getAuthToken()) return
  setAuthToken('')
  disconnect()
  useStore.getState().clearAccount()
  useAuthStore.setState({ user: null, token: '', loading: false })
})
