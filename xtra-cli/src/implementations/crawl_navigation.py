"""A crawl run's navigation map, rebuilt from what the run saved.

`xtra catalog crawl navigation` reads a run's manifest.json, crawl.json and
the records under pages/, and writes navigation.json beside them.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from common.clock import format_duration, run_id_for_json, utc_timestamp
from common.keys import (
    crawl_key,
    dedupe_key,
    manifest_key,
    navigation_key,
    page_html_key,
    page_stem,
)
from implementations.crawl_list_pages import asked_page, read_list_pages
from implementations.crawl_manifest import (
    LockedScope,
    ManifestError,
    read_locked,
)
from implementations.crawl_scope import (
    REASON_EXCLUDE_RULE,
    REASON_EXTENSION,
    REASON_INCLUDE_RULE,
    REASON_OUT_OF_SCOPE,
    REASON_ROBOTS,
    REASON_SCHEME,
    Scope,
    extract_link_records,
)
from implementations.crawl_status import (
    GROUP_FAILED,
    GROUP_SAVED,
    GROUP_SKIPPED,
    list_run_files,
)

logger = logging.getLogger(__name__)

NAVIGATION_SCHEMA = "xtra-navigation-1"
BUILT_FROM_SAVED_PAGES = "saved_pages"

READ_BATCH = 100
PROGRESS_EVERY = 500

CRAWL_COMPLETE = "complete"

FOUND_BY_START_URL = "start_url"
FOUND_BY_SEED_FILE = "seed_file"
FOUND_BY_LINK = "link"
FOUND_BY_PAGE_BUTTON = "page_button"
FOUND_BY_NOT_A_LINK = "not_from_a_link"
FOUND_BY_ORDER = (
    FOUND_BY_START_URL,
    FOUND_BY_SEED_FILE,
    FOUND_BY_LINK,
    FOUND_BY_PAGE_BUTTON,
    FOUND_BY_NOT_A_LINK,
)

NEW = "new"
ALREADY_FOUND = "already_found"
OTHER_WEBSITE = "other_website"
OUTSIDE_SCOPE = "outside_scope"
NOT_A_WEB_PAGE = "not_a_web_page"
FILE = "file"
LEFT_OUT_BY_INCLUDE_REGEX = "left_out_by_include_regex"
LEFT_OUT_BY_EXCLUDE_REGEX = "left_out_by_exclude_regex"
BLOCKED_BY_ROBOTS = "blocked_by_robots"
RESULT_ORDER = (
    NEW,
    ALREADY_FOUND,
    OTHER_WEBSITE,
    OUTSIDE_SCOPE,
    NOT_A_WEB_PAGE,
    FILE,
    LEFT_OUT_BY_INCLUDE_REGEX,
    LEFT_OUT_BY_EXCLUDE_REGEX,
    BLOCKED_BY_ROBOTS,
)
_RESULT_OF_REASON = {
    REASON_SCHEME: NOT_A_WEB_PAGE,
    REASON_EXTENSION: FILE,
    REASON_INCLUDE_RULE: LEFT_OUT_BY_INCLUDE_REGEX,
    REASON_EXCLUDE_RULE: LEFT_OUT_BY_EXCLUDE_REGEX,
    REASON_ROBOTS: BLOCKED_BY_ROBOTS,
}

STATUS_SAVED = "saved"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_NOT_VISITED = "not_visited"
STATUS_ORDER = (STATUS_SAVED, STATUS_FAILED, STATUS_SKIPPED, STATUS_NOT_VISITED)

_GROUP_RANK = {GROUP_SAVED: 3, GROUP_FAILED: 2, GROUP_SKIPPED: 1}

_NO_TIME = "~"


class NavigationError(RuntimeError):
    """There is no run to read, or navigation.json would be replaced."""


@dataclass(frozen=True)
class RunFacts:
    seed_url: str
    start_url: str
    scope: Scope
    seed_scope: Scope
    seed_urls: tuple[str, ...]
    alias_host: str
    status: str
    has_report: bool
    finished: bool
    robots_could_block: bool
    declared_pages: int

    def canonical(self, url: str) -> str:
        if not self.alias_host:
            return url
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() != self.alias_host:
            return url
        host = self.scope.host
        netloc = host if parsed.port is None else f"{host}:{parsed.port}"
        return urlunsplit(parsed._replace(netloc=netloc))


@dataclass(frozen=True)
class _Record:
    group: str
    url: str
    meta: dict[str, Any]


@dataclass(frozen=True)
class _Event:
    at: str
    record: _Record


@dataclass
class _UrlEntry:
    url: str
    key: str
    found_by: str
    source: str = ""
    link_text: str = ""
    redirected_to: str = ""
    targets_read: bool = False
    target_links: int = 0
    page_button_targets: int = 0
    new_targets: list[str] = field(default_factory=list)
    skipped_targets: list[dict[str, str]] = field(default_factory=list)
    skipped_target_urls: set[str] = field(default_factory=set)


def _read_doc(store: Any, key: str) -> dict[str, Any]:
    if not store.exists(key):
        return {}
    try:
        doc = store.get_json(key)
    except ValueError as exc:
        raise NavigationError(f"{key} cannot be read: {exc}") from exc
    if not isinstance(doc, dict):
        raise NavigationError(f"{key} is not a JSON object.")
    return doc


def _locked_scope(
    store: Any, catalog_folder: str, run_id: str, report: dict[str, Any]
) -> LockedScope:
    """The manifest's scope, or the same fields from crawl.json without one."""
    key = manifest_key(catalog_folder, run_id)
    manifest = _read_doc(store, key)
    if manifest:
        try:
            return read_locked(manifest, key=key)
        except ManifestError as exc:
            raise NavigationError(str(exc)) from exc
    return LockedScope(
        seed_url=str(report.get("seed_url") or ""),
        scope_prefix=str(report.get("scope_prefix") or ""),
        include_regex=tuple(report.get("include_regex") or ()),
        exclude_regex=tuple(report.get("exclude_regex") or ()),
        seed_urls=(),
        strategy=str(report.get("strategy") or ""),
    )


def read_run_facts(store: Any, catalog_folder: str, run_id: str) -> RunFacts:
    report = _read_doc(store, crawl_key(catalog_folder, run_id))
    has_manifest = store.exists(manifest_key(catalog_folder, run_id))
    if not report and not has_manifest:
        raise NavigationError(
            f"run {run_id_for_json(run_id)} of {catalog_folder} has no "
            "crawl.json and no manifest.json. Check --url and --run-id "
            "against `xtra catalog crawl status`."
        )
    locked = _locked_scope(store, catalog_folder, run_id, report)
    if not locked.seed_url:
        raise NavigationError(
            f"run {run_id_for_json(run_id)} of {catalog_folder} does not say "
            "which URL it started from."
        )

    start_url = str(report.get("resolved_seed_url") or locked.seed_url)
    scope_prefix = str(report.get("scope_prefix") or locked.scope_prefix)
    scope = Scope.from_seed(
        start_url,
        scope_prefix=scope_prefix,
        include_regex=locked.include_regex,
        exclude_regex=locked.exclude_regex,
    )
    seed_scope = Scope(host=scope.host, path_prefix=scope.path_prefix)
    typed_host = (urlsplit(locked.seed_url).hostname or "").lower()
    alias_host = ""
    if typed_host and typed_host != scope.host:
        alias_host = typed_host

    if report:
        robots_status = report.get("robots_status")
        robots_could_block = (
            isinstance(robots_status, int) and 200 <= robots_status < 400
        )
    else:
        robots_could_block = True

    site_index = report.get("site_index")
    index_pages = 0
    if isinstance(site_index, dict):
        index_pages = int(site_index.get("urls_found") or 0)
    declared_pages = int(report.get("sitemap_urls_found") or 0) + index_pages

    return RunFacts(
        seed_url=locked.seed_url,
        start_url=start_url,
        scope=scope,
        seed_scope=seed_scope,
        seed_urls=tuple(locked.seed_urls),
        alias_host=alias_host,
        status=str(report.get("status") or ""),
        has_report=bool(report),
        finished=bool(report.get("finished_at")),
        robots_could_block=robots_could_block,
        declared_pages=declared_pages,
    )


def _read_many(
    store: Any, keys: list[str]
) -> tuple[list[tuple[str, bytes]], list[str]]:
    if not keys:
        return [], []
    try:
        bodies = store.get_many(keys)
    except FileNotFoundError:
        pass
    else:
        return list(zip(keys, bodies, strict=True)), []
    found: list[tuple[str, bytes]] = []
    missing: list[str] = []
    for key in keys:
        try:
            found.append((key, store.get_bytes(key)))
        except FileNotFoundError:
            missing.append(key)
    return found, missing


def _record_url(group: str, meta: dict[str, Any]) -> str:
    if group == GROUP_SAVED:
        return str(meta.get("requested_url") or "")
    return str(meta.get("url") or "")


class _Records:
    def __init__(self, facts: RunFacts) -> None:
        self.facts = facts
        self.by_key: dict[str, _Record] = {}
        self.unreadable = 0

    def key_of(self, url: str) -> str:
        return dedupe_key(self.facts.canonical(url))

    def read(self, store: Any, keys_by_group: dict[str, list[str]]) -> None:
        for group in (GROUP_SAVED, GROUP_FAILED, GROUP_SKIPPED):
            keys = sorted(keys_by_group.get(group, []))
            for start in range(0, len(keys), READ_BATCH):
                found, missing = _read_many(
                    store, keys[start : start + READ_BATCH]
                )
                self.unreadable += len(missing)
                for _, body in found:
                    self._add(group, body)

    def _add(self, group: str, body: bytes) -> None:
        try:
            meta = json.loads(body.decode("utf-8"))
        except ValueError:
            self.unreadable += 1
            return
        if not isinstance(meta, dict):
            self.unreadable += 1
            return
        url = _record_url(group, meta)
        if not url:
            self.unreadable += 1
            return
        key = self.key_of(url)
        held = self.by_key.get(key)
        if held is not None and _GROUP_RANK[held.group] >= _GROUP_RANK[group]:
            return
        self.by_key[key] = _Record(group=group, url=url, meta=meta)

    def events(self) -> list[_Event]:
        events: list[_Event] = []
        for record in self.by_key.values():
            meta = record.meta
            if record.group == GROUP_SAVED:
                at = meta.get("copied_at") or meta.get("retrieved_at")
            elif record.group == GROUP_SKIPPED and meta.get("final_url"):
                at = meta.get("at")
            else:
                continue
            events.append(_Event(at=str(at or _NO_TIME), record=record))
        events.sort(key=lambda event: (event.at, event.record.url))
        return events


class _Map:
    """The crawl's frontier decisions, replayed over its saved pages."""

    def __init__(self, facts: RunFacts, records: _Records) -> None:
        self.facts = facts
        self.records = records
        self.urls: dict[str, _UrlEntry] = {}
        self.found: set[str] = set()
        self.waiting_since: dict[str, str] = {}
        self.source_counts: Counter = Counter()
        self.link_totals: Counter = Counter()
        self.other_websites: dict[str, dict[str, Any]] = {}
        self.robots_inferred = 0
        self.unreadable_pages = 0
        self.robots_certain = (
            facts.robots_could_block
            and facts.status == CRAWL_COMPLETE
            and records.unreadable == 0
        )

    def declare(self, url: str, found_by: str) -> None:
        url = self.facts.canonical(url)
        if self.facts.seed_scope.rejection(url) is not None:
            return
        key = dedupe_key(url)
        if key in self.found:
            return
        if self.robots_certain and key not in self.records.by_key:
            return
        self.urls[key] = _UrlEntry(url=url, key=key, found_by=found_by)
        self.found.add(key)

    def _is_ancestor(self, candidate: str, start: str) -> bool:
        """True when candidate is start, or start was found through it."""
        key = start
        walked = 0
        while key and walked <= len(self.urls):
            if key == candidate:
                return True
            key = self.urls[key].source
            walked += 1
        return False

    def _judge(self, url: str, key: str, source: _UrlEntry, at: str) -> str:
        reason = self.facts.scope.rejection(url)
        if reason == REASON_OUT_OF_SCOPE:
            host = (urlsplit(url).hostname or "").lower()
            if host != self.facts.scope.host:
                return OTHER_WEBSITE
            return OUTSIDE_SCOPE
        if reason is not None:
            return _RESULT_OF_REASON.get(reason, reason)
        if key in self.found:
            return ALREADY_FOUND
        if key in self.waiting_since:
            if self.waiting_since[key] != at:
                return ALREADY_FOUND
            if self._is_ancestor(key, source.key):
                return ALREADY_FOUND
            return NEW
        if self.robots_certain and key not in self.records.by_key:
            self.robots_inferred += 1
            return BLOCKED_BY_ROBOTS
        return NEW

    def _link(
        self,
        source: _UrlEntry,
        url: str,
        text: str,
        found_by: str,
        at: str,
        counted: set[str],
    ) -> None:
        url = self.facts.canonical(url)
        key = dedupe_key(url)
        result = self._judge(url, key, source, at)
        self.link_totals[result] += 1
        if (
            result in (NEW, ALREADY_FOUND)
            and key != source.key
            and key not in counted
        ):
            counted.add(key)
            self.source_counts[key] += 1
        if result == NEW:
            self._add_new_target(source, url, key, text, found_by)
        elif result == OTHER_WEBSITE:
            self._count_other_website(source, url)
        elif result != ALREADY_FOUND and url not in source.skipped_target_urls:
            source.skipped_target_urls.add(url)
            source.skipped_targets.append(
                {"url": url, "link_text": text, "result": result}
            )

    def _add_new_target(
        self,
        source: _UrlEntry,
        url: str,
        key: str,
        text: str,
        found_by: str,
    ) -> None:
        target = self.urls.get(key)
        if target is None:
            target = _UrlEntry(url=url, key=key, found_by=found_by)
            self.urls[key] = target
        else:
            del self.waiting_since[key]
            target.found_by = found_by
        target.source = source.key
        target.link_text = text
        self.found.add(key)
        source.new_targets.append(key)

    def _count_other_website(self, source: _UrlEntry, url: str) -> None:
        host = (urlsplit(url).hostname or "").lower()
        entry = self.other_websites.get(host)
        if entry is None:
            entry = {
                "host": host,
                "links": 0,
                "sources": 0,
                "first_source_url": source.url,
                "first_target_url": url,
                "_last_source": "",
            }
            self.other_websites[host] = entry
        entry["links"] += 1
        if entry["_last_source"] != source.key:
            entry["_last_source"] = source.key
            entry["sources"] += 1

    def _entry_for(self, url: str, at: str) -> _UrlEntry:
        url = self.facts.canonical(url)
        key = dedupe_key(url)
        entry = self.urls.get(key)
        if entry is None:
            entry = _UrlEntry(url=url, key=key, found_by=FOUND_BY_NOT_A_LINK)
            self.urls[key] = entry
            self.waiting_since[key] = at
        return entry

    def redirect(self, event: _Event) -> None:
        final_url = str(event.record.meta.get("final_url") or "")
        self.found.add(dedupe_key(self.facts.canonical(final_url)))

    def follow(self, event: _Event, html: str, readable: bool) -> None:
        meta = event.record.meta
        requested = event.record.url
        source = self._entry_for(requested, event.at)
        final_url = str(meta.get("final_url") or requested)
        if dedupe_key(final_url) != dedupe_key(requested):
            source.redirected_to = final_url
            self.found.add(dedupe_key(self.facts.canonical(final_url)))
        if not readable:
            self.unreadable_pages += 1
            return

        copied = bool(meta.get("copied_from_run"))
        base_url = requested if copied else final_url
        counted: set[str] = set()

        listed = read_list_pages(html, requested)
        buttons = listed.urls if listed is not None else ()
        for url in buttons:
            number = asked_page(url)
            text = f"page {number}" if number is not None else "page"
            self._link(
                source, url, text, FOUND_BY_PAGE_BUTTON, event.at, counted
            )
        source.page_button_targets = len(buttons)

        links = extract_link_records(html, base_url)
        for link in links:
            self._link(
                source, link.url, link.text, FOUND_BY_LINK, event.at, counted
            )
        source.target_links = len(links)
        source.targets_read = True

    def add_unlinked_records(self) -> None:
        """Failed and skipped URLs no saved page links to: from the sitemap."""
        for key, record in self.records.by_key.items():
            if key in self.urls:
                continue
            url = self.facts.canonical(record.url)
            self.urls[key] = _UrlEntry(
                url=url, key=key, found_by=FOUND_BY_NOT_A_LINK
            )


def _status(record: _Record) -> dict[str, Any]:
    meta = record.meta
    if record.group == GROUP_SAVED:
        status: dict[str, Any] = {
            "status": STATUS_SAVED,
            "http_status": meta.get("http_status"),
        }
        if meta.get("copied_from_run"):
            status["copied_from_run"] = meta["copied_from_run"]
        return status
    if record.group == GROUP_FAILED:
        status = {
            "status": STATUS_FAILED,
            "error": meta.get("error") or "failed",
            "retryable": bool(meta.get("retryable")),
        }
        if meta.get("http_status") is not None:
            status["http_status"] = meta["http_status"]
        return status
    status = {"status": STATUS_SKIPPED, "reason": meta.get("reason") or ""}
    if meta.get("final_url"):
        status["final_url"] = meta["final_url"]
    return status


def _clicks(urls: dict[str, _UrlEntry]) -> dict[str, int]:
    depth: dict[str, int] = {}
    for key in urls:
        chain: list[str] = []
        current = key
        while current and current not in depth and current not in chain:
            chain.append(current)
            current = urls[current].source
        base = depth.get(current, -1) if current else -1
        for step, chain_key in enumerate(reversed(chain), start=1):
            depth[chain_key] = base + step
    return depth


def _ordered(counts: Counter, order: tuple[str, ...]) -> dict[str, int]:
    known = {name: counts[name] for name in order if counts.get(name)}
    rest = {
        name: count
        for name, count in sorted(counts.items())
        if name not in order and count
    }
    return {**known, **rest}


def _entries(
    navigation: _Map, statuses: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    urls = navigation.urls
    clicks = _clicks(urls)
    entries: list[dict[str, Any]] = []
    for key, url_entry in urls.items():
        entry: dict[str, Any] = {
            "url": url_entry.url,
            "found_by": url_entry.found_by,
        }
        if url_entry.source:
            entry["source_url"] = urls[url_entry.source].url
            entry["link_text"] = url_entry.link_text
        entry["clicks"] = clicks[key]
        entry.update(statuses[key])
        if url_entry.redirected_to:
            entry["redirected_to"] = url_entry.redirected_to
        if url_entry.targets_read:
            entry["target_links"] = url_entry.target_links
            if url_entry.page_button_targets:
                entry["page_button_targets"] = url_entry.page_button_targets
        entry["source_count"] = navigation.source_counts[key]
        if url_entry.new_targets:
            entry["new_targets"] = [
                urls[target].url for target in url_entry.new_targets
            ]
        if url_entry.skipped_targets:
            entry["skipped_targets"] = url_entry.skipped_targets
        entries.append(entry)
    return entries


def _same_second(events: list[_Event]) -> int:
    seconds = Counter(
        event.at for event in events if event.record.group == GROUP_SAVED
    )
    return sum(count for count in seconds.values() if count > 1)


def _notes(
    facts: RunFacts,
    navigation: _Map,
    records: _Records,
    by_status: Counter,
    by_found_by: Counter,
    same_second: int,
) -> list[str]:
    notes: list[str] = []
    if not facts.has_report:
        notes.append(
            "The run has no crawl.json, so it was killed before it could "
            "write one. Its scope comes from manifest.json, and whether the "
            "crawl started on another host than the one typed is unknown."
        )
    elif not facts.finished:
        notes.append(
            "crawl.json has no finished_at: the run was interrupted or is "
            "still going, so this map covers only what it had saved."
        )
    if facts.declared_pages:
        notes.append(
            f"The sitemap and site index listed {facts.declared_pages} pages, "
            "and a run does not save which ones. A listed page that a saved "
            "page also links to is shown under that page."
        )
    unlinked = by_found_by.get(FOUND_BY_NOT_A_LINK, 0)
    if unlinked:
        notes.append(
            f"{unlinked} URLs are not a target of any source saved before "
            f"them, so they are marked {FOUND_BY_NOT_A_LINK}. They came from "
            "the sitemap or the site index, or from a link on a page that "
            "failed or could not be read."
        )
    if same_second:
        notes.append(
            f"{same_second} saved pages share the second they were saved in "
            "with another page, and a run records time only to the second. "
            "Between pages saved in the same second, source_url may name "
            "another source that also links there."
        )
    if navigation.robots_inferred:
        notes.append(
            "robots.txt is not saved with a run. This run finished complete, "
            f"so the {navigation.robots_inferred} links marked "
            f"{BLOCKED_BY_ROBOTS} passed every other rule and were never "
            "asked for, which only robots.txt explains."
        )
    not_visited = by_status.get(STATUS_NOT_VISITED, 0)
    if not_visited and facts.status != CRAWL_COMPLETE:
        status = facts.status or "unknown"
        cause = "still waiting to be fetched when it stopped"
        if facts.robots_could_block:
            cause += ", or refused by robots.txt; the saved files can't tell"
        notes.append(
            f"The run ended {status}, so the {not_visited} URLs marked "
            f"{STATUS_NOT_VISITED} were {cause}."
        )
    elif not_visited:
        notes.append(
            f"{not_visited} URLs are marked {STATUS_NOT_VISITED} although "
            "the run finished complete. Unreadable records or a robots.txt "
            "this rebuild can't see would explain it."
        )
    if records.unreadable:
        notes.append(
            f"{records.unreadable} page records under pages/ could not be "
            "read, so those URLs may show the wrong status."
        )
    if navigation.unreadable_pages:
        notes.append(
            f"{navigation.unreadable_pages} saved pages could not be read, so "
            "their links are missing."
        )
    return notes


def _read_pages(
    store: Any, catalog_folder: str, run_id: str, events: list[_Event]
) -> dict[str, str]:
    """HTML of the saved pages among these events, by page key."""
    keys: dict[str, str] = {}
    for event in events:
        if event.record.group != GROUP_SAVED:
            continue
        stem = str(event.record.meta.get("stem") or page_stem(event.record.url))
        keys[page_html_key(catalog_folder, run_id, stem)] = event.record.url
    found, _ = _read_many(store, list(keys))
    pages: dict[str, str] = {}
    for key, body in found:
        pages[keys[key]] = body.decode("utf-8", errors="replace")
    return pages


def _write(store: Any, key: str, doc: dict[str, Any], force: bool) -> None:
    if force:
        store.put_json(key, doc)
        return
    if store.exists(key):
        raise NavigationError(
            f"{key} already exists. Pass --force to build it again."
        )
    try:
        store.put_new_json(key, doc)
    except FileExistsError as exc:
        raise NavigationError(
            f"{key} was written by someone else while this was building. "
            "Pass --force to replace it."
        ) from exc


def build_navigation(
    store: Any,
    catalog_folder: str,
    run_id: str,
    *,
    force: bool = False,
    now: Callable[[], str] = utc_timestamp,
) -> tuple[str, dict[str, Any]]:
    """Write the run's navigation.json. Returns its key and the document."""
    started = time.monotonic()
    key = navigation_key(catalog_folder, run_id)
    if not force and store.exists(key):
        raise NavigationError(
            f"{key} already exists. Pass --force to build it again."
        )
    facts = read_run_facts(store, catalog_folder, run_id)
    files = list_run_files(store, catalog_folder, run_id)
    records = _Records(facts)
    records.read(store, files.by_group)
    events = records.events()
    saved_count = sum(
        1 for event in events if event.record.group == GROUP_SAVED
    )
    logger.info(
        "NAVIGATION %s run %s: %s saved pages, %s records",
        catalog_folder,
        run_id_for_json(run_id),
        saved_count,
        len(records.by_key),
    )

    navigation = _Map(facts, records)
    navigation.declare(facts.start_url, FOUND_BY_START_URL)
    for url in facts.seed_urls:
        navigation.declare(url, FOUND_BY_SEED_FILE)

    done = 0
    for start in range(0, len(events), READ_BATCH):
        batch = events[start : start + READ_BATCH]
        html_by_url = _read_pages(store, catalog_folder, run_id, batch)
        for event in batch:
            if event.record.group != GROUP_SAVED:
                navigation.redirect(event)
                continue
            html = html_by_url.get(event.record.url, "")
            readable = event.record.url in html_by_url
            navigation.follow(event, html, readable)
            done += 1
            if done % PROGRESS_EVERY == 0:
                logger.info(
                    "NAVIGATION read %s of %s saved pages (%s)",
                    done,
                    saved_count,
                    format_duration(time.monotonic() - started),
                )
    navigation.add_unlinked_records()

    statuses: dict[str, dict[str, Any]] = {}
    for url_key in navigation.urls:
        record = records.by_key.get(url_key)
        if record is None:
            statuses[url_key] = {"status": STATUS_NOT_VISITED}
        else:
            statuses[url_key] = _status(record)
    by_status = Counter(status["status"] for status in statuses.values())
    by_found_by = Counter(
        url_entry.found_by for url_entry in navigation.urls.values()
    )

    other_websites = sorted(
        navigation.other_websites.values(),
        key=lambda entry: (-entry["links"], entry["host"]),
    )
    for entry in other_websites:
        del entry["_last_source"]

    notes = _notes(
        facts,
        navigation,
        records,
        by_status,
        by_found_by,
        _same_second(events),
    )
    doc: dict[str, Any] = {
        "schema": NAVIGATION_SCHEMA,
        "catalog_folder": catalog_folder,
        "run_id": run_id_for_json(run_id),
        "built_from": BUILT_FROM_SAVED_PAGES,
        "built_at": now(),
        "crawl": {
            "status": facts.status,
            "seed_url": facts.seed_url,
            "start_url": facts.start_url,
            "scope_host": facts.scope.host,
            "scope_prefix": facts.scope.path_prefix,
            "include_regex": [rule.pattern for rule in facts.scope.include],
            "exclude_regex": [rule.pattern for rule in facts.scope.exclude],
            "seed_urls": list(facts.seed_urls),
        },
        "totals": {
            "urls": len(navigation.urls),
            "urls_by_status": _ordered(by_status, STATUS_ORDER),
            "urls_by_found_by": _ordered(by_found_by, FOUND_BY_ORDER),
            "links_by_result": _ordered(navigation.link_totals, RESULT_ORDER),
        },
        "notes": notes,
        "other_websites": other_websites,
        "urls": _entries(navigation, statuses),
    }
    _write(store, key, doc, force)

    for note in notes:
        logger.info("NAVIGATION note: %s", note)
    logger.info(
        "NAVIGATION wrote %s in %s: %s urls, %s links",
        key,
        format_duration(time.monotonic() - started),
        len(navigation.urls),
        sum(navigation.link_totals.values()),
    )
    return key, doc
