Goal: curate a golden dataset of CTDL records that will be used to validate the xtra-cli pipeline.

Method: create an interactive data labeling UI that is powered by an "overfit" set of deterministic rules, e.g. regular expressions.

Audience of the UI: subject matter experts who are familiar with CTDL and can make judgement calls about which text on various pages of a course catalog should be extracted as CTDL record fields.

The CTDL has several classes (aka "resource types") for example, `ceterms:Course`, `ceterms:LearningProgram`, `ceterms:Credential`, and so on.

Expand on these...

* our design of the golden dataset
  * we're not going to use the CTDL db as a golden dataset. It drifts over time since new crawls update it.
  * we'll label a dataset for a particular crawl "by hand" (using rules and "apply all" in the UI) and so the crawled pages and the golden extracted answers for the crawl will be correct only for a snapshot in time. (think "point-in-time correctness")
  * ^^^ come up with a more formal definition, maybe Latek, and a concrete example
* our design of the metric: we are going to use "exact match" to calculate things like TP, TN, FP, FN.
* we will evaluate globally (per-record) as well as per-field
* we want to eventually get it into CTDL JSON-LD format, but I'm not sure if the evaluation dataset itself should use JSON-LD. It may be that we just want certain values from those. So there's an open question about how the evaluation datasets should be stored (what format)
* I'd prefer to have ONE UI with ONE underlying data annotation format and ONE way to express rules. And as we generate more rules per institution, we plug them into the full-stack data annotation UI--as opposed to generating a whole new UI and dataset format for each institution.

Version 2:
* I'd like the UI itself to have a chat interface over claude code that generates rules. So we'd be building a "rule generator IDE". The rule generator would be "good" if it generates extraction rules and logic that correctly extract records. It'd be measured against the eval.
