// Generate xTRA-style simplified markdown for every .html in a directory.
import fs from "node:fs";
import path from "node:path";
import { prepareSource } from "./simplify.mjs";

const inDir = process.argv[2] || path.resolve(import.meta.dirname, "../wgu");

for (const slug of fs.readdirSync(inDir, { withFileTypes: true })) {
  if (!slug.isDirectory()) continue;
  const html = path.join(inDir, slug.name, "page.html");
  if (!fs.existsSync(html)) continue;
  const { content } = await prepareSource(slug.name, html);
  console.log(`${slug.name}: ${content.length} md`);
}
