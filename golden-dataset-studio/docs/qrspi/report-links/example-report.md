# Example: the AVC run report of 2026-11-04 (as written, no links)

The report Claude wrote when it couldn't publish a fix for six AVC rules (ruleset v9 stayed current). Reproduced as
Eric pasted it. Every course code, rule name and "decision needed" below is something a reader would want to click.

---

Claude couldn't finish: Couldn't publish (ruleset v9 stays): the 6 ACCT199 annotations have no expected values; inCatalog draft ready, Credit Value/Subject Webpage changes would break values marked correct
AVC, 6 rules: nothing published
Outcome: I didn't publish, so ruleset v9 (rs-0009) stays current. None of the six ACCT199 annotations has an expected value, so rule try can't count any of them as fixed. The only change it could score anyway was WORSE.

Rule by rule

| Rule | What Jared asked | What rule try gave | Blocker |
|---|---|---|---|
| course-in-catalog | the page URL (…/course/acct199, in his note) | source_url: ACCT199 gets exactly that URL, 1,062 values filled · UNKNOWN (fixed 0, still wrong 1, newly wrong 0) | The URL is only in the note, not saved as an expected value. The draft is ready: drafts/needs-work.json |
| course-subject-webpage | use inCatalog instead of Subject Webpage | not tried | Emptying it would change 13 values marked correct (AERO199, AJ912, AUTO230, CFE114, DFST202, ENGR955, FTV201, GEOG222, IATH105, KINF244, NS922L, PHIL106, PHYS102) |
| course-credit-value | no value; the units go to the Value Profile properties | rule_type: none · WORSE | course-credit-value-credit-unit-type (outside this run) reads Credit Value, so 998 of its values vanish, including ACCT199, which is marked correct there |
| course-entry-condition | ACCT199 marked wrong while empty | not tried | No expected value or note, so nothing to aim at. The text is already in Entry Condition: Description. This is the parent of the Condition Profile, not a text field |
| course-entry-condition-description | ACCT199 marked wrong | not tried | Jared's note is word for word the current value, so it's unclear what's wrong (is it the label "LIMITATION ON ENROLLMENT:"?). CFE104, CFE105 and RADT207, which keep the label, are marked correct |
| course-description | ACCT199: drop the Limitation text, and also "Leave in the description for now" | not tried | The two notes contradict each other. Dropping the text would change AERO199, CFE114 and NS922L, which are marked correct. There's no expected value. BIOL110 and DA107A are open for the same reasons as in earlier runs (no expected value; DA107A conflicts with DA107B) |

Scorecard (in-catalog draft, rule try)
fixed 0 · still wrong 1 (ACCT199 in-catalog) · newly wrong 0 · unchanged 40 · verdict UNKNOWN

Decisions needed

- In Catalog: save https://avc.elumenapp.com/catalog/2026-27/course/acct199 as ACCT199's expected value, or mark the value correct after a draft publish. The next run would then publish the source_url rule as it is.
- Subject Webpage: should every course page lose it, given the whole catalog is "in a catalog"? If so, re-mark the 13 courses above as wrong with no value.
- Credit Value: if it should be empty, Credit Unit Type (and any Min/Max rules) has to read the header itself first. That needs those rules in scope for the same run, or a run before this one.
- Entry Condition / its Description: say what the right values are: is the label dropped, and what goes in the parent field? Save them as expected values.
- Description: pick one of Jared's two ACCT199 notes. If the Limitation text goes, re-mark AERO199, CFE114 and NS922L.
