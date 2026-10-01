# WGU test data — one directory per credential

Each `<slug>/` contains everything for that credential, named by role in the pipeline:

| File | What it is | Where it came from |
|---|---|---|
| `page.html` | Raw wgu.edu program page | `curl` on the live URL |
| `page-annotated.md` | Readable markdown of the page + a hand-annotated "CTDL-relevant content on this page" section listing every fact that maps to a CTDL field | Manual annotation — this is the **on-page ground truth** for scoring |
| `model-input.md` | The page after xTRA's `simplifyHtml`→`turndown` — the exact text the LLM sees | `harness/simplify.mjs` on `page.html` |
| `registry.json` | WGU's own hand-published CTDL JSON-LD record | `GET credentialengineregistry.org/resources/<ctid>` — the **Registry ground truth** |
| `registry-summary.md` | Flattened list of every populated `ceterms:*` property in `registry.json` | Derived from the JSON for readability |
| `extracted.json` | What the harness extracted: `{baseline, enhanced, results, _meta}` | `harness/run.mjs` on `model-input.md` |

`cert-leadership/` has `registry-proxy-aws-devops.*` instead of `registry.*` — the Leadership Certificate isn't in the Registry, so a different WGU cert (AWS Cloud DevOps OpenBadge) is included as a shape reference; scoring for that page is on-page-only.

`INDEX.md` — the CTID/URL mapping table + Registry field-population matrix. `RUN-NOTES.md` — model, cost, latency.
