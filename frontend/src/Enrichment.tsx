import { useCallback, useEffect, useRef, useState } from 'react'
import { get, personName, post, type EnrichmentJob, type JobsPage, type Person } from './types'

export function useEnrichment() {
  const [data, setData] = useState<JobsPage | null>(null)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  const reload = useCallback(() => setVersion(value => value + 1), [])
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const result = await get<JobsPage>('/api/enrichment/jobs', controller.signal)
        if (!Array.isArray(result.jobs) || !result.allowance) throw new Error('Invalid activity response')
        if (!controller.signal.aborted) { setData(result); setError('') }
      } catch (error) {
        if (!controller.signal.aborted) setError('Activity is unavailable. Check the local server and database connection.')
      } finally { if (!controller.signal.aborted) timer = setTimeout(poll, 2000) }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [version])
  return { data, error, reload }
}

export default function EnrichmentControls({ people, allowance, onCreated }: { people: Person[]; allowance: JobsPage['allowance'] | undefined; onCreated: (job: EnrichmentJob) => void }) {
  const [selected, setSelected] = useState<Person[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const attempt = useRef<{signature: string; key: string} | null>(null)
  const pending = useRef(false)
  const toggle = (person: Person) => { setNotice(''); setSelected(current => current.some(value => value.id === person.id) ? current.filter(value => value.id !== person.id) : current.length < 20 ? [...current, person] : current) }
  async function start(searchAgain: boolean) {
    if (!selected.length || pending.current) return
    pending.current = true; setBusy(true); setError(''); setNotice('')
    const personIds = selected.map(person => person.id).sort()
    const signature = JSON.stringify([personIds, searchAgain])
    if (attempt.current?.signature !== signature) attempt.current = {signature, key: crypto.randomUUID()}
    try {
      const job = await post<EnrichmentJob>('/api/enrichment/jobs', {person_ids: personIds, idempotency_key: attempt.current.key, search_again: searchAgain})
      attempt.current = null
      setNotice('Enrichment queued. Follow progress in Recent activity.')
      onCreated(job)
    } catch (error) { setError(error instanceof Error ? error.message : 'Unable to start enrichment.') }
    finally { pending.current = false; setBusy(false) }
  }
  const canSearchAgain = allowance && !allowance.provider_exhausted && allowance.remaining >= selected.length
  return <section className="enrichment-controls" aria-label="Employee enrichment">
    <details><summary>Select employees for enrichment <span>{selected.length} selected · maximum 20</span></summary>
      <p className="enrichment-help">Select people on this page. Selections remain when you change pages. Only confirmed Australian work context is eligible for accepted findings.</p>
      <div className="enrichment-selection">{people.map(person => <label key={person.id}><input type="checkbox" checked={selected.some(value => value.id === person.id)} disabled={busy || (selected.length >= 20 && !selected.some(value => value.id === person.id))} onChange={() => toggle(person)}/>{personName(person)}</label>)}</div>
      {selected.length > 0 && <p className="selected-names">Selected: {selected.map(personName).join(', ')} <button className="text-button" onClick={() => setSelected([])} disabled={busy}>Clear selection</button></p>}
    </details>
    <div className="enrichment-actions"><button className="button" disabled={!selected.length || busy} onClick={() => void start(false)}>{busy ? 'Submitting…' : 'Enrich selected'}</button><button className="button" disabled={!selected.length || busy || !canSearchAgain} onClick={() => void start(true)}>Search again</button><span>{allowance ? `${allowance.remaining} searches remaining` : 'Checking search allowance…'}</span></div>
    <p className="enrichment-help">Enrich selected reuses eligible searches for seven days. Search again bypasses the cache and allows {selected.length || 1} additional {selected.length === 1 || !selected.length ? 'search' : 'searches'}: one per selected employee. Refresh never starts a search.</p>
    {allowance?.provider_exhausted && <p className="enrichment-help">The search provider quota is exhausted. Existing results remain available.</p>}
    {error && <p role="alert" className="action-error">{error}</p>}{notice && <p role="status" className="action-notice">{notice}</p>}
  </section>
}
