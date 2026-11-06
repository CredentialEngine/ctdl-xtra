import json

from conftest import fixture_html, fixture_url

from review_ui.runs import find_runs, list_pages, now_ts, page_type_of, split_page


def test_find_runs_locates_crawl_json_at_any_depth(tmp_path):
    for rel in ("a/b/run1", "run2"):
        d = tmp_path / rel
        (d / "pages").mkdir(parents=True)
        (d / "crawl.json").write_text(
            json.dumps({"catalog_folder": rel, "run_id": "r"})
        )
    keys = sorted(r.key for r in find_runs(tmp_path))
    assert keys == ["a/b/run1", "run2"]


def test_find_runs_does_not_descend_into_a_run(tmp_path):
    inner = tmp_path / "run" / "pages" / "nested"
    inner.mkdir(parents=True)
    (tmp_path / "run" / "crawl.json").write_text("{}")
    (inner / "crawl.json").write_text("{}")
    assert [r.key for r in find_runs(tmp_path)] == ["run"]


def test_list_pages_reads_url_from_meta(store, run):
    pages = {p.stem: p for p in list_pages(store, run)}
    assert pages["course_admj"].url == fixture_url("course_admj")
    assert pages["course_admj"].html_key.endswith("pages/course_admj.html")


def test_split_page_returns_main_content_without_the_site_menu():
    main, assets = split_page(fixture_html("course_admj"), "#content-body")
    assert 'id="content-body"' in main and "leftsidemenu" not in main
    assert assets.base_href is None
    assert assets.stylesheets == ()
    assert ".course-title{font-weight:bold}" in assets.inline_styles[0]


def test_split_page_without_main_content():
    main, _ = split_page("<html><body><p>hi</p></body></html>", "#content-body")
    assert main is None


def test_the_content_root_is_any_css_selector():
    html = '<html><body><nav>menu</nav><td class="block_content"><p>hi</p></td></body></html>'
    main, _ = split_page(html, "td.block_content")
    assert "<p>hi</p>" in main and "menu" not in main


def test_page_type_comes_from_the_rulesets_url_patterns(ruleset):
    types = ruleset["page_types"]
    base = "https://ccsf.curricunet.com/catalog/iq"
    assert page_type_of(f"{base}/courses/3/131", types) == "course"
    assert page_type_of(f"{base}/courses/3/courses-chinese", types) == "course"
    assert page_type_of(f"{base}/programs/health-safety/1965/2461", types) == "program"
    assert page_type_of(f"{base}/courses/3", types) == "index"
    assert page_type_of(f"{base}/programs/all-by-department", types) == "index"
    assert page_type_of(f"{base}/programs/1788", types) == "index"
    assert page_type_of(f"{base}/1762", types) == "info"
    assert page_type_of(f"{base}/courses/%7Bhost%7D/x/1753", types) == "info"
    assert page_type_of("https://example.org/", types) == "info"


def test_page_type_with_no_rules_is_info():
    assert page_type_of("https://x.edu/anything", []) == "info"


def test_now_ts_matches_bucket_folder_format():
    assert len(now_ts()) == len("2026-10-16T11-14-50Z")
