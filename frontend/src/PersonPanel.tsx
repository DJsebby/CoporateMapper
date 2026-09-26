import { useEffect, useRef, useState } from 'react'
import { get, personName, position, safeUrl, type PersonDetail } from './types'

function Values({ label, values, links = false }: { label: string; values: string[]; links?: boolean }) {
  return <div className="detail-field"><dt>{label}</dt><dd>{values.length ? values.map(value => <div key={value}>{links && safeUrl(value) ? <a href={safeUrl(value)} target="_blank" rel="noreferrer">{value} ↗</a> : value}</div>) : <span className="muted">Not recorded</span>}</dd></div>
}
export default function PersonPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [person, setPerson] = useState<PersonDetail | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => { const previous = document.activeElement as HTMLElement; const modal = dialog.current; modal?.showModal(); return () => { modal?.close(); previous?.focus() } }, [])
  useEffect(() => {
    const controller = new AbortController(); setPerson(null); setError('')
    get<PersonDetail>(`/api/people/${encodeURIComponent(id)}`, controller.signal).then(setPerson).catch(err => { if (err.name !== 'AbortError') setError(err.message) })
    return () => controller.abort()
  }, [id, attempt])
  return <dialog className="person-panel" ref={dialog} onCancel={onClose} aria-labelledby="person-title" onClick={event => { if (event.target === dialog.current && event.clientX < dialog.current!.getBoundingClientRect().left) onClose() }}>
    <div className="panel-top"><span>PERSON DETAILS</span><button className="icon-button" aria-label="Close person details" onClick={onClose}>×</button></div>
    {!person && !error && <div className="panel-body" role="status"><h2 id="person-title">Loading person details…</h2></div>}
    {error && <div className="panel-body" role="alert"><h2 id="person-title">Details unavailable</h2><p>{error}</p><button className="button" onClick={() => setAttempt(x=>x+1)}>Try again</button></div>}
    {person && <div className="panel-body"><span className="large-avatar">{personName(person).split(' ').slice(0,2).map(n=>n[0]).join('')}</span><h2 id="person-title">{personName(person)}</h2><p className="panel-position">{position(person)}</p><div className="panel-score"><span>Score</span><strong>-</strong><small>Not calculated yet</small></div>
      <h3>Profile</h3><dl><Values label="Names" values={person.names}/><Values label="Positions" values={person.job_titles}/><Values label="Organisations" values={person.organisations}/><Values label="Email" values={person.emails}/><Values label="Telephone" values={person.telephones}/><Values label="Profiles" values={person.profile_urls} links/><Values label="Other links" values={person.same_as} links/></dl>
      <h3 className="evidence-title">Source evidence <span>{person.evidence_count}</span></h3><p className="muted text-sm">Original records are retained so you can inspect each source and any differing claims.</p>
      {person.evidence.map((record, i) => { const e = record.evidence as Record<string,unknown> | undefined; const source = typeof e?.source_url === 'string' ? e.source_url : ''; return <details className="evidence" key={i}><summary><strong>Source {i+1}</strong><span>{typeof e?.fetched_at === 'string' ? new Date(e.fetched_at).toLocaleDateString() : 'Date unavailable'}</span></summary>{source && <p>{safeUrl(source) ? <a href={safeUrl(source)} target="_blank" rel="noreferrer">{source} ↗</a> : source}</p>}<pre>{JSON.stringify(record, null, 2)}</pre></details> })}
    </div>}
  </dialog>
}
