/**
 * The build, as a conversation.
 *
 * The panel beside the preview used to be a terminal: raw backend lines,
 * scrolling past faster than anyone could read, with the one sentence that
 * mattered buried in it. The build screen has the opposite problem — it is
 * deliberately calm, shows five paced milestones, and drops everything else,
 * so watching it you cannot tell whether the agent is working or stuck.
 *
 * This is the middle: every action the agent takes, in the order it took it,
 * named in English. Nothing is dropped. A line this does not recognise is
 * shown as it arrived rather than swallowed, because an unrecognised line is
 * usually the interesting one.
 */

// Every action is its own row. Grouping consecutive reads under one icon
// saved space and made three separate steps look like one, which is the
// opposite of what a step-by-step feed is for. Do not cap the list: the chat
// panel pages older rows in rather than silently dropping them.

const KINDS = [
  // [pattern, kind, how to title it]
  [/^\s*Reading\s+(.+)$/i, 'read', m => `Read ${m[1]}`],
  [/^\s*(?:Searching|globFiles|grepSearch)\s+(.+)$/i, 'read', m => `Searched for ${m[1]}`],
  [/^\s*listDir\s+(.+)$/i, 'read', m => `Listed ${m[1]}`],
  [/^\s*Looking at the project/i, 'read', () => 'Looked at the project layout'],
  [/^\s*Deciding what to prove\s*(.*)$/i, 'plan', () => 'Decided what to prove'],
  [/^\s*scope:\s*(\d+)\s*requirement/i, 'plan', m => `Verification scope: ${m[1]} requirement(s)`],
  [/^\s*(written|created|patched|edited)\s+(\S+)\s*\((\d+) lines\)/i, 'write',
    m => `${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]} (${m[3]} lines)`],
  [/^\s*(written|created|patched|edited)\s+(\S+)/i, 'write',
    m => `${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}`],
  [/^\s*removed\s+(\S+)/i, 'write', m => `Removed ${m[1]}`],
  [/^\s*Writing\s+(.+)$/i, 'write', m => `Writing ${m[1]}`],
  [/^\s*Editing\s+(.+)$/i, 'write', m => `Editing ${m[1]}`],
  [/^\s*running\s+(unit|e2e|runtime)\/(.+)$/i, 'test', m => `Running ${m[1]} suite: ${m[2]}`],
  [/^\s*Testing\s+(.+)$/i, 'test', m => `Testing ${m[1]}`],
  [/^\s*Checking in the browser\s*(.*)$/i, 'test', m => `Browser journey${m[1] ? `: ${m[1]}` : ''}`],
  [/^\s*Running\s+(.+)$/i, 'run', m => `Ran ${m[1]}`],
  [/^\s*\$\s+(.+)$/i, 'run', m => m[1]],
  [/^\s*Design contract:\s*(.+)$/i, 'design', m => `Design: ${m[1]}`],
  [/^\s*Scaffolded\s+(.+)$/i, 'setup', m => `Scaffolded ${m[1]}`],
  [/^\s*Context checkpoint/i, 'setup', () => 'Summarised older context to make room'],
]

/** Lines that are noise in a conversation, however useful they are in a log. */
const MUTED = [
  /^\s*\$\s/,                       // the echoed command; the "Ran …" line covers it
  /^\s*(?:HTTP|WS|connection)\b/i,
  /^\s*type:\s/i,
  /\btool error\s*:/i,              // internal tool retries; the agent recovers or reports a real failure
  /fast refresh|webpack|destination stream closed/i,
]

// Every line a dev server prints is forwarded as a log row, so starting one
// filled the conversation with a dozen turns about its own banner, its port,
// its environment file and each recompile — none of which anybody asked for.
// It is a log; it belongs in the log. What survives is the line that says the
// preview is up, and anything the server itself called a problem.
const SERVER_LINE = /^\[[^\]]{1,24}\]\s*/
const SERVER_READY = /\bready in\b|- local:|listening on/i

// The engine polls a long-running command every few seconds and logs a fresh
// "still running" line each time, identical but for the elapsed seconds. Read
// as a conversation that is one command ticking, not a new event every poll.
const STILL_RUNNING = /^Command still running \((\d+)s\):\s*(.+)$/i

/**
 * The badge a backend line wears, turned into the row's own icon.
 *
 * The engine writes its log with a symbol in front of every line - a hammer
 * for a build, a bin for a delete, a warning triangle. In a terminal that is a
 * column you read down. In the conversation it was a second icon sitting in
 * the text beside the row's real one, in a font that renders it at a different
 * size, so a tidy feed read as a pile of symbols.
 *
 * The symbol was never decoration though: it says what kind of thing happened,
 * which is exactly what decides the icon. So it is read, then removed.
 */
const BADGES = [
  [/[🏗🧱]/u, 'setup'], [/[📂📁]/u, 'setup'], [/[📄📎]/u, 'read'],
  [/[✏🖊🖉]/u, 'write'], [/[🗑🚮]/u, 'write'], [/[🖼🎨]/u, 'design'],
  [/[🧪🔬]/u, 'test'], [/[⏹⏸🛑]/u, 'note'], [/[⚠❗]/u, 'warn'],
  [/[✅✔]/u, 'done'], [/[❌✗✖]/u, 'warn'],
]

// Anything at the start of a line that is not a letter, a digit or an opening
// bracket: emoji, arrows, bullets, variation selectors and the spaces between
// them. Deliberately not a list of known symbols - the next release of the
// engine will use one nobody listed here.
//
// A dot is only decoration when nothing follows it, or the warning about
// `.env.local` loses its first character and becomes a sentence about a file
// that does not exist.
const LEADING_SYMBOLS = /^(?:[^\p{L}\p{N}([{"'#/$.]|\.(?![\p{L}\p{N}]))+/u

function badgeOf(line) {
  const head = line.slice(0, 6)
  for (const [pattern, kind] of BADGES) {
    if (pattern.test(head)) return kind
  }
  return ''
}

/** The sentence, without whatever was drawn in front of it. */
export function plainly(text) {
  return String(text || '')
    .replace(/\s+/g, ' ')
    .replace(LEADING_SYMBOLS, '')
    .trim()
}

function classify(row) {
  const raw = String(row.text || '').replace(/\s+/g, ' ').trim()
  if (!raw) return null
  if (MUTED.some(pattern => pattern.test(raw))) return null

  const badge = badgeOf(raw)
  const line = plainly(raw)
  if (!line) return null

  if (row.level === 'ERROR' || row.level === 'WARN') {
    return { kind: 'warn', title: line.slice(0, 200), detail: '' }
  }
  if (SERVER_LINE.test(line)) {
    if (!SERVER_READY.test(line)) return null
    return { kind: 'run', title: plainly(line.replace(SERVER_LINE, '')), detail: '' }
  }
  const stillRunning = STILL_RUNNING.exec(line)
  if (stillRunning) {
    return { kind: 'run', title: `Command still running (${stillRunning[1]}s)`,
             detail: stillRunning[2].slice(0, 200), runKey: stillRunning[2] }
  }
  // Completed file events already carry a path. Keep that information for
  // the clickable file cards instead of inferring success from row order.
  const changed = /^(written|created|patched|edited|updated|removed|deleted)\s+(.+?)(?:\s+\(\d+ lines\))?$/i.exec(line)
  if (changed) {
    const path = changed[2].replace(/^[`'"]|[`'"]$/g, '').replace(/\\/g, '/')
    return { kind: 'write', title: line, detail: '', file: path, action: changed[1].toLowerCase() }
  }
  const starting = /^(writing|editing|removing)\s+(.+?)$/i.exec(line)
  if (starting) {
    const path = starting[2].replace(/^[`'"]|[`'"]$/g, '').replace(/\\/g, '/')
    return { kind: 'write', title: line, detail: '', file: path, action: starting[1].toLowerCase(), inProgress: true }
  }
  const readMatched = /^(?:read|reading)\s+(.+?)(?:\s+\(\d+ lines\))?$/i.exec(line)
  if (readMatched && !/^(?:the|a|from|into|about)\s+/i.test(readMatched[1])) {
    const path = readMatched[1].replace(/^[`'"]|[`'"]$/g, '').replace(/\\/g, '/')
    return { kind: 'read', title: `Read ${path}`, detail: '', file: path, action: 'read' }
  }
  const effortMatched = /^\[effort:(low|medium|high|ultra)\]\s*(.*)$/i.exec(line)
  if (effortMatched) {
    return { kind: 'effort', title: effortMatched[2] || 'Model call', detail: '', level: effortMatched[1].toLowerCase() }
  }
  for (const [pattern, kind, title] of KINDS) {
    const match = pattern.exec(line)
    if (match) return { kind, title: title(match), detail: '' }
  }
  if (row.level === 'SUCCESS') return { kind: 'done', title: line, detail: '' }
  // Not recognised. Show it rather than drop it — the line nobody wrote a rule
  // for is usually the one worth reading — under whatever the engine drew in
  // front of it, which is the best hint available about what it was.
  return { kind: badge || 'note', title: line.slice(0, 220), detail: '' }
}

/**
 * What one log row became, remembered against the row itself.
 *
 * The feed is rebuilt on every arriving line, and the history it is rebuilt
 * from holds eight hundred rows - so during a build every line reclassified
 * the entire run through a dozen regular expressions, several times a second,
 * to add one row at the end. A log row is never edited after it is appended,
 * so its answer cannot change; and returning the same object each time is what
 * lets the rows already on screen skip rendering again.
 */
const remembered = new WeakMap()

// A name a row keeps for as long as it exists. A key built from position would
// change for every row as new lines arrive and remount the history.
let counted = 0

function turnFor(row) {
  if (remembered.has(row)) return remembered.get(row)
  const event = classify(row)
  const turn = event && { role: 'activity', ...event, at: row.at, id: `a${++counted}` }
  remembered.set(row, turn)
  return turn
}

export function chatTurns(logs = [], chat = []) {
  const turns = []
  let previous = ''
  // Track in-progress file operations so that when the completed event arrives,
  // it supersedes the in-progress card rather than rendering a duplicate row.
  const pendingFileTurns = new Map()
  // Same idea for a command being polled: each "still running" tick updates
  // the one row in place instead of piling up a new row every few seconds.
  const pendingRunTurns = new Map()

  for (const row of logs) {
    const turn = row && typeof row === 'object' ? turnFor(row) : null
    if (!turn) continue
    // The engine echoes a command as both "Ran x" and "$ x"; one row, not two.
    if (turn.title === previous) continue
    previous = turn.title

    if (turn.kind === 'run' && turn.runKey) {
      if (pendingRunTurns.has(turn.runKey)) {
        const targetIndex = pendingRunTurns.get(turn.runKey)
        turns[targetIndex] = { ...turn, id: turns[targetIndex].id }
      } else {
        pendingRunTurns.set(turn.runKey, turns.length)
        turns.push(turn)
      }
      continue
    }

    if (turn.kind === 'write' && turn.file) {
      const fileKey = turn.file.replace(/\\/g, '/').replace(/^\.\//, '')
      if (turn.inProgress) {
        if (pendingFileTurns.has(fileKey)) {
          const targetIndex = pendingFileTurns.get(fileKey)
          turns[targetIndex] = { ...turn, id: turns[targetIndex].id }
        } else {
          pendingFileTurns.set(fileKey, turns.length)
          turns.push(turn)
        }
      } else if (pendingFileTurns.has(fileKey)) {
        const targetIndex = pendingFileTurns.get(fileKey)
        turns[targetIndex] = { ...turn, id: turns[targetIndex].id }
        pendingFileTurns.delete(fileKey)
      } else {
        turns.push(turn)
      }
      continue
    }

    turns.push(turn)
  }

  for (const entry of chat) {
    if (!remembered.has(entry)) {
      remembered.set(entry, { ...entry, id: `c${++counted}`,
                              role: entry.role || 'assistant' })
    }
    turns.push(remembered.get(entry))
  }
  turns.sort((a, b) => (a.at || 0) - (b.at || 0))
  return turns
}
