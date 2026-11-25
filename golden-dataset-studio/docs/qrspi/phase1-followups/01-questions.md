# Q — Questions: Credit Value's single value, a bulk reset of reviews, and picking durations from the page

The QRSPI Q step for three follow-ups to the Phase 1 property rules, asked on 2026-11-05:

- **A.** Row 18 of the Phase 1 Extraction tab: `ceterms:creditValue>schema:value`.
- **B.** A button that resets a catalog's approved values in bulk, for when the right answer turns out to be different.
- **C.** Picking Estimated Duration's correct values from the page.

Notes:

- Original prompt: [`prompt.md`](prompt.md). The tab as read on 2026-11-05:
  [`phase1-extraction-2026-11-05.csv`](phase1-extraction-2026-11-05.csv).
- Branch `golden-dataset-studio-value-reset-duration`, off `origin/golden-dataset-studio` (`a0e93fc`).
- **This QRSPI goes as far as S** (questions, research, spec). No code is changed.
- Code reading so far: [`research/code-reset.md`](research/code-reset.md) and
  [`research/code-duration.md`](research/code-duration.md), with file:line references.
- **Live data** on the shared Azure root (`zz-scratch-review-ui-v3`) was read on 2026-11-05 with
  `golden-datasets sql` and `rule list`, for AVC, CCSF, Marshall, UALR and WVU. The live data changed three defaults:
  A2, A5 and B2.
- Each question has a **default**: what research and the spec work from until you answer.
- **First pass answered 2026-11-05, by voice** (A1–A5, B1–B9, C1, C2, C4, C5). What's left is Part E.
- Record answers under each question as `> **Answer:**`. Notes from Claude are marked **Note (Claude)**.

---

## Part A — Row 18: Credit Value's single value

### What I already looked at

- **The sheet changed in two places, both on Credit Value:**
  - **Row 18 is new:**
    - Profile `ceterms:ValueProfile`, column D "Value", label `ceterms:creditValue>schema:value`.
    - Definition "The value of the property value node."
    - Specification "In CTDL: for single values, use schema:value; for ranges, use schema:minValue and
      schema:maxValue."
    - Single, sample `3`.
  - **Row 17 (Credit Value) lost its sample `3`.** The sample moved down to the new row.
  - The rows below shifted down by one. Nothing else changed.
- **A dry run of `properties sync` against the live sheet** (nothing written):
  - It adds one property: `course-credit-value-value`, path `ceterms:creditValue>schema:value`, parent
    `ceterms:creditValue`, sheet row 18.
  - Credit Value's sample becomes empty.
  - Every later row's `sheet_row` goes up by one. No renames, nothing removed.
  - **The new property's name comes out as plain "Value".** Sync takes column D as the name when no sibling uses
    it (`properties.py`, `from_sheet`).
  - The siblings are "Credit Unit Min Value", "Credit Unit Max Value" and "Credit Unit Type".
- **After `properties apply`, every catalog gets the new property with no rule yet** (`rule_type: none`).
  - Applying publishes one ruleset version per catalog and a new extraction. No values change.
  - The property list goes from 36 to 37 rules (41 to 42 on the sheet, less the five folded Estimated Duration
    children). Tests that count 36 move to 37.
- **The Generate rules prompt** says nothing about a single value against a range today.
  - Its only credit example is a range: Credit Unit Max Value reads Credit Value's `1-4 Credit hours`
    (`prompt.py:542-553`).
- **xtra-cli already reads `schema:value`** as both the minimum and the maximum of a credit
  (`xtra-cli/src/implementations/score_extraction_match.py:124-136`). xtra-cli is out of scope here; this is only a fact.
- **Live data: Jared has already said the parent holds nothing.** He marked Credit Value ✕ on one AVC course and four
  Marshall courses, with the same point each time:
  - AVC ACCT199, `1.0 - 8.0 Units`, 2026-11-04: "There should be no values for this property. ceterms:creditValue
    takes the sub-class Value Profile. This information for Credit Value will be values for the properties associated
    with the Value Profile."
  - Marshall BMS600, BMS605, BMS607 and BMS609 (`7 Credit hours`, `5 …`, `3 …`, `6 …`), 2026-11-05: "Credit hour values use
    the properties for Value profile, which are schema:minValue, schema:maxValue, ceterms:creditUnitType. There should
    be no value for this property."
- **Live data: single credits had nowhere to go, so Jared put them in Max Value.**
  - On the same four Marshall courses, he marked Credit Unit Max Value ✕ with "The correct value is 7." (5, 3, 6).
  - Max Value was empty on those courses: Marshall's Min and Max Value rules only fill ranges (2,008 of 6,692 courses).
  - Row 18 is the answer to this. Those numbers are now Credit Unit Value's.
- **Live data: every catalog's Credit Value rule reads the printed text today**, and none of the five catalogs has
  approved it:

  | Catalog | Credit Value rule | Values found | Status |
  |---|---|---|---|
  | AVC | v2 | 1,062 / 1,062 | needs work (Jared's ✕) |
  | CCSF | v2 | 1,927 / 1,927 | in review |
  | Marshall | v2 | 6,692 / 6,692 | needs work (Jared's ✕) |
  | UALR | v2 | 3,044 / 3,130 | in review |
  | WVU | v2 | 22,023 / 22,023 | in review |

  - In CCSF, Marshall, UALR and WVU, Credit Unit Min Value and Max Value read Credit Value's output as their input
    (`input: rule`, checked with `rule show`). AVC's read the page. If the parent goes to `none`, those four catalogs'
    rules need another input.

### Questions

**A1. What is the new property called?**
"Value" alone reads badly in the rule list, the home table and Evals.
*Default:* **Credit Unit Value**, like its siblings. Ask the sheet's owner to change column D, so sync keeps
producing it. Until then, it's an override in the build.

> **Answer:** The new property is `ceterms:creditValue>schema:value`.
>
> **Note (Claude):** the path is settled. Still open is the **name** the rule list shows: sync gives "Value",
> with "part of Credit Value" underneath. See E1.

**A2. What does Credit Value (the parent) hold now?**
The sheet took its sample away and gave it to the child. Choices:
- (a) The credits **as printed**, as one text: `3.0 Units`, `1-4 Credit hours`. The children read it as their input.
  This is what the Generate rules prompt teaches today.
- (b) No rule (`none`), like the condition parents. Only the children carry values.

*Default:* **(b), as Jared said on five courses.** Credit Value gets no value of its own.
- **Value** is the number when the page prints one number (`7`).
- **Min / Max Value** are filled for a range (`1`, `4`). Value stays empty for a range, as row 18's specification says.
- **Credit Unit Type** carries the words (`Credit hours`).

The children stop reading the parent's output and read the page themselves (`css+regex`, or a `labelled` rule). The
parent's printed text can still be shown under the row as evidence, if that helps the expert.

**Note (Claude):** this reverses what the Generate rules prompt teaches today ("Credit Unit Max Value reads Credit
Value's `1-4 Credit hours`"). The prompt changes with it.

> **Answer:** The parent holds nothing. Schema value, minValue and maxValue are now the options: value for a single
> unit, minValue and maxValue for a range like 1 to 4. On the reversed prompt line: "Credit Unit Max Value reads
> Credit Value's `1-4 Credit hours`" should become Min Value `1` and Max Value `4`.
>
> **Note (Claude):** the dictation said "ceterms:creditMinValue" / "creditMaxValue". That reads as xtra-cli's
> spelling of the same two children, `ceterms:creditValue>schema:minValue` and `>schema:maxValue`, which is how this
> doc takes it. Marshall BMS600's `7 Credit hours` is the example of a single value: Value `7`, Unit Type
> `Credit hours`.

**A3. Who writes the first rules for Credit Unit Value?**
*Default:* `properties apply` adds it with no rule. The Generate rules prompt gets one line on single value
against range, with a real example. Claude writes the rules through **Improve all rules** in each catalog. The
build doesn't hand-write rules.

> **Answer:** As the default: `properties apply` adds it with no rule, the Generate rules prompt gets one line on
> a single value against a range with a real example, and Claude writes the rules through Improve all rules. Claude
> can take its best guess, probably with the Marshall catalog as the example.

**A4. Is Credit Unit Value scored in Evals?**
Credit Unit Min Value and Credit Unit Max Value are "not scored" today, because xtra's extract output doesn't emit
them.
*Default:* the same rule applies. Scored only if xtra's extract output emits `creditValue>value`, with no special
case in the Studio.

> **Answer:** Yes, once xtra's extraction extracts those values.

**A5. What happens to Jared's credit reviews?**
- **Credit Value:** no ✓s exist anywhere, only Jared's five ✕s. Once the parent is `none`, they're simply right.
  Nothing to reset.
- **Credit Unit Max Value, Marshall:** four ✕s say "the correct value is 7". Under row 18 that's Credit Unit Value's
  answer, not Max Value's. Max Value should be empty on those courses.
  - The numbers are in notes, not answers, so nothing reads them as Max Value's answer today.
  - **These four are the first real case for Part B.**
- **AVC ACCT199:** Min Value `1.0`, Max Value `8.0` and Unit Type `Units` are ✓. They stay right: it's a range.

*Default:* reset the four Max Value ✕s on Marshall with Part B's button, once it exists. Until then they stay as
they are, harmless.

> **Answer:** As the default: reset the four Max Value ✕s on Marshall with Part B's button, once it exists.


---

## Part B — Reset a catalog's approved values in bulk

### What I already looked at

- **Every decision is an event in one append-only log per catalog**:
  - The log is `<catalog>/golden-dataset-studio/annotations.jsonl` (`layout.py:29`, `log.py:1-8`).
  - The event types are `verdict`, `comment`, `approve` and `reopen` (`log.py:18`).
  - Readers read the log from a byte offset, so it is never rewritten (`log.py:85-97`, `sync.py:53-65`).
- **"Approved" means two different things in the Studio:**
  - **A rule's approval** (the **Approve rule** button). This is an `approve` event on one rule version.
    - **Reopen** undoes it, one rule at a time, with no confirm (`RuleHead.tsx:84`, `RulesTab.tsx:514-532`).
    - A new rule version drops the approval by itself (`review.py:550-558`).
  - **An expert's verdict on a value:** ✓, or ✕ with the right answer. This is what makes a value
    "human-reviewed" in the home table and the golden dataset (`review.py:41-43`, `476-479`).
    - There is no way to clear these, one at a time or in bulk. Another verdict can only supersede one.
- **When the right answer changes but the rule doesn't, old ✓s keep counting.**
  - They also block the fix. `rule publish` refuses when a value marked correct would change, unless `--force` is
    passed (`loop.py:566-570`).
  - The Generate rules prompt tells Claude never to use `--force` (`prompt.py:341-342`).
  - So after a change of mind, **Improve all rules can't publish the corrected rule** until the old ✓s are gone.
    This is inferred from the code, not seen happening.
- **Golden files don't refresh themselves.** A page's file is rewritten only after a verdict on that page
  (`routes_review.py:733-738`), or by a full `golden publish`. A rescore follows five minutes later
  (`golden.py:614`).
- **Earlier specs:**
  - "Columns only grow" (`docs/qrspi/evals/03-spec.md:13`).
  - "Undoing a verdict takes the value out" (`evals/03-spec.md:236`). No code does this yet.
- **No test exercises `reopen`.**
- **Live data: Marshall's Subject Webpage is the case this button is for.**
  - On 22–23 Oct, Seth marked 56 Subject Webpage values ✓ and Jared 13. The page URL,
    `https://catalog.marshall.edu/graduate/courses-az/bms/`.
  - The rule is **approved**, with **69 values human-reviewed**.
  - On 5 Nov, Jared marked it ✕ on six courses (BMS600 … BMS612): "When a resource is in a clearly defined catalog,
    use the property ceterms:inCatalog instead of ceterms:subjectWebpage for the page URL." The same day he marked
    In Catalog ✕ on four courses, giving that URL as the right value.
  - **The other ~60 ✓s still count, and they will block the fix.** Changing Subject Webpage's rule changes values
    marked correct, so `rule publish` refuses.
- **The same change of mind reaches other catalogs.** Subject Webpage is approved in CCSF (69 reviewed), UALR (14)
  and WVU (84), and needs work in AVC (14). Every one of these sites is a catalog, so Jared's rule would apply to all
  of them. That's an inference; he has only marked Marshall.
- **Most ✓s predate the Phase 1 property list.** Subject Webpage's ✓s in CCSF (65), WVU (84) and Marshall (69) were
  all made on 20–23 Oct, before the sheet's definitions were settled. More changes of mind like this one are likely.

### Questions

**B1. What does "approved" cover?**
- (a) Only the **Approve rule** approvals.
- (b) Only the experts' **✓ on values**.
- (c) Both.

Your example ("we've approved a bunch of examples") reads as the ✓s on values, and those are what block the fix.
*Default:* **(c).** The reset clears the ✓s on values and drops the rule's approval with them.

> **Answer:** (c), both: the rule approvals and the experts' ✓ on values.

**B2. One property at a time, or every property in the catalog?**
"All approved properties … for a catalog" could mean either. The reason given ("the value for *a* property should
be different") is about one property.
*Default:* **one property in one catalog.** The button sits on that property's rule. No catalog-wide button; it
would throw away work on properties whose answer didn't change.

Marshall's Subject Webpage shows the other pull: the same decision likely applies to Subject Webpage in all five
catalogs. Resetting five catalogs means five clicks, one per Rules tab. That's acceptable for five, so no
cross-catalog button by default. Say if you'd want one.

> **Answer:** One property at a time, not every property in the catalog.

**B3. Does the reset also clear ✕ verdicts that carry an answer?**
An answer typed under the old understanding is just as stale as a ✓.
*Default:* **yes**, every human-reviewed value of the property: ✓ and ✕-with-answer. These are kept:
- comments,
- questions ("Unsure, needs an expert"),
- ✕ "missing" marks with no answer,
- notes on the rule.

> **Answer:** Yes.

**B4. How is the reset recorded?**
*Default:* a new event type, `reset`, appended to the log. It targets the rule and carries who reset it, when, why
(a required note), and how many values it cleared.
- Verdicts on that property before the reset stop counting.
- Nothing is deleted or rewritten, so the log stays the audit trail and the offset readers keep working.

> **Answer:** A new `reset` event, as the default.

**B5. What does a reset value look like afterwards?**
*Default:* it goes back to **not reviewed**, with a faint "✓ by Jared, before the reset on 5 Nov" hint on the row.
The expert sees what they said before while re-reviewing. The hint doesn't count anywhere.

> **Answer:** Yes, it goes back to not reviewed.

**B6. What happens to the golden dataset?**
*Default:*
- The property's values on every affected page are republished as rule-approved, or left out (unapproved), at once.
- Evals rescore on the usual five-minute delay.
- The datasets' version note names the reset.

This withdraws values from a published column, against "columns only grow". Say if that rule should stand.

> **Answer:** "I don't understand what 'republished as rule-approved' means, because the whole point of this is to
> reset." Reset values are **left out of the golden dataset** once they're unapproved. Evals rescore as the default
> says.
>
> **Note (Claude):** the golden dataset holds two kinds of value. *Human* values are those an expert reviewed. *Rule*
> values are those of a rule someone approved, taken on trust (`approval: rule`). The reset takes the ✓s away and
> drops the rule's approval, so neither kind is left: the property's values leave the golden dataset until someone
> reviews them again. That is what the default meant; "left out" is the whole of it.

**B7. Who can reset, and how is it confirmed?**
*Default:*
- Anyone signed in can reset.
- A confirm dialog like `ApproveDialog` comes first. It shows the counts ("Reset 42 ✓ and 3 answers on Credit
  Value in AVC") and requires a reason.
- No undo button. The log keeps the old verdicts, so an undo can be added later if it's ever needed.

> **Answer:** Yes, anyone can reset.
>
> **Note (Claude):** the confirm dialog with the counts and a required reason stays, as nothing in the answer
> changes it.

**B8. What is the button called, and where does it go?**
*Default:* **Reset reviews…**, in the rule header next to **Approve rule** / **Reopen**, with one line in the tour's
`approve` step.

> **Answer:** Call it **Reset rule**, next to **Approve rule** and **Reopen**.

**B9. Should the reset unblock the fix?**
*Default:* **yes, by design.** Once the ✓s are reset, `rule publish` no longer refuses, and Improve all rules can
publish the corrected rule without `--force`.

> **Answer:** "I don't know what 'unblock the fix' means."
>
> **Note (Claude), in plain terms:** when Claude improves a rule (Improve all rules), the Studio refuses to publish
> the new rule if it would change a value an expert marked ✓. That guard protects good work. After a change of mind
> it gets in the way. Marshall's Subject Webpage has ~60 ✓s on the URL; a rule that moves the URL to In Catalog
> changes all of them, so publishing is refused. Reset rule clears those ✓s first, and then the improved rule can be
> published. No extra work is needed for this: it follows from the reset. Taken as **yes**.

---

## Part C — Picking Estimated Duration's correct values from the page

### What I already looked at

- **Estimated Duration is one list-of-objects rule** (sme-fixes §5.1):
  - Each item is a Duration Profile with `ceterms:description` and `ceterms:timeRequired`, stored as the page's
    words, with a location for each (`profiles_rule.py:25-31`). An example is
    `{description: "Total Course In-Class (Contact) Hours", timeRequired: "54.0 - 432.0"}`.
  - It is the only property of this kind. Credit Value and the conditions stay flat rules.
  - The code keys off `definition.profile`, so a fix here applies to any later list-of-objects property.
- **What an expert can do today** (`web/src/rules/ProfileItems.tsx`, `RulesTab.tsx:493-505, 679`):
  - mark each found duration ✓ or ✕. A ✕ carries no answer, and the duration is left out of the golden dataset.
  - **+ Add a duration** (or H). While adding, a selection on the page is labelled `description` or
    `timeRequired`, and the duration saves once both are labelled.
- **What they can't do:**
  - **Correct a found duration.** If the rule found the right kind of hours with the wrong number, the only route is
    ✕ on the duration, then add a whole new one, labelling every piece again.
  - **Select on the page outside "add".** The highlight bar is turned off for list rules (`RulesTab.tsx:287`), so a
    selection does nothing.
  - **Undo an added duration** in the row.
  - **Mark the whole row at once.** Keys 1 and 2 don't work on list rules.
  - **Comment from the selection.** sme-fixes §5.3 says the bar has the comment button; it doesn't.
  - **Label exact, minimum or maximum duration.**
    - The 2026-11-05 sheet still lists all three as Include, with samples `6 months` / `3 months` / `9 months` (rows
      39–41).
    - W14 calls them "the overall span", not hours.
    - The prompt says they're "parsed from timeRequired at transformation" (`prompt.py`, `REQUISITE_WORDS`). The
      two contradict each other.
- **Real page text** (from earlier research docs, not re-read today):
  - AVC ACCT199 has four durations: `54.0 - 432.0`, `0.0 - 0.0`, `0.0`, `432.0` hours.
  - CCSF prints `Hours: Lecture - 52.5`.
  - UARK prints `Contact Hours: 120` and `Access to Course: 6 Months`.
- **Live data: Jared hit the gap today.** At 18:32Z on 2026-11-05 he marked AVC ACCT199's Estimated Duration ✕ as a
  whole, with no note and no answer.
  - The rule had found four durations: In-Class `54.0 - 432.0`, Out-of-Class `0.0 - 0.0`, Lecture `0.0`, Lab `432.0`.
  - There's no way in the UI to say which of the four is wrong, or what it should be.
  - **Estimated Duration has no ✓ in any catalog.** Rules exist in AVC, CCSF, UALR and WVU (v3), and Marshall (v1,
    nothing found).
- Screens of today's UI: `docs/qrspi/sme-fixes/screens/03-duration-objects.png` and `04-label-a-new-duration.png`.
- The docs say this was left for later: sme-fixes `01-questions.md:428`, `build-notes-profiles.md:147-152`.

### Questions

**C1. What does "selecting correct values from the page" have to do?**
- (a) **Correct a found duration:** select the right text on the page and set it as one sub-value of one found
  duration, without throwing the duration away.
- (b) **Start a new duration from a selection**, with no need to press **+ Add a duration** first.
- (c) Both.

*Default:* **(c).**

> **Answer:** Mostly (a), correcting a found duration. On (b): "it's fine to press + Add a duration" first, so
> **+ Add a duration stays as the way to start a new one.** A selection on the page with no duration chosen does
> nothing new.

**C2. How does the expert say which duration and which sub-value?**
*Default:*
- Selecting text on the page opens the highlight bar with one button per sub-value: **Description**, **Time
  required**, and so on.
- The selection goes to **the duration selected in the row**. If none is selected, it starts a new duration.
- Correcting a found duration records a ✕ with the corrected object as its answer. The whole object becomes the
  answer, so the golden dataset keeps the corrected duration instead of dropping it.

> **Answer:** Looks good.

**C3. Can experts label exact, minimum and maximum duration?**
*Default:* **yes, as optional sub-values.** The sheet still lists them as Include, and UARK's `Access to Course: 6
Months` is an overall span with no hours. The Generate rules prompt's "parsed from timeRequired at transformation"
line is corrected to match W14.

> **Answer:**

**C4. Can a duration be saved with only some sub-values?**
Today it saves only once every sub-value is labelled.
*Default:* **description plus at least one other sub-value.** Description is the key durations pair on, in scoring
and in the golden dataset.

> **Answer:** Looks good.

**C5. The smaller gaps.** Should these come along?
- an **✕ to remove an added duration**;
- keys **1 / 2 marking every duration in the row** ✓ or ✕;
- the **comment button** on the bar.

*Default:* **yes to all three.**

> **Answer:** Looks good: all three.

---

## Part D — Across all three

**D1. One spec or three?**
*Default:* **one spec** with three parts, built in the order A, C, B. A is small. C makes correcting a value
possible, and B's dialog borrows `ApproveDialog`.

> **Answer:**

---

## Part E — Left open after the first pass (2026-11-05)

The first pass answered A1–A5, B1–B9, C1, C2, C4 and C5 by voice. These are left, each with the default the
research works from.

**E1. The name shown for `ceterms:creditValue>schema:value`.** The rule list shows a property's name with "part of
Credit Value" under it, and no path (property-rules §4.5). Sync makes the name "Value". The siblings are "Credit Unit
Min Value", "Credit Unit Max Value" and "Credit Unit Type".
*Default:* **Credit Unit Value**, written in `properties.csv` by a small override in sync until column D says so.
The path shows in the rule header as `ceterms:creditValue → schema:value`.

> **Answer:** Credit Unit Value.

**E2. C3, not yet answered: exact, minimum and maximum duration.** The sheet lists all three as Include. Should an
expert be able to label them as sub-values of a duration?
*Default:* **yes, as optional sub-values** (C3's default).

> **Answer:** No, not now. Description and Time Required stay the only sub-values; exact, minimum and maximum
> duration are left to transformation.

**E3. D1, not yet answered: one spec, built A, C, B?**
*Default:* yes.

> **Answer:** Yes: one spec, built A, C, B.

**E4. Does Reset rule withdraw the property's column from the golden dataset?** Research (B.2) found that leaving the
values out (B6) needs the column withdrawn, which reverses the Evals spec's "columns only grow".
*Default:* yes, for a reset only.

> **Answer:** Yes. A reset takes the column out of that catalog's golden dataset until the rule is approved again.
> Columns still only grow everywhere else.
