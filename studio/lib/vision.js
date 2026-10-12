import { useEffect, useState } from 'react'
import { api } from './api'

const NONE = { vision: new Set(), known: new Set(), pending: 0 }

/**
 * Which models can look at pictures, from what Ollama says of each (`/models/capabilities`). The server asks about the models in
 * the background, so this asks again, a few times, while it still has answers to wait for: the "vision" marks fill in as they
 * arrive. `active` is false until the picker is open, so nothing is asked before it is needed.
 */
export function useVisionModels(active = true) {
  const [state, setState] = useState(NONE)
  useEffect(() => {
    if (!active) return undefined
    let alive = true
    let timer = null
    let rounds = 0
    const look = () => api.modelCapabilities().then(answer => {
      if (!alive) return
      const found = answer?.capabilities || {}
      setState({
        vision: new Set(Object.keys(found).filter(id => found[id]?.vision)),
        known: new Set(Object.keys(found)),
        pending: Number(answer?.pending || 0),
      })
      if (Number(answer?.pending || 0) > 0 && ++rounds < 25) timer = setTimeout(look, 1500)
    }).catch(() => {})
    look()
    return () => { alive = false; clearTimeout(timer) }
  }, [active])
  return state
}
