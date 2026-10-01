"""A CurriQunet catalog's own index of its pages, read like a sitemap.

CurriQunet META public catalogs are single-page apps. They publish no
sitemap, and the page a browser loads is a shell: every entry in its
navigation is javascript:void(0), and the content arrives by XHR after the
load event, driven by a JSON tree of the catalog's sections. Following
links saved exactly one empty page from each of four such catalogs.

The shell does declare where that tree is. Its data-iq-model attribute
names the JSON endpoints its own script reads, so the crawler can read
them too. That is the same act as reading a sitemap: a list of the site's
own pages, published by the site, each of which still has to pass the
crawl's scope gate and is then rendered by the browser like any other
page. Nothing here reads page content.

The tree is not one page per node, and the SPA has traps that decide
whether a URL renders the page it names. They are mirrored here:

- The SPA writes /catalog/view//iq/... for the seed /catalog/view/, but a
  deep link of that double-slash form renders the cover page. The single
  slash form renders the page, so that is the one emitted.
- The server never answers 404. An unknown client path renders the
  catalog's first page, so a root the server resolves to another node
  would yield URLs that all render the cover. Each root that anchors
  emitted URLs is put to the server's own resolver once, and its URLs are
  dropped when the answer names a different node.
- A page whose body is a tab set is rewritten client-side to its first
  tab's URL, with the same content. Only the tabs are emitted.
- Tab bars and link lists are containers, not pages. Their children are
  pages, and their ids never appear in a child's path.
"""

from __future__ import annotations

import html
import json
import logging
import re
from collections import Counter, deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from implementations.crawl_robots import SiteFetchError

logger = logging.getLogger(__name__)

INDEX_KIND = "curriqunet"

# A catalog is a few hundred to a few thousand nodes. The cap is there so a
# tree that never ends cannot hold the crawl at its first step; reaching it
# is warned about and recorded, never silent.
MAX_NODES = 10_000

# catalogsectiontypeid 7 is a tab bar and 8 a link list. Either holds pages
# without being one, and the SPA never puts its id in the address bar.
CONTAINER_SECTION_TYPES = frozenset({7, 8})
CONTAINER_PRESENTATIONS = frozenset({"tablist", "linklist"})

# Only nodes in the body panel are pages the SPA navigates to. A node with
# no panel inherits its parent's.
BODY_PANEL = 2
INHERITED_PANEL = None

# catalognavigationitypeid of an index child: a page the server's resolver
# can find on its own, unlike a tab, which is found through its page.
INDEX_CHILD = 3

# The SPA's catalog selector ranks statuses Draft (4), In Review (6),
# Approved (2), Active (1), Historical (5) and keeps the lowest rank it
# sees, a later entry winning a tie. A public site lists only what it
# publishes, so in practice that is Active ahead of Historical.
STATUS_RANK = {4: 1, 6: 2, 2: 3, 1: 4, 5: 5}
UNRANKED = 99

# How the SPA quotes a client path: slashes stay, everything else unusual
# is escaped.
CLIENT_PATH_SAFE = "/-_.~"

SKIP_HIDDEN = "hidden"
SKIP_CONTAINER = "container"
SKIP_NON_BODY_PANEL = "non_body_panel"
SKIP_NO_TEXT = "no_text"
SKIP_NO_PATH = "no_path"
SKIP_CASCADE = "cascade"
SKIP_UNRESOLVED_ROOT = "unresolved_root"
SKIP_DUPLICATE = "duplicate"


def attribute_pattern(name: str) -> re.Pattern[str]:
    """One HTML attribute, quoted either way or not quoted at all.

    The CurriQunet server writes its JSON attributes unquoted, with every
    quote as &quot;, so an HTML parser that expects quotes is no help.
    """
    return re.compile(
        r"\b" + re.escape(name) + r"""=(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""
    )


def attribute_values(text: str, name: str) -> Iterator[str]:
    """Every value of one attribute in a page, entities decoded."""
    for match in attribute_pattern(name).finditer(text):
        raw = next(group for group in match.groups() if group is not None)
        yield html.unescape(raw)


def attribute_json(text: str, name: str, kind: type) -> Any | None:
    """The first value of an attribute that is JSON of the given kind.

    The first, not the only: the model repeats data-catalogaliases inside
    one of its own strings, escaped once more, and that copy does not
    parse. Taking the first that does is what keeps the order of the two
    from mattering.
    """
    for value in attribute_values(text, name):
        try:
            parsed = json.loads(value)
        except ValueError:
            continue
        if isinstance(parsed, kind):
            return parsed
    return None


@dataclass(frozen=True)
class Shell:
    """What the seed page declares: its endpoints and its catalog aliases."""

    commands: dict[str, str]
    aliases: tuple[dict[str, Any], ...]


def read_shell(text: str) -> Shell | None:
    """The CurriQunet model in a seed page, or None for any other page."""
    model = attribute_json(text, "data-iq-model", dict)
    if model is None:
        return None
    commands = model.get("CommandUrls")
    if not isinstance(commands, dict):
        return None
    if not isinstance(commands.get("navigation"), str):
        return None
    aliases = attribute_json(text, "data-catalogaliases", list) or []
    return Shell(
        commands={
            key: value
            for key, value in commands.items()
            if isinstance(value, str)
        },
        aliases=tuple(alias for alias in aliases if isinstance(alias, dict)),
    )


def _is_number(text: str) -> bool:
    # str.isdigit alone also accepts digits int() refuses, such as "²".
    return text.isascii() and text.isdigit()


def split_seed_path(path: str) -> list[str]:
    """The path components before the first "iq", as the SPA splits them.

    Everything after "iq" is the client path of one page. Everything before
    it is where the catalog lives, and is the same for every page in it.
    """
    parts = path.split("/")
    if "iq" in parts:
        return parts[: parts.index("iq")]
    return parts


def path_catalog_id(seed_url: str, aliases: tuple[dict, ...]) -> int | None:
    """The catalog the seed URL names: a trailing id, or a known alias."""
    prefix = split_seed_path(urlsplit(seed_url).path)
    last = prefix[-1] if prefix else ""
    if _is_number(last) and int(last) > 0:
        return int(last)
    for alias in aliases:
        if alias.get("CatalogAlias") and alias.get("CatalogAlias") == last:
            module_id = alias.get("ModuleId")
            return module_id if isinstance(module_id, int) else None
    return None


def choose_catalog(
    path_id: int | None,
    catalogs: list[dict[str, Any]],
    aliases: tuple[dict, ...],
) -> int | None:
    """The catalog the SPA would show for this seed.

    The id in the path wins when the catalogs endpoint lists it. Otherwise
    the listed catalog with the best status, and with nothing listed, the
    path id or the one catalog the aliases name.
    """
    if path_id is not None and any(c.get("Id") == path_id for c in catalogs):
        return path_id
    chosen = None
    best = UNRANKED
    for catalog in catalogs:
        rank = STATUS_RANK.get(catalog.get("StatusBaseId"), UNRANKED)
        if rank <= best and catalog.get("Id") is not None:
            chosen, best = catalog.get("Id"), rank
    if chosen is not None:
        return chosen
    if path_id is not None:
        return path_id
    module_ids = {alias.get("ModuleId") for alias in aliases} - {None}
    return module_ids.pop() if len(module_ids) == 1 else None


def url_base(seed_url: str, catalog_id: int, catalogs_listed: int) -> str:
    """Where every page of the catalog lives: the seed's prefix plus /iq/.

    Trailing slashes are stripped from the prefix, which is the difference
    between the double-slash form that renders the cover and the form that
    renders the page. With more than one catalog listed the SPA also puts
    the catalog id in the path, replacing a trailing id or appended.
    """
    parsed = urlsplit(seed_url)
    prefix = "/".join(split_seed_path(parsed.path)).rstrip("/")
    if catalogs_listed > 1:
        parts = prefix.split("/")
        if _is_number(parts[-1]):
            parts[-1] = str(catalog_id)
        else:
            parts.append(str(catalog_id))
        prefix = "/".join(parts)
    return urlunsplit((parsed.scheme, parsed.netloc, prefix + "/iq/", "", ""))


def page_url(base: str, alias_path: str) -> str:
    return base + quote(alias_path, safe=CLIENT_PATH_SAFE)


def is_hidden(node: dict[str, Any]) -> bool:
    """excludeFromWebView, from the JSON string in the node's config."""
    raw = node.get("config")
    if not raw:
        return False
    try:
        config = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return False
    if not isinstance(config, dict):
        return False
    node_config = config.get("nodeConfig")
    if not isinstance(node_config, dict):
        return False
    return bool(node_config.get("excludeFromWebView"))


def is_container(node: dict[str, Any]) -> bool:
    return (
        node.get("catalogsectiontypeid") in CONTAINER_SECTION_TYPES
        or node.get("presentationtype") in CONTAINER_PRESENTATIONS
    )


def is_navigation_end(node: dict[str, Any]) -> bool:
    """False for a page whose body is a tab set the SPA redirects into."""
    return not (
        node.get("haschildbodynavs") and node.get("hasnonindexchildbodynavs")
    )


@dataclass(frozen=True)
class CurriqunetIndex:
    """The pages one CurriQunet catalog lists, and what reading it cost."""

    catalog_id: int | None
    url_base: str | None
    urls: tuple[str, ...] = ()
    nodes_walked: int = 0
    requests: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    dropped_roots: tuple[int, ...] = ()
    capped: bool = False
    errors: int = 0

    def to_json(self) -> dict[str, Any]:
        """What crawl.json records, so a run says where its pages came from."""
        return {
            "kind": INDEX_KIND,
            "catalog_id": self.catalog_id,
            "url_base": self.url_base,
            "urls_found": len(self.urls),
            "nodes_walked": self.nodes_walked,
            "requests": self.requests,
            "skipped_by_reason": dict(sorted(self.skipped.items())),
            "dropped_roots": list(self.dropped_roots),
            "capped": self.capped,
            "errors": self.errors,
        }


class _Reader:
    """One read of one catalog's index, counting what it asked for."""

    def __init__(
        self,
        seed_url: str,
        fetch: Callable[[str], tuple[int, bytes]],
        pause: Callable[[], None],
    ) -> None:
        self.seed_url = seed_url
        self.fetch = fetch
        self.pause = pause
        self.requests = 0
        self.errors = 0

    def get(self, url: str) -> tuple[int, bytes]:
        """One GET, paced after the first. SiteFetchError passes through."""
        if self.requests:
            self.pause()
        self.requests += 1
        return self.fetch(url)

    def get_json(self, url: str) -> Any | None:
        """A JSON answer, or None after a warning when there is none.

        A failure part way through costs the pages behind that one request
        and nothing else: what was found before it is kept.
        """
        try:
            status, body = self.get(url)
        except SiteFetchError as exc:
            return self._failed(url, str(exc))
        if status != 200:
            return self._failed(url, f"HTTP {status}")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self._failed(url, "not JSON")

    def _failed(self, url: str, why: str) -> None:
        self.errors += 1
        logger.warning(
            "INDEX %s failed (%s); keeping what the index found without it",
            url,
            why,
        )
        return None

    def endpoint(self, command: str) -> str:
        return urljoin(self.seed_url, command)


def _catalogs(reader: _Reader, shell: Shell) -> list[dict[str, Any]]:
    command = shell.commands.get("catalogs")
    if not command:
        return []
    data = reader.get_json(reader.endpoint(command))
    if isinstance(data, dict) and data.get("Id"):
        data = [data]
    if not isinstance(data, list):
        return []
    return [catalog for catalog in data if isinstance(catalog, dict)]


@dataclass
class _Walk:
    """The tree as walked: each node by id, in BFS order, and its parent.

    The parent is the node whose children request returned it, not the
    node's own parentid field, so the chain followed is the tree that was
    actually walked and cannot loop.
    """

    nodes: dict[Any, dict[str, Any]] = field(default_factory=dict)
    parent_of: dict[Any, Any] = field(default_factory=dict)
    pruned: set[Any] = field(default_factory=set)
    capped: bool = False

    def chain(self, node: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """The node, then each parent up to its root."""
        current: dict[str, Any] | None = node
        while current is not None:
            yield current
            current = self.nodes.get(self.parent_of.get(current.get("id")))

    def is_root(self, node: dict[str, Any]) -> bool:
        return self.parent_of.get(node.get("id")) is None


def _walk(
    reader: _Reader, navigation: str, catalog_id: int, max_nodes: int
) -> _Walk:
    """Breadth first over the navigation tree, children by parentId.

    The SPA honours excludeFromWebView only in the sidebar, which shows
    roots. Tab bars and link lists show a flagged child anyway, and it
    renders, so only a hidden root is pruned, with everything under it.
    """
    walk = _Walk()
    roots = reader.get_json(f"{navigation}?id={catalog_id}&navigationtypeId=1")
    if not isinstance(roots, dict):
        return walk
    queue: deque[tuple[Any, Any]] = deque(
        (node, None) for node in roots.get("navs") or ()
    )
    while queue:
        node, parent = queue.popleft()
        node_id = node.get("id") if isinstance(node, dict) else None
        if node_id is None or node_id in walk.nodes:
            continue
        if len(walk.nodes) >= max_nodes:
            walk.capped = True
            logger.warning(
                "INDEX curriqunet catalog %s stopped at %s nodes; %s queued "
                "nodes were left unexpanded, so the index is incomplete",
                catalog_id,
                max_nodes,
                len(queue) + 1,
            )
            break
        walk.nodes[node_id] = node
        walk.parent_of[node_id] = parent
        if parent is None and is_hidden(node):
            walk.pruned.add(node_id)
            continue
        if (node.get("subitemcount") or 0) <= 0:
            continue
        children = reader.get_json(
            f"{navigation}?id={catalog_id}&parentId={node_id}"
        )
        if isinstance(children, dict):
            queue.extend(
                (child, node_id) for child in children.get("navs") or ()
            )
    return walk


def _skip_reason(walk: _Walk, node: dict[str, Any]) -> str | None:
    """Why this node is not a page the SPA puts in the address bar."""
    ancestry = list(walk.chain(node))
    if any(item.get("id") in walk.pruned for item in ancestry):
        return SKIP_HIDDEN
    if is_container(node):
        return SKIP_CONTAINER
    if any(
        item.get("catalogblockpaneltypeid") not in (BODY_PANEL, INHERITED_PANEL)
        for item in ancestry
    ):
        return SKIP_NON_BODY_PANEL
    if not node.get("text"):
        return SKIP_NO_TEXT
    if not node.get("aliaspath"):
        return SKIP_NO_PATH
    if not is_navigation_end(node):
        return SKIP_CASCADE
    return None


def _anchor(walk: _Walk, node: dict[str, Any]) -> dict[str, Any]:
    """The page the server's resolver finds for this node's path.

    The nearest index child at or above the node, or else its root. A tab
    is found through the page that holds it, and the SPA then selects the
    tab from the rest of the path.
    """
    root = node
    for item in walk.chain(node):
        if (
            not is_container(item)
            and item.get("catalognavigationitypeid") == INDEX_CHILD
        ):
            return item
        root = item
    return root


def _unresolved_roots(
    reader: _Reader,
    resolver: str | None,
    catalog_id: int,
    roots: list[dict[str, Any]],
) -> set[Any]:
    """Roots the server resolves to some other node, so they render the cover.

    A failed check is not an answer. The resolver never says no, it names
    a node, so a URL is only dropped when the server named a different one.
    """
    if not resolver:
        return set()
    dropped: set[Any] = set()
    for root in roots:
        client_path = quote(str(root.get("aliaspath")), safe=CLIENT_PATH_SAFE)
        answer = reader.get_json(
            f"{resolver}?id={catalog_id}&clientPath={client_path}"
        )
        if not isinstance(answer, dict) or answer.get("id") is None:
            continue
        if answer.get("id") != root.get("id"):
            logger.warning(
                "INDEX curriqunet root %s (%s) resolves to node %s, so the "
                "pages under it would render the cover; they are left out",
                root.get("id"),
                root.get("aliaspath"),
                answer.get("id"),
            )
            dropped.add(root.get("id"))
    return dropped


def read_curriqunet_index(
    seed_url: str,
    *,
    fetch: Callable[[str], tuple[int, bytes]],
    pause: Callable[[], None],
    max_nodes: int = MAX_NODES,
) -> CurriqunetIndex | None:
    """Every page a CurriQunet catalog lists, or None for any other site.

    For every other catalog this is one GET of the seed URL, which finds
    no CurriQunet model and stops. `pause` runs between consecutive
    requests, so the walk is paced however the caller chooses.
    """
    reader = _Reader(seed_url, fetch, pause)
    try:
        status, body = reader.get(seed_url)
    except SiteFetchError as exc:
        logger.warning(
            "INDEX %s unreachable (%s), no site index read", seed_url, exc
        )
        return None
    shell = (
        read_shell(body.decode("utf-8", errors="replace"))
        if status == 200
        else None
    )
    if shell is None:
        logger.info("INDEX %s declares no site index", seed_url)
        return None

    catalogs = _catalogs(reader, shell)
    catalog_id = choose_catalog(
        path_catalog_id(seed_url, shell.aliases), catalogs, shell.aliases
    )
    if catalog_id is None:
        logger.warning(
            "INDEX %s is a CurriQunet catalog, but which catalog it shows "
            "could not be told, so no index was read",
            seed_url,
        )
        return CurriqunetIndex(
            catalog_id=None,
            url_base=None,
            requests=reader.requests,
            errors=reader.errors,
        )

    walk = _walk(
        reader,
        reader.endpoint(shell.commands["navigation"]),
        catalog_id,
        max_nodes,
    )
    skipped: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    for node in walk.nodes.values():
        reason = _skip_reason(walk, node)
        if reason is None:
            candidates.append(node)
        else:
            skipped[reason] += 1

    anchored_roots: dict[Any, dict[str, Any]] = {}
    for node in candidates:
        anchor = _anchor(walk, node)
        if walk.is_root(anchor):
            anchored_roots.setdefault(anchor.get("id"), anchor)
    resolver = shell.commands.get("visiblecontentnode")
    dropped = _unresolved_roots(
        reader,
        reader.endpoint(resolver) if resolver else None,
        catalog_id,
        list(anchored_roots.values()),
    )

    base = url_base(seed_url, catalog_id, len(catalogs))
    urls: list[str] = []
    seen: set[str] = set()
    for node in candidates:
        if _anchor(walk, node).get("id") in dropped:
            skipped[SKIP_UNRESOLVED_ROOT] += 1
            continue
        url = page_url(base, str(node["aliaspath"]))
        if url in seen:
            skipped[SKIP_DUPLICATE] += 1
            continue
        seen.add(url)
        urls.append(url)

    index = CurriqunetIndex(
        catalog_id=catalog_id,
        url_base=base,
        urls=tuple(urls),
        nodes_walked=len(walk.nodes),
        requests=reader.requests,
        skipped=dict(skipped),
        dropped_roots=tuple(sorted(dropped)),
        capped=walk.capped,
        errors=reader.errors,
    )
    logger.info(
        "INDEX curriqunet catalog %s -> %s pages from %s nodes (%s requests)",
        catalog_id,
        len(index.urls),
        index.nodes_walked,
        index.requests,
    )
    return index
