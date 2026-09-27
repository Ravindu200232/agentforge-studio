/**
 * The navigation of a deployment is what its own command line tools can show.
 *
 * Which commands exist for each deployment type (Vercel, Netlify, AWS EC2/ECS, Azure, GitHub) is data, in
 * `prompts/deployment/monitors.json`; the server offers the ones it can fill in from the deployment's own record, and
 * this only lays them out in groups. Clicking one runs it and streams its output (see `CliMonitor`).
 */

/** The offered commands, in the order they were offered, under the group each names. */
export function groupMonitors(items) {
  const groups = []
  for (const item of items || []) {
    const name = item.group || 'More'
    let group = groups.find(row => row.name === name)
    if (!group) { group = { name, items: [] }; groups.push(group) }
    group.items.push(item)
  }
  return groups
}
