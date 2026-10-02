'use client'

/** Renders the complete System Requirements Specification (SRS) directly from the project document. */

import { useMemo, useState } from 'react'
import {
  AlertTriangle, ArrowRight, CheckCircle2, Circle, Compass, Database, FileText,
  HelpCircle, Layers, Lock, Maximize2, Shield, Users, Workflow, XCircle,
} from 'lucide-react'
import { Empty } from '../ui'
import DiagramMissing from './DiagramMissing'
import DiagramViewer from './DiagramViewer'

const list = (value) => (Array.isArray(value) ? value : [])
const text = (value) => (typeof value === 'string' ? value.trim() : '')

/** Formats registration configuration mode and roles into a human-readable sentence. */
function registrationSentence(auth) {
  const mode = text(auth?.registration_mode)
  const joining = text(auth?.registration_role)
  const provisioning = text(auth?.provisioning_role)
  if (mode === 'open') {
    return joining
      ? ` Anyone can sign up for themselves, and public sign-up creates a ${joining} account only.`
      : ' Anyone can sign up for themselves.'
  }
  if (mode === 'invite') {
    return provisioning
      ? ` Accounts exist by invitation: ${provisioning} invites a person, who then creates the account.`
      : ' Accounts exist by invitation only.'
  }
  if (mode === 'request') {
    return provisioning
      ? ` A visitor requests access and ${provisioning} approves or rejects the request.`
      : ' A visitor requests access, and the request is approved before the account exists.'
  }
  if (mode === 'admin_created') {
    return provisioning
      ? ` There is no self sign-up: ${provisioning} creates every account.`
      : ' There is no self sign-up; accounts are created for people.'
  }
  if (mode === 'none') return ' No accounts are created in this product.'
  return mode ? ` Accounts are created in "${mode}" mode.` : ''
}

/** A field that is sometimes a string and sometimes a list, as one line. */
function oneLine(value) {
  if (Array.isArray(value)) return value.map(v => (typeof v === 'string' ? v : sentence(v))).join(', ')
  return text(value)
}

/** Formats requirement, validation, or notification objects into readable strings. */
function sentence(item) {
  if (typeof item === 'string') return item
  if (!item || typeof item !== 'object') return String(item ?? '')
  const direct = item.requirement || item.description || item.criterion || item.rule
    || item.risk || item.text || item.title
  if (item.field && item.rule) return `${item.field}: ${item.rule}`
  if (item.event) {
    const to = oneLine(item.recipients)
    const via = oneLine(item.channels)
    return `On ${item.event}${to ? `, notify ${to}` : ''}${via ? ` via ${via}` : ''}.`
  }
  if (item.report_name) {
    const by = oneLine(item.filters)
    const as = oneLine(item.exports)
    return `${item.report_name}${by ? `, filtered by ${by}` : ''}${as ? `, exported as ${as}` : ''}.`
  }
  if (item.name && item.description) return `${item.name} — ${item.description}`
  return direct || item.name || oneLine(item.steps) || JSON.stringify(item)
}

function groupBy(items, key, fallback) {
  const groups = new Map()
  for (const item of items) {
    const name = (item && typeof item === 'object' && text(item[key])) || fallback
    if (!groups.has(name)) groups.set(name, [])
    groups.get(name).push(item)
  }
  return [...groups.entries()]
}

/* ── primitives ──────────────────────────────────────────────────────────── */

/** A neutral label. Colour is reserved for the three things that mean something. */
const Chip = ({ children, tone = 'mute' }) => {
  const tones = {
    mute: 'border-black/10 bg-black/[.04] text-muted',
    id: 'border-black/10 bg-black/[.04] text-muted font-mono',
    warn: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
    good: 'border-emerald-500/30 bg-emerald-500/10 text-ink',
    bad: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
  }
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5
                      text-[10.5px] leading-none ${tones[tone] || tones.mute}`}>
      {children}
    </span>
  )
}

function Block({ n, title, icon: Icon, count, hint, children }) {
  return (
    <section className="rounded-none border border-black/10 bg-panel p-5 sm:p-6">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-black/10 pb-3">
        {Icon && <Icon className="size-4 shrink-0 self-center text-muted2" />}
        <span className="font-mono text-[11px] text-muted2">{n}</span>
        <h3 className="text-[15px] font-bold tracking-tight text-ink">{title}</h3>
        <span className="flex-1" />
        {count != null && <span className="font-mono text-[11px] text-muted2">{count}</span>}
      </header>
      {hint && <p className="mt-3 text-[12px] leading-relaxed text-muted2">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  )
}

const Nothing = ({ what }) => (
  <p className="py-2 text-[12px] text-muted2">The specification records no {what}.</p>
)

/** A paragraph that renders only when the document actually has one. */
const Prose = ({ children }) => (
  children ? <p className="text-[13px] leading-[1.75] text-ink">{children}</p> : null
)

/* ── the page ────────────────────────────────────────────────────────────── */

export default function Overview({ srs, onSelectView }) {
  const doc = srs?.document || {}
  const summary = typeof doc.app_summary === 'string' ? {} : (doc.app_summary || {})
  const blurb = typeof doc.app_summary === 'string' ? doc.app_summary : text(summary.short_description)
  const goal = text(summary.business_goal)
  const projectName = text(doc.project_name) || text(summary.app_name) || 'Application'

  const reqs = list(doc.functional_requirements)
  const nfrs = list(doc.non_functional_requirements)
  const security = list(doc.security_requirements)
  const roles = list(doc.roles)
  const access = list(doc.role_access_matrix)
  const tables = list(doc.database_design?.tables)
  const relationships = list(doc.database_design?.relationships)
  const workflows = list(doc.business_workflows)
  const trace = list(doc.requirement_traceability_matrix)
  const ambiguities = list(doc.ambiguities)
  const risks = list(doc.risk_priority)
  const diagrams = list(srs?.diagrams)

  const [activeDiagram, setActiveDiagram] = useState(0)
  const [zoomed, setZoomed] = useState(false)
  const current = diagrams[Math.min(activeDiagram, Math.max(0, diagrams.length - 1))]

  const verified = useMemo(
    () => trace.filter(r => /verified|passed/i.test(text(r?.verification_status))).length,
    [trace])
  // Calculate requirement verification coverage relative to total document requirements.
  const untraced = useMemo(() => {
    const traced = new Set(trace.map(r => text(r?.requirement_id)).filter(Boolean))
    return reqs.filter(r => text(r?.id) && !traced.has(text(r.id))).length
  }, [reqs, trace])
  const openQuestions = ambiguities.filter(a => a?.needs_clarification).length
  const review = doc.requirements_quality_review || {}
  const reviewer = review.reviewer || null

  if (!srs?.have?.document) {
    return <Empty>No specification has been adopted yet for this project.</Empty>
  }

  const auth = doc.authentication_requirement || {}

  return (
    <div className="mx-auto max-w-[1040px] space-y-5 pb-16 text-ink">

      {/* Header — identity only. Every chip is a field. */}
      <header className="rounded-none border border-black/10 bg-panel p-6">
        <h2 className="text-[24px] font-black tracking-tight text-ink">
          {text(doc.document_title) || `${projectName} — Software Requirements Specification`}
        </h2>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {text(doc.version) && <Chip tone="id">v{doc.version}</Chip>}
          {text(doc.document_control?.document_id) && <Chip tone="id">{doc.document_control.document_id}</Chip>}
          {text(doc.system_category) && <Chip>{doc.system_category}</Chip>}
          {text(doc.app_type) && <Chip>{doc.app_type}</Chip>}
          {text(doc.document_language) && <Chip>{doc.document_language}</Chip>}
          {text(doc.standards_profile?.requirements_standard) &&
            <Chip>{doc.standards_profile.requirements_standard}</Chip>}
          <Chip>{auth.login_required ? 'Sign-in required' : 'No sign-in'}</Chip>
          {openQuestions > 0 && <Chip tone="warn">{openQuestions} open question{openQuestions === 1 ? '' : 's'}</Chip>}
          {reviewer?.iterations_used != null &&
            <Chip tone={reviewer.unresolved_findings?.length ? 'warn' : 'good'}>
              Reviewed · {reviewer.iterations_used} round{reviewer.iterations_used === 1 ? '' : 's'}
            </Chip>}
        </div>
      </header>

      {/* 1 — Purpose */}
      <Block n="1" title="Purpose and scope" icon={FileText}>
        <div className="space-y-3">
          <Prose>{blurb}</Prose>
          {goal && goal !== blurb && (
            <p className="text-[13px] leading-[1.75] text-muted">
              <span className="font-semibold text-ink">Business goal.</span> {goal}
            </p>
          )}
          {!blurb && !goal && <Nothing what="summary" />}
          {list(summary.target_users).length > 0 && (
            <div>
              <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted2">Intended users</p>
              <div className="flex flex-wrap gap-1.5">
                {list(summary.target_users).map((u, i) => <Chip key={i}>{sentence(u)}</Chip>)}
              </div>
            </div>
          )}
          {list(doc.main_modules).length > 0 && (
            <div>
              <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted2">Modules</p>
              <div className="flex flex-wrap gap-1.5">
                {list(doc.main_modules).map((m, i) => <Chip key={i}>{sentence(m)}</Chip>)}
              </div>
            </div>
          )}
        </div>
      </Block>

      {/* 2 — Roles */}
      <Block n="2" title="Who uses it" icon={Users} count={roles.length || null}>
        {roles.length === 0 ? <Nothing what="roles" /> : (
          <ul className="space-y-3">
            {roles.map((role, i) => {
              const name = text(role?.role_name) || text(role?.name) || `Role ${i + 1}`
              const row = access.find(r => text(r?.role) === name || text(r?.role_name) === name)
              const permissions = row
                ? Object.entries(row).filter(([k, v]) => !/^role(_name)?$/.test(k) && v)
                : []
              return (
                <li key={i} className="border-b border-black/[.07] pb-3 last:border-0 last:pb-0">
                  <p className="text-[13px] font-semibold text-ink">{name}</p>
                  {text(role?.description) && (
                    <p className="mt-1 text-[12.5px] leading-relaxed text-muted">{role.description}</p>
                  )}
                  {permissions.length > 0 && (
                    <dl className="mt-2 space-y-1">
                      {permissions.map(([k, v]) => (
                        <div key={k} className="flex flex-wrap gap-x-2 text-[12px] leading-relaxed">
                          <dt className="text-muted2">{k.replace(/_/g, ' ')}</dt>
                          <dd className="text-ink">{v === true ? 'yes' : oneLine(v)}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </li>
              )
            })}
          </ul>
        )}
        {(auth.login_required || text(auth.registration_mode) || text(auth.sign_in_route)) && (
          <p className="mt-4 border-t border-black/[.07] pt-3 text-[12.5px] leading-relaxed text-muted">
            {auth.login_required
              ? 'Signing in is required to reach the protected pages.'
              : 'The application can be used without signing in.'}
            {registrationSentence(auth)}
            {text(auth.sign_in_route) && ` The sign-in route is ${auth.sign_in_route}.`}
            {auth.password_reset_required && ' A password reset flow is required.'}
          </p>
        )}
      </Block>

      {/* 3 — Functional requirements, all of them */}
      <Block n="3" title="What it must do" icon={Workflow} count={reqs.length || null}
        hint="Functional requirements, grouped by the module that owns them.">
        {reqs.length === 0 ? <Nothing what="functional requirements" /> : (
          groupBy(reqs, 'module', 'General').map(([module, items]) => (
            <div key={module} className="mb-4 last:mb-0">
              <p className="mb-2 text-[11px] uppercase tracking-wide text-muted2">
                {module} <span className="font-mono text-muted2">· {items.length}</span>
              </p>
              <ul className="space-y-2">
                {items.map((r, i) => (
                  <li key={i} className="rounded-none border border-black/[.07] bg-black/[.02] p-3">
                    <p className="text-[12.5px] leading-relaxed text-ink">{sentence(r)}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {text(r?.id) && <Chip tone="id">{r.id}</Chip>}
                      {text(r?.priority) && <Chip>{r.priority}</Chip>}
                      {list(r?.allowed_roles).map((role, j) => <Chip key={j}>{sentence(role)}</Chip>)}
                      {text(r?.verification_method) && <Chip>verify by {r.verification_method}</Chip>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </Block>

      {/* 4 — Non-functional */}
      <Block n="4" title="How well it must do it" icon={Layers} count={nfrs.length || null}
        hint="Non-functional requirements, grouped by quality attribute.">
        {nfrs.length === 0 ? <Nothing what="non-functional requirements" /> : (
          groupBy(nfrs, 'category', 'General').map(([category, items]) => (
            <div key={category} className="mb-4 last:mb-0">
              <p className="mb-2 text-[11px] uppercase tracking-wide text-muted2">{category}</p>
              <ul className="space-y-1.5">
                {items.map((n, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-[12.5px] leading-relaxed text-ink">
                    {text(n?.id) && <span className="mt-[3px]"><Chip tone="id">{n.id}</Chip></span>}
                    <span>
                      {sentence(n)}
                      {text(n?.verification_method) && (
                        <span className="ml-1.5 text-muted2">· verify by {n.verification_method}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </Block>

      {/* 5 — Security */}
      <Block n="5" title="Security" icon={Shield} count={security.length || null}>
        {security.length === 0 ? <Nothing what="security requirements" /> : (
          <ol className="space-y-1.5">
            {security.map((s, i) => (
              <li key={i} className="grid grid-cols-[26px_1fr] gap-2 text-[12.5px] leading-relaxed text-ink">
                <span className="font-mono text-[11px] text-muted2">{i + 1}.</span>
                <span>{sentence(s)}</span>
              </li>
            ))}
          </ol>
        )}
      </Block>

      {/* 6 — Workflows: the most readable prose in the document */}
      <Block n="6" title="How the work flows" icon={ArrowRight} count={workflows.length || null}>
        {workflows.length === 0 ? <Nothing what="business workflows" /> : (
          <div className="space-y-4">
            {workflows.map((w, i) => (
              <div key={i} className="border-b border-black/[.07] pb-4 last:border-0 last:pb-0">
                <p className="text-[13px] font-semibold text-ink">
                  {text(w?.workflow_name) || text(w?.name) || `Workflow ${i + 1}`}
                  {text(w?.who) && <span className="ml-2 font-normal text-muted2">— {w.who}</span>}
                </p>
                {list(w?.steps).length > 0 && (
                  <ol className="mt-2 space-y-1">
                    {list(w.steps).map((step, j) => (
                      <li key={j} className="grid grid-cols-[26px_1fr] gap-2 text-[12.5px] leading-relaxed text-ink">
                        <span className="font-mono text-[11px] text-muted2">{j + 1}.</span>
                        <span>{sentence(step)}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            ))}
          </div>
        )}
      </Block>

      {/* 7 — Data */}
      <Block n="7" title="What it remembers" icon={Database} count={tables.length || null}>
        {tables.length === 0 ? <Nothing what="data design" /> : (
          <>
            <ul className="space-y-2">
              {tables.map((table, i) => (
                <li key={i} className="rounded-none border border-black/[.07] bg-black/[.02] p-3">
                  <p className="text-[12.5px] font-semibold text-ink">
                    {text(table?.table_name) || text(table?.name) || `Table ${i + 1}`}
                    <span className="ml-2 font-mono text-[11px] font-normal text-muted2">
                      {list(table?.fields).length} field{list(table?.fields).length === 1 ? '' : 's'}
                    </span>
                  </p>
                  {text(table?.description) && (
                    <p className="mt-1 text-[12px] leading-relaxed text-muted">{table.description}</p>
                  )}
                </li>
              ))}
            </ul>
            {relationships.length > 0 && (
              <div className="mt-4 border-t border-black/[.07] pt-3">
                <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted2">Relationships</p>
                <ul className="space-y-1">
                  {relationships.map((r, i) => (
                    <li key={i} className="text-[12.5px] leading-relaxed text-ink">{sentence(r)}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </Block>

      {/* 8 — Diagrams, with the narrative the document actually carries */}
      <Block n="8" title="Diagrams" icon={Compass} count={diagrams.length || null}>
        {diagrams.length === 0 ? <Nothing what="diagrams" /> : (
          <>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {diagrams.map((d, i) => (
                <button key={i} type="button" onClick={() => setActiveDiagram(i)}
                  className={`rounded-full border px-3 py-1 text-[11px] transition
                    ${i === activeDiagram
                      ? 'border-black/25 bg-black/10 text-ink'
                      : 'border-black/10 text-muted2 hover:text-ink'}`}>
                  {d.title || d.name}
                </button>
              ))}
            </div>

            {current && (
              <div className="space-y-3">
                {current.applicable === false && (
                  <p className="text-[12px] text-amber-700">
                    <AlertTriangle className="mr-1.5 inline size-3.5" />
                    {current.applicabilityNote || 'This diagram does not apply to this product.'}
                  </p>
                )}
                {current.svg
                  ? <button type="button" onClick={() => setZoomed(true)}
                      className="block w-full cursor-zoom-in rounded-none border border-black/10 bg-white p-2"
                      title="Open full size">
                      <div className="srs-diagram flex justify-center [&_svg]:h-auto [&_svg]:max-h-[380px] [&_svg]:max-w-full"
                        dangerouslySetInnerHTML={{ __html: current.svg }} />
                    </button>
                  : current.drawable
                    ? <pre className="overflow-x-auto rounded-none border border-black/10 bg-code p-3
                                      font-mono text-[11px] leading-relaxed text-muted">{current.mermaid}</pre>
                    : <DiagramMissing diagram={current} />}

                {current.businessSummary && (
                  <p className="text-[12.5px] leading-relaxed text-ink">{current.businessSummary}</p>
                )}
                {list(current.flowExplanation).length > 0 ? (
                  <ol className="space-y-1">
                    {list(current.flowExplanation).map((step, i) => (
                      <li key={i} className="grid grid-cols-[26px_1fr] gap-2 text-[12.5px] leading-relaxed text-ink">
                        <span className="font-mono text-[11px] text-muted2">{i + 1}.</span>
                        <span>{String(step).replace(/^\d+\.\s*/, '')}</span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-[12px] text-muted2">No walkthrough was recorded for this diagram.</p>
                )}
                {list(current.keyTakeaways).length > 0 && (
                  <ul className="space-y-1 border-t border-black/[.07] pt-3">
                    {list(current.keyTakeaways).map((t, i) => (
                      <li key={i} className="flex gap-2 text-[12px] leading-relaxed text-muted">
                        <CheckCircle2 className="mt-[2px] size-3.5 shrink-0 text-muted2" />
                        <span>{sentence(t)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <button type="button" onClick={() => setZoomed(true)}
                  className="inline-flex items-center gap-1.5 text-[11.5px] text-muted2 hover:text-ink">
                  <Maximize2 className="size-3.5" /> Open full size
                </button>
              </div>
            )}
          </>
        )}
      </Block>

      {/* 9 — Rules and interfaces, none of which used to be shown */}
      {[['validation_rules', 'Validation rules'], ['notification_rules', 'Notification rules'],
        ['reporting_requirements', 'Reports'], ['integration_requirements', 'Integrations'],
        ['acceptance_criteria', 'Acceptance criteria']]
        .filter(([key]) => list(doc[key]).length > 0).length > 0 && (
        <Block n="9" title="Rules, reports and interfaces" icon={Circle}>
          <div className="space-y-4">
            {[['validation_rules', 'Validation rules'], ['notification_rules', 'Notification rules'],
              ['reporting_requirements', 'Reports'], ['integration_requirements', 'Integrations'],
              ['acceptance_criteria', 'Acceptance criteria']].map(([key, label]) => {
              const items = list(doc[key])
              if (!items.length) return null
              return (
                <div key={key}>
                  <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted2">
                    {label} <span className="font-mono text-muted2">· {items.length}</span>
                  </p>
                  <ul className="space-y-1">
                    {items.map((item, i) => (
                      <li key={i} className="text-[12.5px] leading-relaxed text-ink">{sentence(item)}</li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        </Block>
      )}

      {/* 10 — Open questions */}
      <Block n="10" title="What is still open" icon={HelpCircle}
        count={ambiguities.length || null}
        hint="Ambiguities the specification recorded, and the assumptions made in their place.">
        {ambiguities.length === 0 && !list(doc.assumptions).length && !list(doc.constraints).length
          ? <Nothing what="open questions, assumptions or constraints" />
          : (
            <div className="space-y-4">
              {ambiguities.length > 0 && (
                <ul className="space-y-2">
                  {ambiguities.map((a, i) => (
                    <li key={i} className="rounded-none border border-black/[.07] bg-black/[.02] p-3">
                      <p className="text-[12.5px] leading-relaxed text-ink">{sentence(a)}</p>
                      {text(a?.assumption_made) && (
                        <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                          <span className="text-muted">Assumed:</span> {a.assumption_made}
                        </p>
                      )}
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {text(a?.id) && <Chip tone="id">{a.id}</Chip>}
                        {text(a?.area) && <Chip>{a.area}</Chip>}
                        {a?.needs_clarification && <Chip tone="warn">needs an answer</Chip>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {[['assumptions', 'Assumptions'], ['constraints', 'Constraints']].map(([key, label]) => (
                list(doc[key]).length > 0 && (
                  <div key={key}>
                    <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted2">{label}</p>
                    <ul className="space-y-1">
                      {list(doc[key]).map((item, i) => (
                        <li key={i} className="text-[12.5px] leading-relaxed text-ink">{sentence(item)}</li>
                      ))}
                    </ul>
                  </div>
                )
              ))}
            </div>
          )}
      </Block>

      {/* 11 — Risks */}
      <Block n="11" title="Risks" icon={AlertTriangle} count={risks.length || null}>
        {risks.length === 0 ? <Nothing what="risks" /> : (
          <ul className="space-y-2">
            {risks.map((r, i) => {
              const severity = text(r?.severity) || text(r?.priority) || text(r?.impact)
              const high = /high|critical|severe/i.test(severity)
              return (
                <li key={i} className="rounded-none border border-black/[.07] bg-black/[.02] p-3">
                  <p className="text-[12.5px] leading-relaxed text-ink">{sentence(r)}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {text(r?.id) && <Chip tone="id">{r.id}</Chip>}
                    {severity && <Chip tone={high ? 'bad' : 'mute'}>{severity}</Chip>}
                    {text(r?.mitigation) && <Chip>mitigated</Chip>}
                  </div>
                  {text(r?.mitigation) && (
                    <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                      <span className="text-muted">Mitigation:</span> {r.mitigation}
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Block>

      {/* 12 — Verification: real counts, or an honest absence */}
      <Block n="12" title="What has been verified" icon={CheckCircle2} count={trace.length || null}>
        {trace.length === 0 ? <Nothing what="traceability" /> : (
          <>
            <div className={'mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-none border px-3 py-2 '
              + (untraced > 0 ? 'border-amber-400/30 bg-amber-400/10'
                              : 'border-black/[.07] bg-black/[.02]')}>
              <span className="text-[12.5px] text-ink">
                <b className="font-semibold text-ink">{reqs.length}</b> requirements
              </span>
              <span className="text-[12.5px] text-muted">
                <b className="font-semibold text-ink">{trace.length}</b> traced
              </span>
              <span className="text-[12.5px] text-muted">
                <b className="font-semibold text-ink">{verified}</b> verified
              </span>
              {untraced > 0 && (
                <span className="text-[12.5px] font-semibold text-amber-300">
                  {untraced} with no traceability row
                </span>
              )}
            </div>
            {untraced > 0 && (
              <p className="mb-3 text-[12px] leading-relaxed text-amber-200/80">
                The matrix does not cover every requirement, so the verified count below is a
                share of what is listed, not of the specification.
              </p>
            )}
            <ul className="space-y-1.5">
              {trace.map((row, i) => {
                const status = text(row?.verification_status)
                const ok = /verified|passed/i.test(status)
                return (
                  <li key={i} className="flex flex-wrap items-center gap-1.5 border-b border-black/[.07]
                                         py-2 text-[12px] last:border-0">
                    {ok ? <CheckCircle2 className="size-3.5 shrink-0 text-ink" />
                        : <XCircle className="size-3.5 shrink-0 text-muted2" />}
                    <Chip tone="id">{text(row?.requirement_id) || `#${i + 1}`}</Chip>
                    {oneLine(row?.pages) && <span className="text-muted">pages: {oneLine(row.pages)}</span>}
                    {oneLine(row?.tables) && <span className="text-muted">data: {oneLine(row.tables)}</span>}
                    {oneLine(row?.test_case) && <span className="text-muted">test: {oneLine(row.test_case)}</span>}
                    {status && <Chip tone={ok ? 'good' : 'mute'}>{status}</Chip>}
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </Block>

      {/* 13 — Quality review, including the reviewer's verdict */}
      {(reviewer || list(review.items_needing_human_review).length > 0) && (
        <Block n="13" title="Quality review" icon={Lock}>
          {reviewer && (
            <div className="mb-3 space-y-1.5 text-[12.5px] text-ink">
              <p>
                The draft went through {reviewer.iterations_used ?? 0} review
                round{reviewer.iterations_used === 1 ? '' : 's'}
                {text(reviewer.stopped_because) && `, stopping because ${reviewer.stopped_because}`}.
              </p>
              {reviewer.final_scores && (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(reviewer.final_scores).map(([k, v]) => (
                    <Chip key={k}>{k.replace(/_/g, ' ')}: {v}/5</Chip>
                  ))}
                </div>
              )}
              {list(reviewer.unresolved_findings).length > 0 && (
                <ul className="mt-2 space-y-1">
                  {list(reviewer.unresolved_findings).map((f, i) => (
                    <li key={i} className="text-[12px] leading-relaxed text-amber-300/85">
                      {text(f?.requirement_id) && <span className="font-mono">{f.requirement_id}: </span>}
                      {sentence(f?.problem ? { requirement: f.problem } : f)}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {list(review.items_needing_human_review).length > 0 && (
            <ul className="space-y-1 border-t border-black/[.07] pt-3">
              {list(review.items_needing_human_review).map((item, i) => (
                <li key={i} className="text-[12px] leading-relaxed text-muted">{sentence(item)}</li>
              ))}
            </ul>
          )}
        </Block>
      )}

      {onSelectView && (
        <button type="button" onClick={() => onSelectView('document')}
          className="flex w-full items-center justify-center gap-2 rounded-none border border-black/10
                     bg-black/[.03] px-5 py-4 text-[13px] font-semibold text-ink
                     transition hover:border-black/25 hover:text-ink">
          <FileText className="size-4" />
          Read the formal document
          <ArrowRight className="size-4" />
        </button>
      )}

      {zoomed && current?.svg && (
        <DiagramViewer svg={current.svg} title={current.title || current.name}
          onClose={() => setZoomed(false)} />
      )}
    </div>
  )
}
