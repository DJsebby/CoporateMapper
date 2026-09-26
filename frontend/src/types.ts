export type Person = { id: string; names: string[]; job_titles: string[]; organisations: string[]; score: null; evidence_count: number }
export type PersonDetail = Person & { profile_urls: string[]; same_as: string[]; emails: string[]; telephones: string[]; evidence: Record<string, unknown>[] }
export type Organisation = { name: string | null; count: number }
export type PeoplePage = { people: Person[]; total: number; offset: number; limit: number }
export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal })
  if (!response.ok) throw new Error(response.status === 404 ? 'This person could not be found.' : 'Unable to load people. Check the database connection and try again.')
  return response.json()
}
export const personName = (person: Person) => person.names[0] || 'Name unavailable'
export const position = (person: Person) => person.job_titles.join(' · ') || 'Position unavailable'
export function safeUrl(value: string) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined } catch { return undefined }
}
