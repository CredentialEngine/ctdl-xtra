"""Step 1: crawl (specification section 4). The only step that may use the internet.

"Fetch a page" is one replaceable part: anything with a `get(address)` method. Today that is a
plain request. A site that needs a real browser or a login changes only that part (risk R5).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from .store import Fetch, PageStore

INDEX_ADDRESS = "https://catalog.uark.edu/undergraduatecatalog/coursesofinstruction/"
REGISTRY_RECORD_ADDRESS = (
    "https://credentialengineregistry.org/resources/ce-57603921-78ce-455c-88b5-00506fb33701"
)
DEFAULT_SUBJECTS = ("ACCT", "CHEM", "CSCE", "ENGL", "NURS")
USER_AGENT = "xtra-mockup/0.1 (course catalog research prototype; one request per second)"
MIN_SECONDS_BETWEEN_REQUESTS = 1.0


@dataclass(frozen=True)
class Response:
    final: str
    status: int
    content_type: str | None
    body: bytes


class Fetcher(Protocol):
    def get(self, address: str) -> Response: ...


class HttpFetcher:
    """A plain request that says honestly who is asking (CR4)."""

    def __init__(self, user_agent: str = USER_AGENT, timeout: float = 30.0):
        import httpx

        self._client = httpx.Client(
            headers={"User-Agent": user_agent}, follow_redirects=True, timeout=timeout
        )

    def get(self, address: str) -> Response:
        r = self._client.get(address)
        return Response(str(r.url), r.status_code, r.headers.get("content-type"), r.content)


@dataclass
class CrawlReport:
    fetched: list[str] = field(default_factory=list)
    already_stored: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    disallowed: list[str] = field(default_factory=list)
    unknown_subjects: list[str] = field(default_factory=list)
    no_robots: list[str] = field(default_factory=list)
    subjects: dict[str, str] = field(default_factory=dict)

    @property
    def requests_made(self) -> int:
        return len(self.fetched) + len(self.no_robots) + len([f for f in self.failed if not f[1].startswith("earlier")])


class Crawler:
    def __init__(
        self,
        store: PageStore,
        fetcher: Fetcher,
        user_agent: str = USER_AGENT,
        delay: float = MIN_SECONDS_BETWEEN_REQUESTS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.store = store
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.delay = delay
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self._robots: dict[str, RobotFileParser] = {}
        self.report = CrawlReport()

    # --- the one place a request is made ------------------------------------------------------

    def _request(self, address: str) -> Fetch:
        if self._last_request is not None:
            wait = self.delay - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            response = self.fetcher.get(address)
        except Exception as error:  # a failure is recorded, never retried silently (CR10)
            self._last_request = self._clock()
            fetch = self.store.record_failure(address, now, None, f"{type(error).__name__}: {error}")
            self.report.failed.append((address, fetch.error or ""))
            return fetch
        self._last_request = self._clock()
        if response.status != 200:
            fetch = self.store.record_failure(address, now, response.status, f"HTTP {response.status}")
            self.report.failed.append((address, fetch.error or ""))
            return fetch
        fetch = self.store.record_success(
            address, response.final, now, response.status, response.content_type, response.body
        )
        self.report.fetched.append(address)
        return fetch

    # --- robots.txt ---------------------------------------------------------------------------

    def _robots_for(self, address: str) -> RobotFileParser:
        parts = urlsplit(address)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            robots_address = origin + "/robots.txt"
            # robots.txt is fetched first and stored like any other document (CR1).
            if self.store.seen(robots_address):
                fetch = self.store.current(robots_address)
                if fetch:
                    self.report.already_stored.append(robots_address)
            else:
                fetch = self._request(robots_address)
                if not fetch.ok:  # a site with no robots.txt is not a failed crawl
                    self.report.failed = [f for f in self.report.failed if f[0] != robots_address]
                    self.report.no_robots.append(f"{robots_address} ({fetch.error})")
            parser = RobotFileParser()
            if fetch and fetch.ok:
                parser.parse(self.store.read(fetch.digest).decode("utf-8", "replace").splitlines())
            else:
                parser.parse([])  # no robots.txt: nothing is disallowed
            self._robots[origin] = parser
        return self._robots[origin]

    def allowed(self, address: str) -> bool:
        return self._robots_for(address).can_fetch(self.user_agent, address)

    # --- fetching through the lookup ----------------------------------------------------------

    def get(self, address: str, refetch: bool = False) -> Fetch | None:
        """Return the stored fetch for an address, requesting it only if it was never requested
        before (CR3) or a refetch was asked for explicitly (CR9)."""
        if not self.allowed(address):
            self.report.disallowed.append(address)
            return None
        if self.store.seen(address) and not refetch:
            fetch = self.store.current(address)
            if fetch:
                self.report.already_stored.append(address)
            else:
                last = self.store.history(address)[-1]
                self.report.failed.append((address, f"earlier attempt failed: {last.error}"))
            return fetch
        fetch = self._request(address)
        return fetch if fetch.ok else None

    # --- the crawl ----------------------------------------------------------------------------

    def run(
        self,
        index_address: str = INDEX_ADDRESS,
        subjects: tuple[str, ...] | str = DEFAULT_SUBJECTS,
        registry_record: str | None = REGISTRY_RECORD_ADDRESS,
        refetch: tuple[str, ...] = (),
    ) -> CrawlReport:
        index = self.get(index_address, refetch=index_address in refetch)
        if index is None:
            return self.report
        links = subject_links(self.store.read(index.digest), index.final or index_address)
        self.report.subjects = links
        wanted = sorted(links) if subjects == "all" else [s.upper() for s in subjects]
        for code in wanted:
            address = links.get(code)
            if address is None:
                self.report.unknown_subjects.append(code)
                continue
            self.get(address, refetch=address in refetch)
        if registry_record:
            self.get(registry_record, refetch=registry_record in refetch)
        return self.report


_SUBJECT_PATH = re.compile(r"/coursesofinstruction/[a-z0-9]+/$")
_SUBJECT_CODE = re.compile(r"\(([A-Z0-9]{2,6})\)\s*$")


def subject_links(index_html: bytes, index_address: str) -> dict[str, str]:
    """Subject pages are found from the links on the index page, never from a list (CR2)."""
    soup = BeautifulSoup(index_html.decode("utf-8", "replace"), "html5lib")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        address = urljoin(index_address, a["href"])
        code = _SUBJECT_CODE.search(a.get_text())
        if code and _SUBJECT_PATH.search(urlsplit(address).path) and address.startswith(index_address):
            found.setdefault(code.group(1), address)
    return found
