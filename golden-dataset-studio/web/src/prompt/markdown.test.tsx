import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Markdown, parse } from "./markdown";

const MD = `# Improve rule \`course-description\`

Intro with **bold**, *em* and a [link](https://example.org).

## Context
- Catalog: \`avc\`
- Storage root:

  \`\`\`sh
  export GOLDEN_DATASETS_ROOT='/x'
  \`\`\`

1. **WRONG** — GEOG222
   - page: \`$ROOT/p.html\`
   - note: "<div onclick=alert(1)>not html</div>"
2. second
`;

const TABLE = `| # | Value | Notes |
|---|---|---|
| 1 | \`a \\| b\` | **WRONG** |

|  |  |
|---|---|
| What | x |
`;

describe("markdown", () => {
  it("parses tables, escaped pipes included, and hides an empty header", () => {
    const b = parse(TABLE);
    expect(b.map((x) => x.t)).toEqual(["table", "table"]);
    expect(b[0].t === "table" && b[0].rows[0]).toEqual(["1", "`a | b`", "**WRONG**"]);
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(<Markdown text={TABLE} />);
    const [t1, t2] = container.querySelectorAll("table");
    expect(t1.querySelectorAll("th").length).toBe(3);
    expect(t1.querySelector("td code")?.textContent).toBe("a | b");
    expect(t2.querySelector("thead")).toBeNull();
  });
  it("parses headings, paragraphs, nested lists and fences", () => {
    const b = parse(MD);
    expect(b.map((x) => x.t)).toEqual(["h", "p", "h", "list", "code", "list"]);
    const ol = b[5];
    expect(ol.t === "list" && ol.ordered && ol.items.length).toBe(2);
    expect(ol.t === "list" && ol.items[0].children[0].t).toBe("list");
  });
  it("renders text that looks like HTML as text", () => {
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(<Markdown text={MD} />);
    expect(container.querySelector("div[onclick]")).toBeNull();
    expect(container.textContent).toContain("<div onclick=alert(1)>not html</div>");
    expect(container.querySelector("h1 code")?.textContent).toBe("course-description");
    expect(container.querySelector("a")?.getAttribute("href")).toBe("https://example.org");
    expect(container.querySelectorAll("ol > li").length).toBe(2);
  });
});
