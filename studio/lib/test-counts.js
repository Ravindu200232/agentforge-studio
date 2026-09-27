export function deriveVitestCounts(v) {
  const suites = Array.isArray(v?.testResults) ? v.testResults : []
  const cases = suites.flatMap(s => Array.isArray(s?.assertionResults) ? s.assertionResults : [])
  const passed = cases.filter(c => c?.status === 'passed').length
  const failed = cases.filter(c => c?.status === 'failed').length
  const skipped = cases.filter(c => ['skipped', 'pending', 'todo'].includes(c?.status)).length
  const total = cases.length
  const executed = passed + failed
  return { passed, failed, skipped, total, executed, files: suites.length }
}

/** The one current unit-suite status used by every Studio surface.
 *
 * Vitest's assertion rows are authoritative because summary fields can be
 * stale after targeted repair runs.  Older reports without testResults fall
 * back to their numeric summary instead of being shown as an empty suite.
 */
export function unitTestStatus(v) {
  if (!v) return null
  if (Array.isArray(v.fileResults)) {
    const passed = v.fileResults.filter(r => r.status === 'passed').length
    const failed = v.fileResults.filter(r => r.status === 'failed').length
    return { passed, failed, skipped: 0, total: v.fileResults.length,
             executed: passed + failed, files: v.fileResults.length, tested: true, unit: 'files' }
  }
  if (Array.isArray(v.testResults)) {
    return { ...deriveVitestCounts(v), tested: true }
  }
  const passed = Number(v.numPassedTests || 0)
  const failed = Number(v.numFailedTests || 0)
  const skipped = Number(v.numPendingTests || 0) + Number(v.numTodoTests || 0)
  const total = Number(v.numTotalTests || (passed + failed + skipped))
  return {
    passed, failed, skipped, total, executed: passed + failed,
    files: Number(v.numTotalTestSuites || 0), tested: true,
  }
}

export function projectUnitTestStatus(qa, project) {
  if (!qa || !project || qa.project !== project) return null
  return unitTestStatus(qa.vitest)
}

export function suiteRows(v) {
  return (v?.testResults || []).map(t => ({
    file: String(t?.name || t?.testFilePath || '').replace(/\\/g, '/').split('/tests/').pop(),
    cases: t?.assertionResults || [],
    status: t?.status || '',
  }))
}
