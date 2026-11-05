# Answers, pass 5 (Eric, 2026-11-05 16:10 MST)

Answers to a 9-item list in chat (each item restated here).

| # | Question | Decision |
|---|---|---|
| 1 | Claude's sentence about a row: saved as a comment on the row, or only in the report? | **Saved on the row.** |
| 2 | ✕ in the report opens the row in the Rules tab with ✕ already pressed? | **Yes, but in a new browser tab.** Users would be upset to lose the report. |
| 3 | Run again: through the "Run with Claude?" dialog, or start immediately? | **Through the dialog.** A person decides when a run starts. |
| 4 | Two live runs aiming at the same rule | **Refuse it in the second person's picker.** Eric didn't understand the word "goal": don't use it in the UI; say "rules to improve" or similar. |
| 5 | Block a publish over a % of unreviewed values changed? | **No threshold.** The report says how many values changed per rule, as a structured part of the report computed by the CLI (not by Claude), with a link to the Compare tab to see them. |
| 6 | Rollback for engineers? | **For everyone, and call it "Revert".** |
| 7 | Test on the real K2 server | **Yes, test on the server (cap of 2).** Also **make the queue visible**, so it's easy to tell how long you'll wait. |
| 8 | Picker's default ticks (open annotations, or annotations newer than the last run) | **Yes.** |
| 9 | Drop " · " in the Rules tab too? | **No change to the Rules tab.** It was a writing style rule: no `·` in text written for the report, and the prompt should encourage Claude to write simply (may matter less now that the structure is fixed). |

## Verbatim (dictated)

> Okay, number one. Yeah, just save it on the row. Number two. Yeah, I think that's great. Pressing the X and the report. Well, Yeah, I think that works. Just make sure you're opening it up in like a new browser tab or else users are going to be really upset if they lose the report. Okay, run again. Go through run with Claude dialogue. Yeah, you go have people go through the the human needs to decide when the run actually starts. Okay, four two runs with the same goal, refuse the goal in the second person's picker. I don't know what you mean by goal, but if you just mean the same comments, then yeah, just just pick one. Okay, five large chunks to values nobody has reviewed. Should it change to more than five percent of a rules values block? Publish are only shown the report I don't think the threshold of a percent matters. I think you should just say how many things were changed. And that should be a structured piece of the report. Not something that Claude has to calculate. And you could say v you could ha you could make a link to view in the compare tab to see that. Okay, for rollback. Rollback doesn't just have to be for engineers. Call it revert. That's what it would be. Testing on the real K2 server The cap of two only. Yeah, you should test on the server. Also, you should make it so that the queue is visible so that it's easy to tell so that it's easy to tell how long you're gonna have to wait. Okay, eight, the picker's default ticks. Yeah, go for it. Nine dots on the rules tab the only reason I brought that up was as like a writing style guide. So I don't know what you're saying specifically with dropping it on the rules tab, just in general, don't use that in text and make sure the prompt encourages Claude to be simple. Although now that the structure is more finalized, it may not no it may no longer be necessary. Okay, what I need from you where Claude's comment lives saved as a comment on the row. Um okay, what I need from you. Number one, where Cloud's comment lives. Yeah, keep it on the
