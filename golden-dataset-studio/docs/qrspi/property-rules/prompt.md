# Original prompt

Given on 2026-11-02, in one conversation. Reproduced verbatim, apart from line-break characters.

---

**1.** can you read this spreadsheet:
https://docs.google.com/spreadsheets/d/1zFG1Qzn4NTrvb5KTxucKnz-gPd8H_W0oYYRdh7jT8ro/edit?gid=1596676506#gid=1596676506

*(The sheet is "xTRA: Learning Opportunity BU Template". Its Phase 1 Extraction tab, as read on 2026-11-02, is
saved here as [`phase1-extraction.csv`](phase1-extraction.csv).)*

**2.** Look at the spreadsheet I just gave you Phase 1 extraction tab. Column F, we want to use all of those CLI
extraction labels and implement those into our Golden Dataset Studio. We want the CLI extraction labels to show up as
individual field rules. The required fields should show up at the top, and the rest of the fields should show up below
with preferences towards labels that have been human annotated before. Notice special fields like
"ceterms:creditValue>schema:minValue", Sometimes there are ceterms that are nested and that we can't extract directly
from a web page, so we want to represent them in the example I gave you. You've been using the QRS pattern elsewhere
in this repository. Follow that pattern now and start with the step Q.
