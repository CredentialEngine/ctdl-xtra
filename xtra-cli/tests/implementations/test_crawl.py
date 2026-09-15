from __future__ import annotations

from implementations.crawl import (
    catalog_id_from_url,
    harvest_from_html,
    harvest_playwright,
    slot_to_dict,
)

SEED = "https://catalog.example.edu"


def test_catalog_id_from_url_uses_host_slug() -> None:
    assert catalog_id_from_url(SEED) == "example"
    assert catalog_id_from_url(SEED, "brookdale") == "brookdale"


def test_harvest_from_html_finds_course_urls(catalog_home_html: str) -> None:
    report = harvest_from_html(catalog_home_html, SEED, limit=5)
    urls = [slot.requested_url for slot in report["slots"]]
    assert "https://catalog.example.edu/english/engl101" in urls
    assert report["kept"] <= 5
    assert report["discovered"] >= report["kept"]


def test_harvest_from_html_respects_limit(catalog_home_html: str) -> None:
    report = harvest_from_html(catalog_home_html, SEED, limit=1)
    assert report["kept"] == 1


def test_harvest_from_html_course_detail_url(engl101_html: str) -> None:
    url = "https://catalog.example.edu/english/engl101"
    report = harvest_from_html(engl101_html, url, limit=5)
    assert report["kept"] == 1
    assert report["slots"][0].requested_url == url


def test_harvest_from_html_institution_override(catalog_home_html: str) -> None:
    report = harvest_from_html(
        catalog_home_html, SEED, limit=1, institution="Override College"
    )
    assert report["institution_name"] == "Override College"
    assert report["slots"][0].institution_name == "Override College"


def test_slot_to_dict_includes_stem(catalog_home_html: str) -> None:
    report = harvest_from_html(catalog_home_html, SEED, limit=1)
    payload = slot_to_dict(report["slots"][0])
    assert payload["entity_type"] == "Course"
    assert payload["stem"]
    assert payload["copy_html"] is None


def test_harvest_playwright_applies_limit_and_institution(
    catalog_home_html: str, monkeypatch
) -> None:
    inner = harvest_from_html(catalog_home_html, SEED, limit=None)

    def fake_playwright(seed_url, **kwargs):
        assert seed_url == SEED
        assert kwargs.get("between_pages") is not None or kwargs.get("between_pages") is None
        return dict(inner)

    monkeypatch.setattr(
        "implementations.crawl.harvest_with_playwright", fake_playwright
    )
    report = harvest_playwright(
        SEED,
        limit=1,
        fetch_all=False,
        institution="Override College",
        between_pages=lambda: None,
    )
    assert report["kept"] == 1
    assert report["slots"][0].institution_name == "Override College"
    assert report["institution_name"] == "Override College"
