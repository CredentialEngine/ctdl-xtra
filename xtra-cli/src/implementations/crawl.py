"""Download a catalog and save it. Nothing else.

The crawler renders a page, writes the HTML and a sidecar, follows links,
and stops when the frontier empties or --limit is reached. It does not
detect a CMS family, name an institution, choose templates, or normalize
text. Those belong to discovery and extraction, which read what the crawler
saved.

Crawling a catalog is a rare, one-time job. An incomplete crawl means doing
it again, so the run keeps a checkpoint it can resume from and reports
plainly whether it finished.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter, deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future
from concurrent.futures import wait as wait_for_futures
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from common.clock import run_id_for_json, utc_timestamp
from common.keys import (
    crawl_key,
    dedupe_key,
    failed_key,
    page_html_key,
    page_meta_key,
    page_stem,
    state_key,
)
from common.polite import backoff_delay
from common.storage_uri import join_storage_uri
from implementations.crawl_browser import (
    FetchError,
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
STATE_SCHEMA = "xtra-crawl-state-1"

STATUS_COMPLETE = "complete"
STATUS_LIMIT_REACHED = "limit_reached"
STATUS_INCOMPLETE = "incomplete"

CHECKPOINT_EVERY = 25
MAX_CONSECUTIVE_FAILURES = 20
POLL_SECONDS = 1.0
TOP_PATH_SEGMENTS = 20
EXIT_INTERRUPTED = 130

# --url first, then the sitemap, then the site's own page index (a
# CurriQunet catalog's navigation tree), then --seed-urls-file, then links
# in document order. Both declarations are the site's list of its pages, so
# they come ahead of anything found on the way. Recorded so a run says
# which rule ordered its frontier.
FRONTIER_ORDER = "sitemap_first"

# Index documents are small JSON, and like sitemap documents they are not
# paced by --min-interval-in-seconds. Half a second keeps the walk gentler
# than the page renders it replaces, each of which fires ~20 XHRs.
INDEX_INTERVAL_SECONDS = 0.5


class StrategyMismatchError(RuntimeError):
    """A resume that would mix two rendered sources in one run folder."""


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


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

    def __post_init__(self) -> None:
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
    """What a worker needs to pace and retry one URL on its own thread."""

    min_interval: float
    max_interval: float
    max_retries: int
    sleep: Callable[[float], None] = time.sleep


@dataclass(frozen=True)
class PageOutcome:
    url: str
    result: FetchResult | None = None
    error: str = ""
    http_status: int | None = None
    attempts: int = 0
    retryable: bool = False
    reason: str | None = None


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
            )
            logger.info(
                "RETRY %s attempt %s of %s after %s, waiting %s s",
                url,
                attempt + 1,
                total_attempts,
                last_error,
                format_seconds(delay),
            )
            policy.sleep(delay)
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
        # Spent retries leave it retryable, so a resume asks again.
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
    """Owns the frontier, the seen set, storage, and the checkpoints.

    Worker threads only fetch. Everything that mutates run state happens
    here, on the main thread, so a checkpoint is always a consistent view.
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
    ) -> None:
        self.settings = settings
        self.store = store
        self.url_fetch = url_fetch
        self.sleep = sleep
        self.monotonic = monotonic
        self.now = now
        self.fetcher_factory = fetcher_factory or playwright_fetcher_factory()
        self.facts = facts or strategy_facts(settings.strategy)

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
        self._next_checkpoint = CHECKPOINT_EVERY
        self._first_page_checkpointed = False
        self._consecutive_failures = 0
        self.stopped = False
        self.resumed = False

    # -- keys -------------------------------------------------------------

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

    # -- frontier ---------------------------------------------------------

    def _skip(self, url: str, reason: str) -> None:
        self.totals.skipped[reason] += 1
        level = logging.DEBUG if reason in QUIET_REASONS else logging.INFO
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

    def _requeue(self, url: str) -> None:
        """Put a URL back without the duplicate test, for a resume."""
        url = self.canonical_url(url)
        self.seen.add(dedupe_key(url))
        self.frontier.append(url)

    def _follow(self, html: str, base_url: str) -> None:
        for link in extract_links(html, base_url):
            self.enqueue(link)

    # -- site declarations -------------------------------------------------

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

    # -- resume ------------------------------------------------------------

    def _check_strategy(self, previous: Any) -> None:
        """One run folder is one backend, so a resume may not change it.

        Two backends render differently. A folder holding pages from both
        is not one crawl of one catalog, and nothing downstream could tell
        which page came from which.
        """
        recorded = str(previous or "").strip()
        if not recorded or recorded == self.settings.strategy:
            return
        raise StrategyMismatchError(
            f"run {run_id_for_json(self.settings.run_id)} of "
            f"{self.settings.catalog_folder} was crawled with "
            f"--with-{recorded}, and this run asked for "
            f"--with-{self.settings.strategy}. One run folder must not mix "
            f"rendered sources. Continue it with --with-{recorded}, or "
            "start a new --run-id."
        )

    def load_state(self) -> bool:
        key = self._run_key(state_key)
        if not self.store.exists(key):
            return False
        payload = self.store.get_json(key)
        self._check_strategy(payload.get("strategy"))
        self.seen = set(payload.get("seen") or ())
        self.saved = list(payload.get("saved") or ())
        self._saved_set = set(self.saved)
        self.totals.pages_saved = int(payload.get("pages_saved") or 0)
        self.totals.total_bytes = int(payload.get("total_bytes") or 0)
        self.totals.skipped = Counter(payload.get("skipped_by_reason") or {})
        self.totals.segments = Counter(
            payload.get("discovered_by_first_path_segment") or {}
        )
        self.started_at = payload.get("started_at") or self.started_at
        self._next_checkpoint = self.totals.pages_saved + CHECKPOINT_EVERY

        # Saved pages first: they answer from storage, so a resume re-follows
        # their links without a single GET.
        for url in self.saved:
            self._requeue(url)
        for url in payload.get("frontier") or ():
            self._requeue(url)
        for record in payload.get("failed") or ():
            url = record.get("url")
            if not url:
                continue
            if record.get("retryable"):
                self._requeue(url)
            else:
                self.failed[url] = record
        if not (self.saved or self.frontier or self.failed):
            # The manifest written at startup, before the first page. There
            # is nothing to resume from, so this is still a fresh run and
            # the seed URL still has to be queued.
            return False
        self.resumed = True
        logger.info(
            "RESUME %s saved=%s frontier=%s failed=%s",
            self._run_key(state_key),
            self.totals.pages_saved,
            len(self.frontier),
            len(self.failed),
        )
        return True

    def _replay_from_storage(self, url: str) -> bool:
        """Read a page this run already saved instead of fetching it again."""
        key = self._html_key(url)
        if not self.store.exists(key):
            return False
        html = self.store.get_text(key)
        logger.info("FROM-STORAGE %s (already saved, no GET)", url)
        if url not in self._saved_set:
            self._saved_set.add(url)
            self.saved.append(url)
            self.totals.pages_saved += 1
        self._consecutive_failures = 0
        self._follow(html, url)
        self._maybe_checkpoint()
        return True

    def _sitemap_first(self, declared_pages: list[str]) -> None:
        """On a resume, move declared pages ahead of the old frontier.

        Declared means the sitemap and the site's page index. A resumed run
        reads its frontier back in the order it was left, so links found
        inside one section would be fetched for days before the site's own
        index of its content pages was reached again. Pages this run
        already saved stay in front of both: they answer from storage and
        cost no GET.
        """
        if not declared_pages:
            return
        declared = {
            dedupe_key(self.canonical_url(url)) for url in declared_pages
        }
        saved: list[str] = []
        listed: list[str] = []
        rest: list[str] = []
        for url in self.frontier:
            if url in self._saved_set:
                saved.append(url)
            elif dedupe_key(url) in declared:
                listed.append(url)
            else:
                rest.append(url)
        self.frontier = deque(saved + listed + rest)

    # -- results -----------------------------------------------------------

    def _save(self, result: FetchResult, attempts: int) -> None:
        body = result.html.encode("utf-8")
        stem = page_stem(result.requested_url)
        html_key = self._html_key(result.requested_url)
        meta = {
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
        self.store.put_text(html_key, result.html, "text/html; charset=utf-8")
        self.store.put_json(self._meta_key(result.requested_url), meta)

        if result.requested_url not in self._saved_set:
            self._saved_set.add(result.requested_url)
            self.saved.append(result.requested_url)
        self.totals.pages_saved += 1
        self.totals.total_bytes += len(body)
        self._consecutive_failures = 0
        logger.info(
            "GET %s -> %s %s bytes %s ms -> %s",
            result.requested_url,
            result.http_status,
            len(body),
            result.latency_ms,
            join_storage_uri(self.settings.target_uri, html_key),
        )
        self._follow(result.html, result.final_url or result.requested_url)
        self._maybe_checkpoint()

    def _fail(
        self,
        url: str,
        error: str,
        *,
        http_status: int | None,
        attempts: int,
        retryable: bool,
    ) -> None:
        self.failed[url] = {
            "url": url,
            "error": error,
            "http_status": http_status,
            "attempts": attempts,
            "retryable": retryable,
            "at": self.now(),
        }
        logger.warning("FAIL %s after %s attempts: %s", url, attempts, error)
        self._consecutive_failures += 1
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self.stopped = True
            logger.error(
                "STOP %s URLs failed in a row. The site is probably blocking "
                "this crawl, so the run is checkpointed and left incomplete.",
                self._consecutive_failures,
            )

    def handle_outcome(self, outcome: PageOutcome) -> None:
        url = outcome.url
        if outcome.result is None:
            if outcome.reason:
                self._skip(url, outcome.reason)
                self._consecutive_failures = 0
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
            self._skip(url, REASON_NON_HTML)
            self._consecutive_failures = 0
            return

        # Only a real redirect is re-tested. A URL that landed where it was
        # asked to already passed the scope test that let it in, and an
        # operator seed is allowed to sit outside its own --include-regex.
        final_url = result.final_url or url
        if dedupe_key(final_url) != dedupe_key(url):
            self.seen.add(dedupe_key(final_url))
            if self.scope.rejection(final_url) is not None:
                self._skip(url, REASON_REDIRECT_OUT_OF_SCOPE)
                self._consecutive_failures = 0
                return
        self.failed.pop(url, None)
        self._save(result, outcome.attempts)

    # -- reporting ---------------------------------------------------------

    def _progress(self) -> None:
        elapsed = self.monotonic() - self._started_mono
        eta = (
            len(self.frontier)
            * self.effective_min_interval
            / max(1, self.settings.concurrency_limit)
        )
        logger.info(
            "PROGRESS saved=%s failed=%s skipped=%s frontier=%s elapsed=%s eta=%s",
            self.totals.pages_saved,
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
            "min_interval_in_seconds": self.settings.min_interval_in_seconds,
            "max_interval_in_seconds": self.settings.max_interval_in_seconds,
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
            "pages_saved": self.totals.pages_saved,
            "pages_failed": len(self.failed),
            "failed_by_status": self._failed_by_status(),
            "skipped_by_reason": dict(sorted(self.totals.skipped.items())),
            "frontier_remaining": len(self.frontier),
            "total_bytes": self.totals.total_bytes,
            "discovered_by_first_path_segment": dict(segments),
        }

    def _state_doc(self) -> dict[str, Any]:
        return {
            "schema": STATE_SCHEMA,
            "catalog_folder": self.settings.catalog_folder,
            "run_id": run_id_for_json(self.settings.run_id),
            "strategy": self.settings.strategy,
            "started_at": self.started_at,
            "updated_at": self.now(),
            "pages_saved": self.totals.pages_saved,
            "total_bytes": self.totals.total_bytes,
            "skipped_by_reason": dict(self.totals.skipped),
            "discovered_by_first_path_segment": dict(self.totals.segments),
            "frontier": list(self.frontier),
            "seen": sorted(self.seen),
            "saved": list(self.saved),
            "failed": list(self.failed.values()),
        }

    def checkpoint(
        self, status: str, *, finished: bool = False
    ) -> dict[str, Any]:
        """Write state.json, failed.jsonl, and crawl.json as one snapshot."""
        doc = self.crawl_doc(status, finished=finished)
        self.store.put_json(self._run_key(state_key), self._state_doc())
        lines = "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in self.failed.values()
        )
        self.store.put_text(
            self._run_key(failed_key), lines, "application/x-ndjson"
        )
        self.store.put_json(self._run_key(crawl_key), doc)
        return doc

    def _maybe_checkpoint(self) -> None:
        if self.totals.pages_saved < self._next_checkpoint:
            # The first page is worth a checkpoint of its own. A run killed
            # at page two used to leave saved pages that no manifest
            # described, which is not something a reader can recover from.
            if self.totals.pages_saved and not self._first_page_checkpointed:
                self._first_page_checkpointed = True
                self.checkpoint(STATUS_INCOMPLETE)
            return
        self._next_checkpoint = self.totals.pages_saved + CHECKPOINT_EVERY
        self._first_page_checkpointed = True
        self.checkpoint(STATUS_INCOMPLETE)
        self._progress()

    # -- the loop ----------------------------------------------------------

    def _limit_blocks(self, in_flight: int) -> bool:
        limit = self.settings.limit
        return (
            limit is not None and self.totals.pages_saved + in_flight >= limit
        )

    def work(self, pool: WorkerPool, policy: FetchPolicy) -> str:
        in_flight: dict[Future, str] = {}
        limit_reached = False
        while True:
            while (
                self.frontier
                and not limit_reached
                and not self.stopped
                and len(in_flight) < self.settings.concurrency_limit
            ):
                url = self.frontier.popleft()
                if self._replay_from_storage(url):
                    continue
                if self._limit_blocks(len(in_flight)):
                    self.frontier.appendleft(url)
                    limit_reached = True
                    break
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
                    self._fail(
                        url,
                        str(error) or error.__class__.__name__,
                        http_status=None,
                        attempts=1,
                        retryable=False,
                    )
                    continue
                self.handle_outcome(future.result())

    def run(self) -> CrawlOutcome:
        resumed = self.load_state()
        # Before the first GET, so a run that is hard-killed after two
        # pages still leaves a manifest saying what it was and that it did
        # not finish.
        self.checkpoint(STATUS_INCOMPLETE)
        self._first_page_checkpointed = self.totals.pages_saved > 0
        seed_url = self.resolve_entry_point()
        self._warn_when_scope_is_not_the_site_root(seed_url)
        sitemap_pages = self.read_site_rules(seed_url)
        index_pages = self.read_site_index(seed_url)
        # The sitemap and the page index are the site's own lists of its
        # content pages, so they are reached before any link found on the
        # way. A full run ends up with the same pages either way; a limited
        # one does not. Both are read again on a resume, which is how a run
        # started before the index was read still gets its pages.
        declared_pages = sitemap_pages + index_pages
        if not resumed:
            self.enqueue(seed_url, operator_seed=True)
        for url in declared_pages:
            self.enqueue(url)
        if not resumed:
            for url in self.settings.seed_urls:
                self.enqueue(url, operator_seed=True)
        else:
            self._sitemap_first(declared_pages)

        policy = FetchPolicy(
            min_interval=self.effective_min_interval,
            max_interval=self.settings.max_interval_in_seconds,
            max_retries=self.settings.max_retries,
            sleep=self.sleep,
        )
        pool = WorkerPool(
            workers=self.settings.concurrency_limit,
            fetcher_factory=self.fetcher_factory,
            min_interval=self.effective_min_interval,
            sleep=self.sleep,
        )
        interrupted = False
        try:
            status = self.work(pool, policy)
        except KeyboardInterrupt:
            interrupted = True
            status = STATUS_INCOMPLETE
            logger.warning("INTERRUPTED checkpointing so this run can resume")
        finally:
            pool.close()

        doc = self.checkpoint(status, finished=not interrupted)
        self._progress()
        return CrawlOutcome(
            crawl_doc=doc,
            exit_code=_exit_code(status, len(self.failed), interrupted),
            reason=_exit_reason(status, len(self.failed), interrupted),
        )


def _exit_code(status: str, pages_failed: int, interrupted: bool) -> int:
    if interrupted:
        return EXIT_INTERRUPTED
    if status in {STATUS_COMPLETE, STATUS_LIMIT_REACHED} and pages_failed == 0:
        return 0
    return 1


def _exit_reason(status: str, pages_failed: int, interrupted: bool) -> str:
    if interrupted:
        return "interrupted, state.json written, rerun with the same --run-id"
    if status == STATUS_INCOMPLETE:
        return (
            "crawl stopped before the frontier emptied, "
            "rerun with the same --run-id to continue"
        )
    if pages_failed:
        return f"{pages_failed} page(s) failed, see failed.jsonl"
    return ""


def run_crawl(settings: CrawlSettings, **kwargs: Any) -> CrawlOutcome:
    """Crawl one catalog into object storage and report how it went."""
    return Crawler(settings, **kwargs).run()
