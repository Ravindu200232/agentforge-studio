'use client'

import { PlayCircle } from 'lucide-react'
import { View, Table, Stats, Bars, Flow, duration, tone } from '../parts'

const outcome = run => (run.status === 'completed' ? run.conclusion : run.status)

/** The workflow runs (CI): which passed, which failed, and how long each took. */
export default function GithubRuns({ project, item }) {
  return (
    <View project={project} item={item} icon={PlayCircle} title="CI runs" about="Every run of the repository's workflows on GitHub Actions, newest first, with the result and how long it took.">
      {({ json }) => {
        if (!Array.isArray(json)) return null
        const rows = json.map(r => ({ ...r, result: outcome(r), took: Math.max(0, Date.parse(r.updatedAt) - Date.parse(r.createdAt)) }))
        const passed = rows.filter(r => r.result === 'success').length
        const failed = rows.filter(r => tone(r.result) === 'bad').length
        return (<>
          <Stats items={[{ label: 'Runs', value: rows.length }, { label: 'Passed', value: passed, tone: 'ok' }, { label: 'Failed', value: failed, tone: failed ? 'bad' : 'ok' }, { label: 'Latest', value: rows[0]?.result || '—', tone: rows[0] ? tone(rows[0].result) : undefined }]} />
          {rows[0] && (
            <Flow title="The latest run" steps={[
              { label: 'Push', sub: `${rows[0].event} · ${rows[0].headBranch}`, tone: 'ok' },
              { label: rows[0].workflowName, sub: rows[0].headSha?.slice(0, 7), tone: 'run' },
              { label: rows[0].result, sub: duration(rows[0].took), tone: tone(rows[0].result) },
            ]} />
          )}
          {rows.length > 1 && <Bars title="How long each run took" items={rows.slice(0, 15).map(r => ({ label: r.displayTitle, value: r.took, tone: tone(r.result) }))} format={duration} />}
          <Table rows={rows} empty="No runs yet." columns={[
            { label: 'Result', key: 'result', kind: 'status' }, { label: 'Workflow', key: 'workflowName' }, { label: 'Commit', key: 'displayTitle' },
            { label: 'Branch', key: 'headBranch', mono: true }, { label: 'Event', key: 'event', kind: 'chips' }, { label: 'Started', key: 'createdAt', kind: 'date' },
            { label: 'Took', key: 'took', kind: 'duration' }, { label: 'Logs', key: 'url', kind: 'link' },
          ]} />
        </>)
      }}
    </View>
  )
}
