import { api } from './api'
import { useStore } from './store'

let requestVersion = 0

/** Both manual loads and websocket notifications share the same request order. */
export async function refreshQaReport(project) {
  const version = ++requestVersion
  const report = await api.qa(project)
  if (version !== requestVersion || useStore.getState().project !== project || useStore.getState().agentRole !== 'developer') return
  if (report.error) throw new Error(report.error)
  useStore.getState().setQaReport(report)
  return report
}
