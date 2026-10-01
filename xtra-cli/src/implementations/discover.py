"""Read a whole crawl and say what is in it.

Discovery never fetches anything. It reads every page the crawl saved, works
out what each one is, groups the pages that share a shape, names the shapes
that are unusual, and picks a sample that covers all of them. The result is
a preprocessed list extraction can work from, and a report a person can read
before trusting any of it.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.keys import (
    crawl_key,
    discovery_key,
    discovery_root,
    page_html_key,
    run_prefix,
)
from common.storage_uri import join_storage_uri
from implementations.discover_ner import entities_by_kind
from implementations.discover_page import PageProfile, profile_page
from implementations.discover_patterns import (
    CATALOG_YEAR,
    Pattern,
    Vocabulary,
    assign_patterns,
    build_patterns,
    build_stats,
    build_vocabulary,
)
from implementations.discover_rules import (
    DEFAULT_SAMPLE_LABEL,
    DEFAULT_SAMPLE_SIZE,
    ENTITY_KINDS,
    ENTITY_MEANING,
    MARKER_MEANING,
    RARE_LABEL_SHARE,
)
from implementations.discover_sample import (
    GoldenSample,
    choose_sample,
    population_for,
)

logger = logging.getLogger(__name__)

DISCOVERY_SCHEMA = "xtra-discovery-1"
LABELS_SCHEMA = "xtra-labels-1"
PAGES_FILE = "pages.jsonl"
SUMMARY_FILE = "summary.json"
LABELS_FILE = "labels.json"
FIELD_LABELS_FILE = "field-labels.csv"
ENTITIES_FILE = "entities.csv"
PATTERNS_JSON_FILE = "patterns.json"
PATTERNS_MD_FILE = "patterns.md"
EMPTY_OR_ERROR = "empty_or_error_page"

# What a reader has to know about the crawl to trust a discovery report,
# none of which can be worked out from the saved pages themselves.
PROVENANCE_FIELDS = (
    "strategy",
    "seed_url",
    "resolved_seed_url",
    "effective_min_interval_in_seconds",
    "status",
    "pages_saved",
)
CRAWL_PROVENANCE_MISSING = (
    "crawl.json was not found for this run, so nothing about the crawl "
    "that produced these pages is recorded here."
)
_CLI_ROOT = Path(__file__).resolve().parents[2]


class NoPagesError(RuntimeError):
    """The crawl run has no saved pages to read."""


class UnknownStemError(RuntimeError):
    """A stem was asked for that the crawl run did not save."""


@dataclass(frozen=True)
class DiscoverSettings:
    catalog_folder: str
    run_id: str
    discovery_run_id: str
    source_uri: str
    sample_label: str = DEFAULT_SAMPLE_LABEL
    sample_size: int = DEFAULT_SAMPLE_SIZE
    # The pages to read, when a person is asking about particular ones
    # rather than about the run. Empty means the whole run, which is the
    # only way the report means what it says - see read_saved_pages.
    stems: tuple[str, ...] = ()


@dataclass
class DiscoveryOutcome:
    summary: dict[str, Any]
    profiles: list[PageProfile]
    patterns: list[Pattern]
    sample: GoldenSample
    table: str
    exit_code: int = 0
    reason: str = ""


def git_commit() -> str | None:
    """The commit these rules came from, so a report can be reproduced."""
    try:
        finished = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            cwd=_CLI_ROOT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return finished.stdout.strip() or None


def read_crawl_document(
    source: Any, catalog_folder: str, run_id: str
) -> dict[str, Any] | None:
    """The crawl manifest for this run, or None when there is not one."""
    key = crawl_key(catalog_folder, run_id)
    try:
        if not source.exists(key):
            logger.warning(
                "CRAWL %s is missing, so this report has no provenance", key
            )
            return None
        doc = source.get_json(key)
    except (OSError, ValueError) as exc:
        logger.warning("CRAWL %s could not be read (%s)", key, exc)
        return None
    return doc if isinstance(doc, dict) else None


def provenance_from_crawl(doc: dict[str, Any] | None) -> dict[str, Any]:
    """What the crawl said about itself, or nulls and a note when it did not.

    A report read months later has to say which backend fetched these
    pages, from which URL, how fast, and whether the crawl ever finished.
    None of that is visible in the pages.
    """
    found = bool(doc)
    values = {name: (doc or {}).get(name) for name in PROVENANCE_FIELDS}
    return {
        "crawl_json_found": found,
        **values,
        "note": None if found else CRAWL_PROVENANCE_MISSING,
    }


def provenance_lines(provenance: dict[str, Any]) -> list[str]:
    """The block at the top of patterns.md, in the reader's words."""
    lines = ["## Where these pages came from", ""]
    if not provenance.get("crawl_json_found"):
        lines.append(provenance.get("note") or CRAWL_PROVENANCE_MISSING)
        lines.append("")
        return lines
    seed = provenance.get("seed_url")
    resolved = provenance.get("resolved_seed_url")
    seed_line = f"- Seed URL: {seed}"
    if resolved and resolved != seed:
        seed_line += f", which answers at {resolved}"
    interval = provenance.get("effective_min_interval_in_seconds")
    lines.extend(
        [
            f"- Crawl backend: `{provenance.get('strategy')}`",
            seed_line,
            (
                "- Smallest gap between pages: "
                + (
                    f"{interval} seconds per worker"
                    if interval is not None
                    else "not recorded"
                )
            ),
            (
                f"- Crawl status: `{provenance.get('status')}`, "
                f"{provenance.get('pages_saved')} pages saved"
            ),
            "",
        ]
    )
    return lines


def sample_verdict(
    settings: DiscoverSettings,
    sample: GoldenSample,
    page_types: dict[str, int],
) -> tuple[int, str]:
    """Say out loud when the golden sample is not worth reviewing.

    An empty sample used to be an exit code of 0 and a file holding
    nothing, which is how a run with no course pages went unnoticed.
    """
    if sample.population_size == 0:
        found = (
            ", ".join(
                f"{name} {count}" for name, count in sorted(page_types.items())
            )
            or "none"
        )
        logger.error(
            "SAMPLE no page is labelled %s, so the golden sample is empty. "
            "Page types found instead: %s. The reports are written anyway; "
            "read patterns.md and field-labels.csv, then tune "
            "src/implementations/discover_rules.py and discover again.",
            settings.sample_label,
            found,
        )
        return 1, (
            "the golden sample is empty: no page is labelled "
            f"{settings.sample_label}. Page types found: {found}."
        )
    if sample.population_size < settings.sample_size:
        logger.warning(
            "SAMPLE only %s pages are labelled %s, below the requested "
            "sample size of %s, so the sample is the whole population.",
            sample.population_size,
            settings.sample_label,
            settings.sample_size,
        )
    return 0, ""


def read_saved_pages(
    source: Any,
    catalog_folder: str,
    run_id: str,
    stems: tuple[str, ...] = (),
) -> list[tuple[dict[str, Any], str]]:
    """Every page of the crawl run, in a stable order. No sampling here.

    Profiling the whole run is the point: a special case that only shows up
    on page 700 cannot be found by looking at the first ten.

    `stems` narrows that to named pages, for the one question the whole
    run cannot be read to answer quickly: why is *this* page labelled
    that way. Everything the run-wide reading gives - which labels are
    the site's furniture, which markers are rare, which patterns are
    special - is counted over what was read, so a narrowed run says so
    in its summary and its shares mean nothing on their own.
    """
    prefix = f"{run_prefix(catalog_folder, run_id)}/pages"
    meta_keys = sorted(
        key
        for key in source.list_keys(under=prefix)
        if key.endswith(".meta.json")
    )
    by_stem = {
        key.rsplit("/", 1)[-1][: -len(".meta.json")]: key for key in meta_keys
    }
    if stems:
        missing = [stem for stem in stems if stem not in by_stem]
        if missing:
            raise UnknownStemError(
                f"{run_prefix(catalog_folder, run_id)} saved no page for "
                + ", ".join(sorted(missing))
            )
        meta_keys = [by_stem[stem] for stem in sorted(set(stems))]
    pages: list[tuple[dict[str, Any], str]] = []
    for key in meta_keys:
        meta = source.get_json(key)
        stem = meta.get("stem") or key.rsplit("/", 1)[-1][: -len(".meta.json")]
        html = source.get_text(page_html_key(catalog_folder, run_id, stem))
        pages.append((meta, html))
    return pages


def mark_duplicates(profiles: list[PageProfile]) -> int:
    """The second copy of the same text points at the first."""
    first_seen: dict[str, str] = {}
    duplicates = 0
    for profile in profiles:
        original = first_seen.get(profile.text_sha256)
        if original is None:
            first_seen[profile.text_sha256] = profile.stem
        else:
            profile.duplicate_of = original
            duplicates += 1
    return duplicates


def dominant_page_type(label: str, stats: Any) -> str:
    """The page type a label mostly appears on, which is what rarity means."""
    best_type, best_count = "", -1
    for page_type, counter in stats.label_pages_by_type.items():
        count = counter.get(label, 0)
        if count > best_count:
            best_type, best_count = page_type, count
    return best_type


def field_labels_csv(vocabulary: Vocabulary, stats: Any) -> str:
    """Rarest first: that is the order a reviewer wants to read it in."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "label",
            "pages",
            "share",
            "is_chrome",
            "is_rare",
            "example_url",
            "example_stem",
        ]
    )
    rows = sorted(
        vocabulary.label_pages.items(), key=lambda item: (item[1], item[0])
    )
    for label, count in rows:
        page_type = dominant_page_type(label, stats)
        example_url, example_stem = vocabulary.label_examples.get(
            label, ("", "")
        )
        writer.writerow(
            [
                label,
                count,
                f"{vocabulary.share(label):.4f}",
                label in vocabulary.chrome,
                stats.label_share(page_type, label) < RARE_LABEL_SHARE,
                example_url,
                example_stem,
            ]
        )

    writer.writerow([])
    writer.writerow(["heading", "pages"])
    for heading, count in sorted(
        vocabulary.heading_pages.items(), key=lambda item: (-item[1], item[0])
    ):
        writer.writerow([heading, count])
    return buffer.getvalue()


def entities_csv(profiles: list[PageProfile]) -> str:
    """Every entity every page names, by kind, with the words around it.

    Grouped by kind and then by value, because the question a reviewer
    brings to this file is about a kind: which awards does this catalog
    grant, which jobs does it name, which organizations turn up. The
    quote is here rather than in pages.jsonl for the same reason a
    marker's evidence is in patterns.md - one line per page stays
    readable only if the evidence lives somewhere else.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["kind", "value", "pages", "text", "source", "stem", "url", "quote"]
    )
    rows: list[tuple[str, str, str, str, str, str, str]] = []
    pages_per_value: dict[tuple[str, str], set[str]] = {}
    for profile in profiles:
        for entity in profile.entities:
            key = (entity.kind, entity.value)
            pages_per_value.setdefault(key, set()).add(profile.stem)
            rows.append(
                (
                    entity.kind,
                    entity.value,
                    entity.text,
                    entity.source,
                    profile.stem,
                    profile.url,
                    entity.quote,
                )
            )
    for kind, value, text, source, stem, url, quote in sorted(rows):
        writer.writerow(
            [
                kind,
                value,
                len(pages_per_value[(kind, value)]),
                text,
                source,
                stem,
                url,
                quote,
            ]
        )

    writer.writerow([])
    writer.writerow(["kind", "pages", "distinct_values", "meaning"])
    for kind in ENTITY_KINDS:
        pages = sum(
            1
            for profile in profiles
            if any(entity.kind == kind for entity in profile.entities)
        )
        distinct = sum(1 for found in pages_per_value if found[0] == kind)
        writer.writerow([kind, pages, distinct, ENTITY_MEANING.get(kind, "")])
    return buffer.getvalue()


def patterns_markdown(
    patterns: list[Pattern],
    *,
    settings: DiscoverSettings,
    provenance: dict[str, Any] | None = None,
) -> str:
    """The demo document: special patterns first, with evidence and links."""
    special = [pattern for pattern in patterns if pattern.special]
    ordinary = [pattern for pattern in patterns if not pattern.special]
    lines = [
        f"# Patterns in {settings.catalog_folder} {settings.run_id}",
        "",
        (
            f"Discovery run `{settings.discovery_run_id}`. "
            f"{len(patterns)} patterns, {len(special)} special."
        ),
        "",
        *(provenance_lines(provenance) if provenance is not None else []),
        (
            "A pattern is special when it is a small share of its page "
            "type, carries a rare field label or an uncommon marker, is "
            "empty or archived, or belongs to a different catalog year."
        ),
        "",
    ]
    for title, group in (
        ("Special patterns", special),
        ("Other patterns", ordinary),
    ):
        lines.append(f"## {title}")
        lines.append("")
        if not group:
            lines.append("None.")
            lines.append("")
            continue
        for pattern in group:
            lines.extend(_pattern_section(pattern, settings))
    return "\n".join(lines).rstrip() + "\n"


def _pattern_section(pattern: Pattern, settings: DiscoverSettings) -> list[str]:
    lines = [
        f"### `{pattern.pattern_id}` {pattern.page_type}",
        "",
        (
            f"{pattern.count} pages, {pattern.share:.1%} of the run, "
            f"{pattern.share_of_page_type:.1%} of {pattern.page_type} pages."
        ),
        "",
    ]
    if pattern.special_because:
        lines.append("Why it is special:")
        lines.append("")
        lines.extend(f"- {reason}" for reason in pattern.special_because)
        lines.append("")
    if pattern.rare_field_labels:
        lines.append(
            "Rare field labels: "
            + ", ".join(f"`{label}`" for label in pattern.rare_field_labels)
        )
        lines.append("")
    if pattern.markers:
        lines.append("Markers:")
        lines.append("")
        for marker, quote in pattern.markers.items():
            meaning = MARKER_MEANING.get(marker, "")
            lines.append(f"- **{marker}**: `{quote}`")
            if meaning:
                lines.append(f"  - {meaning}")
        lines.append("")
    lines.append("Examples:")
    lines.append("")
    for url, stem in zip(pattern.urls[:3], pattern.stems[:3], strict=False):
        path = join_storage_uri(
            settings.source_uri,
            page_html_key(settings.catalog_folder, settings.run_id, stem),
        )
        lines.append(f"- {url}")
        lines.append(f"  - `{path}`")
    lines.append("")
    return lines


def patterns_table(patterns: list[Pattern]) -> str:
    """The one screen of output an operator reads before anything else."""
    header = f"{'pattern':<10} {'page_type':<20} {'count':>6} {'share':>7}  special  markers"
    rows = [header, "-" * len(header)]
    for pattern in patterns:
        markers = ", ".join(
            name for name in pattern.markers if name != CATALOG_YEAR
        )[:60]
        rows.append(
            f"{pattern.pattern_id:<10} {pattern.page_type:<20} "
            f"{pattern.count:>6} {pattern.share:>6.1%}  "
            f"{'yes' if pattern.special else 'no ':<7}  {markers}"
        )
    return "\n".join(rows)


def build_summary(
    settings: DiscoverSettings,
    profiles: list[PageProfile],
    patterns: list[Pattern],
    duplicates: int,
    version: str,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    page_types: dict[str, int] = {}
    for profile in profiles:
        page_types[profile.page_type] = page_types.get(profile.page_type, 0) + 1
    total = len(profiles) or 1
    empty = sum(1 for profile in profiles if EMPTY_OR_ERROR in profile.markers)
    return {
        "schema": DISCOVERY_SCHEMA,
        "catalog_folder": settings.catalog_folder,
        "run_id": settings.run_id,
        "discovery_run_id": settings.discovery_run_id,
        "pages": len(profiles),
        # Empty when the whole run was read. Named stems mean every share
        # and every rarity in this report is counted over those pages
        # alone, so a reader has to be told which it is looking at.
        "stems_requested": list(settings.stems),
        "whole_run": not settings.stems,
        "duplicates": duplicates,
        "pages_by_page_type": dict(sorted(page_types.items())),
        "patterns_total": len(patterns),
        "patterns_special": sum(1 for pattern in patterns if pattern.special),
        "empty_or_error_pages": empty,
        "unknown_share": round(page_types.get("Unknown", 0) / total, 4),
        # How many pages name each kind of entity. A catalog where no page
        # names an award, or none names a job, has a reading problem the
        # label counts alone do not show.
        "pages_naming_entity": {
            kind: sum(
                1
                for profile in profiles
                if any(entity.kind == kind for entity in profile.entities)
            )
            for kind in ENTITY_KINDS
        },
        "sample_label": settings.sample_label,
        "sample_size": settings.sample_size,
        "sample_population": len(
            population_for(profiles, settings.sample_label)
        ),
        "crawl": (
            provenance
            if provenance is not None
            else provenance_from_crawl(None)
        ),
        "git_commit": git_commit(),
        "xtra_version": version,
    }


def labels_document(
    settings: DiscoverSettings, profiles: list[PageProfile]
) -> dict[str, Any]:
    """The preprocessed list extraction reads instead of guessing again."""
    return {
        "schema": LABELS_SCHEMA,
        "catalog_folder": settings.catalog_folder,
        "run_id": settings.run_id,
        "discovery_run_id": settings.discovery_run_id,
        "pages": [
            {
                "url": profile.url,
                "stem": profile.stem,
                "page_type": profile.page_type,
                "labels": profile.labels,
                "course_block_count": profile.course_block_count,
                # Names only, not the quotes: extract needs to know that a
                # page holds several credentials, the way it already knows
                # a page holds several courses, and patterns.md is where
                # the evidence for each one is read.
                "markers": sorted(profile.markers),
                # The same rule as the markers: the values, not the
                # quotes. Extraction reads the award and the credits it
                # needs from here rather than finding them again, and
                # entities.csv is where the evidence for each one is read.
                "entities": entities_by_kind(profile.entities),
                "pattern_id": profile.pattern_id,
            }
            for profile in profiles
        ],
    }


def sample_file_name(label: str) -> str:
    return f"golden-sample-{label.lower()}.json"


def latest_discovery_run_id(
    source: Any, catalog_folder: str, run_id: str
) -> str | None:
    """The newest discovery run of a crawl run, by its timestamped folder."""
    root = discovery_root(catalog_folder, run_id)
    ids = {
        key[len(root) + 1 :].split("/", 1)[0]
        for key in source.list_keys(under=root)
        if key.startswith(f"{root}/")
    }
    return max(ids) if ids else None


def run_discovery(
    settings: DiscoverSettings,
    *,
    source: Any,
    target: Any,
    version: str = "",
) -> DiscoveryOutcome:
    """Profile every saved page, then write the reports. Nothing is fetched."""
    summary_key = discovery_key(
        settings.catalog_folder,
        settings.run_id,
        settings.discovery_run_id,
        SUMMARY_FILE,
    )
    if target.exists(summary_key):
        raise FileExistsError(summary_key)

    pages = read_saved_pages(
        source, settings.catalog_folder, settings.run_id, settings.stems
    )
    if not pages:
        raise NoPagesError(
            f"{run_prefix(settings.catalog_folder, settings.run_id)} has no saved pages"
        )
    if settings.stems:
        logger.warning(
            "STEMS reading %s named page(s) of the run, so every share, "
            "every rare marker and every special pattern below is counted "
            "over those pages alone and not over the crawl.",
            len(pages),
        )
    logger.info("READ %s saved pages", len(pages))
    provenance = provenance_from_crawl(
        read_crawl_document(source, settings.catalog_folder, settings.run_id)
    )

    profiles = [
        profile_page(
            url=meta.get("requested_url") or meta.get("final_url") or "",
            html=html,
            stem=meta.get("stem") or "",
            final_url=meta.get("final_url") or "",
            http_status=meta.get("http_status"),
            byte_size=meta.get("bytes"),
        )
        for meta, html in pages
    ]
    duplicates = mark_duplicates(profiles)
    vocabulary = build_vocabulary(profiles)
    assign_patterns(profiles, vocabulary)
    stats = build_stats(profiles, vocabulary)
    patterns = build_patterns(profiles, vocabulary, stats)
    sample = choose_sample(
        profiles,
        vocabulary,
        label=settings.sample_label,
        size=settings.sample_size,
        patterns_total=len(patterns),
    )
    summary = build_summary(
        settings, profiles, patterns, duplicates, version, provenance
    )
    exit_code, reason = sample_verdict(
        settings, sample, summary["pages_by_page_type"]
    )
    logger.info(
        "PROFILED pages=%s duplicates=%s patterns=%s special=%s unknown=%s",
        summary["pages"],
        duplicates,
        summary["patterns_total"],
        summary["patterns_special"],
        summary["pages_by_page_type"].get("Unknown", 0),
    )

    def write(name: str, body: str, content_type: str) -> None:
        target.put_text(
            discovery_key(
                settings.catalog_folder,
                settings.run_id,
                settings.discovery_run_id,
                name,
            ),
            body,
            content_type,
        )

    write(
        PAGES_FILE,
        "".join(
            json.dumps(profile.as_dict(), ensure_ascii=False) + "\n"
            for profile in profiles
        ),
        "application/x-ndjson",
    )
    write(
        PATTERNS_JSON_FILE,
        json.dumps(
            [pattern.as_dict() for pattern in patterns],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        "application/json",
    )
    write(
        PATTERNS_MD_FILE,
        patterns_markdown(patterns, settings=settings, provenance=provenance),
        "text/markdown; charset=utf-8",
    )
    write(
        FIELD_LABELS_FILE,
        field_labels_csv(vocabulary, stats),
        "text/csv; charset=utf-8",
    )
    write(
        ENTITIES_FILE,
        entities_csv(profiles),
        "text/csv; charset=utf-8",
    )
    write(
        LABELS_FILE,
        json.dumps(
            labels_document(settings, profiles), indent=2, ensure_ascii=False
        )
        + "\n",
        "application/json",
    )
    write(
        sample_file_name(settings.sample_label),
        json.dumps(sample.as_dict(), indent=2, ensure_ascii=False) + "\n",
        "application/json",
    )
    write(
        SUMMARY_FILE,
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        "application/json",
    )

    return DiscoveryOutcome(
        summary=summary,
        profiles=profiles,
        patterns=patterns,
        sample=sample,
        table=patterns_table(patterns),
        exit_code=exit_code,
        reason=reason,
    )
