# Review feedback: ccsf-curricunet-com-catalog

- review `2026-10-26T20-11-21Z` of extraction `2026-10-19T17-18-22Z` (ruleset `ccsf-curricunet-com-catalog` v2)
- 657 accepted, 1 rejected, 0 missed, 307 not yet reviewed of 965 items
- 7 page(s) and 1 item(s) flagged for an expert (not rule bugs; see below)
- the loop ends when every item is accepted

## Flagged for review (waiting on subject matter experts)

The reviewer could not judge these. Do not change rules for them unless a
note says what is wrong; they are still undecided.

### Directing – Certificate of Achievement

- page: https://ccsf.curricunet.com/catalog/iq/programs/arts-media-entertainment/1841/2214
- **whole page flagged** by Jared

### E-Business Entrepreneurial Apps and Tools – Certificate of Achievement

- page: https://ccsf.curricunet.com/catalog/iq/programs/business-management-entrepreneurship/1889/2309
- **whole page flagged** by Jared

### ESL Beginning High Oral Communication Skills – Certificate of Competency

- page: https://ccsf.curricunet.com/catalog/iq/programs/communication-languages/1917/2363
- **whole page flagged** by Jared
- **Learning Opportunity Name** (property · record ESLN5350) flagged by Seth: Is 'Beginning High' part of the official course name, or a level? Ask the ESL dept.
  - extracted: `ESL Conversation - Beginning High`

### Health Information Clerk II – Certificate of Achievement

- page: https://ccsf.curricunet.com/catalog/iq/programs/health-safety/1986/2510
- **whole page flagged** by Jared

### Biological Science (Emphasis Health Science) – AS Degree

- page: https://ccsf.curricunet.com/catalog/iq/programs/science-technology-engineering-mathematics/2026/2586
- **whole page flagged** by Jared

### Diversity and Social Justice – Certificate of Accomplishment

- page: https://ccsf.curricunet.com/catalog/iq/programs/society-culture-social-justice/2128/2746
- **whole page flagged** by Jared

### Machining Technology Level I – Certificate of Accomplishment

- page: https://ccsf.curricunet.com/catalog/iq/programs/tools-trades/2104/2847
- **whole page flagged** by Jared

## Problems, grouped by rule

### `stub-credit-value`: Credit Value

current: `{'repeat': '.course-entry', 'selector': '.block-entry-units-display', 'regex': '^\\s*(\\d+(?:\\.\\d+)?)\\s*$', 'group': 1}`

- rule note (Seth): stub-credit-value: noncredit rows (subject title ends in '- Noncredit') show contact hours in the units column. Don't take hours as Credit Value.

- **Credit Value** on https://ccsf.curricunet.com/catalog/iq/programs/communication-languages/1917/2363 (record ESLN5184) [rejected: wrong_element]
  - extracted: `87.5`
  - expected: `0.0`
  - note (Seth): 87.5 is HOURS, not units: on noncredit (Certificate of Competency) pages the column header says HOURS. The department page lists ESLN 5184 as (0.0).
  - html: `<span class="units-display block-entry-units-display">87.5</span>`
