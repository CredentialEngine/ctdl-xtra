# xTRA mockup

University of Arkansas catalog courses, written as CTDL records, with the evidence for every value
kept and shown. Built from [`qrspi/03-specification.md`](qrspi/03-specification.md).

**Nothing here is published.** There is no publish step and no code that can send anything to the
Credential Registry. Every course identifier (CTID) was made here and is a placeholder.

## Run it

```sh
uv run xtra crawl        # step 1: fetch pages into data/store (the only step that uses the internet)
uv run xtra extract      # step 2: build records into data/out (no internet; uses ollama on this machine)
cd viewer && npm install && npm run dev      # step 3: the viewer, at http://localhost:5173
```

- `xtra crawl` a second time makes no requests. `--subjects all` takes every subject the index links to.
- `xtra extract --language-model none` skips the language model; `--language-model nonsense` swaps in a
  stand-in that returns rubbish, to show the guards hold. The default is `ollama:qwen3.5:9b`.
- `npm run build` writes a static site to `viewer/dist/`, with the data copied beside it.
- `npm run build:single` writes `viewer/dist-single/xtra-mockup.html`: the viewer, the data and the stored
  pages' styles in one file that opens from disk with no server, to hand to someone else. It fetches
  those styles from the catalog site the first time; `--no-page-assets` skips that.
- `docker build -t xtra-reviewer-mockup . && docker run --rm -p 8080:8080 xtra-reviewer-mockup` serves the
  static site, with the data in `data/out`, from nginx at http://localhost:8080.
- `uv run pytest` runs the tests, including the extract acceptance criteria against the stored pages.

## What is where

| Path | What |
|---|---|
| `rules/rules.toml` | The rule registry: every pattern, lookup table and parser phrase, as data |
| `rules/teaching.toml` | Hand-written notes per field: why this field, the alternatives, the glossary |
| `src/xtra/crawl.py`, `store.py` | Crawl, and the page store (bytes named by digest, sidecars, lookup) |
| `src/xtra/extract.py` | Builds each record and its provenance |
| `src/xtra/prereq.py` | Prerequisite parser, guards G1 to G5, and the mapping from a structure to CTDL |
| `src/xtra/llm.py` | The language model, behind a replaceable boundary, with a cache |
| `src/xtra/ctid.py` | The CTID service and its ledger |
| `src/xtra/schema.py` | The CTDL schema copy and conformance checks V1 to V8 |
| `data/store/` | The page store |
| `data/ledger/ctid-ledger.jsonl` | Every CTID minted, append-only |
| `data/llm-cache/` | Language model answers, by model name, prompt version and input |
| `data/out/` | Extract output: one file per course, display copies of documents, the run report |
| `viewer/` | The viewer (Vite and React, static files, no backend) |

## Using the viewer

- **Left:** a sidebar of everything under review, by CTDL class (courses by subject, then the
  organization they refer to). The icon at the top left shows and hides it.
- **Middle:** the record as **Pretty** (one card per field) or **Raw** (the JSON, with copy).
- **Right:** the stored page in a browser frame. Tabs name every document the course drew on.
- Click any value that was read from a document, in Pretty or Raw, to go to that place in it.
- `Tab` and `Shift`+`Tab` move between stops; `Enter` and `Shift`+`Enter` between courses.
- Deal with a field in one of three ways: `A` accepts it, `R` rejects it (a reason is required), `C` leaves
  a comment. Each counts toward the course's progress in the sidebar, where every row fills like a bar.
- `V` shows the selected field in the other view.
- Confidence is the colour of a card's right edge (green high, amber medium, red low). Click the
  edge, or the ⓘ on the card, for the reasoning. Brief, Standard and Full set how much of it opens.
- A triangle marks a caution; a purple star marks something a language model proposed.
- With a field selected, drag across the page to attribute different text to it.
- The pencil (or a double-click) opens a form for the value, built from the CTDL schema copy
  (`data/out/forms.json`): text boxes, pick-lists for CTDL's fixed lists (one or many), rows that
  can be added and removed, a course finder for links to other courses, a type choice wherever
  CTDL allows more than one, and a "Kind" choice that moves a requirement to another field (for
  example from prerequisite to corequisite). The `<>` icon in the form is the JSON fallback.
- Click a field's name, or its `ceterms:` term, for what CTDL says about it. Every name on that page is a link.
- Below the proposed fields are all the other fields CTDL allows on a course, blank with a grey edge; they
  can be filled in. A faint red asterisk marks required fields.
- The first field, CTID, is marked “not built yet”: click the mark or the card's ⓘ for what is missing
  (a check of whether the course is already in the Registry).
- Every page load opens a nine-step tour; Esc closes it. The “Show the tour” button in the top bar replays it.
- Everything a reviewer does is kept in the browser's local storage. There is at present no way to export it.

## The specification and the build

`qrspi/03-specification.md` was revised on 2026-10-08 to include everything Eric asked for while reviewing the
built viewer (its comments C14 to C60), so the build no longer departs from it. Its figures are screenshots of
this viewer; `node qrspi/screens/capture.mjs` regenerates them while the viewer is running on port 5199.

Where the build falls short of the revised specification:

- A rule's match is not highlighted on hover when it is in the page's markup or on a document that is not showing.
- The prerequisite parser, the guards, lookups and fixed values explain themselves in a sentence, not a card.
- Edits show in Pretty only; Raw still shows the record on disk.

## Known limits

- “Open original at this text” links are untested in Safari and Firefox (risk R7).
- With the internet off the viewer works, but the catalog's own styling is replaced by a small bundled fallback.
- CTDL definitions come from a schema copy dated 2026-06-07, not the live site (risk R1).
- The language model's reading of “and” and “or” is unproven wherever no bracketed group checks it (risk R3).
