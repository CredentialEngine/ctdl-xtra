"""Pick the pages a golden set has to contain.

Two jobs, in order. First cover every special case at least once, because a
case that never appears in the sample is a case nobody checks. Then fill the
rest in proportion to how common each shape is, so the sample still looks
like the catalog. The same pages and the same code always give the same
sample: every choice is broken by the SHA-256 of the URL.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from implementations.discover_page import PageProfile
from implementations.discover_patterns import CATALOG_YEAR, Vocabulary

FEATURE_LABEL = "label:"
FEATURE_MARKER = "marker:"
EMPTY_OR_ERROR = "empty_or_error_page"


def order_key(url: str) -> str:
    """Stable, arbitrary order, so ties never depend on crawl order."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def features_of(profile: PageProfile, vocabulary: Vocabulary) -> set[str]:
    """What a page would demonstrate to whoever reviews it.

    The catalog year is left out: it says when the page is from, not what
    shape it has, and every page of one catalog carries the same one.
    """
    labels = {
        f"{FEATURE_LABEL}{label}"
        for label in set(profile.field_labels) & vocabulary.signature_labels
    }
    markers = {
        f"{FEATURE_MARKER}{marker}"
        for marker in profile.markers
        if marker != CATALOG_YEAR
    }
    return labels | markers


def population_for(
    profiles: list[PageProfile], label: str
) -> list[PageProfile]:
    """Pages worth sampling: the right label, not a copy, not empty.

    A duplicate adds nothing a reviewer has not already seen, and an empty
    or error page has nothing to extract.
    """
    return [
        profile
        for profile in profiles
        if label in profile.labels
        and profile.duplicate_of is None
        and EMPTY_OR_ERROR not in profile.markers
    ]


@dataclass
class SamplePage:
    url: str
    stem: str
    pattern_id: str
    reason: str
    features_covered: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "stem": self.stem,
            "pattern_id": self.pattern_id,
            "reason": self.reason,
            "features_covered": self.features_covered,
        }


@dataclass
class GoldenSample:
    label: str
    requested_size: int
    population_size: int
    feature_count: int
    features_covered_count: int
    patterns_total: int
    patterns_in_sample: int
    pages: list[SamplePage] = field(default_factory=list)
    coverage_forced_extra: list[str] = field(default_factory=list)
    population_smaller_than_requested: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "requested_size": self.requested_size,
            "population_size": self.population_size,
            "feature_count": self.feature_count,
            "features_covered_count": self.features_covered_count,
            "patterns_total": self.patterns_total,
            "patterns_in_sample": self.patterns_in_sample,
            "coverage_forced_extra": self.coverage_forced_extra,
            "population_smaller_than_requested": (
                self.population_smaller_than_requested
            ),
            "pages": [page.as_dict() for page in self.pages],
        }


def largest_remainder(
    counts: dict[str, int], seats: int, total: int
) -> dict[str, int]:
    """Share `seats` out in proportion to `counts`, without losing one."""
    if seats <= 0 or total <= 0:
        return {key: 0 for key in counts}
    exact = {key: seats * value / total for key, value in counts.items()}
    quota = {key: int(value) for key, value in exact.items()}
    left = seats - sum(quota.values())
    order = sorted(counts, key=lambda key: (-(exact[key] - quota[key]), key))
    for key in order[:left]:
        quota[key] += 1
    return quota


def _cover_every_feature(
    population: list[PageProfile],
    vocabulary: Vocabulary,
) -> tuple[list[SamplePage], set[str], set[str]]:
    """Greedily take the page that adds the most that is still uncovered.

    A feature only one page has is worth more than one a hundred pages
    share, so each is weighted by how rare it is in the population.
    """
    page_features = {
        profile.stem: features_of(profile, vocabulary) for profile in population
    }
    appearances: Counter = Counter()
    for features in page_features.values():
        appearances.update(features)
    every_feature = set(appearances)
    weights = {name: 1 / appearances[name] for name in every_feature}

    uncovered = set(every_feature)
    ordered = sorted(population, key=lambda profile: order_key(profile.url))
    chosen: list[SamplePage] = []
    taken: set[str] = set()

    while uncovered:
        best: PageProfile | None = None
        best_gain: set[str] = set()
        best_score = 0.0
        for profile in ordered:
            if profile.stem in taken:
                continue
            gain = page_features[profile.stem] & uncovered
            score = sum(weights[name] for name in gain)
            if score > best_score:
                best, best_gain, best_score = profile, gain, score
        if best is None:
            break
        taken.add(best.stem)
        uncovered -= best_gain
        chosen.append(
            SamplePage(
                url=best.url,
                stem=best.stem,
                pattern_id=best.pattern_id,
                reason="covers " + ", ".join(sorted(best_gain)),
                features_covered=sorted(best_gain),
            )
        )
    return chosen, every_feature, uncovered


def _fill_proportionally(
    population: list[PageProfile],
    chosen: list[SamplePage],
    taken: set[str],
    seats: int,
) -> list[SamplePage]:
    """Top the sample up so it still looks like the catalog it came from."""
    by_pattern: dict[str, list[PageProfile]] = {}
    for profile in sorted(population, key=lambda item: order_key(item.url)):
        by_pattern.setdefault(profile.pattern_id, []).append(profile)
    counts = {
        pattern_id: len(members) for pattern_id, members in by_pattern.items()
    }
    quota = largest_remainder(counts, seats, len(population))

    added: list[SamplePage] = []
    for pattern_id in sorted(quota, key=lambda key: (-quota[key], key)):
        room = quota[pattern_id]
        for profile in by_pattern[pattern_id]:
            if room <= 0:
                break
            if profile.stem in taken:
                continue
            taken.add(profile.stem)
            room -= 1
            added.append(
                SamplePage(
                    url=profile.url,
                    stem=profile.stem,
                    pattern_id=profile.pattern_id,
                    reason=f"proportional share of pattern {profile.pattern_id}",
                )
            )

    # A pattern can run out of unused pages, so make the shortfall up from
    # whatever is left rather than returning a short sample.
    short = seats - len(added)
    if short > 0:
        for profile in sorted(population, key=lambda item: order_key(item.url)):
            if short <= 0:
                break
            if profile.stem in taken:
                continue
            taken.add(profile.stem)
            short -= 1
            added.append(
                SamplePage(
                    url=profile.url,
                    stem=profile.stem,
                    pattern_id=profile.pattern_id,
                    reason=f"fills the sample from pattern {profile.pattern_id}",
                )
            )
    return added


def choose_sample(
    profiles: list[PageProfile],
    vocabulary: Vocabulary,
    *,
    label: str,
    size: int,
    patterns_total: int,
) -> GoldenSample:
    """Coverage first, then representation. Deterministic either way."""
    population = population_for(profiles, label)
    chosen, every_feature, uncovered = _cover_every_feature(
        population, vocabulary
    )
    taken = {page.stem for page in chosen}

    sample = GoldenSample(
        label=label,
        requested_size=size,
        population_size=len(population),
        feature_count=len(every_feature),
        features_covered_count=len(every_feature) - len(uncovered),
        patterns_total=patterns_total,
        patterns_in_sample=0,
        population_smaller_than_requested=len(population) < size,
    )

    if len(chosen) > size:
        sample.coverage_forced_extra = sorted(
            {name for page in chosen[size:] for name in page.features_covered}
        )
    else:
        chosen.extend(
            _fill_proportionally(population, chosen, taken, size - len(chosen))
        )

    sample.pages = chosen
    sample.patterns_in_sample = len({page.pattern_id for page in chosen})
    return sample
