// Regenerates the screenshots used in ../03-specification.md from the running viewer.
//   cd viewer && npm run dev -- --port 5199      (in another terminal)
//   node qrspi/screens/capture.mjs [name ...]     (no names: all of them)
// Needs Google Chrome. Uses a fresh browser profile, so nothing you accepted or edited is touched.
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from '../../viewer/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js'

const here = dirname(fileURLToPath(import.meta.url))
const out = join(here, '../../data/out/courses')
const BASE = process.env.VIEWER ?? 'http://localhost:5199/'
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

// Reviews to show progress in the sidebar: some ACCT courses accepted in full, a few in part.
function seededReviews() {
  const reviews = {}
  const files = readdirSync(out).filter((f) => f.startsWith('ACCT-')).sort()
  files.slice(0, 19).forEach((f, i) => {
    const course = JSON.parse(readFileSync(join(out, f), 'utf8'))
    const fields = Object.keys(course.provenance).filter((p) => p.lastIndexOf('/') === 0)
    const keep = i < 14 ? fields.length : Math.ceil(fields.length * [0.7, 0.5, 0.4, 0.2, 0.1][i - 14])
    reviews[course.id] = Object.fromEntries(fields.slice(0, keep).map((p) => [p, { accepted: true }]))
  })
  return reviews
}

const why = async (page) => {
  if (!(await page.$('.card.active .why'))) await page.click('.card.active .ico[aria-label="Why this value"]')
  await wait(400)
}
const centre = (page, selector) => page.evaluate((s) => document.querySelector(s)?.scrollIntoView({ block: 'center' }), selector)
// Click part of the card for one CTDL term, whatever its place in the list.
const inCard = (page, term, part) => page.evaluate((term, part) => [...document.querySelectorAll('.card')].find((c) => c.querySelector('.prop')?.textContent === term)?.querySelector(part)?.click(), term, part)
const clickText = (page, selector, text) => page.evaluate((s, t) => [...document.querySelectorAll(s)].find((e) => e.innerText.trim() === t)?.click(), selector, text)

const SHOTS = {
  '01-arrival': { hash: '#/course/ACCT-20203' },
  '02-value-selected': { hash: '#/course/ACCT-20203', run: async (page) => { await inCard(page, 'ceterms:creditValue', '.fvalue') } },
  '03-rule-at-work': {
    hash: '#/course/ACCT-20203?stop=/ceterms:offerFrequencyType',
    run: async (page) => { await why(page); await centre(page, '.card.active .rulecard'); await wait(200); await page.hover('.card.active .rulecard .rx') },
  },
  '04-language-model-kept': { hash: '#/course/ACCT-54103?stop=/ceterms:requires', run: async (page) => { await centre(page, '.card.active .lmbox') } },
  '05-language-model-refused': { hash: '#/course/ACCT-20103?stop=/ceterms:requires', run: async (page) => { await centre(page, '.card.active .failed') } },
  '06-editing-a-requirement': {
    hash: '#/course/ACCT-20203?stop=/ceterms:requires',
    run: async (page) => { await page.click('.card.active .ico[aria-label="Edit the value"]'); await wait(300); await centre(page, '.card.active .subform') },
  },
  '07-editing-a-pick-list': {
    hash: '#/course/ACCT-20203?stop=/ceterms:offerFrequencyType',
    run: async (page) => { await page.click('.card.active .ico[aria-label="Edit the value"]'); await wait(300); await centre(page, '.card.active .editor') },
  },
  '08-raw': {
    hash: '#/course/ACCT-20203?view=json',
    run: async (page) => { await clickText(page, '.jl .chip', '3 · Semester Hour'); await wait(300); await page.evaluate(() => [...document.querySelectorAll('.jl')].find((e) => e.innerText.includes('schema:value'))?.click()) },
  },
  '09-definition-of-a-field': { hash: '#/course/ACCT-20203', run: async (page) => { await inCard(page, 'ceterms:creditValue', '.fname') } },
  '10-definition-of-a-class': {
    hash: '#/course/ACCT-20203',
    run: async (page) => { await inCard(page, 'ceterms:requires', '.fname'); await wait(300); await clickText(page, '.terminfo .ti-chip', 'Condition Profile') },
  },
  '11-html-view': { hash: '#/course/ACCT-20203?stop=/ceterms:inLanguage' },
  '12-sidebar-progress': { hash: '#/course/ACCT-37203', seed: true },
  '14-tour-1-resources': { hash: '#/course/ACCT-20203', tour: true },
  '15-tour-2-accept-or-reject': { hash: '#/course/ACCT-20203', tour: true, run: async (page) => { await page.keyboard.press('Enter') } },
  '26-tour-3-rejecting': { hash: '#/course/ACCT-20203', tour: true, run: async (page) => { for (let i = 0; i < 2; i++) { await page.keyboard.press('Enter'); await wait(400) } } },
  '16-tour-4-evidence': { hash: '#/course/ACCT-20203', tour: true, run: async (page) => { for (let i = 0; i < 3; i++) { await page.keyboard.press('Enter'); await wait(400) } } },
  '20-tour-5-reasoning': { hash: '#/course/ACCT-20203', tour: true, run: async (page) => { for (let i = 0; i < 4; i++) { await page.keyboard.press('Enter'); await wait(400) } } },
  '21-tour-6-field-names': { hash: '#/course/ACCT-20203', tour: true, run: async (page) => { for (let i = 0; i < 5; i++) { await page.keyboard.press('Enter'); await wait(400) } } },
  '25-tour-7-editing': { hash: '#/course/ACCT-20203', tour: true, run: async (page) => { for (let i = 0; i < 6; i++) { await page.keyboard.press('Enter'); await wait(400) } } },
  '23-tour-8-registry': { hash: '#/course/ACCT-20203', tour: true, run: async (page) => { for (let i = 0; i < 7; i++) { await page.keyboard.press('Enter'); await wait(400) } } },
  '24-tour-9-blank-fields': { hash: '#/course/ACCT-20203', tour: true, run: async (page) => { for (let i = 0; i < 8; i++) { await page.keyboard.press('Enter'); await wait(400) } } },
  '22-blank-fields': { hash: '#/course/ACCT-20203', run: async (page) => { await page.evaluate(() => document.querySelector('.group-label.fold').scrollIntoView({ block: 'center' })) } },
  '17-rejecting-a-field': {
    hash: '#/course/ACCT-20203?stop=/ceterms:offerFrequencyType',
    run: async (page) => { await page.keyboard.press('r'); await wait(300); await page.keyboard.type('The page says Fall, Spring and Summer. That is three terms a year, not four.') },
  },
  '18-rejected-with-a-reason': {
    hash: '#/course/ACCT-20203?stop=/ceterms:offerFrequencyType',
    run: async (page) => {
      await page.keyboard.press('r'); await wait(300); await page.keyboard.type('The page says Fall, Spring and Summer. That is three terms a year, not four.'); await page.keyboard.press('Enter')
      await wait(300); await centre(page, '.card.rejected')
    },
  },
  '27-commenting-on-a-field': {
    hash: '#/course/ACCT-20203?stop=/ceterms:codedNotation',
    run: async (page) => { await page.keyboard.press('c'); await wait(300); await page.keyboard.type('Matches the page. Worth asking the registrar whether the old four-digit code should be kept as well.') },
  },
  '19-registry-check-stub': { hash: '#/course/ACCT-20203', run: async (page) => { await page.click('.card.ctid .stub-tag') } },
}

const wanted = process.argv.slice(2)
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' })
try {
  for (const [name, shot] of Object.entries(SHOTS)) {
    if (wanted.length && !wanted.includes(name)) continue
    const context = await browser.createBrowserContext()
    const page = await context.newPage()
    await page.setViewport({ width: 1440, height: shot.height ?? 900, deviceScaleFactor: 2 })
    page.on('pageerror', (e) => console.log('  page error:', e.message))
    if (shot.seed) await page.evaluateOnNewDocument((r) => localStorage.setItem('xtra-reviews', r), JSON.stringify(seededReviews()))
    await page.goto(BASE + shot.hash, { waitUntil: 'networkidle2' })
    await wait(1500)
    // The tour opens with every page load and would cover the screen; only the shots of the tour itself leave it on.
    if (!shot.tour) await page.keyboard.press('Escape')
    if (shot.run) await shot.run(page)
    await wait(1500)
    await page.screenshot({ path: join(here, name + '.png') })
    console.log('wrote', name + '.png')
    await context.close()
  }
} finally {
  await browser.close()
}
