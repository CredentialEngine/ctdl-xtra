# Original prompt

Given on 2026-10-07. Reproduced verbatim, apart from line-break characters.

---

<https://catalog.uark.edu/undergraduatecatalog/coursesofinstruction/>

Please start from this page and extract into valid CTDL (credential transparency definition language) objects the courses.

You'll need to involve a web scraper for phase one. That's fine.

Then you'll need to, based on sections of the doc, e.g. based on predictable patterns and locations such as is matchable by regex, locate key fields and extract them.

Some fields may be ambiguous and not discoverable by a rule. For those, use a local ollama-served model or other probabalistic means.

But a KEY THING is for any extracted piece of data, I want you to remember the exact regions of the page (highlighted bars) where that piece of data came from. I want you to build a mini web app that shows the "source documents/pages" on the left, and the "extracted json ld" on the right. If I click on any of the fields in the JSON object,

1. it should scroll me to the location in the source document with highlighted region where that piece of data was taken from

2. AND it should provide the reasoning, e.g. a description of the deterministic rule that matched the location for extraction or a snippet of AI reasoning, citing the CTDL definition and making an argument / providing rationale as to why this snippet of text (or multiple snippets of text) from the source documents satisfies this requirement.

Follow Q.R.S.P.I. for this. Begin by generating a list of questions to expose presuppositions, clarify, and discover facts about the world.
