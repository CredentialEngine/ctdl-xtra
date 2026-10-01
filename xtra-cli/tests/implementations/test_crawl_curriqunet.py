from __future__ import annotations

import json
import logging
from pathlib import Path

from crawl_doubles import (
    CQ_CATALOG,
    CQ_COMMANDS,
    CQ_NAVIGATION,
    CQ_RESOLVER,
    cq_node,
    curriqunet_documents,
    site_documents,
)

from implementations.crawl_curriqunet import (
    INDEX_KIND,
    SKIP_CASCADE,
    SKIP_CONTAINER,
    SKIP_HIDDEN,
    SKIP_NO_TEXT,
    SKIP_NON_BODY_PANEL,
    SKIP_UNRESOLVED_ROOT,
    attribute_json,
    attribute_values,
    choose_catalog,
    page_url,
    path_catalog_id,
    read_curriqunet_index,
    read_shell,
    url_base,
)
from implementations.crawl_robots import SiteFetchError

SEED = "https://catalog.example.edu/catalog/view/"
BASE = "https://catalog.example.edu/catalog/view/iq/"
NAVIGATION = f"https://catalog.example.edu{CQ_NAVIGATION}"
RESOLVER = f"https://catalog.example.edu{CQ_RESOLVER}"

# The seed shell one Riverside district catalog served, trimmed: its JSON
# attributes are unquoted, and the model repeats the aliases inside itself.
RCCD_SEED = "https://rccd.curriqunet.com/catalog/alias/mvc-catalog/iq/4710"
RCCD_SHELL = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "html"
    / "curriqunet-seed-shell.html"
)


def read(documents: dict[str, bytes], seed: str = SEED, **kwargs):
    """Read one index from canned documents. Returns (index, calls, pauses)."""
    calls: list[str] = []
    pauses: list[None] = []
    index = read_curriqunet_index(
        seed,
        fetch=site_documents(documents, calls=calls),
        pause=lambda: pauses.append(None),
        **kwargs,
    )
    return index, calls, pauses


def programs_tree() -> tuple[list[dict], dict[int, list[dict]]]:
    """A cover page, and a programs page holding a link list of two pages."""
    roots = [
        cq_node(10, "10", "root", text="Cover"),
        cq_node(20, "20", "root", text="Programs"),
    ]
    children = {
        20: [cq_node(21, "20/21", "linklist", text=None)],
        21: [
            cq_node(22, "20/22", text="Biology"),
            cq_node(23, "20/23", text="Chemistry"),
        ],
    }
    return roots, children


# --- reading the shell -----------------------------------------------------


def test_an_unquoted_attribute_is_read_with_its_entities_decoded() -> None:
    text = "<div data-x=[{&quot;a&quot;:1,&quot;b&quot;:&quot;x&amp;y&quot;}]>"
    assert list(attribute_values(text, "data-x")) == ['[{"a":1,"b":"x&y"}]']
    assert attribute_json(text, "data-x", list) == [{"a": 1, "b": "x&y"}]


def test_a_quoted_attribute_is_read_with_either_quote() -> None:
    double = '<div data-x="{&quot;a&quot;: &quot;two words&quot;}">'
    single = "<div data-x='{\"a\": 2}'>"
    assert attribute_json(double, "data-x", dict) == {"a": "two words"}
    assert attribute_json(single, "data-x", dict) == {"a": 2}


def test_an_attribute_is_matched_by_its_whole_name() -> None:
    text = '<div xdata-x="1" data-x-more="2" data-x="3">'
    assert list(attribute_values(text, "data-x")) == ["3"]


def test_a_value_that_is_not_the_json_asked_for_is_passed_over() -> None:
    text = '<p data-x="not json"></p><p data-x="[1]"></p><p data-x="[2]">'
    assert attribute_json(text, "data-x", list) == [1]
    assert attribute_json(text, "data-x", dict) is None


def test_the_real_seed_shell_names_its_endpoints_and_aliases() -> None:
    """The model's own escaped copy of the aliases must not shadow them."""
    shell = read_shell(RCCD_SHELL.read_text(encoding="utf-8"))
    assert shell is not None
    assert shell.commands["navigation"] == "/Catalog/_getNavigation"
    assert shell.commands["catalogs"] == "/Catalog/_getActiveCatalogById/115"
    assert shell.commands["visiblecontentnode"] == (
        "/Catalog/_getVisibleContentBodyNodeForClientPath"
    )
    assert [alias["CatalogAlias"] for alias in shell.aliases] == [
        "mvc-catalog",
        "nc-catalog",
        "rcc-catalog",
    ]


def test_a_page_without_a_model_or_a_navigation_endpoint_is_no_shell() -> None:
    assert read_shell("<html><body><a href='/x'>x</a></body></html>") is None
    no_navigation = "<div data-iq-model={&quot;CommandUrls&quot;:{}}></div>"
    assert read_shell(no_navigation) is None
    not_json = "<div data-iq-model={broken></div>"
    assert read_shell(not_json) is None


# --- which catalog --------------------------------------------------------


def test_the_path_names_a_catalog_by_trailing_id_or_by_alias() -> None:
    aliases = ({"ModuleId": 115, "CatalogAlias": "mvc-catalog"},)
    assert path_catalog_id(RCCD_SEED, aliases) == 115
    assert (
        path_catalog_id("https://x.edu/catalog/view/10327/iq/40258", ())
        == 10327
    )
    # 1768 is the client path of a page, not a catalog.
    assert path_catalog_id("https://x.edu/catalog/iq/1768", aliases) is None
    assert path_catalog_id("https://x.edu/catalog/view/", aliases) is None
    assert path_catalog_id("https://x.edu/catalog/0/iq/1", ()) is None
    assert path_catalog_id("https://x.edu/catalog/²/iq/1", ()) is None


def test_the_best_status_is_chosen_and_a_later_entry_wins_a_tie() -> None:
    historical = {"Id": 1, "StatusBaseId": 5}
    active = {"Id": 2, "StatusBaseId": 1}
    also_active = {"Id": 3, "StatusBaseId": 1}
    assert choose_catalog(None, [historical, active], ()) == 2
    assert choose_catalog(None, [active, historical], ()) == 2
    assert choose_catalog(None, [active, also_active], ()) == 3


def test_the_catalog_in_the_path_wins_when_it_is_listed() -> None:
    first = {"Id": 115, "StatusBaseId": 1}
    second = {"Id": 116, "StatusBaseId": 1}
    assert choose_catalog(115, [first, second], ()) == 115
    # Not listed, so the path id loses to the listed catalogs.
    assert choose_catalog(999, [first, second], ()) == 116


def test_with_nothing_listed_the_one_catalog_the_aliases_name_is_used() -> None:
    one = ({"ModuleId": 10327, "CatalogAlias": None},)
    two = one + ({"ModuleId": 10328, "CatalogAlias": None},)
    assert choose_catalog(None, [], one) == 10327
    assert choose_catalog(None, [], two) is None
    assert choose_catalog(7, [], two) == 7


def test_a_catalog_alias_in_the_seed_names_one_of_the_hosts_catalogs() -> None:
    """One district host serves three colleges; the alias says which.

    The catalogs endpoint lists nothing here, so the alias is the only
    thing that can name the catalog.
    """
    roots = [cq_node(4710, "4710", "root", text="Cover")]
    documents = curriqunet_documents(RCCD_SEED, roots)
    documents[RCCD_SEED] = RCCD_SHELL.read_bytes()
    documents[
        "https://rccd.curriqunet.com/Catalog/_getActiveCatalogById/115"
    ] = json.dumps([]).encode()
    index, _, _ = read(documents, seed=RCCD_SEED)
    assert index is not None
    assert index.catalog_id == 115
    assert index.urls == (
        "https://rccd.curriqunet.com/catalog/alias/mvc-catalog/iq/4710",
    )


# --- walking the tree -------------------------------------------------------


def test_containers_are_not_pages_and_their_ids_stay_out_of_the_path() -> None:
    roots, children = programs_tree()
    index, _, _ = read(curriqunet_documents(SEED, roots, children))
    assert index is not None
    assert index.urls == (
        BASE + "10",
        BASE + "20",
        BASE + "20/22",
        BASE + "20/23",
    )
    assert index.skipped == {SKIP_CONTAINER: 1}
    assert index.nodes_walked == 5


def test_a_page_whose_body_is_a_tab_set_gives_way_to_its_tabs() -> None:
    """The SPA rewrites such a page to its first tab, with the same content."""
    roots = [cq_node(30, "30", "root", text="Biology", cascade=True)]
    children = {
        30: [cq_node(31, "30/31", "tablist", text=None)],
        31: [
            cq_node(32, "30/32", "tab", text="Overview"),
            cq_node(33, "30/33", "tab", text="Courses"),
        ],
    }
    index, _, _ = read(curriqunet_documents(SEED, roots, children))
    assert index is not None
    assert index.urls == (BASE + "30/32", BASE + "30/33")
    assert index.skipped == {SKIP_CASCADE: 1, SKIP_CONTAINER: 1}


def test_a_hidden_root_is_pruned_but_a_hidden_tab_is_kept() -> None:
    """The sidebar hides a flagged root; a tab bar shows a flagged tab."""
    roots = [
        cq_node(40, "40", "root", text="Archive", hidden=True),
        cq_node(50, "50", "root", text="Programs"),
    ]
    children = {
        40: [cq_node(41, "40/41", text="Old")],
        50: [cq_node(51, "50/51", "tablist", text=None)],
        51: [cq_node(52, "50/52", "tab", text="Hidden tab", hidden=True)],
    }
    index, calls, _ = read(curriqunet_documents(SEED, roots, children))
    assert index is not None
    assert index.urls == (BASE + "50", BASE + "50/52")
    assert index.skipped == {SKIP_HIDDEN: 1, SKIP_CONTAINER: 1}
    assert f"{NAVIGATION}?id={CQ_CATALOG}&parentId=40" not in calls


def test_a_node_outside_the_body_panel_is_not_a_page() -> None:
    roots = [
        cq_node(60, "60", "root", text="Sidebar", panel=1),
        cq_node(70, "70", "root", text="Programs"),
    ]
    children = {
        60: [cq_node(61, "60/61", "tab", text="Inherits", panel=None)],
        70: [cq_node(71, "70/71", "tablist", text=None, panel=1)],
        71: [cq_node(72, "70/72", "tab", text="Under a side panel")],
    }
    index, _, _ = read(curriqunet_documents(SEED, roots, children))
    assert index is not None
    assert index.urls == (BASE + "70",)
    assert index.skipped == {SKIP_NON_BODY_PANEL: 3, SKIP_CONTAINER: 1}


def test_a_node_without_text_is_not_a_page() -> None:
    roots = [
        cq_node(10, "10", "root", text="Cover"),
        cq_node(11, "11", text=""),
    ]
    index, _, _ = read(curriqunet_documents(SEED, roots))
    assert index is not None
    assert index.urls == (BASE + "10",)
    assert index.skipped == {SKIP_NO_TEXT: 1}


def test_a_node_listed_under_two_parents_is_walked_once() -> None:
    roots = [cq_node(10, "10", "root"), cq_node(20, "20", "root")]
    shared = cq_node(30, "10/30")
    children = {10: [shared], 20: [dict(shared, aliaspath="20/30")]}
    index, _, _ = read(curriqunet_documents(SEED, roots, children))
    assert index is not None
    assert index.urls == (BASE + "10", BASE + "20", BASE + "10/30")
    assert index.nodes_walked == 3


# --- the URLs -----------------------------------------------------------------


def test_the_url_has_one_slash_before_iq_whatever_the_seed_ends_with() -> None:
    """/catalog/view//iq/A/B renders the cover; /catalog/view/iq/A/B the page."""
    assert url_base(SEED, CQ_CATALOG, 1) == BASE
    assert url_base("https://x.edu/catalog/view", 5, 1) == (
        "https://x.edu/catalog/view/iq/"
    )
    assert url_base("https://x.edu/catalog/iq/1768", 5, 1) == (
        "https://x.edu/catalog/iq/"
    )
    assert url_base(RCCD_SEED, 115, 1) == (
        "https://rccd.curriqunet.com/catalog/alias/mvc-catalog/iq/"
    )
    roots, children = programs_tree()
    index, _, _ = read(curriqunet_documents(SEED, roots, children))
    assert index is not None
    assert all("//iq/" not in url for url in index.urls)


def test_the_catalog_id_joins_the_path_when_several_are_listed() -> None:
    assert url_base(SEED, 115, 2) == (
        "https://catalog.example.edu/catalog/view/115/iq/"
    )
    assert url_base("https://x.edu/catalog/12/iq/3", 15, 2) == (
        "https://x.edu/catalog/15/iq/"
    )
    catalogs = [
        {"Id": 114, "StatusBaseId": 5},
        {"Id": CQ_CATALOG, "StatusBaseId": 1},
    ]
    roots = [cq_node(10, "10", "root")]
    index, _, _ = read(curriqunet_documents(SEED, roots, catalogs=catalogs))
    assert index is not None
    assert index.urls == ("https://catalog.example.edu/catalog/view/115/iq/10",)


def test_a_client_path_is_quoted_the_way_the_spa_quotes_it() -> None:
    assert page_url(BASE, "10/Courses & Programs") == (
        BASE + "10/Courses%20%26%20Programs"
    )
    assert page_url(BASE, "10/a-b_c.d~e") == BASE + "10/a-b_c.d~e"


# --- the resolver check -----------------------------------------------------


def test_a_root_resolved_to_another_node_is_dropped_with_its_tabs() -> None:
    """The server never 404s; it renders its first page for a path it lacks."""
    roots = [
        cq_node(10, "10", "root", text="Cover"),
        cq_node(20, "20", "root", text="Panel root"),
    ]
    children = {
        20: [cq_node(21, "20/21", "tablist", text=None)],
        21: [cq_node(22, "20/22", "tab", text="Tab")],
    }
    documents = curriqunet_documents(SEED, roots, children, resolves={"20": 10})
    index, calls, _ = read(documents)
    assert index is not None
    assert index.urls == (BASE + "10",)
    assert index.dropped_roots == (20,)
    assert index.skipped[SKIP_UNRESOLVED_ROOT] == 2
    resolver_calls = [call for call in calls if call.startswith(RESOLVER)]
    assert resolver_calls == [
        f"{RESOLVER}?id={CQ_CATALOG}&clientPath=10",
        f"{RESOLVER}?id={CQ_CATALOG}&clientPath=20",
    ]


def test_an_index_child_is_its_own_anchor_and_is_not_checked() -> None:
    roots, children = programs_tree()
    _, calls, _ = read(curriqunet_documents(SEED, roots, children))
    resolver_calls = [call for call in calls if call.startswith(RESOLVER)]
    assert resolver_calls == [
        f"{RESOLVER}?id={CQ_CATALOG}&clientPath=10",
        f"{RESOLVER}?id={CQ_CATALOG}&clientPath=20",
    ]


def test_a_resolver_that_does_not_answer_drops_nothing(caplog) -> None:
    """A failed check is not the server naming another page."""
    roots, children = programs_tree()
    documents = curriqunet_documents(SEED, roots, children)
    del documents[f"{RESOLVER}?id={CQ_CATALOG}&clientPath=20"]
    with caplog.at_level(logging.WARNING):
        index, _, _ = read(documents)
    assert index is not None
    assert len(index.urls) == 4
    assert index.dropped_roots == ()
    assert index.errors == 1
    assert "HTTP 404" in caplog.text


# --- limits and failures -----------------------------------------------------


def test_the_walk_stops_at_the_cap_and_says_how_much_it_left(caplog) -> None:
    roots = [cq_node(10, "10", "root")]
    children = {10: [cq_node(n, f"10/{n}") for n in range(11, 16)]}
    with caplog.at_level(logging.WARNING):
        index, _, _ = read(
            curriqunet_documents(SEED, roots, children), max_nodes=3
        )
    assert index is not None
    assert index.capped is True
    assert index.nodes_walked == 3
    assert index.urls == (BASE + "10", BASE + "10/11", BASE + "10/12")
    warning = next(
        record.getMessage()
        for record in caplog.records
        if "unexpanded" in record.getMessage()
    )
    assert "stopped at 3 nodes; 3 queued nodes were left unexpanded" in warning


def test_a_failed_request_mid_walk_keeps_what_was_found(caplog) -> None:
    roots, children = programs_tree()
    documents = curriqunet_documents(SEED, roots, children)
    del documents[f"{NAVIGATION}?id={CQ_CATALOG}&parentId=21"]
    with caplog.at_level(logging.WARNING):
        index, _, _ = read(documents)
    assert index is not None
    assert index.urls == (BASE + "10", BASE + "20")
    assert index.errors == 1
    assert "parentId=21 failed (HTTP 404)" in caplog.text


def test_a_network_error_or_a_non_json_answer_is_counted_not_raised() -> None:
    roots, children = programs_tree()
    documents = curriqunet_documents(SEED, roots, children)
    documents[f"{NAVIGATION}?id={CQ_CATALOG}&parentId=20"] = b"<html>oops"
    serve = site_documents(documents)

    def fetch(url: str) -> tuple[int, bytes]:
        if url.endswith("clientPath=10"):
            raise SiteFetchError("connection reset")
        return serve(url)

    index = read_curriqunet_index(SEED, fetch=fetch, pause=lambda: None)
    assert index is not None
    assert index.urls == (BASE + "10", BASE + "20")
    assert index.errors == 2


def test_a_tree_that_cannot_be_read_is_still_recorded() -> None:
    roots, children = programs_tree()
    documents = curriqunet_documents(SEED, roots, children)
    del documents[f"{NAVIGATION}?id={CQ_CATALOG}&navigationtypeId=1"]
    index, _, _ = read(documents)
    assert index is not None
    assert index.urls == ()
    assert index.errors == 1
    assert index.catalog_id == CQ_CATALOG


# --- costs and the record -----------------------------------------------------


def test_any_other_site_costs_one_get_and_reads_as_no_index() -> None:
    page = b"<html><body><a href='/courses'>Courses</a></body></html>"
    index, calls, pauses = read({SEED: page})
    assert index is None
    assert calls == [SEED]
    assert pauses == []


def test_a_seed_that_does_not_answer_is_no_index() -> None:
    index, calls, _ = read({})
    assert index is None
    assert calls == [SEED]

    def unreachable(url: str) -> tuple[int, bytes]:
        raise SiteFetchError("timed out")

    assert (
        read_curriqunet_index(SEED, fetch=unreachable, pause=lambda: None)
        is None
    )


def test_every_request_after_the_first_is_paced() -> None:
    roots, children = programs_tree()
    index, calls, pauses = read(curriqunet_documents(SEED, roots, children))
    assert index is not None
    assert index.requests == len(calls)
    assert len(pauses) == len(calls) - 1
    # Seed, catalogs, roots, two children requests, two resolver checks.
    assert calls[:3] == [
        SEED,
        f"https://catalog.example.edu{CQ_COMMANDS['catalogs']}",
        f"{NAVIGATION}?id={CQ_CATALOG}&navigationtypeId=1",
    ]
    assert len(calls) == 7


def test_the_index_says_what_it_found_and_what_it_cost(caplog) -> None:
    roots, children = programs_tree()
    with caplog.at_level(logging.INFO):
        index, _, _ = read(curriqunet_documents(SEED, roots, children))
    assert index is not None
    assert index.to_json() == {
        "kind": INDEX_KIND,
        "catalog_id": CQ_CATALOG,
        "url_base": BASE,
        "urls_found": 4,
        "nodes_walked": 5,
        "requests": 7,
        "skipped_by_reason": {SKIP_CONTAINER: 1},
        "dropped_roots": [],
        "capped": False,
        "errors": 0,
    }
    assert (
        f"INDEX curriqunet catalog {CQ_CATALOG} -> 4 pages from 5 nodes "
        "(7 requests)"
    ) in caplog.text
