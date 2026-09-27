import { expect, test, type Page } from '@playwright/test'

const people = Array.from({length: 9}, (_, index) => ({id:`person-${index}`, names:[`Fictional Person ${index}`], job_titles:['Engineer'], organisations:['Fictional Studio'], image_urls:[], score:null, evidence_count:1}))
const finding = {id:'finding-1',category:'skills',value:'Software testing',source_url:'https://fictional.example/team/person-0',source_name:'Fictional Studio team',observed_at:'2026-09-27T00:00:00Z',evidence:'knowsAbout: Software testing',method:'json-ld'}
const item = {id:'item-1',person_id:'person-0',name:'Fictional Person 0',status:'running',stage:'fetching',search_attempts:1,page_attempts:3,findings_count:0,candidates:[] as object[]}
const job = {id:'job-1',status:'running',created_at:'2026-09-27T00:00:00Z',updated_at:'2026-09-27T00:00:00Z',cancel_requested:false,search_attempts:1,page_attempts:3,items:[item]}
const allowance = {limit:10,used:1,remaining:9,provider_exhausted:false}
async function directory(page: Page) {
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/organisations') return route.fulfill({json:{organisations:[{name:'Fictional Studio',count:people.length}]}})
    if (url.pathname.startsWith('/api/people/')) return route.fulfill({json:{...people[0],emails:[],telephones:[],profile_urls:[],same_as:[],evidence:[{raw:'PRIVATE_LEGACY_CONTENT'}],findings:[]}})
    if (url.pathname === '/api/enrichment/jobs') return route.fulfill({json:{jobs:[],allowance}})
    if (url.pathname === '/api/pipeline/jobs') return route.fulfill({json:{jobs:[]}})
    const offset = Number(url.searchParams.get('offset') || 0)
    return route.fulfill({json:{people:people.slice(offset, offset+8),total:people.length,offset,limit:8}})
  })
}
test.beforeEach(async ({page}) => directory(page))

test('selection survives pagination, jobs show progress and cancel, refresh never creates a search', async ({page}) => {
  const submissions: object[] = []
  let current: typeof job | null = null
  let cancelled = false
  await page.route('**/api/enrichment/jobs', route => {
    if (route.request().method() === 'POST') { submissions.push(route.request().postDataJSON()); current = structuredClone(job); return route.fulfill({json:current}) }
    return route.fulfill({json:{jobs:current ? [current] : [],allowance}})
  })
  await page.route('**/api/enrichment/jobs/job-1/cancel', route => {
    cancelled = true; current = {...job,status:'cancelled',cancel_requested:true}
    return route.fulfill({json:current})
  })
  await page.goto('/')
  await page.getByText('Select employees for enrichment', {exact:false}).click()
  await page.getByRole('checkbox',{name:'Fictional Person 0',exact:true}).check()
  await page.getByRole('button',{name:'Next page'}).click()
  await page.getByRole('checkbox',{name:'Fictional Person 8',exact:true}).check()
  await expect(page.getByText('2 selected · maximum 20')).toBeVisible()
  await page.getByRole('button',{name:'Enrich selected',exact:true}).click()
  const activity = page.getByRole('region',{name:'Recent activity'})
  await expect(activity).toContainText('running')
  expect(submissions).toHaveLength(1)
  expect(submissions[0]).toMatchObject({person_ids:['person-0','person-8'],search_again:false})
  await activity.locator('.job-item summary').click()
  await expect(activity).toContainText('Searches 1/1 · Pages 3/15')
  await expect(activity).toContainText('Stage: fetching')
  await page.getByRole('button',{name:'Refresh',exact:true}).click()
  await page.getByRole('link',{name:'View details for Fictional Person 0'}).click()
  await page.getByRole('button',{name:'Close person details'}).click()
  expect(submissions).toHaveLength(1)
  await activity.getByRole('button',{name:'Cancel job'}).click()
  await expect(activity).toContainText('cancelled')
  expect(cancelled).toBe(true)
})

test('Search again displays the extra allowance and explicitly bypasses cached searches', async ({page}) => {
  let submitted: Record<string, unknown> | undefined
  await page.route('**/api/enrichment/jobs', route => {
    if (route.request().method() === 'POST') {submitted = route.request().postDataJSON();return route.fulfill({json:job})}
    return route.fulfill({json:{jobs:[],allowance}})
  })
  await page.goto('/')
  await page.getByText('Select employees for enrichment', {exact:false}).click()
  await page.getByRole('checkbox',{name:'Fictional Person 0',exact:true}).check()
  await page.getByRole('checkbox',{name:'Fictional Person 1',exact:true}).check()
  await expect(page.getByText(/allows 2 additional searches/)).toBeVisible()
  await expect(page.getByText('9 searches remaining')).toBeVisible()
  await page.getByRole('button',{name:'Search again',exact:true}).click()
  await expect.poll(() => submitted?.search_again).toBe(true)
  expect(submitted?.person_ids).toEqual(['person-0','person-1'])
})

test('candidate review requires Australian workplace evidence and shows original sources', async ({page}) => {
  const candidates = [true,false,false].map((confirmed,index) => ({id:`candidate-${index}`,source_url:`https://fictional.example/person-${index}`,source_name:`Candidate source ${index}`,names:['Fictional Person 0'],organisations:['Fictional Studio'],au_confirmed:confirmed,findings:[finding],reason:'External profile needs identity confirmation',status:'pending'}))
  const reviewJob = {...job,status:'awaiting_review',items:[{...item,status:'awaiting_review',stage:'review',candidates}]}
  const decisions: object[] = []
  await page.route('**/api/enrichment/jobs', route => route.fulfill({json:{jobs:[reviewJob],allowance}}))
  await page.route('**/api/enrichment/jobs/job-1/items/item-1/review', route => {
    const body = route.request().postDataJSON(); decisions.push(body)
    const candidate = candidates.find(value => value.id === body.candidate_id)!
    candidate.status = body.decision === 'accept' ? 'accepted' : 'rejected'
    if (body.australian_work_source) candidate.au_confirmed = true
    return route.fulfill({json:reviewJob})
  })
  await page.goto('/')
  const reviews = page.locator('.candidate-review')
  await expect(reviews.nth(0).getByRole('link',{name:'Candidate source 0'})).toHaveAttribute('href','https://fictional.example/person-0')
  await expect(reviews.nth(1).getByRole('button',{name:'Check workplace source'})).toBeDisabled()
  await expect(reviews.nth(1)).toContainText('Needs explicit Australian workplace evidence')
  await reviews.nth(0).getByRole('button',{name:'Accept match'}).click()
  await expect(reviews.nth(0)).toContainText('accepted')
  await reviews.nth(1).getByRole('textbox',{name:'Australian employer or office profile URL'}).fill('https://employer.example/team/person-0')
  await reviews.nth(1).getByRole('button',{name:'Check workplace source'}).click()
  await expect(reviews.nth(1)).toContainText('accepted')
  await reviews.nth(2).getByRole('button',{name:'Reject match'}).click()
  await expect(reviews.nth(2)).toContainText('rejected')
  expect(decisions).toEqual([{candidate_id:'candidate-0',decision:'accept'},{candidate_id:'candidate-1',decision:'accept',australian_work_source:'https://employer.example/team/person-0'},{candidate_id:'candidate-2',decision:'reject'}])
})

test('individual findings cite their sources, preserve conflicts, and can be dismissed without exposing raw records', async ({page}) => {
  let findings = [finding,{...finding,id:'finding-2',value:'Technical writing',evidence:'knowsAbout: Technical writing',source_name:'Fictional conference',source_url:'https://conference.example/speakers/person-0'}]
  await page.route('**/api/people/person-0', route => route.fulfill({json:{...people[0],emails:[],telephones:[],profile_urls:[],same_as:[],evidence:[{raw:'PRIVATE_LEGACY_CONTENT',religion:'RAW_SENSITIVE_FIELD'}],findings}}))
  await page.route('**/api/people/person-0/findings/finding-1/dismiss', route => { findings = findings.filter(value => value.id !== 'finding-1');return route.fulfill({json:{dismissed:true}}) })
  await page.goto('/#person/person-0')
  const dialog = page.getByRole('dialog')
  await expect(dialog.locator('.finding')).toHaveCount(2)
  await expect(dialog.getByRole('link',{name:'Fictional Studio team'})).toHaveAttribute('href',finding.source_url)
  await expect(dialog.getByRole('link',{name:'Fictional conference'})).toHaveAttribute('href','https://conference.example/speakers/person-0')
  await expect(dialog).not.toContainText('PRIVATE_LEGACY_CONTENT')
  await expect(dialog).not.toContainText('RAW_SENSITIVE_FIELD')
  await dialog.locator('.finding').first().getByText('Supporting evidence').click()
  await expect(dialog).toContainText('knowsAbout: Software testing')
  await dialog.locator('.finding').first().getByRole('button',{name:'Dismiss finding'}).click()
  await expect(dialog.locator('.finding')).toHaveCount(1)
  await expect(dialog).toContainText('Technical writing')
  await expect(dialog).not.toContainText('Software testing')
})

test('job creation failures retain the idempotency key for retry and activity failures are recoverable', async ({page}) => {
  const requests: Record<string,unknown>[] = []
  let unavailable = true
  await page.route('**/api/enrichment/jobs', route => {
    if (route.request().method() === 'POST') {
      requests.push(route.request().postDataJSON())
      return requests.length === 1 ? route.fulfill({status:503,json:{detail:'Enrichment is temporarily unavailable.'}}) : route.fulfill({json:job})
    }
    return unavailable ? route.fulfill({status:503,json:{detail:'Unavailable'}}) : route.fulfill({json:{jobs:[],allowance}})
  })
  await page.goto('/')
  const activity = page.getByRole('region',{name:'Recent activity'})
  await expect(activity).toContainText('Activity is unavailable')
  const activityBounds = (await activity.boundingBox())!
  const messageBounds = (await activity.getByRole('status').boundingBox())!
  const retryBounds = (await activity.getByRole('button',{name:'Retry activity'}).boundingBox())!
  expect(Math.abs((retryBounds.x + retryBounds.width / 2) - (activityBounds.x + activityBounds.width / 2))).toBeLessThan(2)
  expect(Math.abs((retryBounds.y + retryBounds.height / 2) - (activityBounds.y + activityBounds.height / 2))).toBeLessThan(2)
  expect(messageBounds.y + messageBounds.height).toBeLessThan(retryBounds.y)
  expect(retryBounds.y - (messageBounds.y + messageBounds.height)).toBeLessThan(24)
  unavailable = false
  await activity.getByRole('button',{name:'Retry activity'}).click()
  await expect(activity).toContainText('No enrichment jobs yet')
  await page.getByText('Select employees for enrichment', {exact:false}).click()
  await page.getByRole('checkbox',{name:'Fictional Person 0',exact:true}).check()
  await page.getByRole('button',{name:'Enrich selected',exact:true}).click()
  await expect(page.getByRole('alert')).toHaveText('Enrichment is temporarily unavailable.')
  await page.getByRole('button',{name:'Enrich selected',exact:true}).click()
  await expect(page.getByText('Enrichment queued. Follow progress in Recent activity.')).toBeVisible()
  expect(requests).toHaveLength(2)
  expect(requests[0].idempotency_key).toBe(requests[1].idempotency_key)
})

test('polling picks up interrupted jobs without repeating searches and zero allowance disables Search again', async ({page}) => {
  let stopped = false
  let writes = 0
  await page.route('**/api/enrichment/jobs', route => {
    if (route.request().method() !== 'GET') writes++
    return route.fulfill({json:{jobs:[{...job,status:stopped ? 'interrupted' : 'running'}],allowance:{...allowance,remaining:0,used:10}}})
  })
  await page.goto('/')
  const activity = page.getByRole('region',{name:'Recent activity'})
  await expect(activity.locator('.job-status')).toHaveText('running')
  stopped = true
  await expect(activity.locator('.job-status')).toHaveText('interrupted', {timeout:5000})
  await expect(activity).toContainText('Saved results remain; no searches will repeat automatically.')
  await page.getByText('Select employees for enrichment', {exact:false}).click()
  await page.getByRole('checkbox',{name:'Fictional Person 0',exact:true}).check()
  await expect(page.getByRole('button',{name:'Search again',exact:true})).toBeDisabled()
  await expect(page.getByRole('button',{name:'Enrich selected',exact:true})).toBeEnabled()
  expect(writes).toBe(0)
})


test('workplace source errors retain pending review and long source links fit on mobile', async ({page}) => {
  const longSource = `https://fictional.example/people/${'profile-'.repeat(35)}`
  const candidate = {id:'candidate-0',source_url:longSource,source_name:longSource,names:['Fictional Person 0'],organisations:['Fictional Studio'],au_confirmed:false,findings:[{...finding,source_name:longSource,source_url:longSource}],reason:'Australian workplace evidence required',status:'pending'}
  const reviewJob = {...job,namespace:'demo',status:'awaiting_review',items:[{...item,status:'awaiting_review',candidates:[candidate]}]}
  await page.route('**/api/enrichment/jobs', route => route.fulfill({json:{jobs:[reviewJob],allowance}}))
  await page.route('**/api/enrichment/jobs/job-1/items/item-1/review', route => route.fulfill({status:409,json:{detail:'This source has already been checked. Supply a new employee-specific workplace source.'}}))
  await page.setViewportSize({width:390,height:844})
  await page.goto('/')
  const activity = page.getByRole('region',{name:'Recent activity'})
  await expect(activity.getByRole('heading',{name:'Demo enrichment'})).toBeVisible()
  await activity.getByText('Preview findings').click()
  await activity.getByRole('textbox',{name:'Australian employer or office profile URL'}).fill('https://employer.example/previously-checked')
  await activity.getByRole('button',{name:'Check workplace source'}).click()
  await expect(activity.getByRole('alert')).toContainText('This source has already been checked')
  await expect(activity.locator('.candidate-review')).toContainText('pending')
  await expect(activity.getByRole('button',{name:'Check workplace source'})).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})


test('established employee workplace evidence permits review of an external profile without repeated location data', async ({page}) => {
  const candidate = {id:'candidate-0',source_url:'https://conference.example/speakers/fictional-person-0',source_name:'Fictional conference',names:['Fictional Person 0'],organisations:['Fictional Studio'],au_confirmed:false,findings:[finding],reason:'External identity requires confirmation.',status:'pending'}
  const reviewJob = {...job,status:'awaiting_review',items:[{...item,status:'awaiting_review',au_confirmed:true,candidates:[candidate]}]}
  let decision: Record<string,unknown> | undefined
  await page.route('**/api/enrichment/jobs', route => route.fulfill({json:{jobs:[reviewJob],allowance}}))
  await page.route('**/api/enrichment/jobs/job-1/items/item-1/review', route => {
    decision = route.request().postDataJSON(); candidate.status = 'accepted'
    return route.fulfill({json:reviewJob})
  })
  await page.goto('/')
  const review = page.locator('.candidate-review')
  await expect(review).toContainText('Australian work context confirmed')
  await expect(review.getByRole('textbox',{name:'Australian employer or office profile URL'})).toHaveCount(0)
  await expect(review.getByRole('button',{name:'Accept match'})).toBeEnabled()
  await review.getByRole('button',{name:'Accept match'}).click()
  await expect(review).toContainText('accepted')
  expect(decision).toEqual({candidate_id:'candidate-0',decision:'accept'})
})
