# Build notes: choices made where the spec is silent or ambiguous

Each entry: what the spec says (or doesn't), what was built, and why. Newest last.

1. **v2 lives in another branch.** `review-ui-v2/` isn't on the `golden-dataset-studio` branch (it's on
   `review-ui-v2-vscode-79248126`). So the Studio doesn't import it: `src/golden_datasets/v2engine.py` is a vendored,
   unmodified copy of `review-ui-v2/server/review_ui/engine.py` (plus `ROOT_ID` from `runs.py`). It is used only by
   the equivalence test that checks the Studio's engine against v2 on real pages. v2 itself is untouched.
