import { useState } from 'react'
import { observedDate, post, readable, safeUrl, type Candidate, type EnrichmentItem, type EnrichmentJob, type JobsPage } from './types'

export default function RecentActivity({ data, error, onRefresh, onChanged }: { data: JobsPage | null; error: string; onRefresh: () => void; onChanged: () => void }) {
  const [pending, setPending] = useState('')
  const [mutationError, setMutationError] = useState('')
  const [workplaceSources, setWorkplaceSources] = useState<Record<string, string>>({})
  async function mutate(path: string, body: unknown, key: string) {
    if (pending) return
    setPending(key); setMutationError('')
    try { await post<EnrichmentJob>(path, body); onChanged(); onRefresh() }
    catch (error) { setMutationError(error instanceof Error ? error.message : 'Unable to update this job.') }
    finally { setPending('') }
  }
  function review(job: EnrichmentJob, item: EnrichmentItem, candidate: Candidate, decision: 'accept' | 'reject', source?: string) {
    return mutate(`/api/enrichment/jobs/${encodeURIComponent(job.id)}/items/${encodeURIComponent(item.id)}/review`, {candidate_id: candidate.id, decision, ...(source ? {australian_work_source: source} : {})}, candidate.id)
  }
  return <section className={`recent-activity ${error ? 'activity-unavailable' : ''}`} aria-labelledby="activity-title" aria-describedby="activity-note">
    <div className="activity-heading"><h2 id="activity-title">Recent activity</h2><span className="activity-live">{error ? 'Unavailable' : 'Live'}</span><p id="activity-note">Saved enrichment jobs. Updated every two seconds.</p></div>
    {error && <div className="activity-message activity-retry"><p role="status">{error}</p><button className="button" onClick={onRefresh}>Retry activity</button></div>}
    {mutationError && <p role="alert" className="activity-message action-error">{mutationError}</p>}
    {!data && !error && <p role="status" className="activity-message">Loading activity…</p>}
    {data && !data.jobs.length && <p className="activity-message">No enrichment jobs yet. Select employees to start.</p>}
    <ol className="activity-list">{data?.jobs.map(job => <li className="activity-job" key={job.id}>
      <div className="job-heading"><h3>{job.kind === 'demo_profile' ? 'Demo profile context' : (job.mode === 'demo' || job.namespace?.startsWith('demo')) ? 'Demo enrichment' : 'Employee enrichment'}</h3><span className={`job-status status-${job.status}`}>{readable(job.status)}</span></div>
      <span className="activity-time">{observedDate(job.created_at)}</span>
      <p>{job.kind === 'demo_profile' ? 'Authored fictional information → Gemini context' : `${job.search_attempts} search attempts · ${job.page_attempts} page attempts`}</p>
      {job.error && <p className="action-error">{job.error}</p>}
      {['queued', 'running', 'awaiting_review'].includes(job.status) && <button className="button small-button" disabled={!!pending || job.cancel_requested} onClick={() => void mutate(`/api/enrichment/jobs/${encodeURIComponent(job.id)}/cancel`, {}, job.id)}>{job.cancel_requested ? 'Cancellation requested' : 'Cancel job'}</button>}
      {job.status === 'interrupted' && <p>Interrupted after the server stopped. Saved results remain; no searches will repeat automatically.</p>}
      {job.items.map(item => <details className="job-item" key={item.id} open={item.status === 'awaiting_review'}><summary><strong>{item.name}</strong><span>{readable(item.status)}</span></summary>
        <p>Stage: {readable(item.stage)}</p><p>{job.kind === 'demo_profile' ? `Fixture findings ${item.findings_count} · Gemini requests ${item.gemini_attempts ?? 0}` : `Searches ${item.search_attempts}/1 · Pages ${item.page_attempts}/15 · Findings ${item.findings_count}`}</p>{item.error && <p className="action-error">{item.error}</p>}
        {item.candidates.map(candidate => { const auConfirmed = candidate.au_confirmed || item.au_confirmed; return <div className="candidate-review" key={candidate.id}>
          <h4>{candidate.names.join(' · ') || 'Candidate match'}</h4><p>{candidate.organisations.join(' · ')}</p>
          {safeUrl(candidate.source_url) && <a className="candidate-source" href={safeUrl(candidate.source_url)} target="_blank" rel="noreferrer">{candidate.source_name || 'Original source'} ↗</a>}
          <p>{candidate.reason}</p><p>{auConfirmed ? 'Australian work context confirmed' : 'Needs explicit Australian workplace evidence before acceptance.'}</p>
          <p>{candidate.findings.length} supported findings · {readable(candidate.status)}</p>
          {candidate.findings.length > 0 && <details className="candidate-findings"><summary>Preview findings</summary>{candidate.findings.map(finding => <div key={finding.id}><p><strong>{readable(finding.category)}:</strong> {finding.value}</p>{safeUrl(finding.source_url) && <a href={safeUrl(finding.source_url)} target="_blank" rel="noreferrer">{finding.source_name || 'Original source'} ↗</a>}<p>Observed {observedDate(finding.observed_at)}</p></div>)}</details>}
          {['pending', 'awaiting_review'].includes(candidate.status) && <>
            {!auConfirmed && <div className="workplace-review"><label htmlFor={`workplace-${candidate.id}`}>Australian employer or office profile URL</label><input id={`workplace-${candidate.id}`} type="url" placeholder="https://…" value={workplaceSources[candidate.id] || ''} onChange={event => setWorkplaceSources(current => ({...current, [candidate.id]: event.target.value}))}/><p>Checking accepts this match only if the page confirms the identity and Australian work context. It uses this employee’s remaining page allowance.</p></div>}
            <div className="review-actions">{auConfirmed ? <button className="button small-button" disabled={!!pending || job.cancel_requested || ['queued','running','cancelled','interrupted','failed'].includes(job.status)} onClick={() => void review(job, item, candidate, 'accept')}>Accept match</button> : <button className="button small-button" disabled={!!pending || item.page_attempts >= 15 || !safeUrl(workplaceSources[candidate.id] || '') || job.cancel_requested || ['queued','running','cancelled','interrupted','failed'].includes(job.status)} onClick={() => void review(job, item, candidate, 'accept', workplaceSources[candidate.id])}>Check workplace source</button>}<button className="button small-button" disabled={!!pending || job.cancel_requested || ['queued','running','cancelled','interrupted','failed'].includes(job.status)} onClick={() => void review(job, item, candidate, 'reject')}>Reject match</button></div>
          </>}
        </div>})}
      </details>)}
    </li>)}</ol>
  </section>
}
