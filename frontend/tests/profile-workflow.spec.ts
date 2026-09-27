import { expect, test, type Page } from '@playwright/test'
import type { DemoProfile, EnrichmentJob, Finding, PersonDetail } from '../src/types'

const email: Finding = {id:'email-fact',category:'business_email',value:'arden@fixture.invalid',source_url:'https://fixture.invalid/team/arden',source_name:'Fictional employer profile',observed_at:'2026-09-27T00:00:00Z',evidence:'Explicit business email',method:'json-ld'}
const sport: Finding = {...email,id:'sport-fact',category:'interest',value:'Cycling',evidence:'interests: Cycling'}
const religion: Finding = {...email,id:'religion-fact',category:'religion',value:'Invented Lantern tradition',source_name:'Authored fictional profile',method:'authored-fixture'}
const address: Finding = {...religion,id:'address-fact',category:'home_address',value:'42 Imaginary Circuit, Exampleton (fictional)'}
const base: PersonDetail = {id:'profile-1',names:['Arden Example — fictional'],job_titles:['Engineer'],organisations:['Fictional Studio'],image_urls:[],score:null,evidence_count:1,emails:[],telephones:[],profile_urls:[],same_as:[],evidence:[],findings:[],demo_profile:null}
const allowance = {limit:5,used:0,remaining:5,provider_exhausted:false}
function fixture(coverage: DemoProfile['coverage'] = 'full'): DemoProfile {
  return {fixture_id:'authored-profile-1',name:'Arden Example',coverage,fictional:true,populated:false,findings:[],missing_categories:['business_email','interest','religion','home_address'],context:{status:'not_started'},risk_score:null}
}
function makeJob(demo = false): EnrichmentJob {
  return {id:'profile-job',kind:demo ? 'demo_profile' : undefined,namespace:demo ? 'demo' : 'real',status:'running',created_at:'2026-09-27T00:00:00Z',updated_at:'2026-09-27T00:00:00Z',cancel_requested:false,search_attempts:demo ? 0 : 1,page_attempts:0,items:[{id:'profile-item',person_id:base.id,name:base.names[0],status:'running',stage:demo ? 'populating' : 'searching',search_attempts:demo ? 0 : 1,page_attempts:0,findings_count:0,candidates:[]}]}
}
async function setup(page: Page, demo: DemoProfile | null = null) {
  const state = {detail:structuredClone({...base,demo_profile:demo}),jobs:[] as EnrichmentJob[],posts:[] as {path:string;body:Record<string,unknown>}[],detailReads:0,detailFails:false}
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    if (route.request().method() === 'POST') {
      state.posts.push({path:url.pathname,body:route.request().postDataJSON()})
      state.jobs = [makeJob(!!demo)]
      return route.fulfill({json:state.jobs[0]})
    }
    if (url.pathname === '/api/enrichment/jobs') return route.fulfill({json:{jobs:state.jobs,allowance}})
    if (url.pathname === '/api/pipeline/jobs') return route.fulfill({json:{jobs:[]}})
    if (url.pathname === '/api/organisations') return route.fulfill({json:{organisations:[{name:'Fictional Studio',count:1}]}})
    if (url.pathname === `/api/people/${base.id}`) {
      state.detailReads++
      return state.detailFails ? route.fulfill({status:503,json:{detail:'Unavailable'}}) : route.fulfill({json:state.detail})
    }
    return route.fulfill({json:{people:[state.detail],total:1,offset:0,limit:8}})
  })
  return state
}
function complete(state: Awaited<ReturnType<typeof setup>>) {
  state.jobs[0] = {...state.jobs[0],status:'completed',updated_at:'2026-09-27T00:00:02Z',items:state.jobs[0].items.map(item => ({...item,status:'completed',stage:'completed',findings_count:2}))}
}

test('real employee button fills the sourced table; polling, reopening and refresh never search automatically', async ({page}) => {
  const state = await setup(page)
  await page.goto('/#person/profile-1')
  const panel = page.getByRole('dialog')
  const table = panel.getByRole('table',{name:'Employee additional information'})
  await expect(table.getByRole('row').filter({hasText:'Business email'})).toContainText('Not recorded')
  await expect(panel.getByText(/Gemini/)).toHaveCount(0)
  await expect(table).not.toContainText('religion')
  expect(state.posts).toHaveLength(0)
  await panel.getByRole('button',{name:'Populate additional information',exact:true}).click()
  await expect(panel.getByRole('button',{name:'Populate additional information',exact:true})).toBeDisabled()
  expect(state.posts).toHaveLength(1)
  expect(state.posts[0]).toMatchObject({path:'/api/enrichment/jobs',body:{person_ids:['profile-1'],search_again:false}})
  state.detail.findings = [email,sport]
  complete(state)
  await expect(table).toContainText(email.value,{timeout:7000})
  await expect(table).toContainText('Cycling')
  await expect(table.getByRole('link',{name:'View source 1',exact:true})).toHaveAttribute('href',email.source_url)
  await expect(panel.getByRole('button',{name:'Populate additional information',exact:true})).toBeEnabled()
  await panel.getByRole('button',{name:'Close person details'}).click()
  await page.getByRole('button',{name:'Refresh',exact:true}).click()
  await page.getByRole('link',{name:`View details for ${base.names[0]}`}).click()
  await expect(page.getByRole('dialog').getByRole('table')).toContainText(email.value)
  expect(state.posts).toHaveLength(1)
  await page.reload()
  await expect(page.getByRole('dialog').getByRole('table')).toContainText('Cycling')
  expect(state.posts).toHaveLength(1)
})

test('fictional profile populates personal fixture facts and automatically shows cited Gemini context', async ({page}) => {
  const state = await setup(page,fixture())
  const externalRequests: string[] = []
  page.on('request', request => { if (new URL(request.url()).hostname.endsWith('.invalid')) externalRequests.push(request.url()) })
  await page.goto('/#person/profile-1')
  const panel = page.getByRole('dialog')
  await expect(panel).toContainText('Fictional demo · full profile')
  await panel.getByRole('button',{name:'Populate demo information',exact:true}).click()
  expect(state.posts[0].path).toBe('/api/demo/profiles/profile-1/populate')
  expect(Object.keys(state.posts[0].body)).toEqual(['idempotency_key'])
  state.detail.demo_profile = {...fixture(),populated:true,findings:[email,sport,religion,address],missing_categories:[],context:{status:'running'},
    risk_score:{score:7.2,band:'high',factors:{age_bracket:'75+',gender:'female',digital_footprint_exposure:'high'},breakdown:{'person.age_bracket=75+':0.3,'person.digital_footprint_exposure=high':1.0}}}
  state.jobs[0] = {...state.jobs[0],updated_at:'2026-09-27T00:00:01Z',items:[{...state.jobs[0].items[0],stage:'gemini_context',findings_count:4,gemini_attempts:1}]}
  await expect(panel.getByRole('table')).toContainText(address.value,{timeout:7000})
  await expect(panel).toContainText('Generating Gemini context')
  await expect(panel.locator('.panel-score')).toContainText('7.2')
  await expect(panel.locator('.panel-score')).toContainText('high')
  await expect(panel.locator('.panel-score')).toHaveClass(/risk-high/)
  await expect(panel).toContainText('age bracket: 75+ (+0.3)')
  state.detail.demo_profile.context = {status:'completed',model:'gemini-fixture-model',summary:[{text:'The fictional profile lists cycling as an interest.',reason:'Included because interest is an explicit, sourced fact already present in this profile\'s table.',finding_ids:[sport.id]}],gaps:['No professional history is recorded.'],privacy_implications:[{text:'This fictional home address demonstrates how location details can expose personal privacy.',reason:'This applies because the table explicitly lists home address: 42 Imaginary Circuit, Exampleton (fictional).',finding_ids:[address.id]}],generated_at:'2026-09-27T00:00:02Z'}
  complete(state)
  await expect(panel.getByRole('heading',{name:'Profile summary',exact:true})).toBeVisible({timeout:7000})
  await expect(panel).toContainText('No professional history is recorded.')
  await expect(panel).toContainText('Included because interest')
  await expect(panel.getByRole('table')).toContainText(religion.value)
  await expect(panel.getByRole('table').getByRole('link')).toHaveCount(0)
  await expect(panel.getByRole('heading',{name:'Sources',exact:true})).toBeVisible()
  await panel.getByRole('link',{name:`home address: ${address.value}`}).click()
  await expect(panel.locator('#additional-finding-address-fact')).toBeFocused()
  await expect(page).toHaveURL(/#person\/profile-1$/)
  expect(state.posts).toHaveLength(1)
  expect(externalRequests).toEqual([])
  await page.screenshot({path:'test-results/fictional-profile-context.png',fullPage:true})
  await panel.getByRole('button',{name:'Close person details'}).click()
  const activity = page.getByRole('region',{name:'Recent activity'})
  await expect(activity.getByRole('heading',{name:'Demo profile context'})).toBeVisible()
  await activity.locator('.job-item summary').click()
  await expect(activity).toContainText('Fixture findings')
  await expect(activity).not.toContainText('Pages 0/15')
})

for (const coverage of ['partial','minimal'] as const) {
  test(`${coverage} demo keeps missing fields explicit and its table usable on mobile`, async ({page}) => {
    const profile = {...fixture(coverage),populated:true,findings:coverage === 'partial' ? [email,sport] : [email],missing_categories:['religion','home_address'],context:{status:'failed' as const,error:'Gemini key is not configured.'}}
    const state = await setup(page,profile)
    await page.setViewportSize({width:390,height:844})
    await page.goto('/#person/profile-1')
    const panel = page.getByRole('dialog')
    await expect(panel).toContainText(`Fictional demo · ${coverage} profile`)
    await expect(panel.getByRole('table').getByRole('row').filter({hasText:'religion'})).toContainText('Not recorded')
    await expect(panel.getByRole('table')).toContainText(email.value)
    await expect(panel).not.toContainText(religion.value)
    await expect(panel).toContainText('Gemini key is not configured.')
    await expect(panel.getByRole('button',{name:'Retry Gemini context'})).toBeEnabled()
    expect(await panel.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect(state.posts).toHaveLength(0)
  })
}

test('failed demo context retains table and retries only context with a stable idempotency key', async ({page}) => {
  const state = await setup(page,{...fixture('partial'),populated:true,findings:[email,sport],context:{status:'failed',error:'Gemini quota is exhausted.'}})
  const retries: Record<string,unknown>[] = []
  await page.route('**/api/demo/profiles/profile-1/context', route => {
    retries.push(route.request().postDataJSON())
    if (retries.length === 1) return route.fulfill({status:503,json:{detail:'The local worker is temporarily unavailable.'}})
    state.jobs = [makeJob(true)]
    state.detail.demo_profile!.context = {status:'queued'}
    return route.fulfill({json:state.jobs[0]})
  })
  await page.goto('/#person/profile-1')
  const panel = page.getByRole('dialog')
  await panel.getByRole('button',{name:'Retry Gemini context'}).click()
  await expect(panel).toContainText('The local worker is temporarily unavailable.')
  await expect(panel.getByRole('table')).toContainText('Cycling')
  await panel.getByRole('button',{name:'Retry Gemini context'}).click()
  await expect(panel).toContainText('Gemini context queued')
  expect(retries).toHaveLength(2)
  expect(retries[0].idempotency_key).toBe(retries[1].idempotency_key)
  expect(Object.keys(retries[1])).toEqual(['idempotency_key'])
  expect(state.posts).toHaveLength(0)
})

test('old demo collection reviews do not block the separate demo profile action', async ({page}) => {
  const state = await setup(page,fixture('minimal'))
  state.jobs = [{...makeJob(false),namespace:'demo',status:'awaiting_review',items:[{...makeJob(false).items[0],status:'awaiting_review',stage:'review'}]}]
  await page.goto('/#person/profile-1')
  const action = page.getByRole('dialog').getByRole('button',{name:'Populate demo information'})
  await expect(action).toBeEnabled()
  await action.click()
  expect(state.posts[0].path).toBe('/api/demo/profiles/profile-1/populate')
})

test('review changes refresh open real details and interrupted collection preserves saved facts', async ({page}) => {
  const state = await setup(page)
  state.detail.findings = [email]
  state.jobs = [{...makeJob(),status:'awaiting_review',items:[{...makeJob().items[0],status:'awaiting_review',stage:'review'}]}]
  await page.goto('/#person/profile-1')
  const panel = page.getByRole('dialog')
  await expect(panel).toContainText('Candidate review is needed')
  await expect(panel.getByRole('button',{name:'Populate additional information'})).toBeDisabled()
  state.detail.findings = [email,sport]
  state.jobs[0] = {...state.jobs[0],status:'interrupted',updated_at:'2026-09-27T00:00:01Z'}
  await expect(panel.getByRole('table')).toContainText('Cycling',{timeout:7000})
  await expect(panel).toContainText('Collection interrupted')
  await expect(panel.getByRole('button',{name:'Populate additional information'})).toBeEnabled()
  state.detailFails = true
  state.jobs[0] = {...state.jobs[0],updated_at:'2026-09-27T00:00:02Z'}
  await expect(panel).toContainText('Unable to refresh details',{timeout:7000})
  await expect(panel.getByRole('table')).toContainText(email.value)
  expect(state.posts).toHaveLength(0)
})
