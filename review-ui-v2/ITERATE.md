# Prompt: revise the extraction rules from a review

Paste this to Claude Code at the repo root, together with the review's
`feedback.md` (and the new `report.json` if you have one).

---

You maintain the declarative ruleset for a catalog. It is published in the storage root
at `review-ui-index/rulesets/<catalog_folder>/rules.json`; fetch a draft with
`review-ui-v2 rules pull <catalog_folder> --out draft.json`, edit that, and when it passes
`review-ui-v2 check-rules --rules draft.json` publish it with `review-ui-v2 rules publish draft.json`
(raise its `version`).
Read `review-ui-v2/README.md` ("The CCSF ruleset") and `review-ui/README.md` ("Rule")
for the format (`map`, `page_title` and `repeat` are the CCSF additions), and read the attached
`feedback.md`: it lists every value Jared rejected or said was missed, grouped by
the rule responsible, with the extracted value, the expected value, his reason
chips and notes, and the HTML around the value. It also lists general notes, notes
on rules, and notes on properties.

Revise the ruleset so that every item in `feedback.md` would be extracted
correctly, then:

1. Keep rules **declarative**: selectors, regexes, constants and the listed
   transforms only. Never write Python or JavaScript.
2. Look at real pages in `<run>/pages/` before changing a selector. Scope every
   rule to `#content-body`.
3. Do not break values Jared already accepted. After editing, run
   `review-ui-v2 check-rules --rules <file>` (validates the file and runs each rule's
   `example_input` -> `example_output`), then
   `review-ui-v2 extract --run <run>`. It exits non-zero and lists any accepted value
   that changed; fix those before finishing.
4. When you add or change a rule, give it a clear `description` and a real
   `example_input` / `example_output` taken from a page.
5. Items in the **Flagged for review** section are waiting on subject matter experts;
   they are not rule bugs. Leave their rules alone unless a note says what is wrong.
6. If a note asks for something the rule format cannot express, say so rather than
   approximating it.
7. Bump `version` in the ruleset. Report, per item in the feedback, what you
   changed and which rule now handles it, and the fill rates from the new extract.

Do not commit or push anything.
