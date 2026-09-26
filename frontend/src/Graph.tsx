import { useEffect, useRef, useState } from 'react'
import cytoscape, { type Core } from 'cytoscape'
import { personName, position, type Person } from './types'

export function PersonCard({ person, selected }: { person: Person; selected?: boolean }) {
  return <article className={`person-card ${selected ? 'selected' : ''}`}>
    <div className="person-card-heading"><span className="avatar">{personName(person).split(' ').slice(0, 2).map(n => n[0]).join('')}</span><div className="min-w-0"><h3 title={personName(person)}>{personName(person)}</h3><p title={position(person)}>{position(person)}</p></div></div>
    <div className="person-card-footer"><span className="score">Score <strong>-</strong></span><a href={`#person/${encodeURIComponent(person.id)}`} aria-label={`View details for ${personName(person)}`}>View details <span aria-hidden="true">↗</span></a></div>
  </article>
}

export default function Graph({ people, organisation, selected }: { people: Person[]; organisation: string | null; selected: string | null }) {
  const container = useRef<HTMLDivElement>(null)
  const graph = useRef<Core | null>(null)
  const [viewport, setViewport] = useState({ x: 0, y: 0, zoom: 1 })
  const columns = Math.min(4, people.length)
  const width = columns * 276 - 36
  const locations = people.map((person, i) => ({ person, x: (i % columns) * 276, y: 200 + Math.floor(i / columns) * 182 }))
  useEffect(() => {
    if (!container.current || !people.length) return
    const cy = cytoscape({ container: container.current, elements: [
      ...(organisation ? [{ data: { id: 'organisation' }, position: { x: width / 2 - 120, y: 24 } }] : []),
      ...locations.map(({person, x, y}) => ({ data: { id: person.id }, position: { x, y } })),
      ...(organisation ? people.map(person => ({ data: { id: `edge-${person.id}`, source: 'organisation', target: person.id } })) : []),
    ], layout: { name: 'preset' }, minZoom: 0.2, maxZoom: 1.5, wheelSensitivity: 0.2, autoungrabify: true,
      style: [
        { selector: 'node', style: { width: 240, height: 126, 'background-opacity': 0, 'border-width': 0, shape: 'round-rectangle' } },
        { selector: '#organisation', style: { width: 240, height: 74 } },
        { selector: 'edge', style: { width: 1.2, 'line-color': '#cbd7d8', 'curve-style': 'taxi', 'taxi-direction': 'downward', 'taxi-turn': 75, 'target-arrow-shape': 'none' } },
      ] })
    graph.current = cy
    let frame = 0
    const update = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => setViewport({ x: cy.pan().x, y: cy.pan().y, zoom: cy.zoom() })) }
    cy.on('pan zoom resize', update)
    const fit = () => { cy.resize(); cy.fit(undefined, 42); if (cy.zoom() > 1) cy.zoom({ level: 1, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }); update() }
    const observer = new ResizeObserver(fit)
    observer.observe(container.current)
    fit()
    return () => { observer.disconnect(); cancelAnimationFrame(frame); cy.destroy(); graph.current = null }
  }, [people, organisation])
  function zoom(factor: number) { const cy = graph.current; if (cy) cy.zoom({ level: Math.max(.2, Math.min(1.5, cy.zoom() * factor)), renderedPosition: { x: cy.width()/2, y: cy.height()/2 } }) }
  return <div className="graph-shell" aria-label="Organisation people map">
    <div ref={container} className="graph-canvas" aria-hidden="true" />
    <div className="graph-overlay" style={{ transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})` }}>
      {organisation && <div className="organisation-node" style={{ left: width / 2 - 240, top: -13 }}><span className="organisation-icon" aria-hidden="true">▦</span><div><small>ORGANISATION</small><strong title={organisation}>{organisation}</strong></div></div>}
      {locations.map(({person,x,y}) => <div className="graph-person" style={{ left: x-120, top: y-63 }} key={person.id}><PersonCard person={person} selected={selected === person.id}/></div>)}
    </div>
    <div className="graph-hint">Drag to pan <span>·</span> Scroll to zoom</div>
    <div className="graph-controls"><button aria-label="Zoom in" onClick={() => zoom(1.2)}>+</button><button aria-label="Zoom out" onClick={() => zoom(1/1.2)}>−</button><button className="fit-button" onClick={() => graph.current?.fit(undefined, 42)}>Fit map</button></div>
  </div>
}
