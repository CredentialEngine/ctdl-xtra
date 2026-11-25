# Feedback, pass 6 (Eric, 2026-11-05 18:53 MST): the first live report

Eric ran an AI run on Subject Webpage on the live Studio (run `20261106T012457Z-b970`). It ended with one decision:
"Should Subject Webpage be empty for every course in this catalog, with the page's address going to In Catalog
instead?" Jared had marked ACCT199 ✕ with the note "use ceterms:inCatalog instead of ceterms:subjectWebpage", but had
marked 13 courses with the same kind of value ✓.

## What was wrong with the report
- **It didn't tell a story.** It never said what the reader is supposed to do. The "If yes … / If no …" lines were at
  the bottom, so the rows above them made no sense. Put what to do, and why, at the top.
- **A yes/no question with no way to answer.** Each answer must be something you can do from the report.
- **Bare course codes** ("AERO199") as labels. Introduce rows in words: "Here is one of them".
- **A list of 12 course codes** as comma-separated text. If each one needs an action, show a table, so it's clear there's
  an action per course.
- **"Eric Riddoch marked it correct, 6:28 PM, after this run"**: other readers won't know the time zone. And Eric had
  no idea he was marking it correct: it must be obvious what a click does.
- The same row card shown twice; "Jared" vs "Jared Diener".
- What Eric needed (from the main session's explanation, but much shorter): the contradiction in one or two sentences, then
  "If the note is right: mark these 13 Not on the page, then run again with Subject Webpage and In Catalog. If not:
  mark ACCT199 correct."

## Verbatim (dictated)

> Okay, this text here that you've added is what's missing in the report that Claude generated. It's totally not obvious what I as the reviewer am supposed to do with this report. Um however the explanation you just gave me was way too verbose. The user needs to Go to the page and do something. It seems like there's Hmm. So you're saying should subject webpage be empty for every course in this catalog with the pages going address instead? Well you so you've asked a yes or no question, but then you didn't give me a way to give a yes or no response. All you you just surfaced these two rows to me. And it's cool that you can surface the two rows. I mean I appreciate that, but I can't respond to you. Like it's really ambiguous what you want me to do. And when you say like arrow one nine nine, I don't know what you're talking about. You need to say something like Here is one of them. Um It looks like the text is now saying Eric Riddock marked it as correct at 6.28 p.m. after this run. First of all, if someone else looks at this, they're not gonna understand my time zone. And secondly, I had no idea I was marking it as correct. Needs to be more obvious what's happening. Um Um at another point you say the other twelve and then you give a list. If you're gonna give a list you need to give some kind of table so that I understand that there's I have to there's an action I need to take for each of these twelve. Okay, down at the bottom you're saying if yes, mark the 13 courses as blah blah blah. If no, then do this. Um that you should have put that at the top, because I had no idea why you were showing me these rows, like what you wanted me to do with them. It just the way this le this report was presented, it just didn't tell a story. So undo these actions that I took where it says I marked things as correct and update the prompt and update stuff and then rerun this and let's see a new AI report that looks better. But this is definitely getting closer. Um Repeat my experiment here And when you're making these changes, deploy it to the live version. Also, new changes, I believe, have been pushed and deployed from the Golden Data Set Studio branch. So also integrate those changes as well
