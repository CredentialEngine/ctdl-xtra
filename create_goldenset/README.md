# `create_goldenset/` — generate a **new** Course golden set

This folder **creates** a golden set from catalog URLs. It does **not** rebuild NJ 30, v1, v2, or v3.

Ship files in this folder: `record.schema.json`, `CLASSIFICATION.md`, `HUMAN_REVIEW.md`, `FIELD_INVENTORY.csv`.

Run every command from the **xTRA repo root**.

```bash
python3 create_goldenset/run.py --url https://catalog.brookdalecc.edu
```

New packs go under `create_goldenset/out/` unless you set `GOLDEN_SET_HOME` (absolute directory) or pass `--out` with an absolute path.

```text
create_goldenset/out/golden_set_brookdalecc_courses/   NEW
```

If `CHECK.json` inside that new folder has `"ok": true`, the pack is **freeze-perfect and ready for human review**. It is still **not** `human_signed`. Two named humans still have to sign before anyone quotes `--signed-only`.

The generator never writes into `golden_set_v1`, `golden_set_v2`, `golden_set_v3`, `golden_sets`, or `golden_set_courses_30`. Use `--out golden_set_<college>_courses` for a new name.

```text
create_goldenset/     ← this folder (flat: run.py, freeze.py, cli.py, …)
  record.schema.json  ← schema copied into each pack
  CLASSIFICATION.md HUMAN_REVIEW.md FIELD_INVENTORY.csv
  out/                ← default pack home (absolute path from this folder)
```

Not the same as:

| Folder | Role |
|---|---|
| `create_goldenset/` | **This folder.** New pack from URLs |
| `goldenset/capture_nj30.py` | Replay the existing NJ 30 slots |
| `goldenset/capture_v4.py` | Mixed-entity v4 pack |
| `generate_goldenset/` | Older TAMIU fetch → draft for human paste |

---

## 1. What “perfect” means here

A pack is **freeze-perfect** when every `expected` value is a copy of text that exists in the frozen HTML, with matching evidence spans, credit rules, and schema 2.0.0.

This toolkit **cannot** produce official signed gold. Project rules:

- Never invent `expected` with an LLM
- Never write `human_signed`
- Never invent `course_credits_min`/`max` from a single printed `3`
- Never match Credential Registry by course name (exact catalog URL only)
- Unknown CMS families fail closed (no LLM fallback)

Supported catalog families: **Clean Catalog**, **Coursedog**, **Acalog** (Modern Campus). Anything else is dropped.

`CHECK.json.ok == true` means freeze-perfect **candidate**. Humans still open freeze + JSON side by side and sign.

---

## 2. Files in this folder

| File | What it is | What it generates |
|---|---|---|
| `run.py` | One-shot generator | A **new** folder under `create_goldenset/out/` (or `GOLDEN_SET_HOME` / `--out`) |
| `union_fields.py` | Label-union runner (Sept 4 1.c.i) | JSON counts; live crawl or `--from-pack` |
| `check.py` | Re-validate a pack | Rewrites `CHECK.json` (exit 1 on failure) |
| `lib.py` | Shared helpers | Used by the two CLIs; not run by itself |
| `cli.py` | Stepwise engine CLI | `python3 cli.py freeze` / `normalize` / `classify` / … |
| `freeze.py` `normalize.py` `build.py` … | Extract engine (flat in this folder) | Called by `run.py` |
| `config.py` | Pack paths (`GOLDEN_SET_PACK`) | Imported by the engine |
| `record.schema.json` | Schema 2.0.0 | Copied into each pack |
| `CLASSIFICATION.md` | Family/template rules | Nothing until you read it |
| `HUMAN_REVIEW.md` | Two-person review checklist | Nothing until humans sign |
| `FIELD_INVENTORY.csv` | Allowed field labels | Copied into each pack by build |
| `requirements.txt` | Python extras | Nothing until you `pip install` |
| `README.md` | This file | Nothing |

---

## 3. Install (once)

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chrome
```

From a git checkout, the same files are `create_goldenset/requirements.txt`.

| Token | Meaning |
|---|---|
| `python3 -m pip install -r requirements.txt` | Playwright, jsonschema, RapidFuzz (run in this folder) |
| `python3 -m playwright install chrome` | Browser used to open catalog pages |

Optional Registry key (exact `ceterms:subjectWebpage` = catalog URL):

```bash
export REGISTRY_API_KEY='your-key'
```

Without a key, every record is `registry_expected.status = not_checked` (HTTP 401). That is honest, not a match.

Where packs are written:

```bash
# Default pack home: create_goldenset/out/
python3 create_goldenset/run.py --url https://catalog.brookdalecc.edu

# Or set a pack home (absolute directory)
export GOLDEN_SET_HOME=/path/to/packs
python3 create_goldenset/run.py --url https://catalog.brookdalecc.edu

# Or pass an absolute pack path
python3 create_goldenset/run.py --url https://catalog.brookdalecc.edu --out /path/to/packs/golden_set_brookdalecc_courses
```

---

## 4. Generate a new pack — every flag

```bash
python3 create_goldenset/run.py [FLAGS]
```

| Flag | Required? | Default | What it does |
|---|---|---|---|
| `--url URL` | one of `--url` / `--url-file` | none | Catalog **home** or a **course detail** URL. Repeatable. |
| `--url-file PATH` | one of `--url` / `--url-file` | none | Text file, one URL per line. `#` comments and blank lines skipped. Relative paths try cwd, then repo root. |
| `--out DIR` | no | `create_goldenset/out/golden_set_<slug>_courses` (one URL) or `create_goldenset/out/golden_set_courses_mix` (several) | Pack folder. A relative name is created inside `GOLDEN_SET_HOME` if set, otherwise `create_goldenset/out/`. Absolute path is used as-is. |
| `--limit N` | no | none | Cap **total** courses after sampling. |
| `--per-college N` | no | `30` if one catalog URL; `5` if several | Cap per catalog home. |
| `--all` | no | off | Freeze **every** discovered course (can be hundreds). |
| `--institution NAME` | no | parsed from the catalog `<title>` / site name | Force `institution_name`. |
| `--skip-registry` | no | off | Do not POST to Credential Engine. |
| `--allow-errors` | no | off | Exit 0 even when `CHECK.json.ok` is false. Pack is still written for inspection. |
| `-h` / `--help` | no | | Print argparse help. |

If both `--url` and `--url-file` are missing, the script prints help and exits **2**.

A course detail URL (example `https://catalog.brookdalecc.edu/courses/ENGL121`) is frozen as that one page. A catalog home is crawled, then sampled.

---

## 5. Commands to copy

**One college, 30 sampled courses (default):**

```bash
python3 create_goldenset/run.py --url https://catalog.brookdalecc.edu
```

| Token | Meaning |
|---|---|
| `python3` | Interpreter with Playwright |
| `create_goldenset/run.py` | Generator |
| `--url` | Next token is a URL |
| `https://catalog.brookdalecc.edu` | Brookdale Coursedog catalog home |

Writes `create_goldenset/out/golden_set_brookdalecc_courses/` unless `GOLDEN_SET_HOME` or `--out` is set.

**Exact course pages (no harvest):**

```bash
python3 create_goldenset/run.py \
  --url https://catalog.brookdalecc.edu/courses/ENGL121 \
  --url https://catalog.brookdalecc.edu/courses/MATH131 \
  --out golden_set_brookdale_two
```

`--out golden_set_brookdale_two` is a folder **name** under `create_goldenset/out/` (or `$GOLDEN_SET_HOME`). Pass an absolute `--out` to choose the full path.

**URL list file:**

```text
# urls.txt
https://catalog.atlanticcape.edu
https://catalog.brookdalecc.edu
```

```bash
python3 create_goldenset/run.py --url-file urls.txt --per-college 5 --out golden_set_two_colleges
```

**Every course on one catalog:**

```bash
python3 create_goldenset/run.py \
  --url https://catalog.brookdalecc.edu \
  --all \
  --out golden_set_brookdale_all
```

**Skip Registry, name the college:**

```bash
python3 create_goldenset/run.py \
  --url https://catalog.rcbc.edu \
  --skip-registry \
  --institution "Rowan College at Burlington County"
```

**Re-check a pack later:**

```bash
python3 create_goldenset/check.py --pack golden_set_brookdalecc_courses
```

| Token | Meaning |
|---|---|
| `check.py` | Quality + schema + xTRA shape |
| `--pack` | Directory `run.py` wrote |

---

## 6. What the generator writes

Example pack: `create_goldenset/out/golden_set_brookdalecc_courses/` (or `$GOLDEN_SET_HOME/...` / `--out`)

| Path | Written by | What it is |
|---|---|---|
| `CHECK.json` | `run.py` / `check.py` | `"ok": true` only if freeze checks passed |
| `GOLDEN_SET.md` | `run.py` | Short pack notes + scoring command |
| `record.schema.json` | copy of this folder's `record.schema.json` | Schema 2.0.0 |
| `slots.json` | discover | Course URLs in this pack |
| `cache/<yyyy-mm-dd>/<stem>.html` | freeze | Frozen `page.content()` HTML (immutable dated cache) |
| `cache/<yyyy-mm-dd>/<stem>.meta.json` | freeze | Retrieval time, HTTP status, sha256 |
| `snapshots/<stem>.html` | freeze | Legacy freeze path; reused if no dated cache copy exists |
| `normalized/<stem>.txt` | normalize | Visible text (scripts/styles stripped) |
| `records/<id>.json` | extract | Schema 2.0.0 candidate + evidence + CTDL map |
| `courses/<id>.json` | assemble | xTRA scoring golden (`id`, `catalogue_type`, `source_url`, `expected`) |
| `html/` | assemble | Unpacked HTML + markdown |
| `registry/` | registry | Exact-URL search freeze (often 401) |
| `MANIFEST.json` | assemble | Pack index, `status: candidate` |
| `records.csv` | assemble | Spreadsheet index |
| `FIELD_INVENTORY.csv` | build | Allowed field labels |
| `CAPTURE_REPORT.json` | engine | Discovery counts |

Pipeline order: discover → freeze → drop 404 → normalize → detect template → extract printed fields → Registry exact URL → quality + schema → assemble → `CHECK.json`.

Copied only if the freeze prints them: `course_id`, `course_name`, `course_description`, `course_credits` **or** min+max, prerequisites, corequisites, lecture/lab hours, program, department, school, division, subject, number, long title, academic level, general education.

Credits: `Credits 3` / `3 Credit(s)` / Coursedog Min `3` with no Max → `course_credits: 3`. Printed `0` hours are kept.

---

## 7. Line-by-line: `run.py`

| Line | Code | What it does |
|---|---|---|
| 1 | `#!/usr/bin/env python3` | Shebang |
| 2 | `"""Generate a NEW candidate Course golden set..."""` | Docstring |
| 4 | `from __future__ import annotations` | `list[str] \| None` on Python 3.9 |
| 6–8 | `argparse`, `sys`, `Path` | CLI, exit, paths |
| 10 | `_HERE = Path(__file__).absolute().parent` | This folder (`create_goldenset/`) |
| 11–12 | put `_HERE` on `sys.path` | So `import lib` works when you run `python3 create_goldenset/run.py` |
| 14–24 | `from lib import ...` | Helpers including `refuse_protected_pack` |
| 26 | `def collect_urls(...)` | Merge `--url` and `--url-file`, drop duplicates, keep order |
| 27 | `urls = list(args.urls or [])` | Repeatable `--url` (None if omitted) |
| 28–29 | extend from `--url-file` | Optional file |
| 30–36 | de-dupe | Same URL twice is kept once |
| 39 | `def main(...)` | Returns process exit code |
| 40–50 | `ArgumentParser` | Description + example epilog |
| 51–57 | `--url` `append` `dest=urls` `metavar=URL` | Repeatable catalog or course URL |
| 58–62 | `--url-file` | Path to URL list |
| 63–66 | `--out` | Pack folder **name** under `create_goldenset/out/` or `GOLDEN_SET_HOME`, or an absolute path |
| 67 | `--limit` | Total cap |
| 68–73 | `--per-college` | Per catalog-home cap |
| 74–78 | `--all` | No sampling |
| 79 | `--institution` | Override college name |
| 80–84 | `--skip-registry` | No Registry HTTP |
| 85–89 | `--allow-errors` | Do not fail the process on CHECK errors |
| 90 | `parse_args` | `sys.argv` or test `argv=` |
| 91 | `collect_urls` | Final URL list |
| 92–95 | no URLs → help, exit 2 | Usage error |
| 97 | `resolve_pack` | Default folder under `golden_set_home()` (`GOLDEN_SET_HOME` or `create_goldenset/out/`), **before** engine import |
| 100–104 | `refuse_protected_pack` | Exit 2 if `--out` is v1/v2/v3/`golden_sets`/NJ 30 |
| 105 | `configure(pack)` | Set `GOLDEN_SET_*` env so the engine writes here |
| 107 | `from college_capture import run_college_capture` | Import **after** env is set |
| 109–116 | run discover/freeze/extract/assemble | Same engine as scoring packs |
| 117 | `check_pack(pack)` | Freeze + schema + xTRA shape |
| 118 | `write_check` | `CHECK.json` |
| 119 | `write_pack_readme` | `GOLDEN_SET.md` |
| 120 | print JSON summary | stdout, no huge `slots` list |
| 121–125 | CHECK failed → stderr, exit 1 (unless `--allow-errors`) | Fail closed |
| 126 | print CHECK passed | stderr |
| 127 | `return 0` | Success |
| 130–131 | `__main__` | `python3 create_goldenset/run.py` → `main()` exit code |

---

## 8. Line-by-line: `check.py`

| Line | Code | What it does |
|---|---|---|
| 1 | shebang | python3 |
| 2 | docstring | Does not invent expected or sign |
| 4–8 | imports | argparse, Path |
| 10–12 | `_HERE` on `sys.path` | `import lib` |
| 14 | `from lib import ...` | `check_pack`, `configure`, `resolve_existing_pack`, `write_check` |
| 17 | `def main` | Exit-code CLI |
| 18–20 | parser | Description |
| 21–25 | `--pack` **required** | Folder name under `create_goldenset/out/` or `GOLDEN_SET_HOME`, or an absolute path |
| 26 | `parse_args` | |
| 27 | `resolve_existing_pack` | Lookup under `golden_set_home()` (`GOLDEN_SET_HOME` or `create_goldenset/out/`) |
| 28 | `configure(pack)` | Env + copy schema |
| 29 | `check_pack` | Same checks as `run.py` |
| 30 | `write_check` | Overwrite `CHECK.json` |
| 31–35 | errors → FAIL + exit 1 | |
| 36–37 | `PASS` + exit 0 | |
| 40–41 | `__main__` | |

`python3 create_goldenset/check.py` with no `--pack` is argparse’s “required: --pack” (exit 2).

---

## 9. Line-by-line: `lib.py`

| Line | Code | What it does |
|---|---|---|
| 1 | module docstring | Shared helpers |
| 3 | future annotations | |
| 5–11 | stdlib | json, env, regex, copy, path, URLs |
| 13 | `HERE` / `ROOT` | Absolute path of this folder (`Path(__file__).absolute().parent`) |
| 16–22 | `PROTECTED_PACK_NAMES` | Names we will not overwrite |
| 27–38 | `college_slug` | `catalog.brookdalecc.edu` → `brookdalecc`. Local copy so `--out` is chosen **before** engine import |
| 29 | hostname | |
| 30–32 | strip `catalog.` / `www.` / … | |
| 33–36 | strip `.edu` / `.org` | |
| 37–38 | non-alnum → `-` | |
| 41–51 | `configure` | Must run before engine import |
| 43 | `GOLDEN_SET_PACK` | Engine output directory |
| 44 | `GOLDEN_SET_SLOTS=dynamic` | URLs from `slots.json`, not NJ 30 |
| 45 | `GOLDEN_SET_MODE=college` | Skip mixed-pack “must be n=30” gates |
| 46 | `GOLDEN_SET_PILE` | Scoring pile label (pack folder name) |
| 47 | `mkdir` | Create pack |
| 48–49 | copy schema | |
| 50–51 | `sys.path` + this folder | So `import freeze` / `college_capture` work |
| 54–66 | `load_url_file` | Parse URL list |
| 56–59 | relative path fallback to repo root | |
| 61–65 | skip blank/`#`; first token only | `https://... extra` → URL |
| 69–81 | `golden_set_home` | `GOLDEN_SET_HOME` if set, else `create_goldenset/out/` |
| 84–91 | `resolve_pack` | `--out` name → under that home; absolute `--out` unchanged |
| 94–104 | `resolve_existing_pack` | `check.py --pack` lookup |
| 107–113 | `refuse_protected_pack` | Block v1/v2/v3/`golden_sets`/NJ 30 |
| 116–118 | `json_dumps` | Drop `slots` from printed JSON |
| 121–131 | `check_pack` | Set college mode, call `_check_pack_college`, restore env |
| 134–167 | `_check_pack_college` | Never writes `expected`; only validates |
| 135–136 | import engine checkers | `cross_check_pack`, `validate_pack` |
| 139–140 | missing directory | |
| 141–144 | list `records/` + `courses/` | |
| 145–148 | no extracts / count mismatch | |
| 149–164 | each `courses/*.json` | COURSES, `source_url`, id+name, credit rule |
| 165–166 | freeze + schema + evidence spans | |
| 170–180 | `write_check` | `CHECK.json` `{ok, records, errors}` |
| 183–220 | `write_pack_readme` | `GOLDEN_SET.md` in the pack |
| 223–230 | `_display_pack` | Path relative to `golden_set_home()` (or this folder) in the scoring example |

---

## 10. Line-by-line: `requirements.txt`

| Line | Text | What it does |
|---|---|---|
| 1 | comment | Python 3.9+; pip install from this folder, then Playwright Chrome |
| 2 | `playwright>=1.40` | Browser freeze. Then `python3 -m playwright install chrome` |
| 3 | `jsonschema>=4.0` | Schema validate |
| 4 | `rapidfuzz>=3.0` | Text scoring (used by `goldenset/score.py`) |

---

## 11. Score a generated pack (candidate only)

```bash
python3 goldenset/score.py score \
  --golden create_goldenset/out/golden_set_brookdalecc_courses \
  --candidate /path/to/extractor/dumps \
  --pile golden_set_brookdalecc_courses
```

`--pile` defaults to the pack folder name. Do **not** pass `--signed-only`.

---

## 12. Failures you should expect

| Symptom | Cause | What to do |
|---|---|---|
| Need `--url` or `--url-file` (exit 2) | No seeds | Pass a catalog or course URL |
| `no course URLs discovered` | Unknown CMS or empty listing | Confirm the URL in a browser; only Clean Catalog / Coursedog / Acalog |
| `drop unknown template` | Detail page layout not in the extractors | Leave it out; do not LLM-fill |
| `drop 404` | Dead course route | Discovery oversamples; another course may fill |
| Playwright missing | Not installed | See [§3](#3-install-once) |
| Registry `not_checked` 401 | No API key | Expected; set `REGISTRY_API_KEY` to retry |
| `CHECK.json.ok: false` | Freeze/schema/credit rule failed | Read `errors`; fix extractors or drop the page. Do not hand-edit `expected` from an LLM |
| `refusing to overwrite ... golden_set_v1` (exit 2) | `--out` named an existing pack | Use a new folder name. Never overwrite v1/v2/v3/`golden_sets`/NJ 30 |
| Want NJ 30 rebuilt | Wrong folder | `python3 goldenset/capture_nj30.py freeze` … `assemble` |
