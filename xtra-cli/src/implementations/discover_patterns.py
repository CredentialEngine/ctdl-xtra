"""Which pages are the same shape, and which shapes are unusual.

Five or ten pages cannot show the special cases hiding in a thousand. So
every page is profiled, pages with the same shape are grouped, and the
groups that are small, or carry something the rest do not, are named. Those
are the pages a golden set has to contain.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from implementations.discover_page import PageProfile
from implementations.discover_rules import (
    CHROME_SHARE,
    MARKER_MEANING,
    PATTERN_ID_LENGTH,
    RARE_LABEL_SHARE,
    RARE_MARKER_SHARE,
    RARE_PATTERN_SHARE,
)

CATALOG_YEAR = "catalog_year"
ALWAYS_SPECIAL_MARKERS = ("empty_or_error_page", "archived")


@dataclass(frozen=True)
class Vocabulary:
    """How often each printed label and heading appears across the run."""

    total_pages: int
    label_pages: dict[str, int]
    heading_pages: dict[str, int]
    label_examples: dict[str, tuple[str, str]]
    chrome: frozenset[str]
    single_page: frozenset[str]
    signature_labels: frozenset[str]

    def share(self, label: str) -> float:
        if not self.total_pages:
            return 0.0
        return self.label_pages.get(label, 0) / self.total_pages


def build_vocabulary(profiles: list[PageProfile]) -> Vocabulary:
    """Count the printed vocabulary and decide what a signature may use.

    A label on nearly every page is the site's furniture: a menu heading,
    not a field. A label on exactly one page cannot group anything, but it
    is the first thing a reviewer should look at, so it stays in the report
    and leaves the signature.
    """
    label_pages: Counter = Counter()
    heading_pages: Counter = Counter()
    label_examples: dict[str, tuple[str, str]] = {}
    for profile in profiles:
        for label in set(profile.field_labels):
            label_pages[label] += 1
            label_examples.setdefault(label, (profile.url, profile.stem))
        for heading in set(profile.headings):
            heading_pages[heading] += 1

    total = len(profiles)
    chrome = {
        label
        for label, count in label_pages.items()
        if total and count / total > CHROME_SHARE
    }
    single = {label for label, count in label_pages.items() if count == 1}
    return Vocabulary(
        total_pages=total,
        label_pages=dict(label_pages),
        heading_pages=dict(heading_pages),
        label_examples=label_examples,
        chrome=frozenset(chrome),
        single_page=frozenset(single),
        signature_labels=frozenset(set(label_pages) - chrome - single),
    )


def signature_of(profile: PageProfile, vocabulary: Vocabulary) -> str:
    """What this page is, plus the shape of what it prints.

    Headings never take part: a course title is written as a heading on most
    catalogs, so including them would give every course its own pattern.
    """
    labels = sorted(set(profile.field_labels) & vocabulary.signature_labels)
    markers = sorted(name for name in profile.markers if name != CATALOG_YEAR)
    return "|".join([profile.page_type, ";".join(labels), ";".join(markers)])


def pattern_id_of(signature: str) -> str:
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    return digest[:PATTERN_ID_LENGTH]


@dataclass
class RunStats:
    """Per page type counts, which is the scale rarity is judged against."""

    page_type_pages: Counter = field(default_factory=Counter)
    label_pages_by_type: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    marker_pages_by_type: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    catalog_years: Counter = field(default_factory=Counter)

    def label_share(self, page_type: str, label: str) -> float:
        total = self.page_type_pages.get(page_type, 0)
        if not total:
            return 0.0
        return self.label_pages_by_type[page_type].get(label, 0) / total

    def marker_share(self, page_type: str, marker: str) -> float:
        total = self.page_type_pages.get(page_type, 0)
        if not total:
            return 0.0
        return self.marker_pages_by_type[page_type].get(marker, 0) / total

    def common_catalog_year(self) -> str | None:
        if not self.catalog_years:
            return None
        return self.catalog_years.most_common(1)[0][0]


def build_stats(
    profiles: list[PageProfile], vocabulary: Vocabulary
) -> RunStats:
    stats = RunStats()
    for profile in profiles:
        stats.page_type_pages[profile.page_type] += 1
        for label in set(profile.field_labels) & vocabulary.signature_labels:
            stats.label_pages_by_type[profile.page_type][label] += 1
        for marker in profile.markers:
            if marker != CATALOG_YEAR:
                stats.marker_pages_by_type[profile.page_type][marker] += 1
        year = profile.markers.get(CATALOG_YEAR)
        if year:
            stats.catalog_years[year] += 1
    return stats


@dataclass
class Pattern:
    pattern_id: str
    signature: str
    page_type: str
    stems: list[str]
    urls: list[str]
    count: int = 0
    share: float = 0.0
    share_of_page_type: float = 0.0
    field_labels: list[str] = field(default_factory=list)
    rare_field_labels: list[str] = field(default_factory=list)
    markers: dict[str, str] = field(default_factory=dict)
    uncommon_markers: list[str] = field(default_factory=list)
    catalog_years: list[str] = field(default_factory=list)
    special: bool = False
    special_because: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "page_type": self.page_type,
            "count": self.count,
            "share": round(self.share, 4),
            "share_of_page_type": round(self.share_of_page_type, 4),
            "special": self.special,
            "special_because": self.special_because,
            "field_labels": self.field_labels,
            "rare_field_labels": self.rare_field_labels,
            "markers": self.markers,
            "uncommon_markers": self.uncommon_markers,
            "catalog_years": self.catalog_years,
            "signature": self.signature,
            "example_stems": self.stems[:3],
            "example_urls": self.urls[:3],
        }


def assign_patterns(
    profiles: list[PageProfile], vocabulary: Vocabulary
) -> None:
    """Write the signature and pattern id onto every profile."""
    for profile in profiles:
        profile.signature = signature_of(profile, vocabulary)
        profile.pattern_id = pattern_id_of(profile.signature)


def build_patterns(
    profiles: list[PageProfile],
    vocabulary: Vocabulary,
    stats: RunStats,
) -> list[Pattern]:
    """Group the profiled pages and mark the groups worth demonstrating."""
    grouped: dict[str, list[PageProfile]] = defaultdict(list)
    for profile in profiles:
        grouped[profile.pattern_id].append(profile)

    total = len(profiles) or 1
    common_year = stats.common_catalog_year()
    patterns: list[Pattern] = []
    for pattern_id, members in grouped.items():
        first = members[0]
        pattern = Pattern(
            pattern_id=pattern_id,
            signature=first.signature,
            page_type=first.page_type,
            stems=[member.stem for member in members],
            urls=[member.url for member in members],
            count=len(members),
        )
        pattern.share = pattern.count / total
        page_type_total = stats.page_type_pages.get(pattern.page_type, 0) or 1
        pattern.share_of_page_type = pattern.count / page_type_total
        pattern.field_labels = sorted(
            set(first.field_labels) & vocabulary.signature_labels
        )
        pattern.markers = _merged_markers(members)
        pattern.rare_field_labels = [
            label
            for label in pattern.field_labels
            if stats.label_share(pattern.page_type, label) < RARE_LABEL_SHARE
        ]
        pattern.uncommon_markers = [
            marker
            for marker in sorted(pattern.markers)
            if marker != CATALOG_YEAR
            and stats.marker_share(pattern.page_type, marker)
            < RARE_MARKER_SHARE
        ]
        pattern.catalog_years = sorted(
            {
                member.markers[CATALOG_YEAR]
                for member in members
                if member.markers.get(CATALOG_YEAR)
            }
        )
        _mark_special(pattern, common_year)
        patterns.append(pattern)

    patterns.sort(key=lambda item: (-item.count, item.pattern_id))
    return patterns


def _merged_markers(members: list[PageProfile]) -> dict[str, str]:
    """Every marker the group carries, with the first page's evidence."""
    markers: dict[str, str] = {}
    for member in members:
        for name, quote in member.markers.items():
            markers.setdefault(name, quote)
    return dict(sorted(markers.items()))


def _mark_special(pattern: Pattern, common_year: str | None) -> None:
    reasons: list[str] = []
    if pattern.share_of_page_type < RARE_PATTERN_SHARE:
        reasons.append(
            f"only {pattern.share_of_page_type:.1%} of {pattern.page_type} pages"
        )
    if pattern.rare_field_labels:
        reasons.append(
            "rare field labels: " + ", ".join(pattern.rare_field_labels)
        )
    if pattern.uncommon_markers:
        reasons.append(
            "markers on under "
            f"{RARE_MARKER_SHARE:.0%} of {pattern.page_type} pages: "
            + ", ".join(pattern.uncommon_markers)
        )
    for marker in ALWAYS_SPECIAL_MARKERS:
        if marker in pattern.markers:
            reasons.append(MARKER_MEANING[marker])
    odd_years = [
        year
        for year in pattern.catalog_years
        if common_year is not None and year != common_year
    ]
    if odd_years:
        reasons.append(
            f"catalog year {', '.join(odd_years)} against {common_year}"
        )
    pattern.special = bool(reasons)
    pattern.special_because = reasons
