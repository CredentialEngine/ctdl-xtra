# Human Review Checklist

Complete this checklist twice, independently, with two different reviewers. The
second reviewer must inspect the frozen artifact and JSON directly, not merely
approve reviewer 1's notes.

## Before review

- [ ] Record ID matches the explicit 30-ID release manifest.
- [ ] Requested/final URL, retrieval timestamp, media type, and catalog edition
  are correct.
- [ ] Frozen bytes and normalized text match their recorded SHA-256 values.
- [ ] Normalizer/extractor version and exact PDF pages/chunk are recorded.
- [ ] Exact `template_id`/version was confirmed from structure, not only vendor.
- [ ] The rendered source contains no unresolved loading/error/auth page.

## Entity and scope review

- [ ] Target class is semantically correct.
- [ ] Program and credential are not conflated.
- [ ] Page entity inventory is complete within its explicit boundary.
- [ ] Every atomic competency in scope has its own record and preserved order.
- [ ] `annotation_scope.mode=complete`; otherwise block evaluation promotion.
- [ ] Repeated/similar titles and duplicate sections were resolved to the correct
  target.

## Source extraction review

For every `source_expected` field:

- [ ] Canonical label is allowed for the target class.
- [ ] Value is verbatim or uses a declared lossless parse.
- [ ] Evidence excerpt proves the semantic boundary, not just token presence.
- [ ] Character offsets, excerpt, and excerpt hash match normalized text exactly.
- [ ] Punctuation, capitalization, order, lists, ranges, and units are preserved.
- [ ] No value came from the model, legacy script, Registry, or filename alone.
- [ ] No missing field was replaced with a placeholder/default.

Then check the reverse direction:

- [ ] Every relevant fact inside the declared scope is represented, so recall can
  be measured.

## CTDL/CTDL-ASN mapping review

For every `ctdl_expected` property:

- [ ] Property is valid for the mapped class in the pinned schema.
- [ ] Source-field or authorized-publisher references fully support the value.
- [ ] Structured profiles preserve all values and cardinality.
- [ ] Controlled vocabulary URI matches the explicit printed/publisher concept.
- [ ] A single credit was not turned into an invented min/max range.
- [ ] No required publication field was guessed merely to satisfy policy.
- [ ] No identifier, description, framework title, language, status, or owner was
  generated.

## Registry reconciliation review

- [ ] Registry bytes, retrieval time, response hash, environment, and CTID are
  recorded, or the layer is explicitly not applicable/not checked.
- [ ] Match used exact CTID, publisher-controlled identifier, or exact canonical
  subject URL; never name alone.
- [ ] All match candidates and ambiguities are retained.
- [ ] Arrays and nested profiles are complete rather than first-item-only.
- [ ] Differences are recorded; Registry data did not overwrite source truth.

## Link review

- [ ] Predicate is valid for both domain and range.
- [ ] Direction is correct.
- [ ] Subject and object resolve to accepted records/immutable fixtures.
- [ ] Page, publisher, or Registry evidence explicitly supports the assertion.
- [ ] No link was inferred from co-occurrence or similar names.

## Release review

- [ ] Reviewer identity and RFC3339 review time are present.
- [ ] Every correction is in the adjudication history.
- [ ] Both stage and final checklists are complete.
- [ ] Reviewer identities differ from the annotator and from one another.
- [ ] Exact count is 30 and each required target class is represented.
- [ ] Every tested exact template has 5–10 records.
- [ ] Institution/page concentration and near-duplicate reports pass.
- [ ] Shared URL/hash/template/near-duplicate groups stay in one data split.
- [ ] Training authorization/licensing is documented.
- [ ] This release is not both training data and the reported held-out benchmark.

Only after all applicable items pass should the release tooling accept
`verification.status=human_signed`.
