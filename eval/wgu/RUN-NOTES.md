# Extraction Runs — Notes

## Method

For each of 5 WGU pages:

1. **Source prep** (`harness/prep-sources.mjs`): saved HTML → `simplifyHtml` (cheerio: strip head/script/style/nav/footer, drop all attrs except `href`, collapse divs) → `turndown` → simplified markdown. This mirrors `ctdl-xtra/server/src/extraction/browser.ts:simplifiedMarkdown` exactly.
2. **Baseline extraction**: apply xTRA's verbatim credential prompt + 4-field schema (from `common/catalogueTypes.ts:431-546`, typos and contradictions preserved) to the simplified markdown.
3. **Enhanced extraction**: apply a ~22-field CTDL-aligned schema with a proper system message, typed nested objects, and enum vocabularies (see `harness/enhanced-schema.mjs`).

Extractions were run via `harness/run.mjs` against the Anthropic API.

## Pages

| slug | URL | source markdown |
|---|---|---:|
| bs-computer-science | https://www.wgu.edu/online-it-degrees/computer-science.html | 44,384 chars |
| mba | https://www.wgu.edu/online-business-degrees/mba-masters-business-administration-program.html | 27,172 chars |
| ms-nursing-education | https://www.wgu.edu/online-nursing-health-degrees/bsn-to-msn-nursing-education-masters-program.html | 37,757 chars |
| bs-accounting | https://www.wgu.edu/online-business-degrees/accounting-bachelors-program.html | 49,862 chars |
| cert-leadership | https://www.wgu.edu/online-business-degrees/certificates/leadership.html | 12,574 chars |

## Model

`claude-opus-4-5` via the Anthropic API (`harness/run.mjs`). xTRA's own default is `gpt-5.4-mini`.

## API-run token/latency (all 3 configs per page)

| slug | baseline-cred | baseline-prog | enhanced | total tok |
|---|---|---|---|---:|
| bs-computer-science | 11117→195, 6.6s | 10670→350, 9.7s | 12532→2024, 35.8s | 36,888 |
| mba | 7878→188, 7.2s | 7431→182, 5.1s | 9293→1471, 28.4s | 26,443 |
| ms-nursing-education | 9870→264, 8.2s | 9423→315, 12.6s | 11285→1786, 33.3s | 32,943 |
| bs-accounting | 12075→165, 7.1s | 11628→288, 9.0s | 13490→2166, 36.5s | 39,812 |
| cert-leadership | 4564→181, 3.1s | 4117→191, 3.4s | 5979→1306, 18.5s | 16,338 |

Baseline `credential_name` values (5/5 stripped of degree type, confirming convention mismatch): `Computer Science`, `Business Administration`, `Nursing Education (BSN to MSN)`, `Accounting`, `Business Leadership`. Enhanced populated 16–20/20 fields per page.

## Outputs

`wgu/<slug>/extracted.json` — `{slug, url, sourceMarkdownChars, baseline:{items:[]}, enhanced:{...}}`
`wgu/<slug>/model-input.md` — the exact markdown fed to the extractor
