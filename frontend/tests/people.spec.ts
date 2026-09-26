import { expect, test } from '@playwright/test'

const people = Array.from({length: 14}, (_, index) => ({ id: `person-${index}`, names: [`${['Alex Morgan', 'Jordan Lee', 'Sam Taylor', 'Casey Chen', 'Riley Patel', 'Jamie Davis', 'Avery Wilson', 'Quinn Campbell', 'Drew Mitchell', 'Morgan Garcia', 'Cameron Wright', 'Blake Nguyen', 'Reese Thompson', 'Taylor Brooks'][index]}`], job_titles: [index === 0 ? 'Engineering Director' : index % 2 ? 'Software Engineer' : 'Product Designer'], organisations: ['Example Studio'], score: null, evidence_count: 1 }))

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/organisations') return route.fulfill({json:{organisations:[{name:'Example Studio',count:14}]}})
    if (url.pathname.startsWith('/api/people/')) {
      const person = people.find(p=>p.id === url.pathname.split('/').at(-1))
      return person ? route.fulfill({json:{...person, emails:['alex@example.invalid'],telephones:['12345678'],profile_urls:['https://example.invalid/alex','javascript:alert(1)'],same_as:[],evidence:[{names:person.names,confidence:.99,evidence:{source_url:'https://example.invalid/team',fetched_at:'2026-09-26T00:00:00Z',method:'json-ld',record:{name:person.names[0]}}}]}}) : route.fulfill({status:404,json:{detail:'Person not found'}})
    }
    const query = url.searchParams.get('q')?.toLowerCase() || ''
    const matching = people.filter(p=>[...p.names,...p.job_titles].some(v=>v.toLowerCase().includes(query)))
    const offset = Number(url.searchParams.get('offset')||0), limit = Number(url.searchParams.get('limit')||12)
    return route.fulfill({json:{people:matching.slice(offset,offset+limit),total:matching.length,offset,limit}})
  })
})

test('map shows names, positions and placeholder score; details contain complete evidence', async ({page}) => {
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
  await expect(dialog.locator('pre')).toContainText('json-ld')
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
