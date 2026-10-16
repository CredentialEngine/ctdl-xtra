import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'

// The viewer reads the extract step's output and writes nothing. In development the files are
// served straight from ../data/out; a build copies them next to the static files.
const OUT = path.resolve(__dirname, '../data/out')
const TYPES: Record<string, string> = { '.json': 'application/json', '.html': 'text/html; charset=utf-8' }

function extractOutput(): Plugin {
  return {
    name: 'xtra-extract-output',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const file = path.join(OUT, decodeURIComponent((req.url ?? '').split('?')[0]))
        if (!file.startsWith(OUT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return next()
        res.setHeader('Content-Type', TYPES[path.extname(file)] ?? 'application/octet-stream')
        res.setHeader('Cache-Control', 'no-store')
        fs.createReadStream(file).pipe(res)
      })
    },
    closeBundle() {
      if (fs.existsSync(OUT)) fs.cpSync(OUT, path.resolve(__dirname, 'dist/data'), { recursive: true })
    },
  }
}

export default defineConfig({ base: './', plugins: [react(), extractOutput()] })
