const n = value => Number.isFinite(Number(value)) ? Number(value) : 0

export function e2eStageSummary(e2e) {
  const total = n(e2e?.stage_total)
  const passed = n(e2e?.stage_passed)
  const failed = n(e2e?.stage_failed)
  const notReached = n(e2e?.stage_not_reached)
  const rate = total ? Math.round((passed * 100) / total) : 0
  return { total, passed, failed, notReached, rate }
}

export function journeyStageSummary(flow) {
  const total = n(flow?.stage_total)
  const passed = n(flow?.stage_passed)
  const failed = n(flow?.stage_failed)
  const notReached = n(flow?.stage_not_reached)
  const rate = total ? Math.round((passed * 100) / total) : 0
  return { total, passed, failed, notReached, rate }
}
