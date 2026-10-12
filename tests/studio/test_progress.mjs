/** Verify that progress stays monotonic across every backend flow. */
import { advance, displayPct, emptyProgress, CEILING } from '../../studio/lib/progress-model.js'
import { e2eStageSummary } from '../../studio/lib/e2e-rate.js'

const FLOWS = [
  [15, 40, 65, 78, 88, 95, 100],   // feature
  [20, 45, 100],                   // image
  [12, 30, 50, 78, 100],           // pencil
  [10, 35, 80, 100],               // edit
  [20, 45, 65, 78, 100],           // repair
  [35, 75, 100],                   // page rewrite
]

let fail = 0
const t0 = 1700000000000

/** Sample repaints between reports to catch visible reversals. */
function watch(gapsMs) {
  let s = emptyProgress(), last = 0, t = t0, drops = 0
  for (let r = 0; r < 400; r++) {
    for (const pct of FLOWS[r % FLOWS.length]) {
      const gap = gapsMs[(r + pct) % gapsMs.length]
      // repaint four times while waiting, as the overlay's timer does
      for (let k = 1; k <= 4; k++) {
        const shown = displayPct(s, t + (gap * k) / 4)
        if (shown < last - 0.001) { console.error(`BACKWARD while waiting ${last} -> ${shown}`); drops++ }
        last = Math.max(last, shown)
      }
      t += gap
      s = advance(s, `step ${pct}`, pct, t)
      const shown = displayPct(s, t)
      if (shown < last - 0.001) { console.error(`BACKWARD on report ${last} -> ${shown}`); drops++ }
      if (shown > CEILING + 0.001) { console.error(`OVER CEILING ${shown}`); drops++ }
      last = shown
    }
  }
  return drops
}

// Fast reports, slow ones, and the long stalls a real build has.
fail += watch([700])
fail += watch([700, 4000, 20000, 60000])
fail += watch([45000, 90000, 150000])
const fresh = advance(advance(emptyProgress(), 'Writing…', 45, t0),
                      'Waiting for you', 0, t0 + 1000)
if (fresh.pct !== 0) { console.error('a new run did not reset'); fail++ }

const first = advance(emptyProgress(), 'Planning…', 15, t0)
if (displayPct(first, t0) < 8) { console.error('first report reads too low'); fail++ }
if (displayPct(first, t0 + 40000) <= displayPct(first, t0)) {
  console.error('a stalled step does not creep'); fail++
}

const cases = [
  [{ stage_total: 12, stage_passed: 12, stage_failed: 0, stage_not_reached: 0 }, 100],
  [{ stage_total: 12, stage_passed: 10, stage_failed: 1, stage_not_reached: 1 }, 83],
  [{ stage_total: 13, stage_passed: 11, stage_failed: 1, stage_not_reached: 1 }, 85],
]
for (const [input, rate] of cases) {
  const got = e2eStageSummary(input)
  if (got.rate !== rate || got.total !== input.stage_total || got.passed !== input.stage_passed) {
    console.error(`e2eStageSummary: expected ${input.stage_passed}/${input.stage_total}=${rate}%, got ${got.passed}/${got.total}=${got.rate}%`)
    fail++
  }
}

console.log(fail ? `Progress verification: ${fail} FAILURE(S)` :
  'Progress verification: forward-only across 3 timing profiles ' +
  '(reports and repaints), pass rates OK')
process.exit(fail ? 1 : 0)
