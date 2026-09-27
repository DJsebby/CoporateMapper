import { expect, test, type Page } from '@playwright/test'

const people = [{id:'person-0', names:['Alex Morgan'], job_titles:['Engineer'], organisations:['Fictional Studio'], image_urls:[], score:null, evidence_count:1}]

async function directory(page: Page, jobs: object[] = []) {
  const state = {jobs, posts: [] as {path: string; body: Record<string, unknown>}[]}
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    if (route.request().method() === 'POST' && url.pathname === '/api/pipeline/jobs') {
      state.posts.push({path: url.pathname, body: route.request().postDataJSON()})
      return route.fulfill({json: state.jobs[0] ?? {}})
    }
    if (url.pathname === '/api/organisations') return route.fulfill({json:{organisations:[{name:'Fictional Studio',count:people.length}]}})
    if (url.pathname === '/api/enrichment/jobs') return route.fulfill({json:{jobs:[],allowance:{limit:10,used:0,remaining:10,provider_exhausted:false}}})
    if (url.pathname === '/api/pipeline/jobs') return route.fulfill({json:{jobs: state.jobs}})
    return route.fulfill({json:{people, total: people.length, offset: 0, limit: 8}})
  })
  return state
}

test('submitting a website queues a discovery job and shows it in the recent list', async ({page}) => {
  const state = await directory(page)
  await page.goto('/')
  const section = page.getByRole('region', {name: 'Add a company website'})
  await expect(section).toBeVisible()
  await section.getByRole('textbox', {name: 'Company website'}).fill('example.com')
  await section.getByRole('button', {name: 'Discover employees'}).click()
  await expect.poll(() => state.posts.length).toBe(1)
  expect(state.posts[0].body.website_url).toBe('example.com')
  expect(Object.keys(state.posts[0].body)).toEqual(['website_url', 'idempotency_key'])
  await expect(section).toContainText('Discovery queued')
  state.jobs = [{id: 'job-1', status: 'queued', website_url: 'https://example.com', created_at: '2026-09-27T00:00:00Z',
    updated_at: '2026-09-27T00:00:00Z', stage: 'Waiting for the worker', report: null, error: null}]
  await expect(section).toContainText('https://example.com', {timeout: 5000})
  await expect(section).toContainText('queued')
})

test('a completed run shows its report summary and a failed run shows its error', async ({page}) => {
  const state = await directory(page, [
    {id: 'job-1', status: 'completed', website_url: 'https://good.example', created_at: '2026-09-27T00:00:00Z',
     updated_at: '2026-09-27T00:00:05Z', stage: 'Discovery finished', error: null,
     report: {base_url: 'https://good.example', discovered_count: 10, discovery_failure_count: 0, valid_unique_count: 10,
               eligible_count: 8, selected_count: 8, fetched_count: 8, pages_with_people: 3, records_stored: 5,
               unique_people: 4, pages: []}},
    {id: 'job-2', status: 'failed', website_url: 'https://bad.example', created_at: '2026-09-27T00:00:00Z',
     updated_at: '2026-09-27T00:00:02Z', stage: 'Discovery failed', error: 'Crawling failed. Earlier page writes may already be committed.',
     report: {base_url: 'https://bad.example', discovered_count: 1, discovery_failure_count: 0, valid_unique_count: 1,
               eligible_count: 1, selected_count: 1, fetched_count: 0, pages_with_people: 0, records_stored: 0,
               unique_people: 0, pages: []}},
  ])
  await page.goto('/')
  const section = page.getByRole('region', {name: 'Add a company website'})
  await expect(section).toContainText('5 records stored · 4 people · 8/8 pages fetched')
  await expect(section).toContainText('Crawling failed. Earlier page writes may already be committed.')
  void state
})

test('a website already running is rejected with a clear conflict message', async ({page}) => {
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    if (route.request().method() === 'POST' && url.pathname === '/api/pipeline/jobs') {
      return route.fulfill({status: 409, json: {detail: 'This website already has an active discovery run.'}})
    }
    if (url.pathname === '/api/organisations') return route.fulfill({json:{organisations:[]}})
    if (url.pathname === '/api/enrichment/jobs') return route.fulfill({json:{jobs:[],allowance:{limit:10,used:0,remaining:10,provider_exhausted:false}}})
    if (url.pathname === '/api/pipeline/jobs') return route.fulfill({json:{jobs:[]}})
    return route.fulfill({json:{people:[], total:0, offset:0, limit:8}})
  })
  await page.goto('/')
  const section = page.getByRole('region', {name: 'Add a company website'})
  await section.getByRole('textbox', {name: 'Company website'}).fill('active.example')
  await section.getByRole('button', {name: 'Discover employees'}).click()
  await expect(section).toContainText('This website already has an active discovery run.')
})
