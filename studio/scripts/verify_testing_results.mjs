// Execute the real websocket/result loader with an in-memory store and API.
// No generated application, browser journey or model is run by this check.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import vm from 'node:vm'

const pending = []
const state = { project: 'hotel', qaReport: null, addLog() {},
  setQaReport(report) { state.qaReport = report } }
const store = { getState: () => state, setState: patch => Object.assign(state, patch) }
const api = { qa: project => new Promise(resolve => pending.push({ project, resolve })) }
class Socket { constructor() { Socket.last = this } }
const context = vm.createContext({ console, setTimeout, clearTimeout, URL,
  window: { location: { protocol: 'http:', hostname: 'localhost' } }, WebSocket: Socket })
const storeModule = new vm.SyntheticModule(['useStore', 'KEYS'], function () {
  this.setExport('useStore', store); this.setExport('KEYS', {})
}, { context })
const apiModule = new vm.SyntheticModule(['api', 'API', 'HTTP_FALLBACK'], function () {
  this.setExport('api', api); this.setExport('API', '/__agentforge/api'); this.setExport('HTTP_FALLBACK', {})
}, { context })
const source = name => fs.readFile(new URL(`../lib/${name}.js`, import.meta.url), 'utf8')
const loader = new vm.SourceTextModule(await source('qa-results'), { context })
await loader.link(name => name === './api' ? apiModule : storeModule)
await loader.evaluate()
const ws = new vm.SourceTextModule(await source('ws'), { context })
await ws.link(name => name === './api' ? apiModule : name === './store' ? storeModule : loader)
await ws.evaluate()
ws.namespace.connect()
assert.ok(Socket.last, 'websocket must connect')
Socket.last.onmessage({ data: JSON.stringify({ type: 'test_report', project: 'hotel' }) })
assert.equal(pending.length, 1, 'report event fetches the saved result')
pending.shift().resolve({ project: 'hotel', complete: false, timeline: [{ status: 'passed' }] })
await new Promise(resolve => setTimeout(resolve, 0))
assert.equal(state.qaReport.timeline[0].status, 'passed', 'partial result arrives before Done')
Socket.last.onmessage({ data: JSON.stringify({ type: 'test_report', project: 'another' }) })
assert.equal(pending.length, 0, 'another project must not replace the active report')

const older = loader.namespace.refreshQaReport('hotel')
const newer = loader.namespace.refreshQaReport('hotel')
pending[1].resolve({ project: 'hotel', version: 2 }); await newer
pending[0].resolve({ project: 'hotel', version: 1 }); await older
assert.equal(state.qaReport.version, 2, 'slow earlier requests cannot erase new results')
pending.length = 0
const switching = loader.namespace.refreshQaReport('hotel')
state.project = 'another'
pending.shift().resolve({ project: 'hotel', version: 3 }); await switching
assert.equal(state.qaReport.version, 2, 'switching projects discards an in-flight response')

const counts = new vm.SourceTextModule(await source('test-counts'), { context })
await counts.link(() => {}); await counts.evaluate()
const unit = counts.namespace.unitTestStatus({ fileResults: [{ status: 'passed' }, { status: 'failed' }] })
assert.equal(unit.unit, 'files'); assert.equal(unit.passed, 1); assert.equal(unit.failed, 1)
const detailed = counts.namespace.unitTestStatus({ numPassedTests: 99, testResults: [{ assertionResults: [{ status: 'failed' }] }] })
assert.equal(detailed.passed, 0); assert.equal(detailed.failed, 1)
console.log('Testing results: websocket updates, project isolation, request ordering and honest file/case counts PASS')

const sent = []
Socket.last.readyState = 1
Socket.last.send = value => sent.push(JSON.parse(value))
Socket.last.close = () => { Socket.last.closed = true }
state.setWorkKind = kind => { state.workKind = kind }
state.setBusy = value => { state.busy = value }
state.setBusyProject = project => { state.busyProject = project }
const prompt = 'create signup page for the customer to craete account'
ws.namespace.send({ type: 'agent_update', project: 'hotel', prompt })
assert.equal(sent[0].prompt, prompt, 'the user wording reaches the transport unchanged')
assert.equal(state.workKind, 'edit', 'chat requests are not classified as bug repair')
ws.namespace.send({ type: 'element_edit', project: 'hotel', prompt: 'Make this title larger',
  elements: [{ tag: 'h1', text: 'Create your account', route: '/signup' }] })
ws.namespace.answerQuestion('only on /signup')
assert.ok(sent[2].prompt.startsWith('Make this title larger'), 'scope answers retain the requested edit')
assert.equal(sent[2].elements[0].route, '/signup')
ws.namespace.disconnect()
assert.equal(Socket.last.onmessage, null, 'unmount removes the old stream listener')
assert.equal(Socket.last.closed, true)
console.log('Chat: original prompt, element context, scope answer and socket cleanup PASS')
