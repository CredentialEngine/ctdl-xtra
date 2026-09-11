"""Locate exact excerpts in normalized text. Never guess offsets."""

from __future__ import annotations

from normalize import sha256_text


class EvidenceError(ValueError):
    pass


def find_excerpt(normalized: str, excerpt: str, occurrence: int | None = None) -> tuple[int, int]:
    if not excerpt:
        raise EvidenceError("empty excerpt")
    starts: list[int] = []
    pos = 0
    while True:
        i = normalized.find(excerpt, pos)
        if i < 0:
            break
        starts.append(i)
        pos = i + 1
    if not starts:
        raise EvidenceError(f"excerpt not found: {excerpt[:80]!r}")
    if len(starts) > 1 and occurrence is None:
        raise EvidenceError(
            f"excerpt occurs {len(starts)} times; set occurrence: {excerpt[:80]!r}"
        )
    idx = 0 if occurrence is None else occurrence - 1
    if idx < 0 or idx >= len(starts):
        raise EvidenceError(f"occurrence {occurrence} out of range for {excerpt[:80]!r}")
    start = starts[idx]
    return start, start + len(excerpt)


def hydrate_evidence(
    *,
    evidence_id: str,
    excerpt: str,
    snapshot_sha256: str,
    normalized_text_sha256: str,
    locator_strategy: str,
    locator_value: str,
    occurrence: int | None,
    normalized: str,
) -> dict:
    start, end = find_excerpt(normalized, excerpt, occurrence)
    slice_ = normalized[start:end]
    if slice_ != excerpt:
        raise EvidenceError("slice/excerpt mismatch after locate")
    return {
        "evidence_id": evidence_id,
        "snapshot_sha256": snapshot_sha256,
        "normalized_text_sha256": normalized_text_sha256,
        "locator": {
            "strategy": locator_strategy,
            "value": locator_value,
            "occurrence": occurrence,
            "page_number": None,
            "bbox": None,
        },
        "occurrence": occurrence,
        "char_start": start,
        "char_end": end,
        "excerpt": excerpt,
        "excerpt_sha256": sha256_text(excerpt),
    }
