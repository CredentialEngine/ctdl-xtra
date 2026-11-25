# Research: v2 data model, provenance, rules, review data

Research phase of QRSPI for review-ui-v3. Facts only. Code facts cite `file:line` under
`review-ui-v2/server/review_ui/`. Data facts come from the real Azure container
`ceteststorage/xtra-cli-output`, read only: the latest extraction plus every review session of each of the five
catalogs, downloaded on 2026-10-26 to a scratch folder. Nothing in Azure was written. Anything **inferred** rather
than checked is marked as inferred.

Scratch scripts and the downloaded copy are in
`/private/tmp/claude-501/-Users-eric--superset-worktrees-ctdl-xtra-glowing-conchoraptor-79248126/9a24ca32-87da-41f1-8d05-111d893d1142/scratchpad/data-model/`
(`scripts/*.py`, `az/`, and `feedback-avc.md`, a real feedback.md generated locally).

Catalogs and the runs used:

| Catalog | Run | Latest extraction | Ruleset version |
|---|---|---|---|
| AVC (eLumen) | `avc-elumenapp-com-catalog-2026-27-welcome/2026-10-12T20-59-13Z` | `2026-10-19T17-27-31Z` | 1 |
| CCSF (CurricUNET) | `ccsf-curricunet-com-catalog/2026-10-01T16-02-34Z` | `2026-10-19T17-18-22Z` | 2 |
| Marshall (CourseLeaf) | `catalog-marshall-edu/2026-10-20T13-18-30Z` | `2026-10-21T14-21-32Z` | 1 |
| UALR (Acalog) | `catalog-ualr-edu/2026-10-18T21-05-00Z` | `2026-10-21T14-14-38Z` | 1 |
| WVU (CourseLeaf) | `catalog-wvu-edu/2026-10-20T13-19-46Z` | `2026-10-21T14-25-24Z` | 1 |

In all five, the published `review-ui-index/rulesets/<catalog>/rules.json` is byte-identical to the latest
extraction's `rules.json`. So the rules have not changed since the last extract.

---

## B1. Shape of an extraction, and where provenance is lost

### How a value flows

1. `engine.run_page` (engine.py:176-224) runs on one page. It cuts out the `content_root` fragment
   (runs.py:88-105) and wraps it in `<div id="xtra-root">`. It returns **labels** and **entities**. An entity is one
   course occurrence: the whole page, or one `repeat` element. Each entity carries `label_rule_id`, `label`,
   `root_path` (the css_path of the record's root element), `index` (its position among that label's entities on the
   page) and `fields`.
2. Each field (engine.py:121-157) has `canonical_label`, `ctdl_property`, `rule_id`, `rule_type`, `presence`,
   `value`, `raw_text` and `location = {css_path, char_start, char_end}`.
   - **`raw_text` is the pre-transform text.** It is the regex group (or the whole element text) *before* the
     `transforms` and the `map` are applied (engine.py:79-94). Example: raw `"GEOG 222:"` became value `"GEOG 222"`.
   - **Offsets exist.** `char_start`/`char_end` are the span of `raw_text` inside the selected element's visible
     text (`text_of`, engine.py:27-36, with `<br>` turned into `\n`). They are **not** offsets in the HTML or
     the page.
   - `location` is `null` for `constant` and `source_url` rules (engine.py:137-140, 151).
   - `css_path` is anchored at `#xtra-root` (the wrapper around the content-root fragment), **not at the page's
     `<html>`** (engine.py:39-51). Example: `#xtra-root > div:nth-of-type(1) > header:nth-of-type(1) > h3:nth-of-type(1)`.
     For UALR the anchor is `#xtra-root > td:nth-of-type(1) > …`. *Inferred:* to resolve these paths in a full-page
     render, the first step has to be mapped to the `content_root` element.
3. `merge.merge_pages` (merge.py:36-114) folds every entity of every page into **one record per course code**.
4. `extract.run_extraction` (extract.py:128-224) writes the files.

### Files under `<run>/extractions/<ts>/` (extract.py:159-223)

| File | Contents |
|---|---|
| `rules.json` | A full copy of the ruleset used (extract.py:160). This is the only frozen copy of an older ruleset. |
| `sample.json` | A copy of `<run>/review-ui/sample.json`: `{run, size, pages:[{stem,url,page_type,reason}]}` (extract.py:161-163). |
| `pages.jsonl` | One row per crawled page: `{stem, url, page_type, title, labels:[{label,rule_id}], record_ids:[…]}` (extract.py:175-191). |
| `report.json` | `{extraction_id, ruleset:{id,version}, pages_total, pages_without_main_content, labels_per_rule, page_types, entities, records, uncoded_records, records_with_conflicts, fill:{label_rule:{property:{total,present,absent}}}, regression:{…}}` (extract.py:209-223). |
| `records/<CODE>.json` | One file per merged record (extract.py:166-174). |
| `../../discovery/<ts>/labels.json` | `[{label, source_url, rule_id, stem}]` (extract.py:193-203). |

A real record, trimmed (CCSF `ART130B.json`). The same course was found on its department page and as a stub on two
program pages:

```json
{
 "record_id": "ART130B", "catalogue_type": "COURSES", "entity_type": "Course",
 "source_urls": ["https://ccsf.curricunet.com/catalog/iq/courses/3/22",
                 "https://ccsf.curricunet.com/catalog/iq/programs/arts-media-entertainment/1839/2210", "…/1875/2283"],
 "source_expected": {"fields": [
  {"canonical_label": "External Identifier", "ctdl_property": "ceterms:identifier",
   "rule_id": "course-external-id", "rule_type": "css+regex", "presence": "present",
   "value": "ART130B", "raw_text": "ART 130B",
   "location": {"css_path": "#xtra-root > div:nth-of-type(1) > article:nth-of-type(1) > … > b:nth-of-type(1)",
                "char_start": 0, "char_end": 8},
   "source_url": "https://ccsf.curricunet.com/catalog/iq/courses/3/22",
   "field_id": "ART130B::External Identifier::https://ccsf.curricunet.com/catalog/iq/courses/3/22::0"},
  {"canonical_label": "External Identifier", "rule_id": "stub-external-id", "value": "ART130B",
   "raw_text": "ART 130B", "location": {"css_path": "… > a:nth-of-type(1) > span:nth-of-type(1)", "…": "…"},
   "source_url": "…/programs/arts-media-entertainment/1839/2210", "field_id": "ART130B::External Identifier::…/2210::0"},
  {"canonical_label": "Learning Type", "ctdl_property": null, "rule_id": "course-learning-type",
   "rule_type": "constant", "value": "Course", "raw_text": "Course", "location": null, "…": "…"}
 ]},
 "conflicts": [{"canonical_label": "Credit Value", "values": [{"value": "3", "source_urls": ["…"]}, "…"]}]
}
```

A pre-merge entity (from running `engine.run_page` on a real AVC program page):

```json
{"label_rule_id": "label-course-on-program-page", "label": "Course",
 "root_path": "#xtra-root > div:nth-of-type(1) > … > div:nth-of-type(1)", "index": 0,
 "fields": [{"rule_id": "stub-code", "value": "MATH150", "raw_text": "MATH150",
             "location": {"css_path": "… > span:nth-of-type(1)", "char_start": 70, "char_end": 77}, "…": "…"}]}
```

### Provenance per value: what exists and where

| Provenance | Engine output | Record file | UI API (`/pages/{stem}`) | Download → golden JSON | Save golden dataset | Review decision |
|---|---|---|---|---|---|---|
| `rule_id` | yes | yes | yes | yes | **no** | yes |
| `rule_type`, `ctdl_property` | yes | yes | yes | yes | only `ctdl_property` | no |
| `raw_text` (pre-transform) | yes | yes | yes | yes | **no** | no |
| element `css_path` + char offsets | yes | yes | yes | yes | **no** | **no** (only looked up later through `field_id`) |
| `source_url` | (page url) | yes | yes | yes | yes | yes |
| entity `root_path`, `index`, `label_rule_id` | yes | **no** | **no** | **no** | **no** | no |
| ruleset id/version | no | no (only `report.json` and `rules.json` of the extraction) | no | no | no | no (only through session → extraction) |
| per-rule version / hash | none | none | none | none | none | none |

Every place a field gets dropped:

1. **Merge drops the record locator.** `merge.py:69-77` copies only the field (`**field`, plus `source_url` and
   `field_id`). The entity's `root_path`, `index` and `label_rule_id` are not stored anywhere on disk. So **v2 has
   no saved "where does this record start on the page".**
2. **Merge drops absent values with their rule.** `merge.py:55` skips every field whose `presence` isn't
   `present`. If a required property is absent from *every* source, `merge.py:80-98` adds one placeholder with
   `rule_id: null` and `location: null`. So "rule X ran on record Y and found nothing" is lost. v3 needs that fact
   for its "missing" signals.
3. **Merge drops a repeat of the same value on the same page.** If the same normalized value appears for the same
   (record, property, page), it's kept once (merge.py:57-65). The location of the second one is lost.
4. **Merge mixes up records that share a code on one page.** When two entities on one page have the same code,
   their fields go into the same record and get numbered `::0`, `::1`, … *per property*. Nothing says which name
   belongs with which description. This is real: WVU `GRAD593` on the PharmD page has three "Special Topics (…)"
   names. It happens in 91 Marshall records and 96 WVU records (see D3).
5. **`views.page`** (views.py:44-76) serves the record's fields filtered by `source_url`. It keeps
   `raw_text`/`location`. The web app uses `location.css_path` to highlight (web/src/components/RecordGroup.tsx:119).
6. **Download → golden JSON** (`exports.golden_for_page`, exports.py:55) keeps every field key except `field_id`,
   and adds `review_status`. A correction keeps the old `raw_text`/`location` beside the new `value`
   (exports.py:65-69). *Inferred:* that provenance is stale for corrected values.
7. **Save golden dataset** (`golden.py:86-92`) keeps exactly `ctdl_property`, `value` and `source_url`, grouped
   by record. It also drops `record_id`, `field_id`, `rule_id` and `review_status`. **A saved golden value can't be
   traced back to its extracted value or decision**, except by matching (`source_url`, `value`). There's no index
   (test_golden.py:245-247 asserts the old `golden-data-index.json` is not written any more).
   Real data: `xtra-golden-sets-verified` has 14 / 12 / 11 / 14 / 4 saved pages for AVC / CCSF / Marshall / UALR /
   WVU (two blobs, `.json` and `.html`, per page). One saved WVU page holds 49 records.
8. **Review decisions** store `rule_id`, `record_id`, `value` and `source_url`, but not the css_path or the raw
   text (review.py:175-188, real examples in B3).

**Is raw pre-transform text kept?** Yes. `raw_text` is in every record file, the UI API and the golden download. It
isn't in the saved golden dataset or in decisions. The page HTML is kept as crawled (`pages/<stem>.html`), and
golden saves copy it whole (golden.py:121).

---

## B2. Can a value be traced to a ruleset version? Can each rule get a content hash?

- **Value → ruleset: only indirectly.** A field has a `rule_id`. The extraction folder has `report.json`
  `ruleset:{id,version}` and a full copy of `rules.json`. Every value in that folder came from that copy. There's
  no version on the value itself.
- **The version number doesn't identify the content.** `rules publish` overwrites the single file
  (rulesets.py:77-85) and only checks `version > published` (and `--force` skips even that). Real case: AVC's
  `2026-10-16T20-14-15Z` extraction and its `2026-10-19T17-27-31Z` extraction both say **v1**, but their
  `rules.json` files differ. The newer one adds `content_root`, `page_types`, `sample`, `pane_css` and `page_title`.
  The field and label rules are identical. CCSF went v1 → v2 with the same kind of change. *Inferred:* the AVC change
  came from the older schema being republished with `--force`, or before the version check existed.
- **Old rulesets survive only as copies inside extractions.** `review-ui-index/rulesets/` holds only the latest.
- **How rules are identified:** `rule_id` strings, unique *within a ruleset* (rules.py:209-214). The same ids are
  used in all five rulesets (`course-code`, `stub-name`, `label-course-page`, …), so a global id needs
  `(ruleset_id, rule_id)`.
- **A per-rule content hash is easy to compute.** Each label rule and field rule is a self-contained JSON object
  (schema rules.py:103-177). `sha256(json.dumps(rule, sort_keys=True))` would work. **But a field rule's behaviour
  also depends on things outside its object:**
  - the ruleset-level `content_root`: it decides which fragment the rule sees, and the `#xtra-root` anchor of every
    css_path;
  - the label rule(s) named in `applies_to`: they decide which pages it runs on;
  - the `scope`/`repeat`/`repeat_filter` copied into each field rule: they decide which entity it belongs to
    (engine.py:192-215);
  - the Coded Notation rule on the same entity: it decides which record the value lands in (merge.py:28-33).

  *Inferred:* a "behavioural" hash would hash the rule together with `content_root`, its label rule(s) and its
  locator. Otherwise two values with the same rule hash can come from different behaviour.

---

## B3. How v2 keys decisions, notes and flags, and how carry-over works

Files are under `<run>/review-ui/<review_id>/`. `events.jsonl` is append-only and is the source of truth
(review.py:158-168). `decisions.json` (a dict by key), `notes.json` (a list) and `flags.json` (a dict by target) are
rewritten after every event (review.py:164-166). `review-ui-index/index.json` gets one entry per (run, review_id)
with its counts (review.py:234-252).

**Keys:**

- **Field decision:** `field_id = "<record_id>::<canonical_label>::<source_url>::<occurrence>"` (merge.py:20-21).
  `record_id` is the Coded Notation with spaces removed and upper-cased (normalize.py:21-23), or
  `UNCODED-<stem>-<label_rule_id>-<index>`.
- **"Missing" (added) field:** `"<record_id>::<label>::<source_url>::added::<random>"`. It has no `rule_id`.
- **Label decision:** `"label::<source_url>::<label>::<rule_id>"` (merge.py:24-25). An added label uses `::manual`.
- **Note:** a random `id`, with `scope` ∈ field|rule|property|general and `target` = field key, rule_id or property
  name (review.py:189-196).
- **Flag:** keyed by `target`, with `scope` ∈ page|field|label. A page flag's target is `page::<stem>`
  (review.py:197-207).

Real decision (AVC, values trimmed):

```json
"GEOG222::External Identifier::https://avc.elumenapp.com/catalog/2026-27/course/geog222::0": {
  "kind": "field", "status": "accepted", "canonical_label": "External Identifier",
  "source_url": "https://avc.elumenapp.com/catalog/2026-27/course/geog222", "record_id": "GEOG222",
  "rule_id": "course-external-id", "value": "GEOG222", "reasons": [], "author": "Jared",
  "carried_from": "2026-10-16T20-23-12Z", "seq": 2, "at": "2026-10-19T17-27-55Z", "review_id": "2026-10-19T17-27-55Z"}
"GEOG222::Description::https://…/course/geog222::added::mvfo6rji": {
  "kind": "field", "status": "missing", "record_id": "GEOG222", "expected_value": "This course provides …",
  "reasons": ["missed"], "author": "Jared", "…": "…"}            // no rule_id
"label::https://…/program/computer-engineering-as-fall-2026::Credential::manual": {"kind": "label", "status": "missing", "…": "…"}
```

Real note: `{"scope":"field","target":"NS922L::Credit Unit Type Description::…::0","text":"Should be creditUnitType","author":"Jared"}`.
Real flag: `page::avc-…-computer-engineering-as-fall-2026-5a1e6e1354` → `{"scope":"page","note":"I have updated the page labels. But properties listed here are all for courses. Should I reject all these properties? …"}`.

**Carry-over** (review.py:56-120, extract.py:55-73):

- A new session gets `baseline_decisions` = the latest decision per key across **all** of the run's sessions.
  Only **accepted** decisions are re-applied, and only when the key still exists in the new extraction's sample and
  the value matches after normalizing case and whitespace (review.py:84-101, 277-280). Labels always match.
- **Rejected, missing and corrected decisions are not carried. Notes are not carried.** Open flags are carried from
  the latest session only if their page or key still exists (review.py:102-118).
- Carried events keep `carried_from`. Real data: 19 of the 213 decisions in AVC's second session were carried over.
- `check_regressions` (extract.py:76-111) compares accepted decisions with a new extraction by key.
- **Fragility.** The key embeds the course code, the property, the page URL and an occurrence number. The occurrence
  depends on page order and on the values on that page. *Inferred:* a decision is lost (orphaned) whenever the code
  rule changes the code's spelling, a locator change shifts the occurrence numbering, or a value isn't the first one
  for that (record, property, page).

---

## B10/B11 and the rule kinds, in plain language

A ruleset is one JSON file per catalog. Here is what each part does, using **Marshall** (CourseLeaf) as the example.

| Part | Plain language | Which job |
|---|---|---|
| `content_root` (`#contentarea`) | "Ignore the menu and footer; only look inside this box." Every rule sees only this box. | Setup for all of them |
| `page_types` | A **label for display and sampling only**: "a URL like `/courses-az/<x>/` is a *course* page". **Extraction doesn't use it** (only extract.py:40 and sample.py read it). It can disagree with the label rules: CCSF has 123 "course" page_types but 118 pages with `label-course-page`. | Organizes the page list, decides nothing |
| `label_rules` | **"Is this page one that has courses on it?"** A label rule matches on the URL (`url_regex`) and on whether some element exists (`requires_selector`) or doesn't (`forbids_selector`). Marshall `label-course-page`: URL is `/courses-az/<x>/` **and** the page has a `div.courseblock`. | **Find course pages** |
| `requires_selector` / `forbids_selector` | The "has a … / has no …" tests inside a label rule. | Find course pages |
| `applies_to` | On a field rule: "run me only on pages that got this label". This is the link between "which pages" and "which fields". | Connects the two |
| `repeat` (+ `repeat_filter`, `scope`) | On a field rule: **"on this page, each `div.courseblock` is one course"**. If there's no `repeat`, the whole page is one course (AVC, UALR course pages). `repeat_filter` keeps only the repeated elements whose text looks like a course code (for example, table rows starting with `ENG 200`). | **Find the course records on a page** |
| `field_rules` | **"Inside one course, where is property X?"** A CSS `selector`, then an optional `regex` (with a capture `group`). | **Extract a field** |
| `transforms` | Clean-up steps after extraction: `strip`, `collapse_ws`, `upper`, `lower`, `remove_spaces`, `rstrip:<chars>` (engine.py:54-68). Example: AVC `course-external-id` turns `"GEOG 222:"` into `"GEOG222"`. | Extract a field |
| `map` | A lookup table after the transforms. Anything not in the table counts as absent (engine.py:90-91). Example: CCSF `Noncredit` → `TRUE`. UALR uses it for credit values. | Extract a field |
| `rule_type` `constant` / `source_url` | Not read from the page: a fixed value (`Course`, `Active`, `English`) or the page's own URL. | Extract a field (always "found") |
| `merge.py` (code, not rules) | After every page is done, **code** groups all course occurrences across the catalog by their Coded Notation. One record per code, so a course listed on its own page and on 12 program pages becomes one record. | Neither: joins the results across pages |
| `page_title`, `sample`, `pane_css` | Display, choosing the review sample, and CSS for the page pane. | UI only |

**Two kinds of label, three kinds of page.** Every ruleset has `label-course-page` (a page with full course entries),
`label-program-page` (labels the page "Program"; **no field rule applies to it**) and `label-course-on-program-page`
(a program page that lists courses). A course found on a program page is a **stub**: the `stub-*` field rules
extract only name, code, external id, credit value and learning type. The stub rules have no Description,
Subject Webpage, Life Cycle or Language.

**A real rule, Marshall `course-description`:**

```json
{"rule_id": "course-description", "rule_type": "css+regex", "canonical_label": "Description",
 "ctdl_property": "ceterms:description", "applies_to": ["label-course-page"],
 "properties": {"repeat": "div.courseblock", "selector": ".courseblockextra",
                "regex": "\\A\\s*(?!Pre-?req|Co-?req)(\\S[\\s\\S]*)", "group": 1, "transforms": ["collapse_ws"]},
 "description": "The first text block of the course, unless it is the Pre-req line (courses with no description).",
 "example_input": "Fundamentals of theatre arts.", "example_output": "Fundamentals of theatre arts."}
```

Read it as: *on pages that the rule `label-course-page` says have courses* (URL `/courses-az/<x>/` and a
`div.courseblock`), *treat each `div.courseblock` as one course* (that's the record locator), *take that course's
first `.courseblockextra` text unless it starts with "Pre-req"/"Co-req", and collapse the whitespace*.

**There's no separate record-locator rule.** The locator is copied into every field rule. Today the copies are
consistent: in all five rulesets, every field rule with the same `applies_to` has the same
(`scope`, `repeat`, `repeat_filter`). The engine groups fields into one entity by `(scope, repeat, element)`
(engine.py:206-214). So if one rule's `repeat` drifted, it would quietly produce separate entities and separate
records. The copies are identical in all five rulesets, so the locator could be factored out into its own rule
without changing any output.

**Can one field rule run alone over the corpus?** Mechanically, yes. If you filter `field_rules` down to one rule
(keeping its label rules and `content_root`), `run_page` runs it, so the run needs no code change. But it depends on
other rules:

- it needs its **label rule(s)** (`applies_to`) to know which pages to run on;
- it needs the **locator** (`repeat`), which travels with it;
- its values can only be **keyed to a course by the Coded Notation rule** on the same entity (merge.py:28-33).
  Run alone, every entity becomes `UNCODED-<stem>-<label>-<index>`.

*Inferred:* a single-rule rerun in v3 should run the label rule + the locator + the code rule + the target rule.
Rerunning one rule against the same label and locator output gives the same entities, so values can be joined by
(page, locator position) without merge.py. Timing measured on one page: 50 ms for an AVC course page and 11 ms for a
program page (whole ruleset).

---

## D1. Field rules mapped to the required properties

The template (`review-ui-index/templates/course.properties.json`) has seven properties with `required: true`.
`Coded Notation` (`ceterms:codedNotation`) and `Credit Value` aren't required.

| Property (term) | AVC | CCSF | Marshall | UALR | WVU |
|---|---|---|---|---|---|
| External Identifier (`ceterms:identifier`) | course + stub | course + stub | course + stub | course + stub | course + stub |
| Learning Type (no term, `ctdl_property: null`) | constant `Course`, course + stub | same | same | same | same |
| Learning Opportunity Name (`ceterms:name`) | course + stub | course + stub | course + stub | course + stub | course + stub |
| Description (`ceterms:description`) | course only | course only | course only | course only | course only |
| Subject Webpage (`ceterms:subjectWebpage`) | `source_url`, course only | same | same | same | same |
| Life Cycle Status Type | constant `Active`, course only | same | same | same | same |
| Language (`ceterms:inLanguage`) | constant `English`, course only | same | same | same | same |
| Coded Notation (`ceterms:codedNotation`) | course + stub | course + stub | course + stub | course + stub | course + stub |
| Credit Value (+ Min/Max) | course + stub; Min/Max course only | same | same | Value/Min/Max course only, with `map`; **no stub credit** | same as AVC |
| Other | Credit Unit Type Description (AVC only) | Is Non-Credit (`map`) | | | |

So three of the seven required properties are constants and one is the page URL. Only **External Identifier,
Name and Description** come from page content. Subject Webpage on CourseLeaf (Marshall, WVU) and CCSF is the URL of
the *listing* page, shared by every course on that page.

**Which property is the "course ID".** In all five rulesets, `course-code` (Coded Notation) and
`course-external-id` (External Identifier) read **the same element with the same regex**. They differ only in that
External Identifier adds `remove_spaces` (AVC: `"GEOG 222"` vs `"GEOG222"`). The record key (`record_id`) is built
from **Coded Notation** (merge.py:16, 28-31): spaces removed, upper-cased. That makes it equal to External
Identifier upper-cased. Selectors per catalog:

| Catalog | Course page | Stub |
|---|---|---|
| AVC | `header.header h3` | `.rule-name` regex `^…\s+-\s+` |
| CCSF | `.course-title-units-row` regex `^(.+?)\s+-\s` | `.course-entry-link-content` |
| Marshall | `.detail-code` | `td.codecol` |
| UALR | `#course_preview_title` regex `^([A-Z]{2,5}\s+\d{4,5})\s+-\s` | `a` in `li.acalog-course` |
| WVU | `.courseblocktitle` regex `^([A-Z&]+\s+\d+[A-Z]*)\.` | `td.codecol` (allows a leading `or`) |

Fill rates in the latest extraction, present/total entities:

| Catalog | Course-page entities (Name / Code / Desc / Credit) | Stub entities (Name / Code) |
|---|---|---|
| AVC | 1062 / 1062 / 1062 / 1005 of 1062 | 2751 / 2751 of 2751 |
| CCSF | 1927 / 1927 / 1926 / 1897 of 1927 | 6071 / 6071 of 6071 |
| Marshall | 6692 / 6692 / 5491 / 4684 of 6692 | 9733 / 9733 of 9738 |
| UALR | 100 / 100 / 99 / 81 of 100 | 7231 / 7232 of 7232 |
| WVU | 22013 / 22015 / 21826 / 14338 of 22023 | 16950 / 16945 of 16953 |

---

## D3/D9. How unique is the course code as a record key?

There are two levels:

- **Entity** = one course occurrence on one page.
- **Record** = all the entities with the same normalized code, merged.

| Catalog | Pages | Entities | Records | No code (`UNCODED-`) | Records seen on >1 page | Full + stub | Stub only | Full course on ≥2 course pages | Same code twice on one page, different names | Records with conflicts |
|---|---|---|---|---|---|---|---|---|---|---|
| AVC | 1467 | 3813 | 1075 | 0 | 907 | 907 | 13 | 0 | 0 | 83 (78 credit, 5 name) |
| CCSF | 521 | 7998 | 1956 | 0 | 1579 | 1544 | 47 | 17 | 0 | 129 (109 credit, 21 name) |
| Marshall | 914 | 16430 | 6734 | 5 | 2704 | 2702 | 37 | 0 | 91 | 327 (304 name, 50 credit) |
| UALR | 591 | 7332 | 1276 | 0 | 1220 | 62 | **1176** | 0 | 0 | 0 |
| WVU | 900 | 38976 | 11242 | 16 | 10080 | 4970 | 56 | **9805** | 96 | 619 (484 name, 145 credit, 10 desc) |

Why codes repeat:

1. **Stub plus full record (the common, harmless case).** The same course is listed in program requirements. This
   happens in 907 of 1075 AVC records, 1544 of 1956 CCSF, 2702 of 6734 Marshall and 4970 of 11242 WVU. The stub's
   name often differs slightly ("Texting the World(CT) (recommended)"), so most "name conflicts" are stub
   decorations, not wrong values.
2. **The same full course on several course pages.** WVU lists each course on its college page *and* on
   `/graduate/courses/` or `/undergraduate/courses/`. Number of course pages per WVU record: 0: 72, 1: 1365,
   2: 8972, 3: 639, 4: 194. CCSF has 17 cross-listed courses (`HIST41B` is on department pages 3/11 and 3/97).
3. **True duplicates or different courses under one code.** WVU has 3 records whose full course pages give
   *different* names (`SEP615` "Research Methodology in Physical Education…" vs "Research Methods in Sport…";
   `PE104` "Intermediate Basketball" vs "Basketball"; `ESPT101`) and 10 with different descriptions. One page can
   also list one code several times with different titles: 91 Marshall and 96 WVU records, mostly stubs such as WVU
   `GRAD593` "Special Topics (…)" ×3 on the PharmD page, or a "(Senior Project)" variant. merge.py folds these into
   one record (B1 item 4).
4. **No code.** 5 Marshall and 16 WVU entities. They get keyed by `UNCODED-<stem>-<label>-<index>`. Examples: a
   Marshall stub with name "Spanish Film" and no code; a WVU course block with a description but no code.
5. **UALR is almost all stubs.** Only 100 course pages are in the crawl, but 333 program pages list courses, so
   1176 of 1276 records come only from program pages. *Inferred:* the crawl is incomplete for course pages.

For D9 ("same course" = same normalized code): this works for nearly all records. The problem cases are (3) and
(4): in Marshall + WVU, about 190 records where one code covers several different entries, plus 21 entities with no
code. Elsewhere it's 0. AVC, CCSF and UALR have no uncoded entities and no same-page code collisions.

---

## D6. How much v2 review work exists, and can it become (course code, rule_id) annotations?

`review-ui-index/index.json` has **9 entries**. Five are the live ones, and their counts match the session files in
Azure exactly. Rejected and missing combine field + label decisions:

| Catalog | Session | Accepted | Rejected | Missing | Flags | Notes | Authors |
|---|---|---|---|---|---|---|---|
| AVC | `2026-10-16T20-23-12Z` (old extraction) | 35 | 6 | 0 | 0 | 6 field | Jared |
| AVC | `2026-10-19T17-27-55Z` | 145 | 26 | 42 | 8 page | 21 field | Jared 212, Seth 1 |
| CCSF | `2026-10-19T16-53-03Z` | 0 | 0 | 0 | 0 | 0 | (empty) |
| CCSF | `2026-10-19T17-58-24Z` | 655 | 8 | 32 | 7 page | 1 field | Jared 658, Seth 37 |
| Marshall | `2026-10-21T16-49-50Z` | 674 | 0 | 77 | 2 page | 0 | Seth 615, Jared 136 |
| UALR | `2026-10-22T16-04-13Z` | 146 | 0 | 22 | 0 | 0 | Jared 119, Seth 49 |
| WVU | `2026-10-22T16-05-24Z` | 822 | 14 | 144 | 12 page + 1 label | 9 field | Jared |

Split by kind and scope. "In scope" = the 7 required properties + Coded Notation:

| Catalog (latest session) | Field accepted in / out of scope | Field rejected | Field missing (all out of scope unless noted) | Label acc / rej / missing | Distinct records touched |
|---|---|---|---|---|---|
| AVC | 107 / 17 | 19 (14 Credit Unit Type Desc, 5 Description) | 26 (14 Credit Unit Type, 5 Prereq, 2 Non-Credit, **5 Description** in scope) | 21 / 7 / 16 | 14 |
| CCSF | 550 / 85 | 0 | 24 (Prerequisites) | 20 / 8 / 8 | 69 |
| Marshall | 552 / 102 | 0 | 77 (69 Credit Unit Type, 8 Prereq) | 20 / 0 / 0 | 69 |
| UALR | 112 / 17 | 0 | 22 (14 Credit Unit Type, 8 Prereq) | 17 / 0 / 0 | 14 |
| WVU | 670 / 135 | 3 (ext id, learning type, name) | 128 (83 Credit Unit Type, 45 Prereq) | 17 / 11 / 16 | 85 |

Key points:

- **Almost all the real work is "accepted" on in-scope fields (≈2,000 field verdicts) and "missing" on
  out-of-scope properties** (Credit Unit Type, Prerequisites, which v3 drops). **Only one "rejected with an
  expected value"** exists, in the old AVC session. Jared records a correction as **reject + a separate "missing"
  with the right value**. Real example: AVC GEOG222 Description was rejected ("Prerequisite should be a separate
  property") and a `missing` Description was added with the text minus the prerequisite. The two are joinable on
  (record_id, canonical_label, source_url).
- **Mapping to (course code, rule_id) is feasible for field decisions.** In every session, 100% of the
  accepted/rejected field-decision keys resolve to a field in their extraction's records, and the decision's
  `rule_id` matches the field's `rule_id` (AVC 143/143, CCSF 635/635, Marshall 654/654, UALR 129/129,
  WVU 808/808). `record_id` *is* the normalized code.
  - "Missing" field decisions have no `rule_id`. *Inferred:* they can be mapped to the rule for that property and
    that page's label (`course-<prop>` on course pages, `stub-<prop>` on program pages), or to "no rule".
  - Label decisions map to (page URL, label rule): a **page-rule** annotation.
  - Page flags map to page-level annotations.
- **What's lost or approximate in that mapping:**
  1. the decision is for **one value on one page**, not for the rule on the whole record: a record has full + stub
     values, and each has its own decision;
  2. **the record locator position isn't in the decision** (it isn't in v2's data at all);
  3. the **rule version** is known only through session → extraction → `rules.json`;
  4. the `occurrence` suffix is ambiguous where codes repeat on a page (B1 item 4);
  5. constants/source_url accepts (Learning Type, Life Cycle, Language, Subject Webpage) make up a large share of
     the "accepted" count but say little about rule quality;
  6. notes are free text keyed to a field key (or rule/property), so they move only as text;
  7. the old AVC session (`2026-10-16`) refers to an older extraction (not downloaded, but present in Azure).

---

## B14. `export-feedback` / `feedback.md` and `ITERATE.md`

- **`export-feedback`** (cli.py:358-378) builds `feedback_markdown` (exports.py:242-383) for the latest (or a given)
  session and **writes it into the storage root** at `<run>/review-ui/<review_id>/feedback.md`. The UI also offers it
  as a download (api.py:434). **No `feedback.md` exists anywhere in `xtra-cli-output`** (checked by listing the
  whole container). So the CLI command has never been run against Azure; *inferred*: the downloads were only ever
  used locally.
- **Contents**, in order:
  - a header (review id, extraction id, ruleset id + version, counts);
  - general notes;
  - "Flagged for review (waiting on experts)", per page;
  - notes on properties;
  - **"Problems, grouped by rule"**: for each rule_id, the rule's current `properties` as a Python dict repr, the rule
    notes, then each rejected/missing item with page URL, record, status + reasons, extracted value, expected value,
    field notes, and an **HTML excerpt of the element at `css_path` (≤500 chars)**. "Missed" items go under
    "No rule found these";
  - notes on rules with nothing rejected;
  - regressions from `report.json`.
- **A real one was generated locally** for AVC's latest session (302 lines, never written to Azure):
  `…/scratchpad/data-model/feedback-avc.md`. Sections: 8 flagged pages, then problems under
  `course-credit-unit-desc` (14), `course-description` (5, each with "Prerequisite should be a separate property"
  and an HTML excerpt), `label-course-on-program-page`, and a long "missed" list that is mostly Credit Unit Type and
  Prerequisites.
- **`ITERATE.md`** is a paste-in prompt for Claude Code:
  1. pull a draft (`rules pull`);
  2. read the README rule format and the attached feedback.md;
  3. fix every item while staying declarative (no Python/JS), looking at real pages in `<run>/pages/`;
  4. don't break accepted values: run `check-rules`, then a full `extract`, which exits non-zero on regressions;
  5. give every changed rule a `description` + `example_input`/`example_output`;
  6. leave flagged items alone;
  7. say when the format can't express something;
  8. bump `version` and report per item plus the fill rates. It ends with "Do not commit or push anything".

  It doesn't mention publishing results back, comparing versions, or running a single rule.

---

## B13. Is v2 deployed anywhere?

**No evidence of a deployment.**

- None of `.github/workflows/*` (build-base, ci-semgrep, ci-xtra-cli, deploy-test, promote-*, release*,
  skooner-token) mentions `review-ui` or `review-ui-v2`. They build `xtra-cli`, `client`/`server`, `base.Dockerfile`
  and `worker.Dockerfile`.
- `review-ui-v2/Dockerfile` and `compose.yaml` exist (one image; Azurite in compose) and are documented for local
  Podman/Docker use.
- The README says "It is not deployed anywhere" and that it is shared over ngrok.
- In the `ceteststorage` subscription, `az containerapp list` fails because the `Microsoft.App` provider isn't even
  registered, and `az webapp list` returned nothing.

*Inferred:* the review data in Azure was written by laptops running v2 with an `azure://` root, or copied there from
local folders.

---

## 10. Other surprises

1. **The doubled `<catalog>/<catalog>/<run>` paths in `index.json` are stale entries from local runs.** Azure has
   only `<catalog>/<run>/…`.
   - The README's own layout line says `<root>/<catalog>/<catalog>/<run>`. `find_runs` locates runs by
     `crawl.json` at any depth (runs.py:52-66), so a local `crawls/` folder with a doubled layout produced
     `run.key`s with the doubled path.
   - Those keys are baked into data that was later copied to Azure: `session.json.run` and `sample.json.run` for the
     AVC and CCSF sessions still say `avc-…/avc-…/2026-10-12T20-59-13Z`.
   - The index has the same review id under both keys with **different counts**. AVC `2026-10-19T17-27-55Z`:
     doubled entry 19 accepted, real entry 145. CCSF `2026-10-19T17-58-24Z`: 0 vs 655. The doubled entries are frozen
     snapshots. The old AVC session `2026-10-16T20-23-12Z` is indexed *only* under the doubled key.
   - Marshall, UALR and WVU sessions use single paths. *Inferred:* they were created directly against Azure.
2. **A ruleset's version number doesn't pin its content** (AVC v1 ≠ v1, see B2). Only the copy in each extraction
   does.
3. **Run folders also contain xtra-cli output with similar names:** `<run>/records/*` (1065 files for AVC), `golden-data/`,
   `extract-report.json`, `extraction-*-report.json` and `discovery/<ts>/entities.csv|patterns.*`. v2 writes
   `extractions/<ts>/records/` and `discovery/<ts>/labels.json`, next to them. Easy to confuse.
4. **The leftover `review-ui-index/golden-data-index.json`** is from an older design. Current code asserts that it
   is no longer written.
5. **`Learning Type` has `ctdl_property: null`.** The template has no term for it, so Save golden dataset always
   drops it (golden.py:83-84: `no_ctdl_property`). One of the seven required properties never reaches a saved
   golden set.
6. **Output size.** Field rows per latest extraction: AVC 24k, CCSF 47k, Marshall 104k, UALR 33k, WVU 267k. Record
   files total 18 MB / 42 MB / 75 MB / 25 MB / 183 MB, across 1,075 to 11,242 files. `css_path` strings are
   12–31% of those bytes and `field_id` 11–15%.
7. **`total_items` in WVU's session is 9,589** for 21 sample pages, because WVU course pages list hundreds of
   courses each. "Review the sample" is already impractical there (8,753 pending).
8. **Records don't say which rule found nothing.** Marshall Description is absent on 1,201 course
   entities (report `fill`), but no record says which rule failed (B1 item 2).
9. Stray `catalog-wvu-edu/2026-10-20T13-19-46Z/discovery/.DS_Store` in Azure.
