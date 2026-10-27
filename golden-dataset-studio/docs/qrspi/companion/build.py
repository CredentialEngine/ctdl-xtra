"""Build the companion page from template.html and 03-spec.md.

Run from anywhere:  uv run --with markdown-it-py python review-ui-v2/qrspi/companion/build.py <out_dir>
Writes <out_dir>/golden-dataset-studio.html and copies the screenshots it references into <out_dir>/img/ as JPEGs.

The template pulls spec sections in with slots, so the page always carries the spec's text:
  {{MD:4.2}}         section 4.2 with its heading
  {{MD:4|nohead}}    section 4 without its own heading (its subsections keep theirs)
  {{MD:7|intro}}     only the text before section 7's first subsection
  {{MD:4.5|nocode}}  section 4.5 without its fenced code blocks
Every top-level spec section must be used by some slot; the build fails otherwise.
"""

import html
import re
import subprocess
import sys
from pathlib import Path

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
QRSPI = HERE.parent
out = Path(sys.argv[1])
(out / "img").mkdir(parents=True, exist_ok=True)

lines = (QRSPI / "03-spec.md").read_text().splitlines()
md = MarkdownIt("commonmark", {"html": True}).enable("table")

# Index headings outside code fences: number -> (level, line index).
heads, fence = [], False
for i, line in enumerate(lines):
    if line.startswith("```"):
        fence = not fence
    m = None if fence else re.match(r"^(#{2,3}) (\d+(?:\.\d+)?)[. ]", line)
    if m:
        heads.append((m.group(2), len(m.group(1)), i))


def section(num, mode):
    for k, (n, level, start) in enumerate(heads):
        if n == num:
            end = next((s for _, lv, s in heads[k + 1:] if lv <= level), len(lines))
            if mode == "intro":
                end = next((s for _, lv, s in heads[k + 1:] if s < end), end)
            body = lines[start + (0 if mode in ("", "nocode") else 1):end]
            text = "\n".join(body)
            if mode == "nocode":
                text = re.sub(r"\n```[^\n]*\n.*?\n```", "", text, flags=re.S)
            return text
    raise SystemExit(f"no spec section {num}")


def shot(name):
    jpg = out / "img" / f"{name}.jpg"
    src = QRSPI / "screens" / f"{name}.png"
    if not jpg.exists() or jpg.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "78", "--resampleWidth", "2400",
                        str(src), "--out", str(jpg)], check=True, capture_output=True)
    return f"img/{name}.jpg"


def render(text):
    tokens = md.parse(text)
    for i, t in enumerate(tokens):
        if t.type == "heading_open":
            title = tokens[i + 1].content
            t.attrSet("id", "s-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"))
            t.tag = {"h2": "h3", "h3": "h3", "h4": "h4"}[t.tag]
    body = md.renderer.render(tokens, md.options, {})
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: f'<pre class="mermaid">{m.group(1)}</pre>', body, flags=re.S)
    body = body.replace("<table>", '<div class="tbl"><table>').replace("</table>", "</table></div>")
    body = re.sub(r'(<img [^>]*?)src="screens/([\w-]+)\.png"([^>]*>)',
                  lambda m: f'<a href="{shot(m.group(2))}" target="_blank">{m.group(1)}src="{shot(m.group(2))}"{m.group(3)}</a>', body)

    def link(m):
        href, label = m.group(1), m.group(2)
        if href.startswith(("http://", "https://", "#")):
            return m.group(0)
        return f'<span class="file-ref" title="review-ui-v2/qrspi/{html.escape(href)}">{label}</span>'

    return re.sub(r'<a href="([^"]+)">(.*?)</a>', link, body, flags=re.S)


page = (HERE / "template.html").read_text()
used = set()


def slot(m):
    num, mode = m.group(1), m.group(2) or ""
    used.add(num.split(".")[0])
    return f'<div class="spec-doc">{render(section(num, mode))}</div>'


page = re.sub(r"\{\{MD:([\d.]+)(?:\|(\w+))?\}\}", slot, page)
page = re.sub(r'\{\{IMG:([\w-]+)\}\}', lambda m: shot(m.group(1)), page)
missing = sorted({n for n, lv, _ in heads if lv == 2} - used, key=float)
if missing:
    raise SystemExit(f"spec sections not on the page: {missing}")
(out / "golden-dataset-studio.html").write_text(page)
print(f"wrote {out / 'golden-dataset-studio.html'} ({len(page):,} bytes); images: {len(list((out / 'img').iterdir()))}")
