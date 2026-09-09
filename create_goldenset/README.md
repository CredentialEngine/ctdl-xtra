# Create a Course golden set

One folder. Unzip it, `cd` into it, run `run.py`.

This is not the live xTRA crawler. It freezes catalog HTML and copies printed course fields into a candidate pack.

## Install (once)

```bash
cd create_goldenset
python3 -m pip install -r requirements.txt
python3 -m playwright install chrome
```

Python 3.9+. Chrome is required to freeze pages.

## Generate

```bash
python3 run.py --url https://catalog.brookdalecc.edu
```

```bash
python3 run.py \
  --url https://catalog.brookdalecc.edu/courses/ENGL121 \
  --url https://catalog.brookdalecc.edu/courses/MATH131 \
  --out my_two_courses
```

```bash
python3 check.py --pack my_two_courses
```

Where packs land:

- `C:\Code\golden_set\` if that folder exists
- otherwise `./handoff/` inside this folder
- or `GOLDEN_SET_HOME` / `--out`

`CHECK.json` with `"ok": true` means freeze-perfect **candidate**. Two named humans still sign before `--signed-only`.

## Flags

| Flag | Meaning |
|------|---------|
| `--url` | Catalog home or course detail URL (repeatable) |
| `--url-file` | One URL per line |
| `--out` | Pack name or absolute path |
| `--per-college N` | Cap per catalog |
| `--limit N` | Total cap |
| `--all` | Every discovered course |
| `--institution NAME` | Override college name |
| `--skip-registry` | No Credential Engine HTTP |
| `--allow-errors` | Write pack even if CHECK fails |

Supported catalogs: Clean Catalog, Coursedog, Acalog. Unknown CMS pages are dropped. No LLM fill.

Proof is `snapshots/{stem}.html` (`proof_html`). `catalog_edition` is omitted when the page does not print one.
