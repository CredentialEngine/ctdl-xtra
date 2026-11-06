"""Deterministic review sample, mixed by page type and configured per ruleset.

Mixed on purpose: a reviewer who only sees course pages never notices that the
labeler also calls an index page a course. The mix lives in the ruleset's ``sample``:

    {"quotas": {"course": 12, "program": 8, "info": 10},
     "strata": {"course": [{"name": "range", "quota": 3, "pattern": "<regex on the
                            page html>"}, {"name": "plain", "quota": 9}]},
     "size_pattern": "<regex counted in the html>", "small_page": 12,
     "spread": {"program": "/programs/([^/]+)/"}}

``strata`` spend a type's quota on pages with unusual features first (a stratum
with no ``pattern`` takes anything left); ``size_pattern`` + ``small_page`` prefer
small pages so a one-hour review is feasible; ``spread`` (a regex with one group,
applied to the URL) spreads picks across groups such as program areas.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Callable

from .runs import PageRef, page_type_of

DEFAULT_TARGET = 30


def _hash_key(page: PageRef) -> str:
    return hashlib.sha256(page.stem.encode()).hexdigest()


def _scale(weights: dict[str, int], target: int) -> dict[str, int]:
    """Split ``target`` across the keys in proportion to ``weights`` (largest remainder)."""
    total = sum(weights.values())
    if total == 0:
        return dict.fromkeys(weights, 0)
    exact = {k: target * w / total for k, w in weights.items()}
    scaled = {k: int(v) for k, v in exact.items()}
    by_remainder = sorted(exact, key=lambda k: exact[k] - scaled[k], reverse=True)
    for key in by_remainder[: target - sum(scaled.values())]:
        scaled[key] += 1
    return scaled


def _spread(
    pages: list[PageRef],
    count: int,
    size_of: Callable[[PageRef], int] | None,
    small_page: int,
    group_of: Callable[[PageRef], str],
) -> list[PageRef]:
    """First ``count`` pages, small ones first, preferring groups not yet seen."""

    def order(page: PageRef):
        big = bool(size_of and size_of(page) > small_page)
        return (big, _hash_key(page))

    chosen: list[PageRef] = []
    used: set[str] = set()
    rest: list[PageRef] = []
    for page in sorted(pages, key=order):
        group = group_of(page)
        if len(chosen) < count and (not group or group not in used):
            chosen.append(page)
            used.add(group)
        else:
            rest.append(page)
    chosen += rest[: max(0, count - len(chosen))]
    return chosen


def pick_sample(
    pages: list[PageRef],
    config: dict,
    page_types: list[dict],
    html_of: Callable[[PageRef], str],
    target: int | None = None,
) -> list[dict]:
    """``html_of`` is only called for pages that a stratum or size pattern needs."""
    quotas = config.get("quotas", {})
    target = target or config.get("target") or sum(quotas.values()) or DEFAULT_TARGET
    small_page = config.get("small_page", 12)
    size_re = re.compile(config["size_pattern"]) if "size_pattern" in config else None

    html_cache: dict[str, str] = {}

    def html(page: PageRef) -> str:
        if page.stem not in html_cache:
            html_cache[page.stem] = html_of(page)
        return html_cache[page.stem]

    size_of = (lambda p: len(size_re.findall(html(p)))) if size_re else None

    by_type: dict[str, list[PageRef]] = defaultdict(list)
    for page in pages:
        by_type[page_type_of(page.url, page_types)].append(page)

    picked: list[tuple[PageRef, str]] = []
    for page_type, quota in _scale(quotas, target).items() if quotas else []:
        candidates = by_type.get(page_type, [])
        spread = config.get("spread", {}).get(page_type)

        def group_of(page: PageRef, spread=spread) -> str:
            match = re.search(spread, page.url) if spread else None
            return match.group(1) if match else ""

        strata = config.get("strata", {}).get(page_type)
        if not strata:
            chosen = _spread(candidates, quota, size_of, small_page, group_of)
            picked += [(p, page_type) for p in chosen]
            continue
        remaining = list(candidates)
        shares = _scale({s["name"]: s["quota"] for s in strata}, quota)
        for stratum in strata:
            pattern = stratum.get("pattern")
            pool = [p for p in remaining if not pattern or re.search(pattern, html(p))]
            chosen = _spread(
                pool, shares[stratum["name"]], size_of, small_page, group_of
            )
            picked += [(p, f"{page_type}, {stratum['name']}") for p in chosen]
            taken = {p.stem for p in chosen}
            remaining = [p for p in remaining if p.stem not in taken]

    taken = {page.stem for page, _ in picked}
    if len(picked) < target:  # unmatched page types still get a full-size sample
        extras = sorted((p for p in pages if p.stem not in taken), key=_hash_key)
        picked += [(p, "top-up") for p in extras[: target - len(picked)]]

    return [
        {
            "stem": page.stem,
            "url": page.url,
            "page_type": page_type_of(page.url, page_types),
            "reason": reason,
        }
        for page, reason in picked
    ]
