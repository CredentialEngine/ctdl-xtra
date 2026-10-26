"""Builders and stand-ins shared by the tests of xtra-cli/lib.

src/lib/ is importable only after load_engine() has put it on sys.path, which
tests/lib/conftest.py does first. So every lib import here sits inside the
function that needs it, and this module can be imported before that.

No test opens a browser. FakeSyncPlaywright stands in for
playwright.sync_api.sync_playwright, and serves crawl_doubles.FakePage
answers, the same canned pages the crawl tests use.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from crawl_doubles import FakePage

if TYPE_CHECKING:
    from slots import Slot

DAY = "2026-10-21"
NOW = "2026-10-21T12:00:00Z"

# One small Clean Catalog course: its page, the normalized text that page
# gives, and the fields a template copies from it.
COURSE_HTML = (
    "<!DOCTYPE html><html><head><title>ENGL101</title></head><body>"
    "<h1>ENGL101:</h1><p>Composition I</p><p>Credits</p><p>3</p>"
    "</body></html>"
)
COURSE_TEXT = "ENGL101:\nComposition I\nCredits\n3\n"
COURSE_FIELDS = [
    ("course_id", "ENGL101", "ENGL101:"),
    ("course_name", "Composition I", "Composition I"),
    ("course_credits", 3, "Credits\n3"),
]


class PlaywrightError(Exception):
    """Stands in for playwright.sync_api.Error."""


class PlaywrightTimeout(PlaywrightError):
    """Stands in for playwright.sync_api.TimeoutError, an Error subclass."""


def refuse_browser(*args: Any, **kwargs: Any) -> None:
    raise AssertionError(
        "a lib test tried to start a real browser. Use the fake_browser "
        "fixture, which installs FakeSyncPlaywright."
    )


def example_slot(**overrides: Any) -> Slot:
    """The conftest engl101_slot as a Slot, with any field replaced."""
    from slots import Slot

    slot = Slot(
        record_id="example-engl101-course",
        entity_type="Course",
        requested_url="https://catalog.example.edu/english/engl101",
        institution_name="Example College",
        source_family="custom_html",
        template_id="clean_catalog_course_detail",
        template_version="1",
        page_id="example-engl101",
        copy_html=None,
        retrieved_at="2026-09-14T18:12:00Z",
    )
    return replace(slot, **overrides)


def write_freeze(
    pack: Path,
    slot: Slot,
    html: str,
    *,
    meta: dict[str, Any] | None = None,
    day: str = DAY,
) -> Path:
    """A dated cache entry and its sidecar meta, as freeze writes them."""
    dest = pack / "cache" / day / f"{slot.stem}.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(html.encode("utf-8"))
    payload = {
        "requested_url": slot.requested_url,
        "final_url": slot.requested_url,
        "retrieved_at": NOW,
        "http_status": 200,
        "content_type": "text/html",
        "redirect_chain": [],
        "etag": None,
        "last_modified": None,
        **(meta or {}),
    }
    (dest.parent / f"{slot.stem}.meta.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def write_normalized(pack: Path, slot: Slot, text: str) -> Path:
    dest = pack / "normalized" / f"{slot.stem}.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def make_record(
    pack: Path,
    slot: Slot,
    *,
    html: str,
    text: str,
    fields: list[tuple[str, Any, str]],
    write: bool = True,
) -> dict[str, Any]:
    """A candidate record put together the way build.build_record does.

    The freeze, the normalized text, the hashes and the evidence offsets
    are all real, so the record passes validate_record and the JSON Schema
    until a test breaks the one thing it is about. `fields` holds
    (canonical_label, value, excerpt) triples.
    """
    import evidence
    import mapping
    import record
    from normalize import sha256_bytes, sha256_text

    snapshot = write_freeze(pack, slot, html)
    normalized = write_normalized(pack, slot, text)
    meta_file = snapshot.parent / f"{slot.stem}.meta.json"
    snapshot_sha = sha256_bytes(snapshot.read_bytes())
    text_sha = sha256_text(text)
    rec = record.shell(
        slot,
        source=record.source_block(
            slot,
            snapshot_rel=snapshot.relative_to(pack).as_posix(),
            snapshot_sha256=snapshot_sha,
            normalized_rel=normalized.relative_to(pack).as_posix(),
            normalized_sha256=text_sha,
            meta=json.loads(meta_file.read_text(encoding="utf-8")),
        ),
        page={
            "page_id": slot.page_id,
            "title": None,
            "canonical_url": slot.requested_url,
            "classification": "detail",
            "classification_confidence": None,
            "entity_locator": record.locator(
                "whole_document", "normalized-visible-text"
            ),
            "entities_observed": [],
            "entity_inventory_complete": None,
        },
        annotation_scope={
            "mode": "complete",
            "entity_boundary": "Single course detail block on this freeze.",
            "included_regions": [
                record.locator("whole_document", "in-scope entity block")
            ],
            "excluded_regions": [],
            "partial_reason": None,
            "completeness_attested": None,
        },
    )
    for index, (label, value, excerpt) in enumerate(fields, start=1):
        occurrence = None if text.count(excerpt) == 1 else 1
        rec["source_expected"]["fields"].append(
            {
                "field_id": f"src_{index:03d}",
                "canonical_label": label,
                "presence": "present",
                "value": value,
                "raw_text": excerpt,
                "evidence": [
                    evidence.hydrate_evidence(
                        evidence_id=f"ev_{index:03d}",
                        excerpt=excerpt,
                        snapshot_sha256=snapshot_sha,
                        normalized_text_sha256=text_sha,
                        locator_strategy="text_anchor",
                        locator_value=label,
                        occurrence=occurrence,
                        normalized=text,
                    )
                ],
                "notes": None,
            }
        )
    rec["ctdl_expected"] = mapping.map_fields(
        slot.entity_type, rec["source_expected"]["fields"]
    )
    if write:
        write_record(pack, rec)
    return rec


def write_record(pack: Path, rec: dict[str, Any], name: str = "") -> Path:
    dest = pack / "records" / f"{name or rec['record_id']}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return dest


def course_record(
    pack: Path,
    *,
    fields: list[tuple[str, Any, str]] | None = None,
    text: str = COURSE_TEXT,
    write: bool = True,
    **slot_overrides: Any,
) -> dict[str, Any]:
    """A valid ENGL101 course record; slot fields can be replaced."""
    return make_record(
        pack,
        example_slot(**slot_overrides),
        html=COURSE_HTML,
        text=text,
        fields=COURSE_FIELDS if fields is None else fields,
        write=write,
    )


def numbered_slot_fields(n: int, **overrides: Any) -> dict[str, Any]:
    """record_id and requested_url for the nth of several course records."""
    return {
        "record_id": f"example-c{n}-course",
        "requested_url": f"https://catalog.example.edu/english/c{n}",
        "page_id": f"example-c{n}",
        **overrides,
    }


# --- a fake Playwright ------------------------------------------------------


def _request_chain(url: str, redirects: list[str]) -> SimpleNamespace:
    """request.redirected_from links, newest hop first, as Playwright has."""
    previous = None
    for hop in redirects:
        previous = SimpleNamespace(url=hop, redirected_from=previous)
    return SimpleNamespace(url=url, redirected_from=previous)


class FakeResponse:
    """What page.goto returns, and what a response listener is handed."""

    def __init__(
        self,
        *,
        url: str,
        status: int = 200,
        content_type: str = "text/html",
        body: Any = None,
        redirects: list[str] | None = None,
    ) -> None:
        self.url = url
        self.status = status
        self.headers = {"content-type": content_type}
        self.request = _request_chain(url, redirects or [])
        self._body = body

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeBrowserPage:
    def __init__(self, world: FakeSyncPlaywright) -> None:
        self.world = world
        self.url = ""
        self.html = ""
        self.handlers: list[Callable[[Any], None]] = []
        self.mouse = SimpleNamespace(wheel=self._wheel)

    def set_default_timeout(self, timeout: float) -> None:
        self.world.default_timeout = timeout

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        if event == "response":
            self.handlers.append(handler)

    def goto(
        self, url: str, wait_until: str = "load", timeout: float | None = None
    ) -> FakeResponse:
        self.world.gotos.append((url, wait_until))
        answer = self.world.answer(url)
        if answer.raises:
            if answer.raises.startswith("Timeout"):
                raise PlaywrightTimeout(answer.raises)
            raise PlaywrightError(answer.raises)
        self.url = answer.final_url or url
        self.html = answer.html
        for body in self.world.json_responses.get(url, []):
            for handler in self.handlers:
                handler(
                    FakeResponse(
                        url=url, content_type="application/json", body=body
                    )
                )
        return FakeResponse(
            url=self.url,
            status=answer.status,
            content_type=answer.content_type,
            redirects=self.world.redirects.get(url),
        )

    def content(self) -> str:
        if self.world.content_errors:
            self.world.content_errors -= 1
            raise PlaywrightError("Execution context was destroyed")
        return self.html

    def wait_for_timeout(self, timeout: float) -> None:
        self.world.waits.append(timeout)

    def wait_for_selector(
        self, selector: str, timeout: float | None = None
    ) -> None:
        if self.world.selector_times_out:
            raise PlaywrightTimeout(f"Timeout {timeout}ms exceeded")

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self)

    def _wheel(self, delta_x: float, delta_y: float) -> None:
        self.world.wheels += 1

    def close(self) -> None:
        self.world.closed.append("page")


class _FakeLocator:
    """A Next button that exists while `next_pages` has a page left."""

    def __init__(self, page: FakeBrowserPage) -> None:
        self.page = page

    @property
    def first(self) -> _FakeLocator:
        return self

    def count(self) -> int:
        return 1 if self.page.world.next_pages else 0

    def click(self, timeout: float | None = None) -> None:
        world = self.page.world
        if world.click_fails:
            raise PlaywrightError("Element is not attached to the DOM")
        self.page.html = world.next_pages.pop(0)


class _FakeContext:
    def __init__(self, world: FakeSyncPlaywright) -> None:
        self.world = world

    def new_page(self) -> FakeBrowserPage:
        page = FakeBrowserPage(self.world)
        self.world.page = page
        return page

    def close(self) -> None:
        self.world.closed.append("context")


class _FakeBrowser:
    def __init__(self, world: FakeSyncPlaywright) -> None:
        self.world = world

    def new_context(self, **kwargs: Any) -> _FakeContext:
        self.world.contexts.append(kwargs)
        return _FakeContext(self.world)

    def close(self) -> None:
        self.world.closed.append("browser")


class _FakeChromium:
    def __init__(self, world: FakeSyncPlaywright) -> None:
        self.world = world

    def launch(self, **kwargs: Any) -> _FakeBrowser:
        self.world.launches.append(kwargs)
        if kwargs.get("channel") == "chrome" and self.world.chrome_missing:
            raise PlaywrightError("Chromium distribution 'chrome' is not found")
        return _FakeBrowser(self.world)


class _FakeManager:
    def __init__(self, world: FakeSyncPlaywright) -> None:
        self.world = world

    def __enter__(self) -> SimpleNamespace:
        return SimpleNamespace(chromium=_FakeChromium(self.world))

    def __exit__(self, *exc_info: object) -> None:
        return None


class FakeSyncPlaywright:
    """Stands in for playwright.sync_api.sync_playwright.

    `pages` maps a URL to a FakePage, or to a list of them consumed one per
    goto, so a test can say "time out, then load". A FakePage whose
    `raises` starts with "Timeout" raises PlaywrightTimeout; any other
    `raises` is a PlaywrightError, as a failed navigation is. An unknown
    URL loads as an empty 404.

    `json_responses` maps a URL to the JSON bodies its load hands every
    response listener. `next_pages` are the pages a Next button walks
    through, one per click. The other flags script one failure each.
    """

    def __init__(
        self,
        pages: dict[str, Any],
        *,
        json_responses: dict[str, list[Any]] | None = None,
        next_pages: list[str] | None = None,
        redirects: dict[str, list[str]] | None = None,
        chrome_missing: bool = False,
        click_fails: bool = False,
        content_errors: int = 0,
        selector_times_out: bool = False,
    ) -> None:
        self.pages = pages
        self.json_responses = json_responses or {}
        self.next_pages = list(next_pages or [])
        self.redirects = redirects or {}
        self.chrome_missing = chrome_missing
        self.click_fails = click_fails
        self.content_errors = content_errors
        self.selector_times_out = selector_times_out
        self.launches: list[dict[str, Any]] = []
        self.contexts: list[dict[str, Any]] = []
        self.gotos: list[tuple[str, str]] = []
        self.waits: list[float] = []
        self.wheels = 0
        self.closed: list[str] = []
        self.default_timeout: float | None = None
        self.page: FakeBrowserPage | None = None

    def __call__(self) -> _FakeManager:
        return _FakeManager(self)

    def answer(self, url: str) -> FakePage:
        page = self.pages.get(url)
        if isinstance(page, list):
            page = page.pop(0) if page else None
        return page if page is not None else FakePage(status=404, html="")
