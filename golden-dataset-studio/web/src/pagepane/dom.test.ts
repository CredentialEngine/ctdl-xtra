import { describe, expect, it } from "vitest";
import {
  blockOf, captureElement, captureRange, cssPathOf, findText, rangeFromOffsets, resolveOffsets, resolvePath, textOffset,
} from "./dom";
import { paint, resolveAll } from "./paint";
import { colorize, sourceUrl } from "./SourceView";

function page(body: string): Document {
  const doc = document.implementation.createHTMLDocument("t");
  doc.body.innerHTML = body;
  return doc;
}

const BODY = `
  <div id="a"><p>one</p><p>two <b>bold</b> three</p></div>
  <div><section><h2>Title</h2><div class="introtext">This course provides a general
     survey of <span>basic</span> methods.<!-- note --></div></section></div>`;

describe("cssPathOf", () => {
  it("writes the engine's document-root format", () => {
    const doc = page(BODY);
    const b = doc.querySelector("b")!;
    expect(cssPathOf(b)).toBe("html > body:nth-of-type(1) > div:nth-of-type(1) > p:nth-of-type(2) > b:nth-of-type(1)");
    const intro = doc.querySelector(".introtext")!;
    expect(cssPathOf(intro)).toBe(
      "html > body:nth-of-type(1) > div:nth-of-type(2) > section:nth-of-type(1) > div:nth-of-type(1)");
    expect(cssPathOf(doc.documentElement)).toBe("html");
  });

  it("round-trips through querySelector for every element", () => {
    const doc = page(BODY);
    for (const el of Array.from(doc.querySelectorAll("*"))) expect(resolvePath(doc, cssPathOf(el))).toBe(el);
  });

  it("resolvePath returns null for bad selectors and misses", () => {
    const doc = page(BODY);
    expect(resolvePath(doc, "html > body:nth-of-type(1) > div:nth-of-type(9)")).toBeNull();
    expect(resolvePath(doc, ">>>")).toBeNull();
  });

  it("an overlay appended to <html> changes no body path", () => {
    const doc = page(BODY);
    const before = Array.from(doc.body.querySelectorAll("*")).map(cssPathOf);
    const ov = doc.createElement("div");
    doc.documentElement.appendChild(ov);
    expect(Array.from(doc.body.querySelectorAll("*")).map(cssPathOf)).toEqual(before);
  });
});

describe("textContent offsets", () => {
  it("maps offsets to a range and back", () => {
    const doc = page(BODY);
    const p = doc.querySelectorAll("p")[1];
    const tc = p.textContent!; // "two bold three"
    const s = tc.indexOf("bold th"), e = s + "bold th".length;
    const r = rangeFromOffsets(p, s, e)!;
    expect(r.toString()).toBe("bold th");
    expect(textOffset(p, r.startContainer, r.startOffset)).toBe(s);
    expect(textOffset(p, r.endContainer, r.endOffset)).toBe(e);
  });

  it("ignores comments, like textContent", () => {
    const doc = page(BODY);
    const intro = doc.querySelector(".introtext")!;
    const tc = intro.textContent!;
    expect(tc).not.toContain("note");
    const r = rangeFromOffsets(intro, 0, tc.length)!;
    expect(r.toString()).toBe(tc);
  });

  it("returns null when offsets don't fit", () => {
    const doc = page(BODY);
    const p = doc.querySelector("p")!;
    expect(rangeFromOffsets(p, 2, 99)).toBeNull();
    expect(rangeFromOffsets(p, 3, 1)).toBeNull();
  });
});

describe("findText / resolveOffsets (text-search fallback)", () => {
  it("finds exact and whitespace-insensitive matches", () => {
    expect(findText("abc def", "def")).toEqual([4, 7]);
    const hay = "a general\n     survey of basic";
    const [s, e] = findText(hay, "general survey")!;
    expect(hay.slice(s, e)).toBe("general\n     survey");
    expect(findText("abc", "zzz")).toBeNull();
    expect(findText("abc", "  ")).toBeNull();
  });

  it("keeps offsets that hold the text, else searches", () => {
    const doc = page(BODY);
    const intro = doc.querySelector(".introtext")!;
    const tc = intro.textContent!;
    const s = tc.indexOf("basic");
    expect(resolveOffsets(intro, s, s + 5, "basic")).toEqual([s, s + 5]);
    expect(resolveOffsets(intro, s, s + 5, null)).toEqual([s, s + 5]);
    // offsets from another text model (e.g. off by the <br> newlines): fall back to the text
    expect(resolveOffsets(intro, s + 2, s + 7, "basic")).toEqual([s, s + 5]);
    expect(resolveOffsets(intro, 500, 600, "basic")).toEqual([s, s + 5]);
    expect(resolveOffsets(intro, 500, 600, null)).toBeNull();
  });
});

describe("selection capture", () => {
  it("reports the nearest element, textContent offsets, and context", () => {
    const doc = page(BODY);
    const intro = doc.querySelector(".introtext")!;
    const span = intro.querySelector("span")!;
    const first = intro.firstChild as Text;
    const r = doc.createRange();
    r.setStart(first, first.data.indexOf("general"));
    r.setEnd(span.firstChild!, 3);
    const cap = captureRange(r)!;
    expect(cap.css_path).toBe(cssPathOf(intro));
    expect(cap.text).toBe(intro.textContent!.slice(cap.char_start, cap.char_end));
    expect(cap.text.startsWith("general")).toBe(true);
    expect(cap.text.endsWith("bas")).toBe(true);
    expect(cap.prefix).toBe("This course provides a ");
    expect(cap.suffix.startsWith("ic methods.")).toBe(true);
    // the capture resolves back to the same text
    const back = rangeFromOffsets(resolvePath(doc, cap.css_path)!, cap.char_start, cap.char_end)!;
    expect(back.toString()).toBe(cap.text);
  });

  it("a selection inside one text node reports its parent element", () => {
    const doc = page(BODY);
    const b = doc.querySelector("b")!;
    const r = doc.createRange();
    r.setStart(b.firstChild!, 1);
    r.setEnd(b.firstChild!, 3);
    const cap = captureRange(r)!;
    expect(cap).toMatchObject({ text: "ol", char_start: 1, char_end: 3, prefix: "b", suffix: "d" });
    expect(cap.css_path.endsWith("b:nth-of-type(1)")).toBe(true);
  });

  it("ignores collapsed and whitespace-only selections", () => {
    const doc = page(BODY);
    const r = doc.createRange();
    r.setStart(doc.querySelector("p")!.firstChild!, 1);
    expect(captureRange(r)).toBeNull();
  });

  it("captureElement and blockOf pick the block around an inline", () => {
    const doc = page(BODY);
    const span = doc.querySelector(".introtext span")!;
    const block = blockOf(span.firstChild!, null)!;
    expect(block.className).toBe("introtext");
    const cap = captureElement(block);
    expect(cap.css_path).toBe(cssPathOf(block));
    expect(cap.char_end).toBe(block.textContent!.length);
  });
});

describe("paint", () => {
  it("resolves highlights and paints into an overlay outside <body>", () => {
    const doc = document; // needs a window (defaultView)
    doc.body.innerHTML = BODY;
    // jsdom has no layout: give every element and range a box
    const rect = { left: 40, top: 30, width: 100, height: 18, right: 140, bottom: 48, x: 40, y: 30, toJSON: () => ({}) };
    Element.prototype.getBoundingClientRect = () => rect as DOMRect;
    (Range.prototype as unknown as { getClientRects: () => DOMRect[] }).getClientRects = () => [rect as DOMRect];
    const intro = doc.querySelector(".introtext")!;
    const before = Array.from(doc.body.querySelectorAll("*")).map(cssPathOf);
    const bodyHtml = doc.body.innerHTML;
    const resolved = resolveAll(doc, [
      { id: "v", kind: "value", cssPath: cssPathOf(intro), text: "basic", badge: 1 },
      { id: "b", kind: "block", cssPath: cssPathOf(doc.querySelector("section")!), badge: 2 },
      { id: "m", kind: "mark", cssPath: cssPathOf(intro), text: "not on the page" },
      { id: "x", kind: "value", cssPath: "html > body:nth-of-type(1) > nav:nth-of-type(1)" },
    ]);
    expect(resolved.map((r) => r.h.id)).toEqual(["v", "b"]); // the unfound mark and the missing element are dropped
    expect(resolved[0].range!.toString()).toBe("basic");
    paint(doc, resolved, "v");
    expect(doc.body.innerHTML).toBe(bodyHtml);
    expect(Array.from(doc.body.querySelectorAll("*")).map(cssPathOf)).toEqual(before);
    const ov = doc.getElementById("gds-overlay")!;
    expect(ov.parentElement).toBe(doc.documentElement);
    const badges = Array.from(ov.querySelectorAll(".gds-badge"));
    expect(badges.map((b) => b.getAttribute("data-n"))).toEqual(["1", "2"]);
    expect(ov.querySelectorAll(".gds-box.gds-block.gds-focus").length).toBe(0);
    expect(ov.querySelectorAll(".gds-box.gds-value").length).toBe(1);
    badges.forEach((b) => expect(b.textContent).toBe("")); // numbers are drawn by CSS, not text
  });
});

describe("source view helpers", () => {
  it("builds the /source URL", () => {
    const u = sourceUrl("avc", "s1", { id: "1", kind: "value", cssPath: "html > body:nth-of-type(1)", charStart: 2, charEnd: 5, text: "abc" });
    expect(u).toBe("/api/catalogs/avc/pages/s1/source?css_path=html+%3E+body%3Anth-of-type%281%29&char_start=2&char_end=5&text=abc");
  });

  it("colorizes tags and attributes without losing text", () => {
    const parts = colorize('<div class="x">hi</div>', "k");
    const flat = parts.map((p) => (typeof p === "string" ? p : (p as { props: { children: string } }).props.children)).join("");
    expect(flat).toBe('<div class="x">hi</div>');
  });
});
