import fs from 'node:fs'

const source = fs.readFileSync(new URL('../lib/test-counts.js', import.meta.url), 'utf8')
const mod = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

const cases = Array.from({ length: 100 }, (_, i) => ({ title: `case ${i + 1}`, status: 'passed' }))
const report = {
  numPassedTests: 90,
  numTotalTests: 90,
  testResults: [{ name: 'tests/example.test.js', assertionResults: cases }],
}
const counts = mod.deriveVitestCounts(report)
if (counts.passed !== 100 || counts.total !== 100 || counts.failed !== 0) {
  throw new Error(`expected 100/100 from assertion rows, got ${counts.passed}/${counts.total}`)
}

const status = mod.projectUnitTestStatus({ project: 'demo', vitest: report }, 'demo')
if (!status?.tested || status.passed !== 100 || status.failed !== 0 || status.total !== 100) {
  throw new Error(`shared project status did not use assertion rows: ${JSON.stringify(status)}`)
}
if (mod.projectUnitTestStatus({ project: 'old', vitest: report }, 'demo') !== null) {
  throw new Error('a different project\'s cached QA result must not be shown')
}

const legacy = mod.unitTestStatus({
  numPassedTests: 7, numFailedTests: 2, numPendingTests: 1,
  numTotalTests: 10, numTotalTestSuites: 3,
})
if (legacy.passed !== 7 || legacy.failed !== 2 || legacy.total !== 10 || legacy.files !== 3) {
  throw new Error(`legacy summary fallback is wrong: ${JSON.stringify(legacy)}`)
}

const consumers = [
  ['Preview/Testing tab', '../app/page.jsx'],
  ['Deployment gate', '../components/deploy/DeployPanel.jsx'],
]
for (const [label, rel] of consumers) {
  const body = fs.readFileSync(new URL(rel, import.meta.url), 'utf8')
  if (!body.includes('projectUnitTestStatus')) {
    throw new Error(`${label} is not using the shared current-suite status`)
  }
  if (/tests\.(?:fail|rows)/.test(body)) {
    throw new Error(`${label} still reads accumulated streamed retry failures`)
  }
}

console.log('Vitest count regression: shared current-suite status OK (stale summary ignored)')
