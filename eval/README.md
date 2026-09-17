# CTDL xTRA × Claude — Evaluation

Evaluation of `ctdl-xtra`'s Credential extractor against 5 WGU program pages, scored vs on-page content and WGU's published Registry records. Baseline **8.3%** field-level recall; an expanded 22-field schema on the same input reaches **90.5%**.

**Start with [`REPORT.html`](REPORT.html)** (or `REPORT.md`) — results, method, improvement proposal, and eval design in one doc.

## Reproduce

```bash
cd harness && npm install
export ANTHROPIC_API_KEY=sk-ant-...
node run.mjs bs-computer-science ../wgu/bs-computer-science/page.html
# → ../wgu/bs-computer-science/extracted.json  {baseline, enhanced, _meta}
```

## Contents

| | |
|---|---|
| `REPORT.html` / `.md` | The write-up |
| `harness/` | Standalone runner: `run.mjs`, `xtra-prompts.mjs` (verbatim baseline), `enhanced-schema.mjs` (proposed 22-field), `simplify.mjs` |
| `wgu/<slug>/` | One dir per credential: `page.html` · `page-annotated.md` · `model-input.md` · `registry.json` · `extracted.json` — see `wgu/README.md` |
| `scoring/` | 90-cell field matrix + scorecards + multi-extractor coverage |
| `code-review/` | `01-architecture.md`, `02-hypotheses.md` (10 findings, file:line), `00-open-issues.md` |
| `ctdl-reference/field-spec.md` | 30-row CTDL field checklist |
