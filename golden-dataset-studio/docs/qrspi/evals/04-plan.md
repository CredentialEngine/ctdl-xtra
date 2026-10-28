# P — Plan: Evals

Builds [`03-spec.md`](03-spec.md) (read §1, §4, §6 and the mockups first). One step per commit; `make check` passes
after each. Nothing is pushed. Local data only: never write to the shared Azure containers while developing.

## Data layout

```
xtra-golden-sets/                                       (golden root; local dev: .data/golden)
├── <catalog>/<crawl>/<stem>/<stem>.json                latest golden dataset, replaced per page, never merged
└── catalogs/<catalog>/versions/ruleset-vN/<catalog>/<crawl>/<stem>/<stem>.json

<studio root>/<catalog>/<crawl>/golden-dataset-studio/
├── golden/ruleset-vN/{publication.json, lineage.parquet, golden.parquet}
├── scores/sc-NNNN/{score.json, values.parquet}         score.json: status running|done|failed|interrupted
├── scores/pending.json                                 {due_at, reason}: a score due 5 min after the last review
└── extract-outputs/<report-last-modified>/{records/, extract-report.json}
```

Annotation events gain two optional fields: `author_role` (`sme` | `engineer`) and `compared_with` (§4.2). An event
without `author_role` takes its author's role from `profiles.json`.

## API (new or changed)

| Route | Does |
|---|---|
| `GET /api/catalogs/{c}/golden` | versions: columns, values, human-reviewed count, latest score, where written |
| `POST /api/catalogs/{c}/rules/{rule}/approve` | existing approve; now also publishes the column and queues a score |
| `GET /api/catalogs/{c}/extract-outputs` | outputs seen (copies), newest first, with their scores per golden dataset |
| `POST /api/catalogs/{c}/scores` | `{golden: "ruleset-v3" \| "human-reviewed" \| "rs-0007", output}` → `sc-NNNN` (running) |
| `GET /api/catalogs/{c}/scores/{id}` | status, both results, provenance |
| `GET /api/catalogs/{c}/scores/{id}/values` | rows: column, course, outcome, similarity, golden/extracted value, location |
| `GET /api/catalogs-summary?basis=human\|rule` | home table: per catalog, per column status and exact-match % |

## Steps

1. **Golden versions and human-reviewed values** (`golden.py`, `review.py`, `log.py`, `routes_review.py`, `cli.py`).
   Publish writes the full dataset into the version folder and replaces the latest location per page; `golden.parquet`.
   An expert's verdict rewrites that one page's file in both places and writes `scores/pending.json`. `author_role` on
   new events; engineer ✓ isn't `approval: human`; engineer ✕ still marks the rule needs work. Backfill AVC as
   ruleset v2 and v3 (`golden-datasets golden backfill`).
2. **Scores** (`evals.py` → `scores.py`, `server/jobs.py`, `server/routes_evals.py`, `cli.py`, `pyproject.toml`).
   xtra-cli as a uv path dependency; a store adapter (`list_keys`, `get_json`, `describe_location`) over the records
   folder and over a golden version / the human-reviewed set; two runs per score; `score.json` + `values.parquet`;
   durable job (interrupted on start); the pending-score loop (every 30 s and on start); copy each new extract output;
   `golden-datasets score`. Remove `xtra run`, `serve --allow-runs`, the extraction job runner, `xtra-runs/`.
   Check against AVC: ruleset v3 vs today's records ≈ 65.3% of 75 human-reviewed (fewer now that engineer checks
   wait) and 59.5% of 4,248 rule-matched.
3. **Annotated by and Confirm** (§6.7, §6.8). Builds on the Sample drawer's existing "Annotated by" stratum and
   "Annotated by me": people grouped by role, "Any engineer · waiting for an expert", rule-list counts, the experts'
   note, Confirm on engineer-checked rows; the same filter on the Records tab (in the URL).
4. **Evals tab** (§6.3–6.5): title with the golden chip/dropdown, history chart, switch, column bars, filter, rows;
   the shared Split/Unified diff with notes (`compared_with`) and the page with both values; the same diff in Compare.
5. **Home catalogs table** (§6.1, §6.2).
6. **Approving publishes** (§6.6): approve confirmation; the Publish tab becomes the read-only Golden datasets tab.
7. **Wrap-up:** `check` rules, tests, tour, spec screenshots.
