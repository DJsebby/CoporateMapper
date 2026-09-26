import { useEffect, useRef, useState } from 'react'
import Graph, { PersonCard } from './Graph'
import PersonPanel from './PersonPanel'
import { get, type Organisation, type PeoplePage } from './types'

const PAGE_SIZE = 8
const selection = () => { try { return location.hash.startsWith('#person/') ? decodeURIComponent(location.hash.slice(8)) : null } catch { return null } }
export default function App() {
  const initialOrganisation = useRef(true)
  const [organisations, setOrganisations] = useState<Organisation[]>([])
  const [organisation, setOrganisation] = useState('all')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<PeoplePage | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  const [view, setView] = useState<'map'|'list'>(() => matchMedia('(max-width: 760px)').matches ? 'list' : 'map')
  const [selected, setSelected] = useState(selection)
  useEffect(() => { const handle = () => setSelected(selection()); addEventListener('hashchange',handle); return () => removeEventListener('hashchange', handle) }, [])
  useEffect(() => { const timeout = setTimeout(() => { setQuery(search); setOffset(0) }, 250); return () => clearTimeout(timeout) }, [search])
  useEffect(() => {
    const controller = new AbortController()
    get<{organisations: Organisation[]}>('/api/organisations',controller.signal).then(result => {
      setOrganisations(result.organisations)
      if (initialOrganisation.current && result.organisations.length) {
        const first = result.organisations[0]
        setOrganisation(first.name === null ? 'unassigned' : `org:${first.name}`)
        setOffset(0)
        initialOrganisation.current = false
      }
    }).catch(err => { if(err.name !== 'AbortError') setError(err.message) })
    return () => controller.abort()
  }, [refresh])
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    const params = new URLSearchParams({q: query, offset: String(offset), limit: String(PAGE_SIZE)})
    if (organisation === 'unassigned') params.set('unassigned','true')
    else if (organisation !== 'all') params.set('organisation',organisation.slice(4))
    get<PeoplePage>(`/api/people?${params}`, controller.signal).then(result => { setData(result); setLoading(false) }).catch(err => { if(err.name !== 'AbortError') { setError(err.message); setLoading(false) } })
    return () => controller.abort()
  }, [organisation, query, offset, refresh])
  const organisationName = organisation.startsWith('org:') ? organisation.slice(4) : null
  const title = organisationName || (organisation === 'unassigned' ? 'Unassigned people' : 'All organisations')
  const count = data?.total ?? 0
  function closePanel() { history.replaceState(null,'',location.pathname + location.search); setSelected(null) }
  return <div className="app-layout">
    <aside className="sidebar"><a className="brand" href="#" onClick={() => setSelected(null)}><span className="brand-mark" aria-hidden="true">◈</span><span>Corporate<span className="brand-light">Mapper</span></span></a><div className="workspace-label">WORKSPACE</div><div className="active-nav"><span aria-hidden="true">⌘</span> People map <span className="nav-dot"/></div><div className="sidebar-bottom"><span className="workspace-avatar">CM</span><div><strong>Local workspace</strong><small>Organisation intelligence</small></div></div></aside>
    <main><header className="topbar"><span>Workspace <span className="breadcrumb-slash">/</span> <strong>People map</strong></span><span className="read-only">Read only</span></header>
      <div className="page-content"><div className="page-heading"><div><div className="eyebrow">ORGANISATION DIRECTORY</div><h1>People map</h1><p>Explore your organisation, one connection at a time.</p></div><button className="button refresh" onClick={() => { setOffset(0); setRefresh(x=>x+1) }} disabled={loading}><span aria-hidden="true">↻</span> Refresh</button></div>
        <section className="directory" aria-label="People directory"><div className="directory-toolbar"><div className="organisation-filter"><label htmlFor="organisation">Organisation</label><select id="organisation" value={organisation} onChange={event => { setOrganisation(event.target.value); setOffset(0) }}><option value="all">All organisations</option>{organisations.map(org => <option value={org.name === null ? 'unassigned' : `org:${org.name}`} key={org.name ?? 'unassigned'}>{org.name ?? 'Unassigned'} ({org.count})</option>)}</select></div><div className="search-box"><span aria-hidden="true">⌕</span><input aria-label="Search people" placeholder="Search by name or position…" value={search} onChange={event => setSearch(event.target.value)}/>{search && <button aria-label="Clear search" onClick={() => setSearch('')}>×</button>}</div><div className="view-switch" aria-label="View"><button aria-pressed={view==='map'} onClick={() => setView('map')}>Map</button><button aria-pressed={view==='list'} onClick={() => setView('list')}>List</button></div></div>
          <div className="map-heading"><div><span className="map-heading-icon" aria-hidden="true">▦</span><h2>{title}</h2><span className="count-pill">{loading ? '…' : `${count} ${count === 1 ? 'person' : 'people'}`}</span></div><span className="score-note">Score <strong>-</strong><span>Not calculated yet</span></span></div>
          {error ? <div className="empty-state" role="alert"><span className="empty-icon">!</span><h3>We couldn’t load your people</h3><p>{error}</p><button className="button" onClick={() => { setOffset(0); setRefresh(x=>x+1) }}>Try again</button></div> : loading ? <div className="empty-state" role="status"><div className="spinner"/><h3>Loading your people…</h3><p>Building the picture from your source records.</p></div> : !data?.people.length ? <div className="empty-state"><span className="empty-icon" aria-hidden="true">⌘</span><h3>{query ? 'No matching people' : 'Your people map starts here'}</h3><p>{query ? 'Try another name or position, or clear your search.' : 'People will appear here once organisation information has been extracted.'}</p>{query && <button className="button" onClick={() => setSearch('')}>Clear search</button>}</div> : view === 'map' ? <Graph people={data.people} organisation={organisationName} selected={selected}/> : <div className="people-list">{data.people.map(person => <PersonCard key={person.id} person={person} selected={selected===person.id}/>)}</div>}
          <footer className="directory-footer"><span>{!loading && !error && count > 0 ? `Showing ${offset+1}–${Math.min(offset+PAGE_SIZE,count)} of ${count} people` : 'People and their recorded organisations'}<span className="footer-dot">·</span><span className="membership-note">Connections show organisation membership</span></span><div className="pagination"><button aria-label="Previous page" disabled={loading || offset===0} onClick={() => setOffset(Math.max(0,offset-PAGE_SIZE))}>←</button><span>{count > 0 ? `${Math.floor(offset/PAGE_SIZE)+1} / ${Math.ceil(count/PAGE_SIZE)}` : '0 / 0'}</span><button aria-label="Next page" disabled={loading || offset+PAGE_SIZE>=count} onClick={() => setOffset(offset+PAGE_SIZE)}>→</button></div></footer>
        </section><p className="page-footnote"><span className="legend-dot"/> Person <span className="legend-line"/> Recorded membership <span className="footnote-right">Select “View details” to explore a person’s full profile.</span></p>
      </div>
    </main>{selected && <PersonPanel id={selected} onClose={closePanel}/>}
  </div>
}
