# Program pages in the five Studio crawls (research for ceterms:LearningProgram)

Data read: `~/review-ui-v3-data/xtra-cli-output/<catalog>/<crawl>/` (read-only).
Azure could not be checked: `az` refresh token expired (AADSTS700082). This did not matter for pages. In every crawl, the local `pages/*.html` count equals `crawl.json.pages_saved`, so the mirror has every saved page.

| Catalog | Crawl used | Platform | pages_saved (local) |
|---|---|---|---|
| avc-elumenapp-com-catalog-2026-27-welcome | 2026-10-12T20-59-13Z | eLumen | 1467 (1467) |
| ccsf-curricunet-com-catalog | 2026-10-01T16-02-34Z (status **incomplete**, 437 left in frontier, 37 errors) | CurricUNET / CurriQunet META | 521 (521) |
| catalog-marshall-edu | 2026-10-20T13-18-30Z | CourseLeaf | 914 (914) |
| catalog-ualr-edu | 2026-10-18T21-05-00Z (the older 2026-09-27 crawl has only 12 program pages) | Acalog | 4439 (4439) |
| catalog-wvu-edu | 2026-10-20T13-19-46Z | CourseLeaf | 900 (900) |

## How pages are typed (crawl.json / meta.json / discovery)

- **crawl.json** has no page types. It only has `discovered_by_first_path_segment`, for example UALR `{"preview_course_nopop.php": 3133, "preview_program.php": 1111, ...}`. **meta.json** has no page type either: it holds the URL, status, sha256, stem and render info.
- **Page types are in two other places:**
  1. **Studio rulesets**, at `review-ui-index/rulesets/<catalog>/rules.json`. Each one already has a `page_types` entry `{"type":"program","url_regex":...}` and a `label-program-page` rule with label `"Program"`. The vocabulary is `["Course","Program","Credential","LearningOpportunity","Competency"]`. The regexes are in the per-catalog sections below.
  2. **xtra-cli discovery**, at `discovery/<run>/labels.json`. There are two formats:
     - New Studio-rule format: a list of `{label, rule_id, stem, source_url}`. Program counts: Marshall 647 (`label-program-page`), UALR 421, WVU 727.
     - Old `xtra-discovery-1` format: `pages[].labels` and `page_type`. CCSF (2026-10-05) labels 347 `/programs/` pages: 279 `Competency+Credential`, 38 `Competency+LearningOpportunity`, 16 `Credential`, 2 `LearningOpportunity`, 12 none. AVC (2026-10-23) labels its 197 program pages: 136 none, 59 `Course`, 2 `Competency`. So xtra-cli does **not** type AVC program pages as programs.
- WVU counts include duplicates. 900 pages have only 786 distinct URLs, because http/https and trailing-slash variants were saved twice. AVC has 77 duplicate final URLs, mostly department pages (`department,french` vs `department/french`), and none among program pages. Marshall has 7 duplicates, CCSF 5, UALR 0.

## Q1: Program pages per catalog

| Catalog | Program URL pattern | Program pages | Notes |
|---|---|---|---|
| AVC | `/catalog/2026-27/program/<slug>-<term>-<year>` e.g. `.../program/administration-of-justice-aa-fall-2026` | **197** distinct | One page per program. Slug suffixes: 66 `-cert`, 37 `-as`, 21 `-aa`, 18 `-aa-t`, 17 `-certificate-noncredit`, 11 `-certificate`, 10 `-as-t`, 7 `-cert-noncredit`, 1 `-bs`, plus a few others. The slug ends in a version term: 168 `fall-2026`, 22 `fall-2025`, and the rest older. There are also 156 `/department/<x>` pages (78 distinct). |
| CCSF | `/catalog/iq/programs/<area>/<id1>/<id2>` e.g. `.../programs/health-safety/1961/2453` | **335** (both ids unique) | There are about 13 more `/programs/...` index pages (`/programs/<area>`, `/programs/all-by-department`, ...). By title suffix: 158 Certificate of Achievement, 52 AS Degree, 30 Certificate of Accomplishment, 25 AA-T, 20 AA, 19 Certificate of Competency, 12 AS-T, 3 Certificate of Completion. The crawl is incomplete, so some programs may be missing. |
| Marshall | `/{undergraduate,graduate}/programs-az/<college>/<program>/[<emphasis>/]` | **647** under `programs-az` (all labelled Program), about **550** real programs | The rest (about 96) are college and department index pages titled without a ", X" suffix, e.g. "Department of Mathematics and Physics". Titles: 103 Minor, 102 Emphasis (+~45 other "Emphasis (...)"), 45 Accelerated Graduate Degree, 39 B.A., 33 B.S., 32 M.S., 26 Graduate Certificate, 14 M.A., 12 B.B.A., 9 Certificate, ... |
| UALR | `/preview_program.php?catoid=<c>&poid=<p>[&returnto=<n>]` | **1111** pages = **319** distinct (catoid,poid) | catoid 43 = 2026-27 Undergraduate (228), 42 = 2026-27 Graduate (86), 44 = 2025-26 Law (5). The crawl matches the catalog's own program lists: `content.php?catoid=43&navoid=5048` links 227 programs and `catoid=42&navoid=4919` links 86. Every program was saved 3-4 times because of different `returnto` values. Types: 73 Minor, 65 Certificate, 22 Concentration, 13 Track, 12 Emphasis, plus degrees. |
| WVU | `/<level>/<college>/<dept>/<program>/` (no fixed segment). Studio's rule is "page has `table.sc_courselist`" | **617** distinct URLs with `sc_courselist` (727 `Program` labels before de-duplication) | 357 have a degree in the title (e.g. "Music, B.A."), 184 are `/undergraduate/minors/<x>/`, 46 are certificates (`/graduatecertificates/`, `/undergraduatecertificate/`), and 30 are other pages ("Regents Bachelor of Arts", "Social Work", "School of Business"). Some of those are department pages that hold several programs. Campuses: Morgantown, Potomac State, WVU Tech. |

## Q2: What a typical program page prints

The rows below are the requested properties, and each cell quotes the page or says "not printed". On all five sites the language is only the HTML attribute `<html lang="en">`.

### AVC (eLumen): `program/administration-of-justice-aa-fall-2026`, `program/advanced-esl-certificate-noncredit-fall-2026`
| Property | Printed? |
|---|---|
| name | `<h2>` in `#mainContent header`: "Administration of Justice AA"; "Advanced ESL Certificate (Noncredit)" |
| description | `.introtext`: "The requirements for an associate degree in Administration of Justice may be satisfied by completing 12 units of required courses, ... and sufficient elective units to total 60 units." |
| code | **Not printed.** The HTML has the string "CTE TOP Code?" / "Yes", but it sits inside a 15 KB HTML **comment** (the program proposal form), so it is not rendered and carries no value. |
| subject webpage | The page URL only. |
| life cycle | Not printed. The slug carries an effective term (`-fall-2026`, `-fall-2025`). |
| in catalog | The site banner reads "2026-27 Catalog". |
| non-credit | In the name and slug: "(Noncredit)", `-certificate-noncredit-`. 24 such pages. |
| credits | "Administration of Justice AA (Total 18)" counts the major only. The degree total appears only in the description ("total 60 units"). The page never names the unit type. For the noncredit certificate, "Required Courses (Total 180)" is in **hours** but is not labelled. The pathway section also shows "Total Credits 15.0" per term. |

### CCSF (CurricUNET): `programs/health-safety/1961/2453` (Administration of Justice – AS Degree), `programs/communication-languages/1913/2355` (ESL Advanced Low – Certificate of Competency)
| Property | Printed? |
|---|---|
| name | `#content-body h2`: "Administration of Justice – AS Degree". The award is after the en dash. |
| description | "Program Summary": "The Associate Degree in Administration of Justice provides a strong theoretical and practical foundation ..." It is followed by "Learning Outcomes:". |
| code | Not printed. The URL ids (1961/2453) are unique. |
| subject webpage | The page URL. |
| life cycle | Not printed for the program. Each course row has "( Active )" / "( Historical )". The page also prints "Program Requirements Last Revised: Fall 2025". |
| in catalog | Footer: "2026-2027 City College of San Francisco Catalog". |
| non-credit | Implied only: Certificate of Competency/Completion pages use an "HOURS" column and ESLN courses, e.g. "Required HOURS 175.0 ... Total : 700.0". The word "Noncredit" appears on 21 program pages. |
| credits | "Required Units 21.0 ... Choose 9 units from the following Units 9.0 ... Total : 30.0" counts the major only. Course rows can be ranges, e.g. "1.0- 3.0". Completion time: "minimum time for completion ... four semesters". |

### Marshall (CourseLeaf): `graduate/programs-az/business/accountancy-ms/`, `undergraduate/.../child-welfare-certificate`
| Property | Printed? |
|---|---|
| name | `h1.page-title`: "Accountancy, M.S."; "Child Welfare, Certificate"; "Psychology, Minor" |
| description | "Program Description: The Master of Science in Accountancy requires 30 semester hours of study. ..." Minors print only a short paragraph. |
| code | Not printed. "CIP code" appears only in general regulations text, on 3 pages. |
| subject webpage | The page URL. |
| life cycle / non-credit | Not printed. |
| in catalog | "2026-2027 Undergraduate Catalog" in the page chrome. |
| credits | "Total Credit Hours 30"; "Total Credit Hours 18". Bachelor's pages instead say "Minimum of 120 hours to graduate." 434 programs-az pages contain "Total Credit Hours". |

### UALR (Acalog): `preview_program.php?catoid=43&poid=10907` (Accounting, B.B.A.), `...poid=10999` (Middle Eastern Studies Minor)
| Property | Printed? |
|---|---|
| name | `#acalog-page-title`: "Accounting, B.B.A."; "Middle Eastern Studies Minor" |
| description | Varies. The B.B.A. page has none and goes straight to requirements. The minor has prose: "The Middle Eastern Studies minor is an interdisciplinary program ... The minor consists of 18 credit hours ..." |
| code | Not printed. poid is a URL id and is unique within a catoid. Course codes print as "ACCT 20003 - (was 2310)". |
| subject webpage | The page URL. Some pages also have a "Website" link to the department. |
| life cycle / non-credit | Not printed. |
| in catalog | "2026-2027 Undergraduate Catalog [OFFICIAL CATALOG]" |
| credits | "General: (120 total minimum hours, including 45 hours of upper-level ...)", "Core (35 hours)", "Major (79 hours)"; "The minor requires 18 upper level hours". |

### WVU (CourseLeaf): `undergraduate/collegeofappliedhumansciences/schoolofsportssciences/sportldr/`, `graduate/eberlycollegeofartsandsciences/biology/ms/`, `undergraduate/minors/economics/`
| Property | Printed? |
|---|---|
| name | `h1.page-title` is outside `#contentarea`: "Sport Leadership, B.A.", "Biology, M.S.". The minor's h1 is just "Economics", and only the URL and "Minor Code" say it is a minor. |
| description | Overview tab: "Degree Offered Bachelor of Arts Nature of the Program Offered either online or in-person, the undergraduate sport leadership degree program prepares ..." |
| code | **Yes.** "In-Person Major Code: 5542 Online Major Code: 5545"; "M.A. Major Code: 1442"; "Minor Code - U003" |
| subject webpage | The page URL. |
| life cycle / non-credit | Not printed. |
| in catalog | Not on the page. The title is "Biology, M.S. < West Virginia University". |
| credits | "Total Hours 120"; "Total Hours 30"; GEF "Total Hours 31-37" (a range); "Credit Hours: Students are required to complete a minimum of 30 graduate credit hours". The minor prints "Total Hours 15". |

## Q3: Program codes

| Catalog | Printed code? | Unique? |
|---|---|---|
| AVC | No. The TOP code exists only as a "CTE TOP Code? Yes" flag inside an HTML comment. | The URL slug is unique (197/197). |
| CCSF | No. | URL id pairs are unique (335/335). |
| Marshall | No. CIP is mentioned only in regulations prose. | The URL is unique apart from 7 trailing-slash duplicates. Some titles repeat in the undergraduate and graduate catalogs (e.g. "Psychology, Minor" x2, accelerated degrees). |
| UALR | No. | (catoid, poid) is unique (319). Each one appears 3-4 times through `returnto=`. |
| WVU | **Yes: "Major Code: NNNN" and "Minor Code - UNNN".** Major Code appears 237 times on 205 pages (218 distinct values), Minor Code 225 times on 224 pages (155 distinct values). | **Not one code per page.** One page can hold 2-4 codes: modality ("In-Person"/"Online"), or several degrees on one department page. 13 Major Codes appear on 2 pages, e.g. accelerated degrees printed on both the undergraduate and graduate pages (1449 on graduate/.../history/ and undergraduate/.../history/). Most repeated Minor Codes are the http/https duplicate pages, not real collisions. Only about a third of program pages print any code. |

## Q4: Several programs on one page, or one program across pages

- **Several programs per page:**
  - **WVU** department pages have a tab per program. For example, graduate/.../english/ has tabs "MA - English, MA - Professional Writing and Editing, MFA, Doctoral" and 4 Major Codes. Titles can name two awards: "Materials Science and Engineering, M.S.M.S.E., Ph.D.", "Coaching and Teaching Studies, Ph.D., Ed.D.". Some pages list several minors or certificates, e.g. "School of Business" with tabs Programs/Minors/Certificate.
  - **AVC** department pages (78) list programs by name only under "Degrees/Certificates", with no details. Each program also has its own page.
  - **UALR** entity pages (`preview_entity.php`) describe degrees in prose and link to the program pages. A few titles combine awards ("A.E.T./B.S.", "B.S. to M.S.").
  - **CCSF**: one program per page.
- **One program split across pages:**
  - **Marshall**: a degree page links its emphases, and each emphasis has its own page. `accountancy-ms/` prints "Area of Emphasis ... 9 / Total Credit Hours 30", and `accountancy-ms/tax-compliance-and-planning/` (titled "Tax Compliance and Planning, Emphasis") prints only "Select nine hours from the following courses: 9". There are about 150 emphasis pages.
  - **WVU**: same pattern. For example `.../mechanical/msme/` and `.../materialscienceandengineering/` are both parent and child pages.
  - **UALR**: concentrations and tracks are separate poids ("Biology, Ecology & Organismal Concentration, B.S."), each restating the full degree.
  - **All CourseLeaf pages** (Marshall, WVU) put Overview, Requirements and Semester Plan in tabs, and all tabs are in the saved HTML.

## Q5: xtra-cli records for program pages

- In the README, xtra-cli puts program pages in two classes (around lines 507-511 and 744-749):
  - Pages that name an award → `Credential` (`ceterms:Credential`).
  - Pages with requirements and no award (minor, pre-professional, non-credit, "Program (not a degree)"), or that only have a program URL → `LearningOpportunity` (`ceterms:LearningProgram`, `ENTITY_PROGRAM = "LearningProgram"` in `src/implementations/extract_dom.py:112`).
  - Learning outcomes become a separate `Competency` record (`{stem}--{entity}`).
  - So by that rule most degree pages are **Credential**, not LearningProgram.
- **Records that exist today:**
  - Only AVC has a top-level `records/` folder: 1065 records = 1062 `Course` + 3 `Competency`. Two of the Competency records come from program pages, e.g. `records/avc-...-program-alcohol-and-other-drug-studies-aods-ce-50a39ec867.json`, whose `ceasn:name` is "2026-27 Catalog". There are **0** Credential or LearningProgram records. `extract-report.json`: 1134 pages considered, 1065 written, 69 skipped as `multi_course_page`.
  - The other four crawls have no `records/`.
  - The `extractions/<run>/records` folders in all five crawls are Studio rule extractions and are **Course only** (AVC 1075, CCSF 1956, Marshall 6734, UALR 1276, WVU 11242). They come from `label-course-on-program-page` and `label-course-page`.
- The only xtra-cli typing of programs is in CCSF's discovery labels: 295 Credential and 40 LearningOpportunity, nearly all with Competency attached. No records were extracted from those labels.
