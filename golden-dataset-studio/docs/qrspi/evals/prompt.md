# Original prompts

Given on 2026-10-27, in one conversation. Reproduced verbatim, apart from line-break characters.

---

**1.** This is the process for running the evaluation (pasted):

```
az login

export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string -n ceteststorage --query connectionString -o tsv)"

xtra environment set test --data-uri azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output

xtra environment set test --baseline-uri azure://https://ceteststorage.blob.core.windows.net/xtra-golden-sets

xtra score extraction match --exactly --catalog-id "avc-elumenapp-com-catalog-2026-27-welcome" --run-id "2026-10-12T20-59-13Z"

xtra score extraction match --partially --catalog-id "avc-elumenapp-com-catalog-2026-27-welcome" --run-id "2026-10-12T20-59-13Z"
```

help me design a workflow that combines the golden rules studio loop with the xtra extraction loop which then
actually calculates an eval. And we'll think of how we might show this in the UI. Because think of this: some
considerations -->

- add an evals UI into the annotation thing
- show a diff from the golden dataset against xtra cli output
- point the diff process to the xtra cli output and the non verified golden datasets subfolders
- allow to view a diff from various versions of the golden dataset and various versions of xtra cli output

**2.** Help me plan an "Evals" tab. In that tab I want to be able trigger xtra extractions and eval comparisons. I'd
like to show some data visualizations that allow us to see how the eval performed, I'd also like the ability to drill
down to various segments of rows so we can explore which segments don't agree with the golden dataset.

**3.** btw this is relevant (pasted):

```
az login

xtra score extraction match --exactly \
--source-uri "azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output" \
--baseline-uri "azure://https://ceteststorage.blob.core.windows.net/xtra-golden-sets" \
--source-azure-storage-connection-string "$(az storage account show-connection-string -n ceteststorage --query connectionString -o tsv)" \
--baseline-azure-storage-connection-string "$(az storage account show-connection-string -n ceteststorage --query connectionString -o tsv)" \
--catalog-id "avc-elumenapp-com-catalog-2026-27-welcome" \
--run-id "2026-10-12T20-59-13Z"

xtra score extraction match --partially \
  (same flags)
```

**4.** also, in the design: it'd be good to show the eval results when the golden ONLY consists of records approved
by hand and ALSO have the ability to see it against the full golden dataset (manual records AND records annotated by
a rule)

**5.** actually, I think we just updated this in another session, it should now be easier to see directly in the
golden dataset what type of annotation it was *(commit `fcacef5`: every golden value carries `approval` human / rule)*

**6.** K, start the QRS process. Give me the questions.
