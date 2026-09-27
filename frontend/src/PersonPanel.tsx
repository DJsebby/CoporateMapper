import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { get, observedDate, personName, position, post, readable, safeUrl, type ContextStatement, type DemoProfile, type EnrichmentJob, type Finding, type PersonDetail, type RiskScore } from './types'
import PersonAvatar from './PersonAvatar'

const realCategories = ['business_email', 'business_phone', 'interest', 'qualification', 'skill', 'professional_history', 'publication', 'profile_url', 'office_location']
const permittedCategories = new Set([...realCategories, 'role', 'portrait_url', 'australian_work_context', 'skills', 'professional_role'])
const categoryLabel = (category: string) => ({business_email:'Business email',business_phone:'Business telephone',interest:'Interests and sports',skill:'Skills',profile_url:'Profile',office_location:'Office city / country'}[category] || readable(category))
const active = (job: EnrichmentJob) => ['queued', 'running', 'awaiting_review'].includes(job.status)
const rowId = (id: string) => `additional-finding-${id}`

function Values({ label, values, links = false }: { label: string; values: string[]; links?: boolean }) {
  return <div className="detail-field"><dt>{label}</dt><dd>{values.length ? values.map(value => <div key={value}>{links && safeUrl(value) ? <a href={safeUrl(value)} target="_blank" rel="noreferrer">{value} ↗</a> : value}</div>) : <span className="muted">Not recorded</span>}</dd></div>
}

function InformationTable({ findings, missing, demo }: { findings: Finding[]; missing: string[]; demo: boolean }) {
  return <table className="information-table" aria-label="Employee additional information">
    <thead><tr><th scope="col">Information</th><th scope="col">Value</th><th scope="col">Source</th></tr></thead>
    <tbody>{findings.map((finding, index) => <tr id={rowId(finding.id)} tabIndex={-1} key={finding.id}>
      <th scope="row">{categoryLabel(finding.category)}</th><td>{finding.value}</td>
      <td>{demo ? <span className="fixture-source" title={finding.source_url}>{finding.source_name || 'Authored fixture'} <small>Fixture source {index + 1}</small></span> : safeUrl(finding.source_url) ? <a href={safeUrl(finding.source_url)} target="_blank" rel="noreferrer" aria-label={`View source ${index + 1}`} title={finding.source_name}>{finding.source_name || 'Original source'} ↗</a> : <span>Source unavailable</span>}<small>Observed {observedDate(finding.observed_at)}</small></td>
    </tr>)}{missing.map(category => <tr key={`missing-${category}`}><th scope="row">{categoryLabel(category)}</th><td className="muted">Not recorded</td><td className="muted">—</td></tr>)}</tbody>
  </table>
}

function citationMap(statementGroups: ContextStatement[][], findings: Finding[]) {
  const map = new Map<string, number>()
  for (const statement of statementGroups.flat()) {
    for (const id of statement.finding_ids) {
      if (map.has(id) || findings.findIndex(finding => finding.id === id) < 0) continue
      map.set(id, map.size + 1)
    }
  }
  return map
}

function StatementList({ statements, citations }: { statements: ContextStatement[]; citations: Map<string, number> }) {
  return <div className="context-statements">{statements.map((statement, index) => <p className="context-statement" key={index}>
    {statement.text} <span className="context-reason-inline">{statement.reason}</span>
    {statement.finding_ids.map(id => citations.get(id)).filter((n): n is number => n !== undefined).map(n =>
      <sup key={n}><a href={`#context-source-${n}`}>[{n}]</a></sup>)}
  </p>)}</div>
}

function SourceList({ citations, findings }: { citations: Map<string, number>; findings: Finding[] }) {
  function focusFact(event: MouseEvent<HTMLAnchorElement>, id: string) {
    event.preventDefault()
    const row = document.getElementById(rowId(id))
    row?.scrollIntoView({behavior: 'auto', block: 'center'}); row?.focus({preventScroll:true})
  }
  const entries = [...citations.entries()].sort((a, b) => a[1] - b[1])
  if (!entries.length) return null
  return <><h4>Sources</h4><ol className="context-sources">{entries.map(([id, n]) => {
    const finding = findings.find(value => value.id === id)
    return !finding ? null : <li key={id} id={`context-source-${n}`}>[{n}] <a href={`#${rowId(id)}`} onClick={event => focusFact(event,id)}>{categoryLabel(finding.category)}: {finding.value}</a></li>
  })}</ol></>
}

function riskFactorLabel(key: string) {
  return key.replace(/^person\./, '').replace(/_/g, ' ').replace('=', ': ')
}

function RiskScoreSummary({ risk }: { risk: RiskScore }) {
  const entries = Object.entries(risk.breakdown).filter(([, points]) => points !== 0)
  return <div className="risk-summary">
    <h4>Fictional risk score</h4>
    <p className={`risk-badge risk-${risk.band}`}>{risk.score.toFixed(1)} / 10 · {readable(risk.band)}</p>
    <p className="profile-help">A literature-informed phishing-susceptibility heuristic, not a calibrated probability, computed from this profile's authored fictional traits and how much personal data its table currently exposes.</p>
    {entries.length > 0 && <ul className="risk-breakdown">{entries.map(([key, points]) => <li key={key}>{riskFactorLabel(key)} ({points > 0 ? '+' : ''}{points})</li>)}</ul>}
  </div>
}

function ProfileContext({ profile, busy, onRetry }: { profile: DemoProfile; busy: boolean; onRetry: () => void }) {
  const context = profile.context
  const failed = ['failed','interrupted','cancelled'].includes(context.status)
  const summary = context.summary ?? []
  const privacy = context.privacy_implications ?? []
  const citations = citationMap([summary, privacy], profile.findings)
  return <section className="demo-context" aria-labelledby="demo-context-title">
    <h3 id="demo-context-title">Gemini context · fictional demo</h3>
    <div className="fictional-banner"><strong>Safe to demonstrate</strong><p>Every fact and AI insight below is fictional proof-of-concept data from authored, reserved <code>.invalid</code> sources. Nothing here is a real person.</p></div>
    {profile.risk_score && <RiskScoreSummary risk={profile.risk_score}/>}
    <p className="profile-help">A concise profile summary, missing information and general privacy implications, based only on the authored fixture facts above.</p>
    {!profile.populated && <p className="profile-status">Populate the demo information to generate context automatically.</p>}
    {profile.populated && context.status === 'not_started' && <p className="profile-status">Context has not been generated.</p>}
    {['queued','running'].includes(context.status) && <p className="profile-status" role="status">{context.status === 'queued' ? 'Gemini context queued…' : 'Generating Gemini context…'} The populated table remains available.</p>}
    {failed && <p className="action-error" role="alert">{context.error || `Context ${context.status}.`} Saved demo information remains available.</p>}
    {context.status === 'completed' && <>
      <h4>Profile summary</h4><StatementList statements={summary} citations={citations}/>
      <h4>Gaps</h4>{context.gaps?.length ? <ul className="context-gaps">{context.gaps.map((gap,index) => <li key={index}>{gap}</li>)}</ul> : <p>No additional gaps reported.</p>}
      <h4>General privacy implications</h4><StatementList statements={privacy} citations={citations}/>
      <SourceList citations={citations} findings={profile.findings}/>
      <p className="context-meta">{context.model}{context.generated_at ? ` · Generated ${observedDate(context.generated_at)}` : ''}</p>
    </>}
    {profile.populated && (failed || context.status === 'not_started') && <button className="button" disabled={busy} onClick={onRetry}>{busy ? 'Queuing…' : failed ? 'Retry Gemini context' : 'Generate Gemini context'}</button>}
  </section>
}

export default function PersonPanel({ id, jobs, onClose, onChanged }: { id: string; jobs: EnrichmentJob[]; onClose: () => void; onChanged: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const mounted = useRef(false)
  const [person, setPerson] = useState<PersonDetail | null>(null)
  const [error, setError] = useState('')
  const [dismissError, setDismissError] = useState('')
  const [dismissing, setDismissing] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [submittedJob, setSubmittedJob] = useState<EnrichmentJob | null>(null)
  const pending = useRef(false)
  const submission = useRef<{action: string; key: string} | null>(null)
  const matchingJobs = jobs.filter(job => job.items.some(item => item.person_id === id))
  // Changes to progress or reviewed candidates refresh detail without creating another job.
  const jobRevision = JSON.stringify(matchingJobs)
  const demo = person?.demo_profile ?? null
  const profileJobs = matchingJobs.filter(job => demo ? job.kind === 'demo_profile' : job.kind !== 'demo_profile')
  const currentJobs = submittedJob && !profileJobs.some(job => job.id === submittedJob.id) ? [submittedJob, ...profileJobs] : profileJobs
  const activeJob = currentJobs.find(active)
  const latestJob = currentJobs[0]
  const contextPending = !!demo && ['queued','running'].includes(demo.context.status)
  const disabled = busy || !!activeJob || contextPending
  const findings = demo ? (demo.populated ? demo.findings : []) : (person?.findings ?? []).filter(finding => permittedCategories.has(finding.category))
  const missing = demo ? demo.missing_categories : realCategories.filter(category => !findings.some(finding => finding.category === category))

  useEffect(() => { mounted.current = true; const previous = document.activeElement as HTMLElement; const modal = dialog.current; modal?.showModal(); return () => { mounted.current = false; modal?.close(); previous?.focus() } }, [])
  useEffect(() => {
    const controller = new AbortController()
    get<PersonDetail>(`/api/people/${encodeURIComponent(id)}`, controller.signal).then(result => { if (!controller.signal.aborted) { setPerson(result); setError('') } }).catch(err => { if (err.name !== 'AbortError' && !controller.signal.aborted) setError(err.message) })
    return () => controller.abort()
  }, [id, attempt, jobRevision])

  async function populate(action: 'populate' | 'context') {
    if (disabled || pending.current) return
    pending.current = true; setBusy(true); setActionError(''); setNotice('')
    if (submission.current?.action !== action) submission.current = {action, key:crypto.randomUUID()}
    const path = demo ? `/api/demo/profiles/${encodeURIComponent(id)}/${action}` : '/api/enrichment/jobs'
    const body = demo ? {idempotency_key:submission.current.key} : {person_ids:[id], idempotency_key:submission.current.key, search_again:false}
    try {
      const job = await post<EnrichmentJob>(path, body)
      if (!mounted.current) return
      submission.current = null; setSubmittedJob(job); setAttempt(value => value + 1)
      setNotice(demo ? action === 'context' ? 'Gemini context queued.' : 'Demo information queued. Gemini context follows automatically.' : 'Additional information queued. Saved findings appear here as collection progresses.')
      onChanged()
    } catch (error) { if (mounted.current) setActionError(error instanceof Error ? error.message : 'Unable to queue profile information.') }
    finally { pending.current = false; if (mounted.current) setBusy(false) }
  }
  async function dismiss(findingId: string) {
    if (dismissing) return
    setDismissing(findingId); setDismissError('')
    try {
      await post(`/api/people/${encodeURIComponent(id)}/findings/${encodeURIComponent(findingId)}/dismiss`)
      if (mounted.current) { setAttempt(value => value + 1); onChanged() }
    } catch (error) { if (mounted.current) setDismissError(error instanceof Error ? error.message : 'Unable to dismiss this finding.') }
    finally { if (mounted.current) setDismissing('') }
  }
  return <dialog className="person-panel" ref={dialog} onCancel={onClose} aria-labelledby="person-title" onClick={event => { if (event.target === dialog.current && event.clientX < dialog.current!.getBoundingClientRect().left) onClose() }}>
    <div className="panel-top"><span>PERSON DETAILS</span><button className="icon-button" aria-label="Close person details" onClick={onClose}>×</button></div>
    {!person && !error && <div className="panel-body" role="status"><h2 id="person-title">Loading person details…</h2></div>}
    {error && !person && <div className="panel-body" role="alert"><h2 id="person-title">Details unavailable</h2><p>{error}</p><button className="button" onClick={() => setAttempt(x=>x+1)}>Try again</button></div>}
    {person && <div className="panel-body"><PersonAvatar person={person} large/><h2 id="person-title">{personName(person)}</h2><p className="panel-position">{position(person)}</p>{demo?.risk_score ? <div className={`panel-score risk-${demo.risk_score.band}`}><span>Risk score</span><strong>{demo.risk_score.score.toFixed(1)}</strong><small>{readable(demo.risk_score.band)} · fictional demo</small></div> : <div className="panel-score"><span>Score</span><strong>-</strong><small>{demo ? 'Populate demo information to calculate' : 'Not calculated yet'}</small></div>}
      {error && <div className="action-error" role="alert">Unable to refresh details. Saved information remains visible. <button className="text-button" onClick={() => setAttempt(value => value + 1)}>Retry details</button></div>}
      <section className="additional-information" aria-labelledby="additional-information-title">
        <h3 id="additional-information-title">Additional information</h3>
        {demo ? <div className="fictional-banner"><strong>Fictional demo · {demo.coverage} profile</strong><p>All details, including personal information, are invented. Sources are authored fixtures, not live websites.</p></div> : <p className="profile-help">Collect source-backed business contacts, professional details and general interests, including sports when explicitly supported. Missing information stays marked “Not recorded”.</p>}
        <div className="profile-actions"><button className="button" disabled={disabled || !!demo?.populated} onClick={() => void populate('populate')}>{busy && submission.current?.action === 'populate' ? 'Queuing…' : demo ? demo.populated ? 'Demo information populated' : 'Populate demo information' : 'Populate additional information'}</button></div>
        {!demo && <p className="profile-help">Up to one Australian search per run; eligible results are reused for seven days. Opening or refreshing this profile never starts a search.</p>}
        {activeJob && <p className="profile-status" role="status">{activeJob.status === 'awaiting_review' ? 'Candidate review is needed in Recent activity. Saved findings are shown below.' : `Profile progress: ${readable(activeJob.items.find(item => item.person_id === id)?.stage || activeJob.status)}.`}</p>}
        {!demo && latestJob && ['failed','incomplete','interrupted','cancelled'].includes(latestJob.status) && <p className="action-error" role="alert">Collection {readable(latestJob.status)}. {latestJob.items.find(item => item.person_id === id)?.error || latestJob.error || 'Saved findings remain available.'}</p>}
        {notice && !activeJob && !latestJob && <p className="action-notice" role="status">{notice}</p>}
        {actionError && <p className="action-error" role="alert">{actionError}</p>}
        <InformationTable findings={findings} missing={missing} demo={!!demo}/>
        {demo && !demo.populated && <p className="profile-help">The table will be populated after you click. This fixture deliberately contains {demo.coverage === 'full' ? 'a fuller set of information' : 'missing information'}.</p>}
      </section>
      {demo && <ProfileContext profile={demo} busy={disabled} onRetry={() => void populate('context')}/>}
      <h3>Profile</h3><dl><Values label="Names" values={person.names}/><Values label="Positions" values={person.job_titles}/><Values label="Organisations" values={person.organisations}/><Values label="Email" values={person.emails}/><Values label="Telephone" values={person.telephones}/><Values label="Profiles" values={person.profile_urls} links/><Values label="Other links" values={person.same_as} links/><Values label="Portrait images" values={person.image_urls ?? []} links/></dl>
      <h3 className="evidence-title">Supported findings <span>{person.findings?.length ?? 0}</span></h3><p className="muted text-sm">Each finding links to its supporting page. Different sources and conflicting observations remain separate.</p>
      {dismissError && <p role="alert" className="action-error">{dismissError}</p>}
      {!person.findings?.length && <p className="finding-empty">No supported findings recorded.</p>}
      {person.findings?.map(finding => <article className="finding" key={finding.id}>
        <span className="finding-category">{readable(finding.category)}</span><p className="finding-value">{finding.value}</p>
        {safeUrl(finding.source_url) && <a href={safeUrl(finding.source_url)} target="_blank" rel="noreferrer">{finding.source_name || 'Original source'} ↗</a>}
        <p className="finding-date">Observed {observedDate(finding.observed_at)}</p>
        <details><summary>Supporting evidence</summary><p>{finding.evidence}</p><p>Method: {finding.method}</p></details>
        <button className="text-button" disabled={!!dismissing} onClick={() => void dismiss(finding.id)}>{dismissing === finding.id ? 'Dismissing…' : 'Dismiss finding'}</button>
      </article>)}
    </div>}
  </dialog>
}
