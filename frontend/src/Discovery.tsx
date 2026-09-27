import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { get, observedDate, post, readable, type PipelineJob, type PipelineJobsPage } from './types'

export function useDiscovery() {
  const [data, setData] = useState<PipelineJobsPage | null>(null)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  const reload = useCallback(() => setVersion(value => value + 1), [])
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const result = await get<PipelineJobsPage>('/api/pipeline/jobs', controller.signal)
        if (!Array.isArray(result.jobs)) throw new Error('Invalid discovery response')
        if (!controller.signal.aborted) { setData(result); setError('') }
      } catch (error) {
        if (!controller.signal.aborted) setError('Website discovery activity is unavailable. Check the local server and database connection.')
      } finally { if (!controller.signal.aborted) timer = setTimeout(poll, 2000) }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [version])
  return { data, error, reload }
}

const active = (job: PipelineJob) => ['queued', 'running'].includes(job.status)

export default function CompanyDiscovery({ jobs, onCreated }: { jobs: PipelineJob[]; onCreated: () => void }) {
  const mounted = useRef(false)
  const [website, setWebsite] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const submission = useRef<{website: string; key: string} | null>(null)
  const pending = useRef(false)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const trimmed = website.trim()
    if (!trimmed || pending.current) return
    pending.current = true; setBusy(true); setError(''); setNotice('')
    if (submission.current?.website !== trimmed) submission.current = {website: trimmed, key: crypto.randomUUID()}
    try {
      await post<PipelineJob>('/api/pipeline/jobs', {website_url: trimmed, idempotency_key: submission.current.key})
      if (!mounted.current) return
      submission.current = null; setNotice('Discovery queued. Progress appears below; refresh the people map once it finishes.'); setWebsite('')
      onCreated()
    } catch (error) { if (mounted.current) setError(error instanceof Error ? error.message : 'Unable to start discovery.') }
    finally { pending.current = false; if (mounted.current) setBusy(false) }
  }

  const recent = jobs.slice(0, 5)
  return <section className="company-discovery" aria-labelledby="company-discovery-title">
    <h2 id="company-discovery-title">Add a company website</h2>
    <p className="profile-help">Enter an employer's website to discover, crawl and extract publicly listed people using the same public-source access policy as the CLI pipeline. Runs cannot be cancelled once started.</p>
    <form className="discovery-form" onSubmit={event => void submit(event)}>
      <input aria-label="Company website" type="text" placeholder="example.com" value={website} onChange={event => setWebsite(event.target.value)} disabled={busy}/>
      <button className="button" type="submit" disabled={busy || !website.trim()}>{busy ? 'Starting…' : 'Discover employees'}</button>
    </form>
    {notice && <p role="status" className="action-notice">{notice}</p>}
    {error && <p role="alert" className="action-error">{error}</p>}
    {recent.length > 0 && <ol className="discovery-list">{recent.map(job => <li className="discovery-job" key={job.id}>
      <div className="job-heading"><strong>{job.website_url}</strong><span className={`job-status status-${job.status}`}>{readable(job.status)}</span></div>
      <span className="activity-time">{observedDate(job.created_at)}</span>
      <p>{active(job) ? readable(job.stage) : job.report ? `${job.report.records_stored} records stored · ${job.report.unique_people} people · ${job.report.fetched_count}/${job.report.selected_count} pages fetched` : readable(job.stage)}</p>
      {job.error && <p className="action-error">{job.error}</p>}
    </li>)}</ol>}
  </section>
}
