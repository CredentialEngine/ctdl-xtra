"""Stand-ins for the browser and for robots.txt, shared by the crawl tests.

No test opens a browser or a socket. A fake fetcher stands in for one
worker's Playwright instance, and a fake url_fetch stands in for robots.txt,
sitemap, and site index reads.
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

from implementations.crawl_browser import FetchError, FetchResult


@dataclass
class FakePage:
    """One canned answer from the fake browser."""

    html: str = "<html><body>ok</body></html>"
    status: int = 200
    content_type: str = "text/html; charset=utf-8"
    final_url: str | None = None
    retry_after: float | None = None
    raises: str | None = None
    retryable: bool = True
    reason: str | None = None
    render: dict[str, Any] | None = None


class FakeFetcher:
    """Stands in for one worker's browser.

    `pages` maps a URL to a FakePage, or to a list of them that is consumed
    one entry per attempt, so a test can say "429 twice, then 200".
    """

    def __init__(
        self,
        pages: dict[str, Any],
        *,
        calls: list[str] | None = None,
        before: Callable[[str], None] | None = None,
    ) -> None:
        self.pages = pages
        self.calls = calls if calls is not None else []
        self.before = before
        self.closed = False

    def fetch(self, url: str) -> FetchResult:
        if self.before is not None:
            self.before(url)
        self.calls.append(url)
        page = self.pages.get(url)
        if isinstance(page, list):
            page = page.pop(0) if page else FakePage(status=404, html="")
        if page is None:
            page = FakePage(status=404, html="")
        if page.raises:
            raise FetchError(
                page.raises, retryable=page.retryable, reason=page.reason
            )
        return FetchResult(
            requested_url=url,
            final_url=page.final_url or url,
            http_status=page.status,
            content_type=page.content_type,
            html=page.html,
            latency_ms=7,
            retry_after=page.retry_after,
            render=page.render,
        )

    def close(self) -> None:
        self.closed = True


def fetcher_factory(
    pages: dict[str, Any],
    *,
    calls: list[str] | None = None,
    before: Callable[[str], None] | None = None,
    made: list[FakeFetcher] | None = None,
) -> Callable[[], FakeFetcher]:
    """A new fake browser per worker thread, sharing one page map."""

    def factory() -> FakeFetcher:
        fetcher = FakeFetcher(pages, calls=calls, before=before)
        if made is not None:
            made.append(fetcher)
        return fetcher

    return factory


def no_site_documents(url: str) -> tuple[int, bytes]:
    """robots.txt and sitemap.xml both missing."""
    return 404, b""


def site_documents(
    documents: dict[str, bytes],
    *,
    calls: list[str] | None = None,
) -> Callable[[str], tuple[int, bytes]]:
    """Serve canned robots.txt and sitemap bodies; anything else is a 404.

    `calls`, when given, records every URL asked for, in order.
    """

    def fetch(url: str) -> tuple[int, bytes]:
        if calls is not None:
            calls.append(url)
        body = documents.get(url)
        return (200, body) if body is not None else (404, b"")

    return fetch


# --- a CurriQunet catalog ---------------------------------------------------

CQ_CATALOG = 115
CQ_CATALOGS = "/Catalog/_getCatalogs"
CQ_NAVIGATION = "/Catalog/_getNavigation"
CQ_RESOLVER = "/Catalog/_getVisibleContentBodyNodeForClientPath"
CQ_COMMANDS = {
    "catalogs": CQ_CATALOGS,
    "navigation": CQ_NAVIGATION,
    "page": "/Catalog/_getPage",
    "visiblecontentnode": CQ_RESOLVER,
}

# (catalogsectiontypeid, catalognavigationitypeid, presentationtype) for
# each kind of node a real catalog's tree holds.
CQ_KINDS = {
    "root": (4, 1, "list"),
    "index": (6, 3, "listitem"),
    "tab": (6, 2, "listitem"),
    "tablist": (7, 2, "tablist"),
    "linklist": (8, 2, "linklist"),
}


def cq_node(
    node_id: int,
    path: str,
    kind: str = "index",
    *,
    text: str | None = "Page",
    panel: int | None = 2,
    hidden: bool = False,
    cascade: bool = False,
) -> dict[str, Any]:
    """One _getNavigation entry, with the fields the server sends.

    parentid and subitemcount are left for curriqunet_documents to fill
    in from the tree it serves, so a test cannot get them out of step.
    `cascade` is a page whose body is a tab set.
    """
    section, navigation, presentation = CQ_KINDS[kind]
    config = {
        "nodeConfig": {
            "pdfBookmarkLabel": "",
            "excludeFromWebView": hidden,
            "startOnNewPage": False,
        }
    }
    return {
        "id": node_id,
        "parentid": None,
        "moduleid": CQ_CATALOG,
        "text": text,
        "description": None,
        "urlalias": None,
        "sortorder": 1,
        "catalogsectiontypeid": section,
        "catalognavigationitypeid": navigation,
        "catalogblockpaneltypeid": panel,
        "catalogblocktypeid": 0,
        "subitemcount": 0,
        "config": json.dumps(config),
        "aliaspath": path,
        "haschildbodynavs": cascade,
        "hasnonindexchildbodynavs": cascade,
        "presentationtype": presentation,
    }


def unquoted_attribute(value: Any) -> str:
    """JSON as the CurriQunet server writes an attribute: no quotes at all.

    An unquoted attribute ends at the first space, so a test value with a
    space in it would not survive the real server either.
    """
    text = html.escape(json.dumps(value, separators=(",", ":")), quote=True)
    assert not any(char.isspace() for char in text), text
    return text


def curriqunet_shell(
    commands: dict[str, str] | None = None,
    aliases: list[dict[str, Any]] | None = None,
) -> bytes:
    """The seed page of a CurriQunet catalog: a model and no content."""
    aliases = aliases or [{"ModuleId": CQ_CATALOG, "CatalogAlias": None}]
    model = {
        "Catalogs": None,
        "HideLogin": True,
        # The server repeats the aliases inside the model, escaped once
        # more, which is a second match for the aliases attribute.
        "CatalogMappings": "data-catalogaliases="
        + json.dumps(aliases, separators=(",", ":")),
        "ClientCode": "EXAMPLE",
        "UserCanEdit": False,
        "CommandUrls": CQ_COMMANDS if commands is None else commands,
        "IsPublic": False,
    }
    return (
        "<!DOCTYPE html><html><head><title>View - CurriQunet META</title>"
        '</head><body><div class="content-body">'
        f"<body data-catalogaliases={unquoted_attribute(aliases)}></body>"
        '<ul class="iq-catalog-nav"><li><a href="javascript:void(0)">'
        "Courses</a></li></ul>"
        '<div id="content-body" class="iq-catalog" '
        f"data-iq-model={unquoted_attribute(model)}></div>"
        "</div></body></html>"
    ).encode()


def curriqunet_documents(
    seed_url: str,
    roots: list[dict[str, Any]],
    children: dict[int, list[dict[str, Any]]] | None = None,
    *,
    catalog_id: int = CQ_CATALOG,
    catalogs: list[dict[str, Any]] | None = None,
    aliases: list[dict[str, Any]] | None = None,
    resolves: dict[str, int] | None = None,
    commands: dict[str, str] | None = None,
) -> dict[str, bytes]:
    """Every document a CurriQunet catalog serves for its index, by URL.

    `children` maps a node id to the nodes its parentId request returns.
    The resolver answers each node's own path with that node, unless
    `resolves` names another node id for the path, which is what a root
    the server cannot find looks like.
    """
    commands = CQ_COMMANDS if commands is None else commands
    roots = [dict(node) for node in roots]
    children = {
        parent: [dict(node, parentid=parent) for node in kids]
        for parent, kids in (children or {}).items()
    }
    every = roots + [node for kids in children.values() for node in kids]
    for node in every:
        node["subitemcount"] = len(children.get(node["id"], ()))
    by_id = {node["id"]: node for node in every}

    navigation = urljoin(seed_url, commands.get("navigation", CQ_NAVIGATION))
    documents = {
        seed_url: curriqunet_shell(commands, aliases),
        f"{navigation}?id={catalog_id}&navigationtypeId=1": json.dumps(
            {"moduleid": catalog_id, "navs": roots}
        ).encode(),
    }
    for parent, kids in children.items():
        documents[f"{navigation}?id={catalog_id}&parentId={parent}"] = (
            json.dumps({"moduleid": catalog_id, "navs": kids}).encode()
        )
    if "catalogs" in commands:
        listed = catalogs
        if listed is None:
            listed = [{"Id": catalog_id, "StatusBaseId": 1}]
        documents[urljoin(seed_url, commands["catalogs"])] = json.dumps(
            listed
        ).encode()
    if "visiblecontentnode" in commands:
        resolver = urljoin(seed_url, commands["visiblecontentnode"])
        for node in every:
            path = node["aliaspath"]
            if not path:
                continue
            answer = by_id[(resolves or {}).get(path, node["id"])]
            client_path = quote(path, safe="/-_.~")
            documents[
                f"{resolver}?id={catalog_id}&clientPath={client_path}"
            ] = json.dumps(answer).encode()
    return documents


# --- a Coursedog catalog ----------------------------------------------------

# What the server renders where a list will go, before its XHR lands:
# Brookdale's /courses as the crawl of 2026-09-23 saved it.
COURSEDOG_LOADING = '<p data-v-6c735c42="">Loading results...</p>'

_COURSEDOG_ARROW = '<svg aria-hidden="true"><path d="M0 0"></path></svg>'


def coursedog_button(number: int, current: int) -> str:
    """One numbered page button, as Coursedog draws it."""
    if number == current:
        return (
            '<button class="btn btn-primary mx-1" type="button" disabled="" '
            f'aria-label="Go to page {number}" aria-hidden="false" '
            f'number="{number}">{number}</button>'
        )
    return (
        '<button class="btn btn-secondary mx-1" type="button" '
        f'aria-label="Go to page {number}" aria-hidden="false" '
        f'number="{number}">{number}</button>'
    )


def coursedog_row(current: int, last: int) -> str:
    """A row of page buttons as Coursedog draws one.

    Previous, the first page, the pages beside the current one, the last
    page, and Next, with a disabled "..." button where pages are left out.
    """
    numbers = sorted(
        {1, current - 1, current, current + 1, last} & set(range(1, last + 1))
    )
    parts = [
        '<div class="flex ml-2 px-0 text-xs ui-font base-pagination mt-4">',
        '<button class="btn btn-secondary mx-1" type="button" '
        f'aria-label="Previous page">{_COURSEDOG_ARROW}</button>',
    ]
    previous = 0
    for number in numbers:
        if number - previous > 1:
            parts.append(
                '<button class="btn btn-secondary mx-1" type="button" '
                'disabled="" aria-label="Go to page ..." aria-hidden="true" '
                'number="...">...</button>'
            )
        parts.append(coursedog_button(number, current))
        previous = number
    parts.append(
        '<button class="btn btn-secondary mx-1" type="button" '
        f'aria-label="Next page">{_COURSEDOG_ARROW}</button></div>'
    )
    return "".join(parts)


def coursedog_page(*content: str) -> str:
    """A Coursedog page around `content`.

    Every Coursedog page carries the print stylesheet that names the page
    row, and a footer that names the platform.
    """
    return (
        "<html><head><style>.theme-container--print .base-pagination"
        "{display:none}</style></head><body><main>"
        + "".join(content)
        + '</main><footer><a href="https://www.coursedog.com">Powered by '
        "Coursedog</a></footer></body></html>"
    )


def coursedog_list(current: int, last: int, codes: list[str]) -> str:
    """Page `current` of `last` of a Coursedog course list."""
    links = "".join(f'<a href="/courses/{code}">{code}</a>' for code in codes)
    return coursedog_page(links, coursedog_row(current, last))
