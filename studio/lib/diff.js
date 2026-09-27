/**
 * Fast LCS unified line diff algorithm for comparing text revisions.
 * Produces GitHub-style diff lines with additions, deletions, and unchanged lines.
 */

export function computeLineDiff(oldText = '', newText = '') {
  const oldLines = String(oldText || '').split(/\r?\n/)
  const newLines = String(newText || '').split(/\r?\n/)

  // If old text is empty, everything is an addition
  if (!oldText && newText) {
    return {
      lines: newLines.map((text, i) => ({ type: 'add', text, newNo: i + 1 })),
      additions: newLines.length,
      deletions: 0,
    }
  }

  // If new text is empty, everything is a deletion
  if (oldText && !newText) {
    return {
      lines: oldLines.map((text, i) => ({ type: 'del', text, oldNo: i + 1 })),
      additions: 0,
      deletions: oldLines.length,
    }
  }

  // Optimize common prefix
  let prefixCount = 0
  while (
    prefixCount < oldLines.length &&
    prefixCount < newLines.length &&
    oldLines[prefixCount] === newLines[prefixCount]
  ) {
    prefixCount++
  }

  // Optimize common suffix
  let suffixCount = 0
  while (
    suffixCount < oldLines.length - prefixCount &&
    suffixCount < newLines.length - prefixCount &&
    oldLines[oldLines.length - 1 - suffixCount] === newLines[newLines.length - 1 - suffixCount]
  ) {
    suffixCount++
  }

  const midOld = oldLines.slice(prefixCount, oldLines.length - suffixCount)
  const midNew = newLines.slice(prefixCount, newLines.length - suffixCount)

  // Compute LCS matrix on middle section
  const m = midOld.length
  const n = midNew.length
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1))

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (midOld[i - 1] === midNew[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1])
      }
    }
  }

  // Backtrack LCS
  let i = m
  let j = n
  const midDiff = []

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && midOld[i - 1] === midNew[j - 1]) {
      midDiff.push({ type: 'same', text: midOld[i - 1], oldRel: i, newRel: j })
      i--
      j--
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      midDiff.push({ type: 'add', text: midNew[j - 1], newRel: j })
      j--
    } else if (i > 0 && (j === 0 || dp[i][j - 1] < dp[i - 1][j])) {
      midDiff.push({ type: 'del', text: midOld[i - 1], oldRel: i })
      i--
    }
  }

  midDiff.reverse()

  // Assemble full diff with line numbers
  const result = []
  let curOld = 1
  let curNew = 1
  let additions = 0
  let deletions = 0

  // 1. Common prefix
  for (let k = 0; k < prefixCount; k++) {
    result.push({ type: 'same', text: oldLines[k], oldNo: curOld++, newNo: curNew++ })
  }

  // 2. Middle changes
  for (const item of midDiff) {
    if (item.type === 'same') {
      result.push({ type: 'same', text: item.text, oldNo: curOld++, newNo: curNew++ })
    } else if (item.type === 'add') {
      additions++
      result.push({ type: 'add', text: item.text, newNo: curNew++ })
    } else if (item.type === 'del') {
      deletions++
      result.push({ type: 'del', text: item.text, oldNo: curOld++ })
    }
  }

  // 3. Common suffix
  const oldSuffixStart = oldLines.length - suffixCount
  for (let k = 0; k < suffixCount; k++) {
    result.push({ type: 'same', text: oldLines[oldSuffixStart + k], oldNo: curOld++, newNo: curNew++ })
  }

  return { lines: result, additions, deletions }
}
