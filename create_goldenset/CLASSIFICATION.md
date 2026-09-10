# Page classification (Sept 4 item 1.b.i)

How `create_goldenset` classifies a cached course page. There is no LLM. Unknown layouts are dropped.

## Detection order

1. **Crawl / family** (`detect_family` in `catalog.py`) — CMS family from HTML + URL, used to find course-detail links.
2. **Cache** — freeze HTML (do not classify from the live page after this).
3. **Template** (`detect_template` in `transcribe_courses.py`) — extractor id from **normalized freeze text**.

Family is not the same as template. Family picks a crawler. Template picks an extractor.

## Three families

Order in `detect_family`: **Coursedog, then Acalog, then Clean Catalog.** A Coursedog page that happens to say “clean catalog” must stay Coursedog.

| Family id | Distinctive markers | Typical course URL |
|---|---|---|
| `coursedog` | `coursedog` in HTML or URL; or path `/courses/{CODE}` with two or more slashes | `https://catalog.brookdalecc.edu/courses/ENGL121` |
| `acalog` | `acalog`, `preview_course`, `catoid=`, or `modern campus catalog` in HTML/URL | `preview_course_nopop.php?catoid=&coid=` |
| `custom_html` (Clean Catalog) | `cleancatalog.com` in HTML or URL. Not the loose phrase “clean catalog”. | `https://catalog.atlanticcape.edu/english/engl101` |
| `unknown` | none of the above | harvest still tries mixed URL regexes; extract will drop if no template matches |

## Where the extractors live

One module per catalog family under `templates/`. Each exposes `FAMILY`,
`detect(text) -> template_id | None`, and `TEMPLATES = {template_id: fn}`.

| Module | Family | Templates |
|---|---|---|
| `templates/clean_catalog.py` | `custom_html` | `clean_catalog_course_detail` |
| `templates/coursedog.py` | `coursedog` | `coursedog_rcbc_course_detail`, `coursedog_mccc_course_detail`, `coursedog_brookdale_course_detail` |
| `templates/acalog.py` | `acalog` | `acalog_bergen_glued_credits`, `acalog_raritan_hours_credits` |
| `templates/_shared.py` | - | helpers only; knows nothing about any layout |

`templates/__init__.py` holds the registry and `detect_template`, which asks
each family in `FAMILIES` order. `transcribe_courses.py` is a thin dispatcher
kept as the import surface.

Adding a family is a one-file change: write `templates/<family>.py` with those
three names and append it to `FAMILIES`. Nothing else in the pipeline changes.

To probe one live page for its family:

```bash
python3 detect_family.py --url https://catalog.brookdalecc.edu/courses/ENGL121
```

## Six template ids

`detect_template` returns the first match. College name is not a signal.

| `template_id` | Signature on normalized freeze text |
|---|---|
| `clean_catalog_course_detail` | `Course Catalog Software by Clean Catalog` **or** a line like `ENGL101:` **and** a line that is exactly `Credits` |
| `coursedog_rcbc_course_detail` | `Course Long Title` **or** `(Credit Hours) Min` |
| `coursedog_mccc_course_detail` | lines `Subject Code` and `Course Number` and `Course Description` |
| `coursedog_brookdale_course_detail` | `Course Description` and (`Credit Hours` or `Credit Hours Min`) |
| `acalog_bergen_glued_credits` | a line matching `{CODE}-{NNN} … {n} Credit(s)` |
| `acalog_raritan_hours_credits` | `(lecture,lab) N Credits` and a NBSP hyphen `\xa0-\xa0` |

RCBC is checked before Brookdale because RCBC pages also contain `Course Description` / credit-hour labels.

## No match

- **Family `unknown`:** crawl may still collect URLs; many will fail later.
- **Template `None`:** `attach_templates` prints `drop unknown template {url}` and drops the slot. `classify` CLI reports `dropped_unknown_template`.
- **Extract:** if `detect_template` is `None` but `slot.template_id` is one of the six ids, extract **warns on stderr** (`detect_template=None` vs `slot.template_id=…`) and uses the slot. If the slot id is not in the six, extract fails closed (no LLM).

## CLI

```bash
python3 cli.py crawl --url https://catalog.brookdalecc.edu --limit 5
python3 cli.py freeze
python3 cli.py normalize
python3 cli.py classify
```

`GOLDEN_SET_PACK` and `GOLDEN_SET_SLOTS=dynamic` must point at the pack (create_goldenset/run.py sets these).
