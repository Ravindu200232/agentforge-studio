/** The screen tells a diagram from words a model said instead of drawing it - the same way the server does. */
import assert from 'node:assert/strict'
import { isMermaid } from '../../studio/lib/mermaid-source.js'

const narration = 'Let me read the Booking module requirements — lines 2270-2470 (FR-042 to FR-058). Let me read 2270-2470.'

// what an older run saved as the sequence diagram: never shown as code
assert.equal(isMermaid(narration), false)
assert.equal(isMermaid(''), false)
assert.equal(isMermaid(undefined), false)
assert.equal(isMermaid('graph of the booking flow is below'), false)      // prose that starts like a declaration

// every kind's real declaration
for (const source of [
  'flowchart LR\n  a --> b',
  'flowchart TD\r\n  a --> b',
  'graph TD;\n  a --> b',
  'sequenceDiagram\n  A->>B: hi',
  'classDiagram\n  class A',
  'stateDiagram-v2\n  [*] --> A',
  'erDiagram\n  A ||--o{ B : has',
  '%%{init: {"theme": "base"}}%%\nstateDiagram-v2\n  [*] --> A',   // a theme line before the declaration
]) {
  assert.equal(isMermaid(source), true, source)
}

console.log('Diagram source check: narration is never a diagram, every real declaration is')
