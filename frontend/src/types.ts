export type Person = { id: string; names: string[]; job_titles: string[]; organisations: string[]; image_urls?: string[]; score: null; evidence_count: number }
export type PersonDetail = Person & { profile_urls: string[]; same_as: string[]; emails: string[]; telephones: string[]; evidence: Record<string, unknown>[]; findings?: Finding[]; demo_profile?: DemoProfile | null }
export type Organisation = { name: string | null; count: number }
export type PeoplePage = { people: Person[]; total: number; offset: number; limit: number }
const LOAD_ERROR = 'Unable to load people. Check the database connection and try again.'
function requestFailure(error: unknown): never {
  if (error instanceof Error && error.name === 'AbortError') throw error
  throw new Error(LOAD_ERROR)
}
export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal }).catch(requestFailure)
  if (!response.ok) throw new Error(response.status === 404 ? 'This person could not be found.' : LOAD_ERROR)
  return response.json().catch(requestFailure)
}
export const personName = (person: Person) => person.names[0] || 'Name unavailable'
export const position = (person: Person) => person.job_titles.join(' · ') || 'Position unavailable'
export function safeUrl(value: string) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined } catch { return undefined }
}

export type Finding = { id: string; category: string; value: string; source_url: string; source_name: string; observed_at: string; evidence: string; method: string }
export type Candidate = { id: string; source_url: string; source_name: string; names: string[]; organisations: string[]; au_confirmed: boolean; findings: Finding[]; reason: string; status: string }
export type EnrichmentItem = { id: string; person_id: string; name: string; status: string; stage: string; search_attempts: number; page_attempts: number; findings_count: number; au_confirmed?: boolean; gemini_attempts?: number; error?: string; candidates: Candidate[] }
export type EnrichmentJob = { id: string; status: string; created_at: string; updated_at: string; cancel_requested: boolean; search_attempts: number; page_attempts: number; items: EnrichmentItem[]; mode?: string; namespace?: string; kind?: string; error?: string }
export type SearchAllowance = { limit: number; used: number; remaining: number; provider_exhausted: boolean }
export type JobsPage = { jobs: EnrichmentJob[]; allowance: SearchAllowance }
export async function post<T>(path: string, body: unknown = {}): Promise<T> {
  let response: Response
  try { response = await fetch(path, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) }) }
  catch { throw new Error('The request could not be completed. Check the local server and try again.') }
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'The request could not be completed. Try again.')
  if (!payload) throw new Error('The server returned an unreadable response. Try again.')
  return payload as T
}
export const readable = (value: string) => value.replaceAll('_', ' ')
export const observedDate = (value: string) => { const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleString() }

export type PipelinePage = { url: string; priority_score: number; priority_reasons: string[]; status: string; final_url: string | null; records_stored: number }
export type PipelineReport = { base_url: string; discovered_count: number; discovery_failure_count: number; valid_unique_count: number; eligible_count: number; selected_count: number; fetched_count: number; pages_with_people: number; records_stored: number; unique_people: number; pages: PipelinePage[] }
export type PipelineJob = { id: string; status: string; website_url: string; created_at: string; updated_at: string; stage: string; report: PipelineReport | null; error: string | null }
export type PipelineJobsPage = { jobs: PipelineJob[] }

export type ContextStatement = { text: string; reason: string; finding_ids: string[] }
export type DemoContext = { status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed' | 'interrupted' | 'cancelled'; model?: string; summary?: ContextStatement[]; gaps?: string[]; privacy_implications?: ContextStatement[]; generated_at?: string; error?: string }
export type DemoProfile = { fixture_id: string; name: string; coverage: 'full' | 'partial' | 'minimal'; fictional: true; populated: boolean; findings: Finding[]; missing_categories: string[]; context: DemoContext; job_id?: string }
