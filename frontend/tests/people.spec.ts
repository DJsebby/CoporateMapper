import { expect, test } from '@playwright/test'

const people = Array.from({length: 14}, (_, index) => ({ id: `person-${index}`, names: [`${['Alex Morgan', 'Jordan Lee', 'Sam Taylor', 'Casey Chen', 'Riley Patel', 'Jamie Davis', 'Avery Wilson', 'Quinn Campbell', 'Drew Mitchell', 'Morgan Garcia', 'Cameron Wright', 'Blake Nguyen', 'Reese Thompson', 'Taylor Brooks'][index]}`], job_titles: [index === 0 ? 'Engineering Director' : index % 2 ? 'Software Engineer' : 'Product Designer'], organisations: ['Example Studio'], score: null, evidence_count: 1 }))

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/enrichment/jobs') return route.fulfill({json:{jobs:[0,1].map(index => ({id:`job-${index}`,status:'completed',created_at:'2026-09-27T00:00:00Z',updated_at:'2026-09-27T00:00:00Z',cancel_requested:false,search_attempts:1,page_attempts:2,items:[]})),allowance:{limit:10,used:2,remaining:8,provider_exhausted:false}}})
    if (url.pathname === '/api/organisations') return route.fulfill({json:{organisations:[{name:'Example Studio',count:14}]}})
    if (url.pathname === '/api/pipeline/jobs') return route.fulfill({json:{jobs:[]}})
    if (url.pathname.startsWith('/api/people/')) {
      const person = people.find(p=>p.id === url.pathname.split('/').at(-1))
      return person ? route.fulfill({json:{...person, emails:['alex@example.invalid'],telephones:['12345678'],profile_urls:['https://example.invalid/alex','javascript:alert(1)'],same_as:[],findings:[{id:'fact-1',category:'professional_role',value:'Engineering Director',source_url:'https://example.invalid/team',source_name:'Example Studio team',observed_at:'2026-09-26T00:00:00Z',evidence:'jobTitle: Engineering Director',method:'json-ld'}],evidence:[{names:person.names,confidence:.99,evidence:{source_url:'https://example.invalid/team',fetched_at:'2026-09-26T00:00:00Z',method:'json-ld',record:{name:person.names[0]}}}]}}) : route.fulfill({status:404,json:{detail:'Person not found'}})
    }
    const query = url.searchParams.get('q')?.toLowerCase() || ''
    const matching = people.filter(p=>[...p.names,...p.job_titles].some(v=>v.toLowerCase().includes(query)))
    const offset = Number(url.searchParams.get('offset')||0), limit = Number(url.searchParams.get('limit')||12)
    return route.fulfill({json:{people:matching.slice(offset,offset+limit),total:matching.length,offset,limit}})
  })
})

test('map shows names, positions and placeholder score; details show cited findings', async ({page}) => {
  await page.goto('/')
  await page.getByLabel('Organisation', {exact:true}).selectOption('org:Example Studio')
  await expect(page.locator('.organisation-node')).toContainText('Example Studio')
  await expect(page.getByRole('heading',{name:'Alex Morgan'})).toBeVisible()
  await expect(page.locator('.person-card').first()).toContainText('Engineering Director')
  await expect(page.locator('.person-card .score strong')).toHaveText(Array(8).fill('-'))
  await page.getByRole('link',{name:'View details for Alex Morgan'}).focus()
  await page.keyboard.press('Enter')
  const dialog=page.getByRole('dialog')
  await expect(dialog.getByRole('heading',{name:'Alex Morgan'})).toBeVisible()
  await expect(dialog).toContainText('alex@example.invalid')
  await expect(dialog.locator('.panel-score strong')).toHaveText('-')
  await expect(dialog.locator('a[href^="javascript:"]')).toHaveCount(0)
  await dialog.locator('summary').click()
  await expect(dialog.locator('.finding')).toContainText('Method: json-ld')
  await expect(dialog.locator('pre')).toHaveCount(0)
  await expect(dialog.getByRole('link',{name:'Example Studio team'})).toHaveAttribute('href','https://example.invalid/team')
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('link',{name:'View details for Alex Morgan'})).toBeFocused()
  await page.getByRole('button',{name:'Zoom in',exact:true}).click()
  await page.getByRole('button',{name:'Fit map',exact:true}).click()
})

test('pagination and search reach people beyond the first page', async ({page}) => {
  await page.goto('/')
  await expect(page.getByText('Showing 1–8 of 14 people')).toBeVisible()
  await page.getByRole('button',{name:'Next page'}).click()
  await expect(page.getByRole('heading',{name:'Drew Mitchell'})).toBeVisible()
  await expect(page.getByText('Showing 9–14 of 14 people')).toBeVisible()
  await page.getByLabel('Search people').fill('Engineering Director')
  await expect(page.getByRole('heading',{name:'Alex Morgan'})).toBeVisible()
  await expect(page.getByText('Showing 1–1 of 1 people')).toBeVisible()
  await page.getByLabel('Search people').fill('does-not-exist')
  await expect(page.getByRole('heading',{name:'No matching people'})).toBeVisible()
  await page.getByRole('button',{name:'Clear search',exact:true}).first().click()
  await expect(page.getByText('Showing 1–8 of 14 people')).toBeVisible()
})

test('mobile list and details stay usable without horizontal overflow', async ({page}) => {
  await page.setViewportSize({width:390,height:844})
  await page.goto('/')
  await expect(page.getByRole('button',{name:'List',exact:true})).toHaveAttribute('aria-pressed','true')
  await page.getByRole('link',{name:'View details for Alex Morgan'}).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('dialog').getByRole('heading',{name:'Alex Morgan'})).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button',{name:'Close person details'}).click()
  await expect(page.locator('.people-list .person-card')).toHaveCount(8)
})

test('empty database and unavailable database have distinct states with retry', async ({page}) => {
  await page.route('**/api/people?**', route=>route.fulfill({json:{people:[],total:0,offset:0,limit:12}}))
  await page.goto('/')
  await expect(page.getByRole('heading',{name:'Your people map starts here'})).toBeVisible()
  await page.route('**/api/people?**', route=>route.fulfill({status:503,json:{detail:'Unavailable'}}))
  await page.getByRole('button',{name:'Refresh'}).click()
  await expect(page.getByRole('alert')).toContainText('We couldn’t load your people')
  await page.route('**/api/people?**', route=>route.fulfill({json:{people:[people[0]],total:1,offset:0,limit:12}}))
  await page.getByRole('button',{name:'Try again'}).click()
  await expect(page.getByRole('heading',{name:'Alex Morgan'})).toBeVisible()
})

test('direct person links work and missing people show a recoverable error', async ({page}) => {
  await page.goto('/#person/person-0')
  await expect(page.getByRole('dialog').getByRole('heading',{name:'Alex Morgan'})).toBeVisible()
  await page.getByRole('button',{name:'Close person details'}).click()
  await page.goto('/#person/missing')
  await expect(page.getByRole('dialog')).toContainText('This person could not be found.')
})

test('capture populated map for visual review', async ({page}) => {
  await page.goto('/')
  await page.getByLabel('Organisation', {exact:true}).selectOption('org:Example Studio')
  await expect(page.locator('.organisation-node')).toBeVisible()
  await expect(page.getByRole('heading',{name:'Alex Morgan'})).toBeVisible()
  await page.screenshot({path:'test-results/people-map.png',fullPage:true})
})


test('refresh returns to the first page when data has shrunk', async ({page}) => {
  await page.goto('/')
  await page.getByRole('button',{name:'Next page'}).click()
  await expect(page.getByText('Showing 9–14 of 14 people')).toBeVisible()
  await page.route('**/api/people?**', route=>route.fulfill({json:{people:[people[0]],total:1,offset:0,limit:8}}))
  await page.getByRole('button',{name:'Refresh'}).click()
  await expect(page.getByText('Showing 1–1 of 1 people')).toBeVisible()
})


test('saved activity stays visible during loading, empty results and database errors', async ({page}) => {
  let releaseResponses!: () => void
  const responsesReady = new Promise<void>(resolve => { releaseResponses = resolve })
  const apiPaths: string[] = []
  page.on('request', request => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/')) apiPaths.push(path)
  })
  await page.route('**/api/people?**', async route => {
    await responsesReady
    await route.fulfill({json:{people:[],total:0,offset:0,limit:8}})
  })
  await page.goto('/')
  await expect(page.getByRole('heading',{name:'Loading your people…'})).toBeVisible()
  const activity = page.getByRole('region',{name:'Recent activity'})
  await expect(activity).toBeVisible()
  await expect(activity).toContainText('Live')
  await expect(activity).toContainText('Saved enrichment jobs. Updated every two seconds.')
  await expect(activity.getByRole('listitem')).toHaveCount(2)
  releaseResponses()
  await expect(page.getByRole('heading',{name:'Your people map starts here'})).toBeVisible()
  await expect(activity).toBeVisible()
  await page.route('**/api/people?**', route => route.fulfill({status:503,json:{detail:'Unavailable'}}))
  await page.getByRole('button',{name:'Refresh'}).click()
  await expect(page.getByRole('alert')).toContainText('We couldn’t load your people')
  await expect(activity).toBeVisible()
  expect(apiPaths.every(path => ['/api/organisations','/api/people','/api/enrichment/jobs','/api/pipeline/jobs'].includes(path))).toBe(true)
})

const portraitUrl = 'https://images.example.invalid/alex.png'
const portraitFixture = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB1kAAAAASUVORK5CYII=', 'base64')

test('stored portraits render on the map, in the list and in person details', async ({page}) => {
  const person = {...people[0], image_urls:[portraitUrl]}
  await page.route(portraitUrl, route => route.fulfill({contentType:'image/png',body:portraitFixture}))
  await page.route('**/api/people?**', route => route.fulfill({json:{people:[person],total:1,offset:0,limit:8}}))
  await page.route('**/api/people/person-0', route => route.fulfill({json:{...person,emails:[],telephones:[],profile_urls:[],same_as:[],evidence:[]}}))
  await page.goto('/')
  const portrait = page.getByRole('img',{name:'Portrait of Alex Morgan'})
  await expect(portrait).toBeVisible()
  await expect(portrait).toHaveAttribute('src',portraitUrl)
  await expect.poll(() => portrait.evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  await expect(portrait).toHaveAttribute('referrerpolicy','no-referrer')
  await page.getByRole('button',{name:'List',exact:true}).click()
  await expect(page.locator('.people-list').getByRole('img',{name:'Portrait of Alex Morgan'})).toBeVisible()
  await page.getByRole('link',{name:'View details for Alex Morgan'}).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('img',{name:'Portrait of Alex Morgan'})).toHaveAttribute('src',portraitUrl)
  await expect(dialog.getByRole('link',{name:portraitUrl,exact:false})).toHaveAttribute('href',portraitUrl)
})

test('missing, broken and unsafe portraits fall back to initials without breaking profiles', async ({page}) => {
  const brokenUrl = 'https://images.example.invalid/missing.png'
  const fixtures = [
    {...people[0],image_urls:[brokenUrl]},
    {...people[1],image_urls:['javascript:alert(1)','data:image/png;base64,invalid','file:///private.png','https://user:secret@images.example.invalid/alex.png']},
    {...people[2],image_urls:[]},
    {...people[3],image_urls:[brokenUrl,portraitUrl]},
    people[4],
  ]
  await page.route(brokenUrl, route => route.fulfill({status:404,body:'Missing image'}))
  await page.route(portraitUrl, route => route.fulfill({contentType:'image/png',body:portraitFixture}))
  await page.route('**/api/people?**', route => route.fulfill({json:{people:fixtures,total:fixtures.length,offset:0,limit:8}}))
  await page.route('**/api/people/person-0', route => route.fulfill({json:{...fixtures[0],emails:[],telephones:[],profile_urls:[],same_as:[],evidence:[]}}))
  await page.goto('/')
  await page.getByRole('button',{name:'List',exact:true}).click()
  for (const [index, initials] of [[0,'AM'],[1,'JL'],[2,'ST'],[4,'RP']] as const) {
    const card = page.locator('.person-card').nth(index)
    await expect(card.locator('.avatar')).toHaveText(initials)
    await expect(card.getByRole('img')).toHaveCount(0)
    await expect(card.getByRole('link')).toBeVisible()
  }
  await expect(page.getByRole('img',{name:'Portrait of Casey Chen'})).toHaveAttribute('src',portraitUrl)
  await expect(page.locator('img[src^="javascript:"], img[src^="data:"], img[src^="file:"]')).toHaveCount(0)
  await page.getByRole('link',{name:'View details for Alex Morgan'}).click()
  await expect(page.getByRole('dialog').locator('.large-avatar')).toHaveText('AM')
  await expect(page.getByRole('dialog').getByRole('heading',{name:'Alex Morgan'})).toBeVisible()
})

for (const failure of ['network', 'invalid JSON']) {
  test(`${failure} failures show a friendly message and recover on retry`, async ({page}) => {
    await page.route('**/api/organisations', route => route.fulfill({json:{organisations:[]}}))
    await page.route('**/api/people?**', route => failure === 'network'
      ? route.abort('failed')
      : route.fulfill({contentType:'application/json',body:'not valid JSON'}))
    await page.goto('/')
    await expect(page.getByRole('alert')).toContainText('Unable to load people. Check the database connection and try again.')
    await expect(page.getByRole('alert')).not.toContainText('Failed to fetch')
    await page.route('**/api/people?**', route => route.fulfill({json:{people:[people[0]],total:1,offset:0,limit:8}}))
    await page.getByRole('button',{name:'Try again'}).click()
    await expect(page.getByRole('heading',{name:'Alex Morgan'})).toBeVisible()
  })
}


test('activity panel sits to the left of the map on desktop and below it on smaller screens', async ({page}) => {
  await page.goto('/')
  await expect(page.locator('.organisation-node')).toBeVisible()
  const directory = page.getByRole('region', {name:'People directory'})
  const activity = page.getByRole('region', {name:'Recent activity'})
  const mapBounds = (await directory.boundingBox())!
  const activityBounds = (await activity.boundingBox())!
  expect(activityBounds.x + activityBounds.width).toBeLessThanOrEqual(mapBounds.x)
  expect(activityBounds.y + activityBounds.height).toBeGreaterThanOrEqual(mapBounds.y + mapBounds.height - 2)
  expect(Math.abs(activityBounds.y - mapBounds.y)).toBeLessThan(2)
  const entries = activity.getByRole('listitem')
  const first = (await entries.nth(0).boundingBox())!
  const second = (await entries.nth(1).boundingBox())!
  expect(second.y).toBeGreaterThanOrEqual(first.y + first.height)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  for (const width of [1024, 390]) {
    await page.setViewportSize({width,height:900})
    const map = (await directory.boundingBox())!
    const panel = (await activity.boundingBox())!
    expect(panel.y).toBeGreaterThan(map.y + map.height)
    expect(Math.abs(panel.x - map.x)).toBeLessThan(2)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
})
