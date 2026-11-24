// Reports each test and each test.step as it happens, so the studio can show the run live.
//
// When the Studio started the run (AGENTFORGE_LIVE_URL is set) the rows go to it, for the
// first worker only (the one whose browser is streamed, see live-view.js). Otherwise each row
// is one JSON line on stdout that starts with "@@pw ", standing apart from anything else.
import { isLive, post } from './live-view.js'

const emit = row => process.stdout.write(`@@pw ${JSON.stringify(row)}\n`)

export default class LiveReporter {
  total = 0
  finished = 0
  queue = Promise.resolve()

  send(row, result) {
    if (!isLive) return emit(row)
    if (result && result.parallelIndex !== 0) return
    const index = Math.min(this.finished + (row.state === 'journey_start' ? 1 : 0), this.total)
    const { project, ...rest } = row   // `project` is this app's Studio project on the receiving side
    // In order, one at a time: a step must not arrive before the journey it belongs to.
    this.queue = this.queue.then(() => post({ kind: 'event', ...rest, project_name: project, index, total: this.total }))
  }

  onBegin(_config, suite) {
    this.total = suite.allTests().length
  }

  onTestBegin(test, result) {
    this.send({ state: 'journey_start', title: test.title, suite: test.titlePath().slice(1).join(' > '),
      project: test.parent?.project()?.name || '', lane: result.workerIndex + 1 }, result)
  }

  onStepBegin(test, result, step) {
    if (step.category !== 'test.step') return
    this.send({ state: 'step', title: test.title, label: step.title, lane: result.workerIndex + 1 }, result)
  }

  onStepEnd(test, result, step) {
    if (step.category !== 'test.step') return
    this.send({ state: step.error ? 'step_failed' : 'step_done', title: test.title, label: step.title,
      message: step.error?.message?.split('\n')[0] || '', lane: result.workerIndex + 1 }, result)
  }

  onTestEnd(test, result) {
    this.finished += 1
    this.send({ state: 'journey_done', title: test.title, status: result.status,
      ok: result.status === 'passed' || result.status === 'skipped',
      message: result.error?.message?.split('\n')[0] || '', lane: result.workerIndex + 1,
      shots: result.attachments.filter(a => a.path && a.contentType?.startsWith('image/')).map(a => a.path) }, result)
  }

  async onEnd() {
    if (!isLive) return
    await this.queue
    await post({ kind: 'end' })
  }

  printsToStdio() {
    return false
  }
}
