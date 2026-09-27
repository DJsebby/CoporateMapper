import { useState } from 'react'
import { personName, safeUrl, type Person } from './types'

export default function PersonAvatar({ person, large = false }: { person: Person; large?: boolean }) {
  const [failed, setFailed] = useState<string[]>([])
  const source = (person.image_urls ?? []).map(safeUrl).find(url => url && !failed.includes(url))
  const name = personName(person)
  const initials = name.split(/\s+/).slice(0, 2).map(part => part[0]).join('')
  const riskClass = person.risk_band ? `avatar-risk risk-${person.risk_band}` : ''
  const title = person.risk_band ? `Fictional demo risk score: ${person.risk_score?.toFixed(1)} (${person.risk_band.replaceAll('_',' ')})` : undefined
  return <span className={`${large ? 'large-avatar' : 'avatar'} ${riskClass}`} title={title}>
    {source ? <img key={source} src={source} alt={`Portrait of ${name}`} className="avatar-image" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(previous => [...previous, source])}/> : initials}
  </span>
}
