// HTML → simplified markdown, mirroring ctdl-xtra/server/src/extraction/browser.ts:simplifyHtml + toMarkdown
import fs from "node:fs";
import path from "node:path";
import * as cheerio from "cheerio";
import TurndownService from "turndown";

export const WGU_DIR = path.resolve(import.meta.dirname, "../wgu");

export function simplifyHtml(html) {
  const $ = cheerio.load(html);
  $("head").empty();
  $("script, style, noscript, link, footer, nav, header, iframe:empty").remove();
  $("*").each((_, el) => {
    for (const a of Object.keys(el.attribs || {})) {
      if (a !== "href") delete el.attribs[a];
    }
  });
  $("div").each((_, el) => {
    const $el = $(el);
    const first = $el.children().first();
    if ($el.children().length === 1 && first.is("div")) $el.replaceWith(first);
  });
  return $.html();
}

const td = new TurndownService({ linkReferenceStyle: "full" });

export function simplifiedMarkdown(html) {
  return td.turndown(simplifyHtml(html));
}

// Load HTML from URL or file, simplify to markdown, persist the model input, return {url, content}.
export async function prepareSource(slug, src) {
  let html, url;
  if (/^https?:\/\//.test(src)) {
    const res = await fetch(src, {
      headers: { "User-Agent": "Mozilla/5.0 (Macintosh) xtra-eval-harness" },
    });
    if (!res.ok) throw new Error(`fetch ${src}: ${res.status}`);
    html = await res.text();
    url = src;
  } else {
    html = fs.readFileSync(src, "utf8");
    const urlFile = src.replace(/\.html?$/i, "") + ".url";
    url =
      urlFile !== src && fs.existsSync(urlFile)
        ? fs.readFileSync(urlFile, "utf8").trim()
        : `file://${path.basename(src)}`;
  }
  const content = simplifiedMarkdown(html);
  const dir = path.join(WGU_DIR, slug);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "model-input.md"), content);
  return { url, content, dir };
}
