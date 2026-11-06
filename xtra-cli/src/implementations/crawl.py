"""Download a catalog and save it. Nothing else.

The crawler renders a page, writes the HTML and a sidecar, follows links,
and stops when the frontier empties or --limit is reached. It does not
detect a CMS family, name an institution, choose templates, or normalize
text. Those belong to discovery and extraction, which read what the crawler
saved.

Crawling a catalog is a rare, one-time job, A later run gets a new run id and names the earlier one with
--from-run-id: each page the earlier run saved is copied into the new run
when the crawl reaches it, instead of fetched again. Every file a run
writes about a page is written once.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from collections import Counter, deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future
from concurrent.futures import wait as wait_for_futures
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from common.clock import (
    format_duration,
    run_id_for_json,
    run_id_for_path,
    utc_timestamp,
)
from common.keys import (
    crawl_key,
    dedupe_key,
    failed_meta_key,
    manifest_key,
    page_html_key,
    page_meta_key,
    page_stem,
    pages_prefix,
    run_prefix,
    skipped_meta_key,
)
from common.polite import PACING_JITTER_FRACTION, backoff_delay
from common.storage_uri import join_storage_uri
from implementations.crawl_browser import (
    FetchError,
    FetcherStartError,
    FetchResult,
    WorkerPool,
    WorkerState,
    playwright_fetcher_factory,
)
from implementations.crawl_challenge import challenge_kind
from implementations.crawl_curriqunet import (
    CurriqunetIndex,
    read_curriqunet_index,
)
from implementations.crawl_list_pages import queue_list_pages
from implementations.crawl_manifest import (
    LockedScope,
    ManifestError,
    RunExistsError,
    manifest_doc,
    read_locked,
)
from implementations.crawl_robots import (
    collect_sitemap_urls,
    default_sitemap_url,
    fetch_url,
    read_robots,
    resolve_final_url,
)
from implementations.crawl_scope import (
    QUIET_REASONS,
    REASON_DUPLICATE,
    REASON_NON_HTML,
    REASON_REDIRECT_OUT_OF_SCOPE,
    Scope,
    content_type_is_html,
    extract_links,
    first_path_segment,
)
from implementations.crawl_strategy import StrategyFacts, strategy_facts

logger = logging.getLogger(__name__)

CRAWL_SCHEMA = "xtra-crawl-2"

STATUS_COMPLETE = "complete"
STATUS_LIMIT_REACHED = "limit_reached"
STATUS_INCOMPLETE = "incomplete"

RESULT_SAVED = "saved"
RESULT_FAILED = "failed"
RESULT_FAILED_RETRYABLE = "failed-retryable"
RESULT_SKIPPED = "skipped"

REPORT_EVERY = 25
MAX_CONSECUTIVE_FAILURES = 20

FAILURE_PAGE = "page"
FAILURE_BLOCKING = "blocking"
BLOCKING_STATUSES = frozenset({401, 403, 429})
POLL_SECONDS = 1.0
TOP_PATH_SEGMENTS = 20
EXIT_INTERRUPTED = 130

# --url first, then the sitemap, then the site's own page index (a
# CurriQunet catalog's navigation tree), then --seed-urls-file, then links
# in document order. Both declarations are the site's list of its pages, so
# they come ahead of anything found on the way. A list's later pages, read
# off its page buttons, go ahead of the links of the page that leads to
# them. Recorded so a run says which rule ordered its frontier.
FRONTIER_ORDER = "sitemap_first"

# Index documents are small JSON, and like sitemap documents they are not
# paced by --min-interval-in-seconds. Half a second keeps the walk gentler
# than the page renders it replaces, each of which fires ~20 XHRs.
INDEX_INTERVAL_SECONDS = 0.5


class StrategyMismatchError(RuntimeError):
    """A run that would copy pages rendered."""


def format_seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


@dataclass(frozen=True)
class CrawlSettings:
    seed_url: str
    catalog_folder: str
    run_id: str
    target_uri: str
    limit: int | None = None
    concurrency_limit: int = 1
    min_interval_in_seconds: float = 180.0
    max_interval_in_seconds: float = 3600.0
    max_retries: int = 5
    scope_prefix: str | None = None
    include_regex: tuple[str, ...] = ()
    exclude_regex: tuple[str, ...] = ()
    seed_urls: tuple[str, ...] = ()
    strategy: str = "playwright"
    pacing_jitter_fraction: float = PACING_JITTER_FRACTION
    max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES
    from_run_id: str | None = None

    def __post_init__(self) -> None:
        if self.from_run_id is not None and run_id_for_path(
            self.from_run_id
        ) == run_id_for_path(self.run_id):
            raise ValueError(
                f"--from-run-id {self.from_run_id} is the run being "
                "started. Give the new run another --run-id, or leave it "
                "out for now."
            )
        if self.max_consecutive_failures < 1:
            raise ValueError(
                "--max-consecutive-failures must be at least 1, not "
                f"{self.max_consecutive_failures}"
            )
        if not 0 <= self.pacing_jitter_fraction <= 1:
            raise ValueError(
                "pacing_jitter_fraction must be between 0 and 1, not "
                f"{self.pacing_jitter_fraction}"
            )
        if self.min_interval_in_seconds > self.max_interval_in_seconds:
            raise ValueError(
                "--min-interval-in-seconds "
                f"({format_seconds(self.min_interval_in_seconds)}) is above "
                "--max-interval-in-seconds "
                f"({format_seconds(self.max_interval_in_seconds)}). "
                "The minimum is the gap between pages and the first retry "
                "wait; the maximum caps the backoff."
            )


@dataclass(frozen=True)
class FetchPolicy:
    """What a worker needs to retry one URL; its own clock paces it."""

    min_interval: float
    max_interval: float
    max_retries: int
    jitter_fraction: float = 0.0
    uniform: Callable[[float, float], float] = random.uniform


@dataclass(frozen=True)
class PageOutcome:
    url: str
    result: FetchResult | None = None
    error: str = ""
    http_status: int | None = None
    attempts: int = 0
    retryable: bool = False
    reason: str | None = None


class RunStopError(RuntimeError):
    """A failure no page can get past, so the run stops at the first one.

    The browser will not start, or storage refuses a write. Fetching on
    would only fail the same way, or fetch pages that cannot be kept.
    """


def failure_kind(http_status: int | None) -> str:
    if (
        http_status is not None
        and 400 <= http_status < 500
        and http_status not in BLOCKING_STATUSES
    ):
        return FAILURE_PAGE
    return FAILURE_BLOCKING


def is_retryable_status(status: int | None) -> bool:
    """429 and 5xx are worth another try. Other 4xx are the site's answer."""
    return status is not None and (status == 429 or status >= 500)


def fetch_page(
    state: WorkerState, url: str, policy: FetchPolicy
) -> PageOutcome:
    """Fetch one URL with this worker's pacing and backoff. No storage here."""
    total_attempts = policy.max_retries + 1
    attempts = 0
    last_error = ""
    last_status: int | None = None
    retry_after: float | None = None

    for attempt in range(total_attempts):
        if attempt:
            delay = backoff_delay(
                attempt,
                min_interval=policy.min_interval,
                max_interval=policy.max_interval,
                retry_after=retry_after,
                jitter_fraction=policy.jitter_fraction,
                uniform=policy.uniform,
            )
            logger.info(
                "RETRY %s attempt %s of %s after %s, waiting %s s",
                url,
                attempt + 1,
                total_attempts,
                last_error,
                format_seconds(delay),
            )
            state.pacer.wait(delay)
        else:
            state.pacer.wait()

        attempts += 1
        retry_after = None
        try:
            result = state.fetcher.fetch(url)
        except FetchError as exc:
            state.pacer.record_fetch()
            last_error = str(exc)
            if not exc.retryable:
                return PageOutcome(
                    url=url,
                    error=last_error,
                    attempts=attempts,
                    reason=exc.reason,
                )
            continue

        state.pacer.record_fetch()
        last_status = result.http_status
        if is_retryable_status(last_status):
            last_error = f"HTTP {last_status}"
            retry_after = result.retry_after
            continue
        # An interstitial is not the page that was asked for, whatever its
        # status says: AWS WAF sends 202. The browser strategy waits one out
        # on its own; this is what keeps every strategy from saving one.
        # Spent retries leave it retryable, so the next run asks again.
        kind = challenge_kind(last_status, {}, result.html)
        if kind is not None:
            last_error = f"{kind} challenge page"
            continue
        return PageOutcome(
            url=url,
            result=result,
            http_status=last_status,
            attempts=attempts,
        )

    return PageOutcome(
        url=url,
        error=last_error,
        http_status=last_status,
        attempts=attempts,
        retryable=True,
    )


@dataclass
class CrawlOutcome:
    crawl_doc: dict[str, Any]
    exit_code: int
    reason: str = ""


@dataclass
class _Totals:
    pages_saved: int = 0
    total_bytes: int = 0
    skipped: Counter = field(default_factory=Counter)
    segments: Counter = field(default_factory=Counter)


class Crawler:
    """Owns the frontier, the seen set, storage, and the page records.

    Worker threads only fetch. Everything that mutates run state happens
    here, on the main thread, so the records and crawl.json are always on the same page.
    """

    def __init__(
        self,
        settings: CrawlSettings,
        *,
        store: Any,
        fetcher_factory: Callable[[], Any] | None = None,
        url_fetch: Callable[[str], tuple[int, bytes]] = fetch_url,
        resolve_url: Callable[[str], str] = resolve_final_url,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], str] = utc_timestamp,
        facts: StrategyFacts | None = None,
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.settings = settings
        self.store = store
        self.url_fetch = url_fetch
        self.sleep = sleep
        self.uniform = uniform
        self.monotonic = monotonic
        self.now = now
        self.fetcher_factory = fetcher_factory or playwright_fetcher_factory()
        self.facts = facts or strategy_facts(settings.strategy)

        # The frontier is the crawl's queue: URLs found but not fetched yet.
        self.frontier: deque[str] = deque()
        self.seen: set[str] = set()
        self.saved: list[str] = []
        self._saved_set: set[str] = set()
        self.failed: dict[str, dict[str, Any]] = {}
        self.totals = _Totals()

        self.resolve_url = resolve_url
        self.resolved_seed_url = settings.seed_url
        self.host_aliases: set[str] = set()
        self.scope = Scope.from_seed(
            settings.seed_url,
            scope_prefix=settings.scope_prefix,
            include_regex=settings.include_regex,
            exclude_regex=settings.exclude_regex,
        )
        self.robots_status: int | None = None
        self.robots_crawl_delay: float | None = None
        self.effective_min_interval = settings.min_interval_in_seconds
        self.sitemap_urls_found = 0
        self.site_index: CurriqunetIndex | None = None

        self.resolved_host_differs = False

        self.started_at = self.now()
        self._started_mono = self.monotonic()
        self._saves_since_progress = 0
        self._consecutive_failures = 0
        self._skips_logged: set[tuple[str, str]] = set()
        self._in_flight: dict[Future, str] = {}
        self.cache_stems: set[str] = set()
        self.pages_copied = 0
        self.pages_fetched = 0
        self.stopped = False

    def _html_key(self, url: str) -> str:
        return page_html_key(
            self.settings.catalog_folder, self.settings.run_id, page_stem(url)
        )

    def _meta_key(self, url: str) -> str:
        return page_meta_key(
            self.settings.catalog_folder, self.settings.run_id, page_stem(url)
        )

    def _run_key(self, maker: Callable[[str, str], str]) -> str:
        return maker(self.settings.catalog_folder, self.settings.run_id)

    def _skip(self, url: str, reason: str) -> None:
        self.totals.skipped[reason] += 1
        level = logging.DEBUG if reason in QUIET_REASONS else logging.INFO
        if level == logging.INFO:
            seen_before = (dedupe_key(url), reason)
            if seen_before in self._skips_logged:
                level = logging.DEBUG
            else:
                self._skips_logged.add(seen_before)
        logger.log(level, "SKIP %s reason=%s", url, reason)

    def enqueue(self, url: str, *, operator_seed: bool = False) -> bool:
        """Add a URL to the frontier when it is in scope and new.

        An operator seed (--url, --seed-urls-file) skips --include-regex and
        --exclude-regex: those narrow what a crawl follows, and a seed that
        does not match its own filter would leave nothing to start from. It
        still has to be the same host, inside the scope prefix, and allowed
        by robots.txt.
        """
        url = self.canonical_url(url)
        scope = self.scope
        if operator_seed:
            scope = Scope(
                host=scope.host,
                path_prefix=scope.path_prefix,
                robots=scope.robots,
            )
        reason = scope.rejection(url)
        if reason is not None:
            self._skip(url, reason)
            return False
        key = dedupe_key(url)
        if key in self.seen:
            self._skip(url, REASON_DUPLICATE)
            return False
        self.seen.add(key)
        self.frontier.append(url)
        self.totals.segments[first_path_segment(url)] += 1
        return True

    def _follow(
        self, html: str, base_url: str, page_url: str, *, replay: bool = False
    ) -> None:

        queue_list_pages(html, page_url, enqueue=self.enqueue, quiet=replay)
        for link in extract_links(html, base_url):
            self.enqueue(link)

    def resolve_entry_point(self) -> str:
        """Follow the seed URL to the host that answers, and scope to it.

        Skipping this made a renamed college uncrawlable: every page was
        fetched and then dropped as an off-site redirect.
        """
        resolved = self.resolve_url(self.settings.seed_url)
        self.resolved_seed_url = resolved
        typed_host = self.scope.host
        answering_host = (urlsplit(resolved).hostname or "").lower()
        if not answering_host or answering_host == typed_host:
            return resolved
        self.resolved_host_differs = True
        logger.warning(
            "ENTRY %s answers as %s, so the crawl follows %s",
            self.settings.seed_url,
            resolved,
            answering_host,
        )
        logger.warning(
            "FOLDER %s is named after the typed host %s, but the pages come "
            "from %s. The folder name is kept as typed so the run id stays "
            "stable; crawl.json records resolved_seed_url %s and "
            "catalog_folder_matches_resolved_host false.",
            self.settings.catalog_folder,
            typed_host,
            answering_host,
            resolved,
        )
        self.scope = Scope.from_seed(
            resolved,
            scope_prefix=self.settings.scope_prefix,
            include_regex=self.settings.include_regex,
            exclude_regex=self.settings.exclude_regex,
        )
        self.host_aliases.add(typed_host)
        self._recanonicalize()
        return resolved

    def _warn_when_scope_is_not_the_site_root(self, seed_url: str) -> None:
        """A narrowed scope is a choice, so it is never made silently.

        A --url with a path crawls that section and nothing above it,
        which is right when it is meant and invisible when it is not.
        """
        prefix = self.scope.path_prefix
        if prefix == "/":
            return
        parsed = urlsplit(seed_url)
        root = f"{parsed.scheme or 'https'}://{parsed.netloc}/"
        logger.warning(
            "SCOPE the scope prefix is %s, so only that part of the catalog "
            "will be crawled; pass --scope-prefix %s to crawl all of it",
            prefix,
            root,
        )

    def canonical_url(self, url: str) -> str:
        """Rewrite a known alias host to the host that answers.

        A renamed college keeps serving the old name, and its sitemap often
        still lists it. Treating the old host as an alias rather than as a
        different site is what keeps those pages in the crawl, and keeps one
        page from being saved twice under two names.
        """
        if not self.host_aliases:
            return url
        parsed = urlsplit(url)
        if (parsed.hostname or "").lower() not in self.host_aliases:
            return url
        host = self.scope.host
        netloc = host if parsed.port is None else f"{host}:{parsed.port}"
        return urlunsplit(parsed._replace(netloc=netloc))

    def _recanonicalize(self) -> None:
        """Move whatever is already queued onto the host that answers."""
        self.frontier = deque(self.canonical_url(url) for url in self.frontier)
        self.saved = [self.canonical_url(url) for url in self.saved]
        self._saved_set = set(self.saved)
        self.seen = {
            dedupe_key(self.canonical_url(f"//{key}")) for key in self.seen
        }

    def read_site_rules(self, seed_url: str) -> list[str]:
        """robots.txt and the sitemaps. Returns the page URLs they declare."""
        rules = read_robots(seed_url, fetch=self.url_fetch)
        self.robots_status = rules.robots_status
        self.robots_crawl_delay = rules.crawl_delay
        self.scope = self.scope.with_robots(rules.robots)
        self.effective_min_interval = max(
            self.settings.min_interval_in_seconds, rules.crawl_delay or 0.0
        )
        documents = list(rules.sitemap_urls)
        default = default_sitemap_url(seed_url)
        if default not in documents:
            documents.append(default)
        pages = collect_sitemap_urls(documents, fetch=self.url_fetch)
        self.sitemap_urls_found = len(pages)
        return pages

    def read_site_index(self, seed_url: str) -> list[str]:
        """The page index a catalog's seed page declares, as page URLs.

        A CurriQunet catalog has no sitemap and no href links; its shell
        names the JSON tree its script navigates by, and that tree is the
        catalog's list of its pages. For any other site this is one GET of
        the seed URL and an empty list.

        That GET is of a page, not of a site document, so robots.txt has a
        say: a seed it disallows is not read here either.
        """
        robots = self.scope.robots
        if robots is not None and not robots.can_fetch("*", seed_url):
            logger.info(
                "INDEX %s is disallowed by robots.txt, no site index read",
                seed_url,
            )
            self.site_index = None
            return []
        self.site_index = read_curriqunet_index(
            seed_url,
            fetch=self.url_fetch,
            pause=lambda: self.sleep(INDEX_INTERVAL_SECONDS),
        )
        return list(self.site_index.urls) if self.site_index else []

    def locked_scope(self) -> LockedScope:
        """What this command says the run is, in the manifest's terms."""
        return LockedScope(
            seed_url=self.settings.seed_url,
            scope_prefix=self.settings.scope_prefix or "",
            include_regex=tuple(self.settings.include_regex),
            exclude_regex=tuple(self.settings.exclude_regex),
            seed_urls=tuple(self.settings.seed_urls),
            strategy=self.settings.strategy,
        )

    def _run_label(self, run_id: str | None = None) -> str:
        return (
            f"{run_id_for_json(run_id or self.settings.run_id)} of "
            f"{self.settings.catalog_folder}"
        )

    def _next_run_hint(self) -> str:
        return f"--from-run-id {run_id_for_json(self.settings.run_id)}"

    def refuse_an_existing_run(self) -> None:
        prefix = run_prefix(self.settings.catalog_folder, self.settings.run_id)
        if not self.store.list_keys(under=prefix):
            return
        raise RunExistsError(
            f"run {self._run_label()} already exists, and a run is never "
            "continued in place. Start a new run that copies its saved "
            f"pages instead of fetching them: {self._next_run_hint()}, "
            "with a new --run-id or none."
        )

    def write_manifest(self) -> None:
        doc = manifest_doc(
            catalog_folder=self.settings.catalog_folder,
            run_id=run_id_for_json(self.settings.run_id),
            created_at=self.now(),
            from_run_id=(
                run_id_for_json(self.settings.from_run_id)
                if self.settings.from_run_id
                else None
            ),
            locked=self.locked_scope(),
            crawl_schema=CRAWL_SCHEMA,
        )
        self.started_at = doc["created_at"]
        key = self._run_key(manifest_key)
        try:
            self.store.put_new_json(key, doc)
        except FileExistsError as exc:
            raise RunExistsError(
                f"run {self._run_label()} was started by another crawl "
                "while this one was starting."
            ) from exc
        logger.info("MANIFEST %s written", key)

    # -- the cache: an earlier run's saved pages ---------------------------

    def _check_strategy(self, previous: Any, cache_run: str) -> None:
        """A run's pages all come from one backend, copied ones included.

        Two backends render differently. A folder holding pages from both
        is not one crawl of one catalog, and nothing downstream could tell
        which page came from which.
        """
        recorded = str(previous or "").strip()
        if not recorded or recorded == self.settings.strategy:
            return
        raise StrategyMismatchError(
            f"run {self._run_label(cache_run)} was crawled with "
            f"--with-{recorded}, and this run asked for "
            f"--with-{self.settings.strategy}. A run's pages come from one "
            "backend, so it cannot copy another backend's pages. Use "
            f"--with-{recorded}, or leave out --from-run-id to fetch "
            "everything again."
        )

    def _cache_strategy(self, cache_run: str) -> Any:
        """The backend the earlier run used, from its manifest or report."""
        folder = self.settings.catalog_folder
        key = manifest_key(folder, cache_run)
        if self.store.exists(key):
            try:
                doc = self.store.get_json(key)
            except ValueError as exc:
                raise ManifestError(f"{key} cannot be read: {exc}") from exc
            return read_locked(doc, key=key).strategy
        report = crawl_key(folder, cache_run)
        if self.store.exists(report):
            try:
                doc = self.store.get_json(report)
            except ValueError:
                return None
            return doc.get("strategy") if isinstance(doc, dict) else None
        return None

    def open_cache(self) -> None:
        cache_run = self.settings.from_run_id
        if not cache_run:
            return
        folder = self.settings.catalog_folder
        prefix = pages_prefix(folder, cache_run)
        names = {
            key[len(prefix) + 1 :] for key in self.store.list_keys(under=prefix)
        }
        stems = {
            name[: -len(".meta.json")]
            for name in names
            if "/" not in name and name.endswith(".meta.json")
        }
        self.cache_stems = {stem for stem in stems if f"{stem}.html" in names}
        has_report = self.store.exists(crawl_key(folder, cache_run))
        if not self.cache_stems and not has_report:
            raise ManifestError(
                f"--from-run-id: run {self._run_label(cache_run)} has no "
                f"saved pages and no crawl.json under {prefix}. Check the "
                "run id against the folders under the catalog folder."
            )
        self._check_strategy(self._cache_strategy(cache_run), cache_run)
        logger.info(
            "CACHE run %s saved %s pages; each is copied when the crawl "
            "reaches it, instead of fetched",
            run_id_for_json(cache_run),
            len(self.cache_stems),
        )

    def _from_cache(self, url: str) -> bool:
        """Copy the earlier run's copy of this page, if it has a good one.

        True when the page is now saved in this run. A cached page that is
        a bot challenge, or whose sidecar cannot be read, is fetched again.
        """
        stem = page_stem(url)
        if stem not in self.cache_stems:
            return False
        self.cache_stems.discard(stem)
        cache_run = str(self.settings.from_run_id)
        folder = self.settings.catalog_folder
        html = self.store.get_text(page_html_key(folder, cache_run, stem))
        kind = challenge_kind(None, None, html)
        if kind is not None:
            logger.warning(
                "REFETCH %s the page run %s saved is a bot challenge (%s), "
                "not the catalog page, so it is fetched again",
                url,
                run_id_for_json(cache_run),
                kind,
            )
            return False
        try:
            meta = self.store.get_json(page_meta_key(folder, cache_run, stem))
        except ValueError:
            meta = None
        if not isinstance(meta, dict):
            logger.warning(
                "REFETCH %s the sidecar run %s saved cannot be read, so the "
                "page is fetched again",
                url,
                run_id_for_json(cache_run),
            )
            return False

        html_key = self._html_key(url)
        copied = dict(meta)
        copied.update(
            {
                "result": RESULT_SAVED,
                "stem": stem,
                "html_key": html_key,
                "html_path": join_storage_uri(
                    self.settings.target_uri, html_key
                ),
                "copied_from_run": run_id_for_json(cache_run),
                "copied_at": self.now(),
            }
        )
        self._write_page(url, html, copied)
        size = len(html.encode("utf-8"))
        self._count_saved(url, size)
        self.pages_copied += 1
        logger.info(
            "COPY %s (saved by run %s, no GET)",
            url,
            run_id_for_json(cache_run),
        )
        self._follow(html, url, url, replay=True)
        self._maybe_progress()
        return True

    def _count_saved(self, url: str, size: int) -> None:
        if url not in self._saved_set:
            self._saved_set.add(url)
            self.saved.append(url)
        self.totals.pages_saved += 1
        self.totals.total_bytes += size
        self._saves_since_progress += 1

    def _write_page(self, url: str, html: str, meta: dict[str, Any]) -> None:
        """The page, then its sidecar. The sidecar says the page is whole."""
        html_key = self._html_key(url)
        try:
            self.store.put_new_text(html_key, html, "text/html; charset=utf-8")
            self.store.put_new_json(self._meta_key(url), meta)
        except Exception as exc:
            self.frontier.appendleft(url)
            raise RunStopError(
                f"storage refused a write of {html_key}: {exc}"
            ) from exc

    def _write_record(self, key: str, doc: dict[str, Any]) -> None:
        try:
            self.store.put_new_json(key, doc)
        except Exception as exc:
            raise RunStopError(
                f"storage refused the record {key}: {exc}"
            ) from exc

    def _save(self, result: FetchResult, attempts: int) -> None:
        body = result.html.encode("utf-8")
        stem = page_stem(result.requested_url)
        html_key = self._html_key(result.requested_url)
        meta = {
            "result": RESULT_SAVED,
            "requested_url": result.requested_url,
            "final_url": result.final_url,
            "http_status": result.http_status,
            "content_type": result.content_type,
            "bytes": len(body),
            "latency_ms": result.latency_ms,
            "retrieved_at": self.now(),
            "attempts": attempts,
            "sha256": hashlib.sha256(body).hexdigest(),
            "stem": stem,
            # Where this stem's page is, whole, so a sidecar read on its
            # own says where to find the bytes it describes. It is the
            # URI this run wrote to, so it is right until someone copies
            # the run somewhere else; `stem` is what every later stage
            # keys on, and it survives the copy.
            "html_key": html_key,
            "html_path": join_storage_uri(self.settings.target_uri, html_key),
            "strategy": self.settings.strategy,
        }
        if result.render is not None:
            # How the backend decided the page was ready, so a page taken
            # at a wait's cap rather than at its signal can be found later.
            meta["render"] = result.render
        self._write_page(result.requested_url, result.html, meta)
        self._count_saved(result.requested_url, len(body))
        self.pages_fetched += 1
        self._consecutive_failures = 0
        logger.info(
            "GET %s -> %s %s bytes %s ms -> %s",
            result.requested_url,
            result.http_status,
            len(body),
            result.latency_ms,
            join_storage_uri(self.settings.target_uri, html_key),
        )
        self._follow(
            result.html,
            result.final_url or result.requested_url,
            result.requested_url,
        )
        self._maybe_progress()

    def _fail(
        self,
        url: str,
        error: str,
        *,
        http_status: int | None,
        attempts: int,
        retryable: bool,
    ) -> None:
        kind = failure_kind(http_status)
        stem = page_stem(url)
        record = {
            "result": RESULT_FAILED_RETRYABLE if retryable else RESULT_FAILED,
            "url": url,
            "error": error,
            "http_status": http_status,
            "attempts": attempts,
            "retryable": retryable,
            "kind": kind,
            "at": self.now(),
            "stem": stem,
            "strategy": self.settings.strategy,
        }
        self.failed[url] = record
        logger.warning("FAIL %s after %s attempts: %s", url, attempts, error)
        self._write_record(
            failed_meta_key(
                self.settings.catalog_folder, self.settings.run_id, stem
            ),
            record,
        )
        self._count_failure(kind)
        self._maybe_progress()

    def _count_failure(self, kind: str) -> None:
        if kind == FAILURE_PAGE:
            return
        self._consecutive_failures += 1
        limit = self.settings.max_consecutive_failures
        if self._consecutive_failures >= limit:
            self.stopped = True
            logger.error(
                "STOP %s blocking failures in a row (401, 403, 429, 5xx, "
                "challenge pages, network errors; --max-consecutive-failures "
                "%s). The site is probably blocking this crawl, so the run "
                "is left incomplete.",
                self._consecutive_failures,
                limit,
            )

    def handle_outcome(self, outcome: PageOutcome) -> None:
        url = outcome.url
        if outcome.result is None:
            if outcome.reason:
                self._skip_fetched(url, outcome.reason)
                return
            self._fail(
                url,
                outcome.error or "fetch failed",
                http_status=outcome.http_status,
                attempts=outcome.attempts,
                retryable=outcome.retryable,
            )
            return

        result = outcome.result
        status = result.http_status
        if status is None or status >= 400:
            self._fail(
                url,
                f"HTTP {status}",
                http_status=status,
                attempts=outcome.attempts,
                retryable=False,
            )
            return
        if not content_type_is_html(result.content_type):
            self._skip_fetched(url, REASON_NON_HTML, http_status=status)
            return

        # Only a real redirect is re-tested. A URL that landed where it was
        # asked to already passed the scope test that let it in, and an
        # operator seed is allowed to sit outside its own --include-regex.
        final_url = result.final_url or url
        if dedupe_key(final_url) != dedupe_key(url):
            self.seen.add(dedupe_key(final_url))
            if self.scope.rejection(final_url) is not None:
                self._skip_fetched(
                    url,
                    REASON_REDIRECT_OUT_OF_SCOPE,
                    http_status=status,
                    final_url=final_url,
                )
                return
        self.failed.pop(url, None)
        self._save(result, outcome.attempts)

    def _skip_fetched(self, url: str, reason: str, **fields: Any) -> None:
        self._skip(url, reason)
        stem = page_stem(url)
        self._write_record(
            skipped_meta_key(
                self.settings.catalog_folder, self.settings.run_id, stem
            ),
            {
                "result": RESULT_SKIPPED,
                "url": url,
                "reason": reason,
                **fields,
                "at": self.now(),
                "stem": stem,
                "strategy": self.settings.strategy,
            },
        )
        self._consecutive_failures = 0
        self._maybe_progress()

    def _progress(self) -> None:
        elapsed = self.monotonic() - self._started_mono
        eta = (
            len(self.frontier)
            * self.effective_min_interval
            / max(1, self.settings.concurrency_limit)
        )
        logger.info(
            "PROGRESS saved=%s copied=%s failed=%s skipped=%s frontier=%s "
            "elapsed=%s eta=%s",
            self.totals.pages_saved,
            self.pages_copied,
            len(self.failed),
            sum(self.totals.skipped.values()),
            len(self.frontier),
            format_duration(elapsed),
            format_duration(eta),
        )

    def _failed_by_status(self) -> dict[str, int]:
        counts: Counter = Counter()
        for record in self.failed.values():
            status = record.get("http_status")
            counts[str(status) if status else "error"] += 1
        return dict(sorted(counts.items()))

    def crawl_doc(self, status: str, *, finished: bool) -> dict[str, Any]:
        segments = self.totals.segments.most_common(TOP_PATH_SEGMENTS)
        stamp = self.now()
        return {
            "schema": CRAWL_SCHEMA,
            "catalog_folder": self.settings.catalog_folder,
            "run_id": run_id_for_json(self.settings.run_id),
            "seed_url": self.settings.seed_url,
            "resolved_seed_url": self.resolved_seed_url,
            "catalog_folder_matches_resolved_host": (
                not self.resolved_host_differs
            ),
            "scope_prefix": self.scope.path_prefix,
            "include_regex": list(self.settings.include_regex),
            "exclude_regex": list(self.settings.exclude_regex),
            "strategy": self.settings.strategy,
            "strategy_version": dict(self.facts.version),
            "strategy_settings": dict(self.facts.settings),
            "strategy_notes": list(self.facts.notes),
            "started_at": self.started_at,
            "updated_at": stamp,
            "finished_at": stamp if finished else None,
            "status": status,
            "limit": self.settings.limit,
            "concurrency_limit": self.settings.concurrency_limit,
            "max_consecutive_failures": (
                self.settings.max_consecutive_failures
            ),
            "min_interval_in_seconds": self.settings.min_interval_in_seconds,
            "max_interval_in_seconds": self.settings.max_interval_in_seconds,
            "pacing_jitter_fraction": self.settings.pacing_jitter_fraction,
            "pacing": "one clock per worker",
            "robots_status": self.robots_status,
            "robots_crawl_delay": self.robots_crawl_delay,
            "effective_min_interval_in_seconds": self.effective_min_interval,
            "sitemap_urls_found": self.sitemap_urls_found,
            # The page index the seed declared and what reading it cost, or
            # null for a site that declares none, which is most of them.
            "site_index": (
                self.site_index.to_json() if self.site_index else None
            ),
            "frontier_order": FRONTIER_ORDER,
            "from_run_id": (
                run_id_for_json(self.settings.from_run_id)
                if self.settings.from_run_id
                else None
            ),
            "pages_saved": self.totals.pages_saved,
            "pages_copied": self.pages_copied,
            "pages_fetched": self.pages_fetched,
            "pages_failed": len(self.failed),
            "failed_by_status": self._failed_by_status(),
            "skipped_by_reason": dict(sorted(self.totals.skipped.items())),
            "frontier_remaining": len(self.frontier) + len(self._in_flight),
            "total_bytes": self.totals.total_bytes,
            "discovered_by_first_path_segment": dict(segments),
        }

    def write_report(self, doc: dict[str, Any]) -> None:
        try:
            self.store.put_json(self._run_key(crawl_key), doc)
        except Exception as exc:
            raise RunStopError(
                f"storage refused the run report: {exc}"
            ) from exc

    def report(self, status: str, *, finished: bool = False) -> dict[str, Any]:
        doc = self.crawl_doc(status, finished=finished)
        self.write_report(doc)
        return doc

    def _maybe_progress(self) -> None:
        """A PROGRESS line after every REPORT_EVERY saved pages."""
        if self._saves_since_progress >= REPORT_EVERY:
            self._saves_since_progress = 0
            self._progress()

    def _limit_blocks(self, in_flight: int) -> bool:
        limit = self.settings.limit
        return (
            limit is not None and self.totals.pages_saved + in_flight >= limit
        )

    def work(self, pool: WorkerPool, policy: FetchPolicy) -> str:
        in_flight = self._in_flight
        limit_reached = False
        while True:
            while (
                self.frontier
                and not limit_reached
                and not self.stopped
                and len(in_flight) < self.settings.concurrency_limit
            ):
                url = self.frontier.popleft()
                if self._limit_blocks(len(in_flight)):
                    self.frontier.appendleft(url)
                    limit_reached = True
                    break
                if self._from_cache(url):
                    continue
                in_flight[pool.submit(fetch_page, url, policy)] = url

            if not in_flight:
                if self.stopped:
                    return STATUS_INCOMPLETE
                if limit_reached:
                    return STATUS_LIMIT_REACHED
                return STATUS_COMPLETE

            done, _ = wait_for_futures(
                set(in_flight),
                timeout=POLL_SECONDS,
                return_when=FIRST_COMPLETED,
            )
            for future in done:
                url = in_flight.pop(future)
                error = future.exception()
                if error is not None:
                    if isinstance(error, FetcherStartError):
                        self.frontier.appendleft(url)
                        raise RunStopError(str(error)) from error
                    self._fail(
                        url,
                        str(error) or error.__class__.__name__,
                        http_status=None,
                        attempts=1,
                        retryable=True,
                    )
                    continue
                self.handle_outcome(future.result())

    def run(self) -> CrawlOutcome:
        self.refuse_an_existing_run()
        self.open_cache()
        self.write_manifest()
        seed_url = self.resolve_entry_point()
        self._warn_when_scope_is_not_the_site_root(seed_url)
        sitemap_pages = self.read_site_rules(seed_url)
        index_pages = self.read_site_index(seed_url)
        self.enqueue(seed_url, operator_seed=True)
        for url in sitemap_pages + index_pages:
            self.enqueue(url)
        for url in self.settings.seed_urls:
            self.enqueue(url, operator_seed=True)

        policy = FetchPolicy(
            min_interval=self.effective_min_interval,
            max_interval=self.settings.max_interval_in_seconds,
            max_retries=self.settings.max_retries,
            jitter_fraction=self.settings.pacing_jitter_fraction,
            uniform=self.uniform,
        )
        pool = WorkerPool(
            workers=self.settings.concurrency_limit,
            fetcher_factory=self.fetcher_factory,
            min_interval=self.effective_min_interval,
            sleep=self.sleep,
            jitter_fraction=self.settings.pacing_jitter_fraction,
            max_interval=self.settings.max_interval_in_seconds,
            uniform=self.uniform,
            monotonic=self.monotonic,
        )
        interrupted = False
        stop_reason = ""
        try:
            status = self.work(pool, policy)
        except KeyboardInterrupt:
            interrupted = True
            status = STATUS_INCOMPLETE
            logger.warning(
                "INTERRUPTED writing crawl.json; continue with a new run: %s",
                self._next_run_hint(),
            )
            # Now, not only after the browsers close: closing waits for the
            # fetch in flight, pacing sleep included, and the process can be
            # killed during that wait.
            try:
                self.report(status)
            except RunStopError as exc:
                logger.error("REPORT %s", exc)
        except RunStopError as exc:
            status = STATUS_INCOMPLETE
            stop_reason = str(exc)
            logger.error(
                "STOP %s. Nothing more is fetched; fix it and start a new "
                "run with %s.",
                stop_reason,
                self._next_run_hint(),
            )
        finally:
            pool.close()

        try:
            doc = self.report(status, finished=not interrupted)
        except RunStopError as exc:
            logger.error("REPORT %s", exc)
            doc = self.crawl_doc(status, finished=False)
            stop_reason = stop_reason or str(exc)
        self._progress()
        if stop_reason:
            return CrawlOutcome(
                crawl_doc=doc,
                exit_code=1,
                reason=(
                    f"stopped: {stop_reason}. Fix it and start a new run "
                    f"with {self._next_run_hint()}."
                ),
            )
        return CrawlOutcome(
            crawl_doc=doc,
            exit_code=_exit_code(status, len(self.failed), interrupted),
            reason=_exit_reason(
                status,
                len(self.failed),
                interrupted,
                next_run=self._next_run_hint(),
            ),
        )


def _exit_code(status: str, pages_failed: int, interrupted: bool) -> int:
    if interrupted:
        return EXIT_INTERRUPTED
    if status in {STATUS_COMPLETE, STATUS_LIMIT_REACHED} and pages_failed == 0:
        return 0
    return 1


def _exit_reason(
    status: str, pages_failed: int, interrupted: bool, *, next_run: str
) -> str:
    if interrupted:
        return f"interrupted, crawl.json written; continue with {next_run}"
    if status == STATUS_INCOMPLETE:
        return (
            "crawl stopped before the frontier emptied; continue with "
            f"{next_run}"
        )
    if pages_failed:
        return (
            f"{pages_failed} page(s) failed, see pages/failed/ or "
            "xtra catalog crawl summary --failed"
        )
    return ""


def run_crawl(settings: CrawlSettings, **kwargs: Any) -> CrawlOutcome:
    """Crawl one catalog into object storage and report how it went."""
    return Crawler(settings, **kwargs).run()
