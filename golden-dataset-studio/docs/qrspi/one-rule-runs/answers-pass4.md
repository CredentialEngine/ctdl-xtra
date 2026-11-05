# Answers, pass 4 (Eric, 2026-11-05 15:45 MST): checking and correcting Claude's work from the report

About `screens/2-report-transaction.png` (Credit Value goal, Credit Unit Type also changed, row cards in the report).

## Decisions
- **Keep:** showing courses as Rules tab rows in the report ("I love the way you're showing the vocab now"), and
  **Claude's comments in conversation with the reviewers' comments** on a row ("absolutely brilliant"). The comment
  button on a report row, which appends a comment to that row, is wonderful. Confirm the workflow (Claude Code + CLI)
  can really produce this.
- **Problem: a reviewer can't verify a row without seeing the page.** The report makes ✓ and ✕ easy, but checking
  needs the page beside the value. Find a quick way to see where the value is on the page: a page view, or a quick
  way to open that row (with its page) in another tab, consistent with today's "Open in Records →" / "Open in Rules"
  buttons.
- **Claude's comment must not tell people to press ✓ or ✕** ("Press ✓ to save it" is out of scope for Claude).
  Instead, add a very compact note in parentheses of **when** Claude said it: the ruleset and the AI run.
- **Correcting needs the full Rules tab.** ✕ with the right answer (selecting text on the page) isn't possible in the
  report. Send the reviewer to that row in the Rules tab for that property (a new tab) to annotate it there. Don't
  re-implement annotating in the side panel; link out cleverly while keeping what the panel shows.
- **Rerun with the latest feedback**: after rejecting things, starting a new run that uses the new verdicts and comments
  must be easy.
- **Known issue to investigate:** rows opened in another tab can't update the report panel by themselves. Work out the
  whole experience.

## Verbatim (dictated)

> Okay, this is actually awesome. I love the way that you're showing the vocab now. Like if this is something Claude Code can actually like if this is something this workflow can actually support, it's gonna be really helpful. Um I think one thing that you need here now to be consistent is you know how we normally have that open and records button or open and rules button? Um I think I want you to Well so Jared and others they're gonna want to be able to approve or deny or like like mark approve or reject what you're showing here. The issue is The issue is um they can't check your work without actually looking at the page. That's a problem. So So maybe we need a way to see the browser view, or maybe we need a quick way to like navigate to that row in another tab so they can check and see what's going on. Cause Like you've made it really easy for them to accept and reject your changes for the manually annotated rows, but you haven't um You haven't made it easy for like they can see which rows you're talking about, they just can't verify it easily because they can't see the page on the side. I love this idea of ha showing clawed comments in conversation with the rules. I think that's absolutely brilliant. Don't click on don't mention pressing like accept or reject to save it. I think that's a bad idea. I think that's like stuff that's out of scope for what you should be saying in the cloud comment here, but the fact that you're doing I think you should in parentheses mention something about when Claude made this comment, like mention the rule set and the AI run, do that in an extremely compact way. But this should just be to but that would communicate when exactly this was this was done. And I love that you're allowing us to basically add comments because that would allow us to just basically just that would allow us to append a comment to the row as well, which is wonderful. Um, now you can't Obviously, we don't have the full abilities to annotate here, so I think if someone I think if someone wants to include the correct answer when you do the reject button, you'd need to take them to that view in a new tab on the rules page for this property so that they could annotate it there. So basically we need a quick way to review where this is on the page and we need a quick way to correct what Claude is doing. But we don't want to completely re-implement those features here in the sidebar is so we need clever ways to link them out to to the regular experience without getting rid of what's on the sidebar. And if they've rejected things here and they want to go again, there needs to be an easy way for them to rerun with the latest feedback on these rows. Now I recognize that if you're opening a new tab, these rows can't necessarily update. Anyway, so go and investigate that kind of experience.
