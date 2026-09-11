# Page classification (Sept 4 item 1.b.i)

How `xtra-cli` classifies a cached course page. There is no LLM. Unknown layouts are dropped.

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
python3 xtra-cli/xtra_cli.py catalog crawl --url https://catalog.brookdalecc.edu --limit 5 --pack my_pack
python3 xtra-cli/xtra_cli.py page download --pack my_pack --normalize
python3 xtra-cli/xtra_cli.py page classify --pack my_pack
```

`XTRA_PACK` and `XTRA_SLOTS=dynamic` must point at the pack (`pipeline run` sets these).
