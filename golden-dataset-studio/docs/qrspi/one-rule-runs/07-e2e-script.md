# The end-to-end video: script

The video ([`screens/e2e.mp4`](screens/e2e.mp4)) records the local Studio on the AVC scratch copy while real Claude
runs work through a K2 v0.46.5 daemon (setup and results: [`08-e2e-results.md`](08-e2e-results.md)). Each step's
number and words show as a subtitle at the bottom of the frame.

1. **Pick a rule to improve.** In the rule list, hover Credit Value and press ✦ Improve. "Run with Claude?" opens
   with Credit Value ticked. Press ✦ Run on 1 rule.
2. **Run on several rules.** Press "Improve rules with AI…" under the rule list. Tick Subject Webpage and In Catalog
   only. Press ✦ Run on 2 rules.
3. **The queue.** Press ✦ Improve on Description: the dialog says two runs are working and this one would wait.
   Start it. The run bar says Description is 1st in line, the sidebar shows a clock beside it, and See the queue
   shows "Working now: 2 of 2 places" and "Waiting".
4. **Read the report.** When a run ends, open its report: the outcome, the facts (rules to improve, also changed,
   the whole-suite check), each rule with its values changed and a Compare link, and the row cards with Claude's
   comment "(vN, AI run …)".
5. **Reject a value Claude got wrong.** Press ✕ on a row Claude said was right. A new browser tab opens.
6. **Check it on the page.** The new tab is the Rules tab, pinned to the run's ruleset, with that row selected, ✕
   pressed and the page beside it. Select the right text and save.
7. **Compare the versions.** Back in the report, press Compare: the two rulesets side by side, rule by rule.
8. **Revert.** In the report, press Revert vN. The dialog says what it will publish. Confirm.
9. **Run again.** The new verdict counts as new feedback: the report says so and offers ✦ Run again, which opens
   the picker with the run's rules ticked.
