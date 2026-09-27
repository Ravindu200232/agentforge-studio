const CURATED = [
  { id: 'llama3.1:8b', label: 'Llama 3.1 8B', tag: 'fast',
    desc: 'Meta. Fast instruction following.' },
  { id: 'llama3.2:3b', label: 'Llama 3.2 3B', tag: 'fast',
    desc: 'Meta. Ultra-fast, lightweight.' },
  { id: 'mistral:7b', label: 'Mistral 7B', tag: 'fast',
    desc: 'Mistral AI. Quick, solid reasoning.' },
  { id: 'phi4:14b', label: 'Phi-4 14B', tag: 'quality',
    desc: 'Microsoft. Excellent reasoning for its size.' },
  { id: 'gemma3:12b', label: 'Gemma 3 12B', tag: 'quality',
    desc: 'Google. Strong general model.' },
  { id: 'qwen2.5-coder:14b', label: 'Qwen 2.5 Coder 14B', tag: 'code',
    desc: 'Best local model for code.' },
  { id: 'qwen2.5-coder:7b', label: 'Qwen 2.5 Coder 7B', tag: 'code',
    desc: 'Lighter code model.' },
  { id: 'deepseek-coder-v2:16b', label: 'DeepSeek Coder V2 16B', tag: 'code',
    desc: 'Excellent at code generation.' },
  { id: 'codellama:13b', label: 'Code Llama 13B', tag: 'code',
    desc: 'Meta. Llama fine-tuned for code.' },
  { id: 'llama3.1:70b', label: 'Llama 3.1 70B', tag: 'big',
    desc: 'Highest quality — needs a lot of memory.' },
  { id: 'qwen2.5:72b', label: 'Qwen 2.5 72B', tag: 'big',
    desc: 'Very capable — needs ~40GB.' },
]

// Presentation aliases only. Requests always keep the exact Ollama model id.
const CLOUD_UI_LABELS = {
  'qwen3.5:397b-cloud': 'Qwen 397B',
  'minimax-m3:cloud': 'MiniMax M3',
  'gemma4:31b-cloud': 'Gemma 4 31B',
  'bjoernb/gemma4-31b-fast:latest': 'Gemma 4 31B Fast',
  'bjoernb/gemma4-31b-fast': 'Gemma 4 31B Fast',
  'deepseek-v4-flash:cloud': 'DeepSeek V4 Flash',
  'deepseek-v4-pro:cloud': 'DeepSeek V4 Pro',
}

export const TIERS = {
  medium: { id: 'medium', label: 'Medium', model: 'deepseek-v4', think: false },
  high: { id: 'high', label: 'High', model: 'deepseek-v4-flash:cloud', think: true },
  ultra: { id: 'ultra', label: 'Ultra', model: 'deepseek-v4-pro:cloud', think: true },
}

export function tierFromModel(model, think) {
  const m = String(model || '').toLowerCase()
  if (m.includes('pro')) return 'ultra'
  if (m.includes('flash')) return 'high'
  if (think) return 'high'
  return 'medium'
}

export function tierDisplayName(model) {
  if (!model) return ''
  const m = String(model).toLowerCase()
  if (m.includes('pro')) return 'Ultra'
  if (m.includes('flash')) return 'High'
  if (m.includes('deepseek')) return 'Medium'
  return 'Standard'
}

export const modelLabel = (model) =>
  CLOUD_UI_LABELS[String(model?.id || '').toLowerCase()]
  || model?.label || model?.id || ''

export const isCloud = (id) => String(id || '').includes('-cloud')
  || String(id || '').endsWith(':cloud')

/**
 * Cloud by the server's own classification, falling back to the name.
 *
 * The name is not always enough: the server decides from `remote_host`, which
 * also catches a community wrapper such as `bjoernb/gemma4-31b-fast:latest`
 * that proxies to ollama.com while carrying no -cloud suffix at all.
 */
export const cloudModel = (cat, id) => {
  const entry = (cat?.all || []).find(m => m.id === id)
  return entry ? !!entry.cloud : isCloud(id)
}

export function catalogue(payload) {
  const p = payload || {}
  const cloud = (p.cloud || []).map(m => ({
    ...m, label: modelLabel(m), cloud: true, tag: m.tag || 'cloud',
  }))
  const localObjs = (p.local_models || []).map(m =>
    typeof m === 'string' ? { id: m } : m)
  const installed = (p.local || []).map(m => typeof m === 'string' ? m : m.id)

  const byId = new Map()
  for (const m of localObjs) byId.set(m.id, { tag: 'local', ...m })
  for (const id of installed) {
    if (!byId.has(id)) byId.set(id, { id, tag: 'local' })
  }

  for (const m of CURATED) {
    if (!byId.has(m.id)) byId.set(m.id, { ...m, willPull: true })
  }
  const local = [...byId.values()]
  return {
    cloud, local, installed,
    all: [...cloud, ...local],
    cloudEnabled: !!p.cloud_enabled,
    cloudVia: p.cloud_via || 'none',
    ollamaReady: !!p.ollama_ready,
    cloudAccount: p.cloud_account || '',
  }
}

/**
 * Whether the chosen model can actually be reached right now, and through
 * what. Null when nothing is chosen, so the picker shows no line at all.
 *
 * An empty local list is not the same answer as an unreachable daemon --
 * a fresh Ollama with nothing pulled reports the same empty list as one that
 * is not running -- so the reachable flag comes from the server rather than
 * being inferred here.
 */
export function connection(cat, id) {
  if (!id) return null
  if (cloudModel(cat, id)) {
    if (!cat.cloudEnabled) {
      return { on: false, text: 'not connected — sign in to Ollama or add a key' }
    }
    if (cat.cloudVia === 'api-key') {
      return { on: true, text: 'connected · ollama.com key' }
    }
    return {
      on: true,
      text: cat.cloudAccount
        ? `connected · ollama.com as ${cat.cloudAccount}`
        : 'connected · signed-in Ollama',
    }
  }
  if (!cat.ollamaReady) return { on: false, text: 'Ollama is not answering' }
  return (cat.installed || []).includes(id)
    ? { on: true, text: 'connected · local Ollama' }
    : { on: false, text: 'not pulled yet — it downloads on the first build' }
}

export const hasVision = (all, id) => !!all.find(m => m.id === id)?.vision

export const maxContext = (all, id) =>
  Number(all.find(m => m.id === id)?.ctx) || 0

export const roomyContext = (all, id) => {
  const ctx = maxContext(all, id)
  return ctx === 0 || ctx >= 32768
}
