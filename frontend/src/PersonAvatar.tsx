import { useState } from 'react'
import { personName, safeUrl, type Person } from './types'

export default function PersonAvatar({ person, large = false }: { person: Person; large?: boolean }) {
  const [failed, setFailed] = useState<string[]>([])
  const source = (person.image_urls ?? []).map(safeUrl).find(url => url && !failed.includes(url))
  const name = personName(person)
  const initials = name.split(/\s+/).slice(0, 2).map(part => part[0]).join('')
  return <span className={large ? 'large-avatar' : 'avatar'}>
    {source ? <img key={source} src={source} alt={`Portrait of ${name}`} className="avatar-image" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(previous => [...previous, source])}/> : initials}
  </span>
}
