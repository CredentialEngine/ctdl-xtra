#!/usr/bin/env node
// Builds the viewer, and everything it reads, into one HTML file that opens from disk with no
// server: the script and styles are inlined, every file under ../data/out is packed inside, and
// the stylesheets, fonts and images the stored catalog pages ask the live site for are fetched
// once and packed too, so the pages look the same with no internet.
//
//   node scripts/single-file.mjs [--out <file>] [--no-page-assets] [--refresh]
//
// --no-page-assets  leave the stored pages asking the live site for their styles (no internet needed to build)
// --refresh         fetch the pages' styles, fonts and images again instead of using the kept copies
import { build } from 'vite'
import react from '@vitejs/plugin-react'
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import zlib from 'node:zlib'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

const VIEWER = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const DATA = path.resolve(VIEWER, '../data/out')
const KEPT = path.join(VIEWER, 'node_modules/.cache/xtra-single-file')

const { values: args } = parseArgs({
  options: {
    out: { type: 'string', default: path.join(VIEWER, 'dist-single/xtra-mockup.html') },
    'no-page-assets': { type: 'boolean', default: false },
    refresh: { type: 'boolean', default: false },
  },
})

const TEXT = { '.json': 'application/json', '.html': 'text/html; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.css': 'text/css', '.svg': 'image/svg+xml' }
const BY_EXTENSION = { '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.otf': 'font/otf' }
const sha = (text) => crypto.createHash('sha256').update(text).digest('hex')
const mb = (bytes) => `${(bytes / 1024 / 1024).toFixed(1)} MB`

// ---------------------------------------------------------------------------------------------
// 1. The viewer itself: one script, one stylesheet, both written into the page.

async function buildViewer() {
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'xtra-single-'))
  try {
    await build({
      root: VIEWER,
      configFile: false, // not vite.config.ts: its build copies the data beside the files, and here the data goes inside
      base: './',
      logLevel: 'warn',
      plugins: [react()],
      build: { outDir, emptyOutDir: true, assetsInlineLimit: Number.MAX_SAFE_INTEGER, cssCodeSplit: false, modulePreload: false, rolldownOptions: { output: { codeSplitting: false } } },
    })
    const used = new Set()
    const read = (ref) => {
      const file = path.resolve(outDir, ref)
      used.add(file)
      return fs.readFileSync(file, 'utf8')
    }
    let script = ''
    const html = fs
      .readFileSync(path.join(outDir, 'index.html'), 'utf8')
      .replace(/<link\b[^>]*\brel="modulepreload"[^>]*>\s*/g, '')
      .replace(/<link\b[^>]*\brel="stylesheet"[^>]*>/g, (tag) => `<style>${read(tag.match(/\bhref="([^"]+)"/)[1]).replace(/<\/style/gi, '<\\/style')}</style>`)
      .replace(/<script\b[^>]*\bsrc="([^"]+)"[^>]*><\/script>\s*/g, (_, src) => ((script += read(src)), ''))
    const left = fs.readdirSync(outDir, { recursive: true, withFileTypes: true }).filter((f) => f.isFile()).map((f) => path.join(f.parentPath, f.name)).filter((f) => !used.has(f) && path.basename(f) !== 'index.html')
    if (left.length) throw new Error(`The build wrote files that were not put into the page: ${left.map((f) => path.relative(outDir, f)).join(', ')}`)
    if (!script) throw new Error('The build wrote no script.')
    return { html, script }
  } finally {
    fs.rmSync(outDir, { recursive: true, force: true })
  }
}

// ---------------------------------------------------------------------------------------------
// 2. What the stored pages ask the live site for. Each is fetched once, kept, and given a short
//    name ("xtra-asset:…") that stands where its address stood; the page turns the names into
//    data: addresses when it shows a stored page. A stylesheet is rewritten the same way, so a
//    font it names is packed once however many pages use it.

const assets = {}
const asked = new Map()
const failed = []
const closed = []

async function download(address) {
  const kept = path.join(KEPT, sha(address))
  if (!args.refresh && fs.existsSync(kept) && fs.existsSync(kept + '.json')) return { body: fs.readFileSync(kept), ...JSON.parse(fs.readFileSync(kept + '.json', 'utf8')) }
  // A current browser's name, so that font services answer with woff2.
  const ask = () => fetch(address, { signal: AbortSignal.timeout(30_000), headers: { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36' } })
  const response = await ask().catch(ask) // a dropped connection is tried once more
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const body = Buffer.from(await response.arrayBuffer())
  const type = (response.headers.get('content-type') ?? '').split(';')[0].trim() || BY_EXTENSION[path.extname(new URL(address).pathname).toLowerCase()] || 'application/octet-stream'
  const facts = { type, open: response.headers.get('access-control-allow-origin') === '*' }
  fs.mkdirSync(KEPT, { recursive: true })
  fs.writeFileSync(kept, body)
  fs.writeFileSync(kept + '.json', JSON.stringify(facts))
  return { body, ...facts }
}

function asset(address, kind) {
  const key = `${kind} ${address}`
  if (!asked.has(key)) {
    asked.set(
      key,
      (async () => {
        const { body, type, open } = await download(address)
        // A browser loads a font from another site only where that site allows it. One it would
        // refuse is left as an address, so the page looks here as it does in the served viewer.
        if (kind === 'font' && !open) return closed.push(address), null
        const name = `xtra-asset:${sha(key).slice(0, 16)}`
        assets[name] = kind === 'css' ? { type: 'text/css;charset=utf-8', css: await rewriteCss(body.toString('utf8'), address) } : { type, b64: body.toString('base64') }
        return name
      })().catch((e) => (failed.push(`${address} (${e.message})`), null)),
    )
  }
  return asked.get(key)
}

/** The packed name for an address, or the address made absolute where it cannot or need not be packed. */
async function packed(raw, base, kind, pack = true) {
  const address = raw.trim()
  if (!address || /^(data:|blob:|about:|javascript:|#)/i.test(address)) return raw
  let url
  try {
    url = new URL(address, base)
  } catch {
    return raw
  }
  if (!/^https?:$/.test(url.protocol)) return raw
  const whole = url.href
  url.hash = ''
  return (pack && (await asset(url.href, kind))) || whole
}

async function replaceAsync(text, pattern, each) {
  const found = [...text.matchAll(pattern)]
  const made = await Promise.all(found.map((m) => each(...m)))
  let at = 0
  let out = ''
  found.forEach((m, i) => {
    out += text.slice(at, m.index) + made[i]
    at = m.index + m[0].length
  })
  return out + text.slice(at)
}

const FONT_FACE = /@font-face\s*\{[^}]*\}/g
const CSS_IMPORT = /@import\s+(?:url\(\s*)?(["']?)([^"')\s;]+)\1(?:\s*\))?/g
const CSS_URL = /url\(\s*(["']?)([^"')]*)\1\s*\)/g
const FORMATS = [/\.woff2(\?|$)/i, /\.woff(\?|$)/i]

async function rewriteCss(css, base) {
  const fonts = (text, pack) => replaceAsync(text, CSS_URL, async (_, __, raw) => `url("${await packed(raw, base, 'font', pack(raw))}")`)
  // A font is offered in several formats and a browser takes one: pack the best one, leave the rest as addresses.
  const marks = []
  css = await replaceAsync(css, FONT_FACE, async (block) => {
    const offered = [...block.matchAll(CSS_URL)].map((m) => m[2].split('#')[0])
    const best = FORMATS.find((f) => offered.some((u) => f.test(u)))
    marks.push(await fonts(block, (raw) => !best || best.test(raw.split('#')[0])))
    return `\0${marks.length - 1}\0`
  })
  css = await replaceAsync(css, CSS_IMPORT, async (_, __, raw) => `@import url("${await packed(raw, base, 'css')}")`)
  css = await replaceAsync(css, /url\("xtra-asset:[0-9a-f]{16}"\)|url\(\s*(["']?)([^"')]*)\1\s*\)/g, async (whole, _, raw) => (raw === undefined ? whole : `url("${await packed(raw, base, 'file')}")`))
  return css.replace(/\0(\d+)\0/g, (_, i) => marks[Number(i)])
}

const decode = (value) => value.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
const encode = (value) => value.replace(/&/g, '&amp;').replace(/"/g, '&quot;')

/** A stored page with its stylesheets, fonts and images named for packing. Only attributes and
 *  styles in <head> change, never text under <body>: every position in the evidence counts that text. */
async function rewritePage(html, address) {
  const base = decode(html.match(/<base\b[^>]*\bhref="([^"]*)"/i)?.[1] ?? '') || address
  const attribute = (tag, name, each) => replaceAsync(tag, new RegExp(`(\\s${name}=")([^"]*)(")`, 'gi'), async (_, a, value, b) => a + encode(await each(decode(value))) + b)
  const head = html.search(/<body\b/i)
  html =
    (await replaceAsync(html.slice(0, Math.max(head, 0)), /(<style\b[^>]*>)([\s\S]*?)(<\/style>)/gi, async (_, a, css, b) => a + (await rewriteCss(css, base)) + b)) +
    html.slice(Math.max(head, 0))
  html = await replaceAsync(html, /<link\b[^>]*>/gi, (tag) => (/\srel="[^"]*\bstylesheet\b/i.test(tag) ? attribute(tag, 'href', (v) => packed(v, base, 'css')) : tag))
  html = await replaceAsync(html, /<(?:img|source|input)\b[^>]*>/gi, async (tag) => {
    tag = await attribute(tag, 'src', (v) => packed(v, base, 'file'))
    return attribute(tag, 'srcset', async (v) =>
      (await Promise.all(v.split(/,\s+|,$/).filter((c) => c.trim()).map(async (c) => {
        const [url, ...rest] = c.trim().split(/\s+/)
        return [await packed(url, base, 'file'), ...rest].join(' ')
      }))).join(', '),
    )
  })
  return replaceAsync(html, /(\sstyle=")([^"]*url\([^"]*)(")/gi, async (_, a, css, b) => a + encode(await rewriteCss(decode(css), base)) + b)
}

// ---------------------------------------------------------------------------------------------
// 3. The data, and the few lines in the page that hand it to the viewer in place of a server.

async function packData() {
  if (!fs.existsSync(path.join(DATA, 'courses.json'))) throw new Error(`No extract output at ${DATA}. Run "uv run xtra extract" first.`)
  const files = {}
  for (const f of fs.readdirSync(DATA, { recursive: true, withFileTypes: true })) {
    if (!f.isFile() || f.name === '.DS_Store') continue
    const file = path.join(f.parentPath, f.name)
    const type = TEXT[path.extname(f.name).toLowerCase()]
    files[path.relative(DATA, file).split(path.sep).join('/')] = type ? { type, text: fs.readFileSync(file, 'utf8') } : { type: 'application/octet-stream', b64: fs.readFileSync(file).toString('base64') }
  }
  const pages = {}
  if (!args['no-page-assets']) {
    const documents = Object.values(JSON.parse(files['documents.json'].text))
    for (const [name, f] of Object.entries(files)) {
      if (name.endsWith('.html')) pages[name] = await rewritePage(f.text, documents.find((d) => d.file === name)?.finalAddress ?? 'about:blank')
    }
  }
  return { files, pages, assets }
}

/** Runs in the page, before the viewer. Written here as a function so that it is checked as code. */
function inPage() {
  const root = new URL('data/', document.baseURI).href
  let pack = null
  const ready = (async () => {
    if (!('DecompressionStream' in window)) throw new Error('This browser is too old to open this file. Please use a current Chrome, Edge, Firefox or Safari.')
    const packed = atob(document.getElementById('xtra-pack').textContent)
    const bytes = new Uint8Array(packed.length)
    for (let i = 0; i < packed.length; i++) bytes[i] = packed.charCodeAt(i)
    pack = JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text())
  })()
  ready.catch((e) => {
    document.getElementById('root').innerHTML = '<p style="font: 16px system-ui; margin: 3em; max-width: 40em"></p>'
    document.querySelector('#root p').textContent = `This file could not be opened. ${e.message}`
  })
  window.__xtraSingleFile = ready

  /** The packed file an address means, or null when the address is not one of ours. */
  const local = (address) => {
    try {
      const url = new URL(address, document.baseURI)
      url.hash = url.search = ''
      return url.href.startsWith(root) ? decodeURIComponent(url.href.slice(root.length)) : null
    } catch {
      return null
    }
  }
  const unpack = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))

  const realFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const file = local(typeof input === 'string' ? input : (input?.url ?? String(input)))
    if (file === null) return realFetch(input, init)
    await ready
    const found = pack.files[file]
    if (!found) return new Response('Not found', { status: 404, statusText: 'Not Found' })
    return new Response(found.text ?? unpack(found.b64), { status: 200, headers: { 'Content-Type': found.type } })
  }

  // Packed names become data: addresses, a stylesheet after the names inside it have.
  const made = new Map()
  const fill = (text) => text.replace(/xtra-asset:[0-9a-f]{16}/g, (name) => {
    if (!made.has(name)) {
      const a = pack.assets[name]
      let b64 = a?.b64
      if (a && b64 === undefined) {
        const bytes = new TextEncoder().encode(fill(a.css))
        let chars = ''
        for (let i = 0; i < bytes.length; i += 0x8000) chars += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000))
        b64 = btoa(chars)
      }
      made.set(name, a ? `data:${a.type};base64,${b64}` : 'about:invalid')
    }
    return made.get(name)
  })

  // A frame asked to show a stored page is given the page itself; a file opened from disk may not read its neighbours.
  const shown = new Map()
  const page = (address) => {
    const file = pack && local(String(address))
    if (!file || !/^text\/html/.test(pack.files[file]?.type ?? '')) return undefined
    if (!shown.has(file)) shown.set(file, file in pack.pages ? fill(pack.pages[file]) : pack.files[file].text)
    return shown.get(file)
  }
  const frames = HTMLIFrameElement.prototype
  const setAttribute = Element.prototype.setAttribute
  const src = Object.getOwnPropertyDescriptor(frames, 'src')
  const show = (frame, address, otherwise) => {
    const html = page(address)
    if (html === undefined) return frame.removeAttribute('srcdoc'), otherwise()
    frame.srcdoc = html
  }
  frames.setAttribute = function (name, value) {
    if (String(name).toLowerCase() !== 'src') return setAttribute.call(this, name, value)
    show(this, value, () => setAttribute.call(this, name, value))
  }
  Object.defineProperty(frames, 'src', { ...src, set(value) { show(this, value, () => src.set.call(this, value)) } })
}

// ---------------------------------------------------------------------------------------------

const inline = (code) => code.replace(/<\/script/gi, '<\\/script').replace(/<!--/g, '<\\!--')

const [{ html, script }, data] = await Promise.all([buildViewer(), packData()])
const pack = zlib.gzipSync(JSON.stringify(data), { level: 9 }).toString('base64')
const page = html.replace(/<\/body>/, () =>
  [
    `<script id="xtra-pack" type="application/octet-stream">${pack}</script>`,
    `<script>(${inline(inPage.toString())})()</script>`,
    // A module runs after the page is read, so after the lines above; it waits for the data, then starts.
    `<script type="module">await window.__xtraSingleFile\n${inline(script)}</script>`,
    '</body>',
  ].join('\n'),
)
if (/\b(?:src|href)="\.\//.test(html)) throw new Error('The page still names a file beside it.')

fs.mkdirSync(path.dirname(args.out), { recursive: true })
fs.writeFileSync(args.out, page)

const pages = Object.keys(data.pages).length
console.log(`${path.relative(process.cwd(), args.out)}  ${mb(Buffer.byteLength(page))}`)
console.log(`  ${Object.keys(data.files).length} data files (${mb(Object.values(data.files).reduce((n, f) => n + (f.text ?? f.b64).length, 0))} before packing)`)
console.log(pages ? `  ${pages} stored pages, with ${Object.keys(assets).length} stylesheets, fonts and images packed for them` : '  stored pages left asking the live site for their styles')
if (closed.length) console.log(`  ${closed.length} fonts left out, as their site lets no other site load them (the served viewer cannot show them either):\n${closed.map((f) => `    ${f}`).join('\n')}`)
if (failed.length) console.log(`  ${failed.length} could not be fetched, and the pages will ask the live site for them:\n${failed.map((f) => `    ${f}`).join('\n')}`)
